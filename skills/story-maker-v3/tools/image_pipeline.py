"""Image media pipeline for story-maker-v3 (the "hands").

Deterministic image generation. No LLM calls. Agent 4 (Claude) authors prompt
*text* into ``<run_dir>/image_prompts/...``; this module reads those prompts,
assembles reference-image URLs, and dispatches to the ``generate_grok_t2i`` /
``generate_grok_edit`` backend (replicate / fal).

Asset layout:
  <assets_dir>/characters/<cid>.png     shared character sheets (T2I, once)
  <assets_dir>/locations/<lid>.png       shared location locks  (T2I, once)
  <run_dir>/storyboard_sheet_<scene>_<gen>.png  per-generation clean-panel
      storyboard sheet (edit + refs) — attached verbatim as the Minimax H3
      reference image. No crops, no upscales.

Reference ordering for a storyboard sheet edit (proven reel_v2 order):
  location lock -> previous sheet -> character sheets (capped by provider ref limit).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import config
from . import char_sheet_builder
from . import location_sheet_builder
from .grok_tools import generate_grok_edit, generate_grok_t2i

RENDER_STYLE = os.getenv(
    "RENDER_STYLE",
    "Cinematic 3D animation, warm natural lighting, shallow depth of field.",
)


# ---------------------------------------------------------------------------
# URL helpers (ported verbatim from skills/story-maker)
# ---------------------------------------------------------------------------

def _url_reachable(url: str) -> bool:
    if not url or not str(url).startswith("http"):
        return False
    try:
        import httpx

        resp = httpx.head(url, timeout=15.0, follow_redirects=True)
        if resp.status_code < 400:
            return True
        resp = httpx.get(url, timeout=15.0, follow_redirects=True, headers={"Range": "bytes=0-0"})
        return resp.status_code < 400
    except Exception:
        return False


def ensure_asset_url(entry: dict, *, provider: str | None = None) -> str | None:
    """Upload a local PNG if needed; return a URL the target provider can fetch.

    Replicate Files API URLs are auth-gated — fal edit cannot download them — so
    when the target provider is ``fal`` we always re-upload locals via
    ``fal_client.upload_file``.
    """
    if not isinstance(entry, dict):
        return None
    url = entry.get("fal_image_url") or ""
    local_path = entry.get("output_path")
    resolved = (provider or config.get_image_provider()).strip().lower()
    replicate_gated = "api.replicate.com/v1/files/" in url
    needs_upload = (
        not url
        or "replicate.delivery/" in url
        or (resolved == "fal" and replicate_gated)
        or (
            local_path
            and os.path.isfile(local_path)
            and (not replicate_gated)
            and ("api.replicate.com/v1/files/" not in url)
            and not _url_reachable(url)
        )
    )
    if needs_upload and local_path and os.path.isfile(local_path):
        if resolved == "fal":
            import fal_client

            if not os.environ.get("FAL_KEY"):
                os.environ["FAL_KEY"] = config.FAL_KEY or ""
            url = fal_client.upload_file(local_path)
        else:
            from .grok_replicate import upload_local_image

            url = upload_local_image(local_path)
        entry["fal_image_url"] = url
    return url or None


# ---------------------------------------------------------------------------
# Asset registry (filesystem-backed)
# ---------------------------------------------------------------------------

class AssetRegistry:
    """Tracks output_path + hosted URL for char sheets, location locks, sheets.

    Persisted at ``<run_dir>/asset_registry.json`` so resume can re-use hosted
    URLs without re-uploading. In-memory entries are mutated by
    :func:`ensure_asset_url` (which sets ``fal_image_url``); call :meth:`save`
    after a generation op.
    """

    def __init__(self, run_dir: str, assets_dir: str):
        self.run_dir = run_dir
        self.assets_dir = assets_dir
        self.path = os.path.join(run_dir, "asset_registry.json")
        self.data: dict[str, dict[str, dict]] = self._load()

    def _load(self) -> dict[str, dict[str, dict]]:
        if os.path.isfile(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    return {
                        "characters": loaded.get("characters", {}) or {},
                        "locations": loaded.get("locations", {}) or {},
                        "sheets": loaded.get("sheets", {}) or {},
                    }
            except (json.JSONDecodeError, OSError):
                pass
        return {"characters": {}, "locations": {}, "sheets": {}}

    def save(self) -> None:
        os.makedirs(self.run_dir, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # -- accessors ---------------------------------------------------------
    def character(self, cid: str) -> dict:
        return self.data["characters"].setdefault(cid, {"output_path": "", "fal_image_url": ""})

    def location(self, lid: str) -> dict:
        return self.data["locations"].setdefault(lid, {"output_path": "", "fal_image_url": ""})

    def sheet(self, sheet_id: str) -> dict:
        """``sheet_id`` is ``<scene_id>_<gen_id>`` (e.g. ``s1_g2``)."""
        return self.data["sheets"].setdefault(sheet_id, {"output_path": "", "fal_image_url": ""})

    def character_path(self, cid: str) -> str:
        return os.path.join(self.assets_dir, "characters", f"{cid}.png")

    def location_path(self, lid: str) -> str:
        return os.path.join(self.assets_dir, "locations", f"{lid}.png")

    def sheet_path(self, scene_id: str, gen_id: str) -> str:
        return os.path.join(self.run_dir, f"storyboard_sheet_{scene_id}_{gen_id}.png")


# ---------------------------------------------------------------------------
# Reference-URL assembly
# ---------------------------------------------------------------------------

def _char_sort_key(cid: str) -> tuple[int, int | str]:
    m = re.match(r"char_(\d+)$", (cid or "").strip().lower())
    if m:
        return (0, int(m.group(1)))
    return (1, cid or "")


def build_sheet_ref_urls(
    registry: AssetRegistry,
    *,
    location_ref_id: str | None,
    character_ref_ids: list[str],
    prev_sheet_id: str | None = None,
    provider: str | None = None,
    ref_limit: int | None = None,
    attach_prev_sheet: bool = True,
) -> list[str]:
    """Ordered refs for a storyboard sheet edit: location -> prev sheet -> chars."""
    resolved = provider or config.get_storyboard_image_provider()
    limit = ref_limit if ref_limit is not None else config.get_image_ref_limit(resolved)
    urls: list[str] = []

    if location_ref_id:
        loc_url = ensure_asset_url(registry.location(location_ref_id), provider=resolved)
        if loc_url:
            urls.append(loc_url)

    if attach_prev_sheet and prev_sheet_id:
        prev_entry = registry.sheet(prev_sheet_id)
        if prev_entry.get("output_path") and os.path.isfile(prev_entry.get("output_path", "")):
            prev_url = ensure_asset_url(prev_entry, provider=resolved)
            if prev_url and prev_url not in urls:
                urls.append(prev_url)

    for cid in sorted(character_ref_ids or [], key=_char_sort_key):
        url = ensure_asset_url(registry.character(cid), provider=resolved)
        if url and url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls[:limit]


# ---------------------------------------------------------------------------
# Generation ops
# ---------------------------------------------------------------------------

def _check(result: dict, what: str) -> dict:
    if result.get("status") != "success":
        raise RuntimeError(f"{what} failed: {result.get('message', result)}")
    return result


def _registry_entry_from_result(entry: dict, result: dict) -> None:
    """Copy the backend's output path + hosted URL into a registry entry."""
    entry["output_path"] = result.get("generated_image_path") or entry.get("output_path") or ""
    if result.get("fal_image_url"):
        entry["fal_image_url"] = result["fal_image_url"]


def generate_character_sheet(
    registry: AssetRegistry,
    cid: str,
    *,
    prompt_text: str | None = None,
    character_fields: dict[str, Any] | None = None,
    render_style: str = RENDER_STYLE,
    provider: str | None = None,
) -> dict:
    """Generate one character sheet (T2I, no refs). Returns the registry entry."""
    backend = provider or config.get_character_sheet_image_provider()
    if not prompt_text:
        if not character_fields:
            raise ValueError(f"char sheet {cid}: need prompt_text or character_fields")
        prompt_text = char_sheet_builder.build_character_sheet_prompt(
            {"id": cid, **character_fields}, render_style=render_style,
        )
    out_path = registry.character_path(cid)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    result = _check(
        generate_grok_t2i(
            prompt_text, out_path,
            size=config.CHARACTER_SHEET_SIZE,
            quality=config.REPLICATE_SHEET_QUALITY,
            provider=backend,
        ),
        f"char sheet {cid}",
    )
    entry = registry.character(cid)
    _registry_entry_from_result(entry, result)
    registry.save()
    return entry


def generate_location_lock(
    registry: AssetRegistry,
    lid: str,
    *,
    prompt_text: str | None = None,
    location_fields: dict[str, Any] | None = None,
    render_style: str = RENDER_STYLE,
    provider: str | None = None,
) -> dict:
    """Generate one location lock plate (T2I empty stage). Returns registry entry."""
    backend = provider or config.get_image_provider()
    if not prompt_text:
        if not location_fields:
            raise ValueError(f"location lock {lid}: need prompt_text or location_fields")
        prompt_text = location_sheet_builder.build_location_sheet_prompt(
            {"id": lid, **location_fields}, render_style=render_style,
        )
    out_path = registry.location_path(lid)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    result = _check(
        generate_grok_t2i(
            prompt_text, out_path,
            size=config.BACKGROUND_IMAGE_SIZE,
            quality=config.REPLICATE_SHEET_QUALITY,
            provider=backend,
        ),
        f"location lock {lid}",
    )
    entry = registry.location(lid)
    _registry_entry_from_result(entry, result)
    registry.save()
    return entry


def generate_storyboard_sheet(
    registry: AssetRegistry,
    scene_id: str,
    gen_id: str,
    *,
    prompt_text: str,
    character_ref_ids: list[str],
    location_ref_id: str | None = None,
    prev_sheet_id: str | None = None,
    render_style: str = RENDER_STYLE,
    provider: str | None = None,
    attach_prev_sheet: bool = True,
) -> dict:
    """Generate one generation's clean-panel storyboard sheet (edit + refs).

    ``prev_sheet_id`` is the preceding sheet key (previous generation of the
    same scene, or the last generation of the previous scene) so continuity
    carries across the 15s Minimax boundary. Returns the registry entry.
    """
    backend = provider or config.get_storyboard_image_provider()
    ref_urls = build_sheet_ref_urls(
        registry,
        location_ref_id=location_ref_id,
        character_ref_ids=character_ref_ids,
        prev_sheet_id=prev_sheet_id,
        provider=backend,
        attach_prev_sheet=attach_prev_sheet,
    )
    out_path = registry.sheet_path(scene_id, gen_id)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    result = _check(
        generate_grok_edit(
            prompt_text, ref_urls, out_path,
            size=config.STORYBOARD_SHEET_SIZE,
            quality=config.REPLICATE_SHEET_QUALITY,
            provider=backend,
        ),
        f"storyboard sheet {scene_id}_{gen_id}",
    )
    entry = registry.sheet(f"{scene_id}_{gen_id}")
    _registry_entry_from_result(entry, result)
    registry.save()
    return entry


# ---------------------------------------------------------------------------
# Prompt-file loading (Agent 4 writes these)
# ---------------------------------------------------------------------------

def image_prompts_dir(run_dir: str) -> str:
    return os.path.join(run_dir, "image_prompts")


def character_prompt_path(run_dir: str, cid: str) -> str:
    return os.path.join(image_prompts_dir(run_dir), "characters", f"{cid}.txt")


def location_prompt_path(run_dir: str, lid: str) -> str:
    return os.path.join(image_prompts_dir(run_dir), "locations", f"{lid}.txt")


def sheet_prompt_path(run_dir: str, scene_id: str, gen_id: str) -> str:
    return os.path.join(image_prompts_dir(run_dir), scene_id, f"storyboard_sheet_{gen_id}.txt")


def video_prompt_path(run_dir: str, scene_id: str, gen_id: str) -> str:
    """Minimax H3 timeline prompt for one generation (Agent 5 authors this)."""
    return os.path.join(run_dir, "video_prompts", f"{scene_id}_{gen_id}.txt")


def read_prompt(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    return open(path, encoding="utf-8").read().strip()