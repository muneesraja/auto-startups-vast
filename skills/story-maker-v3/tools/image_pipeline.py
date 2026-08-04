"""Image media pipeline for story-maker-v3 (the "hands").

Deterministic image generation + cropping + upscaling. No LLM calls. Agent 4
(Claude) authors prompt *text* into ``<run_dir>/image_prompts/...``; this module
reads those prompts, assembles reference-image URLs, and dispatches to the
``generate_grok_t2i`` / ``generate_grok_edit`` backend (replicate / fal).

Asset layout:
  <assets_dir>/characters/<cid>.png     shared character sheets (T2I, once)
  <assets_dir>/locations/<lid>.png       shared location locks  (T2I, once)
  <run_dir>/storyboard_sheet_<scene>.png per-scene 2x4 album sheet (edit + refs)
  <run_dir>/panels/<scene>/panel_<r><c>.png   white-gutter crop of each panel
  <run_dir>/panels/<scene>/upscale_<r><c>.png per-panel upscale (edit: crop + char refs)

Reference ordering for a storyboard sheet edit (proven reel_v2 order):
  location lock -> previous scene's sheet -> character sheets (capped by provider ref limit).
Reference ordering for a panel upscale edit:
  panel crop (Image 1) -> character sheets of characters_present.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import config
from . import char_sheet_builder
from . import location_sheet_builder
from . import panel_crop
from .grok_tools import generate_grok_edit, generate_grok_t2i

RENDER_STYLE = os.getenv(
    "RENDER_STYLE",
    "Cinematic 3D animation, warm natural lighting, shallow depth of field.",
)

PANEL_ID_RE = re.compile(r"^panel_(\d)(\d)$")


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

    def sheet(self, scene_id: str) -> dict:
        return self.data["sheets"].setdefault(scene_id, {"output_path": "", "fal_image_url": ""})

    def character_path(self, cid: str) -> str:
        return os.path.join(self.assets_dir, "characters", f"{cid}.png")

    def location_path(self, lid: str) -> str:
        return os.path.join(self.assets_dir, "locations", f"{lid}.png")

    def sheet_path(self, scene_id: str) -> str:
        return os.path.join(self.run_dir, f"storyboard_sheet_{scene_id}.png")

    def panel_path(self, scene_id: str, panel_id: str) -> str:
        return os.path.join(self.run_dir, "panels", scene_id, f"{panel_id}.png")

    def upscale_path(self, scene_id: str, panel_id: str) -> str:
        return os.path.join(self.run_dir, "panels", scene_id, f"upscale_{panel_id}.png")

    def prepad_path(self, scene_id: str, panel_id: str) -> str:
        return os.path.join(self.run_dir, "panels", scene_id, f"prepad_{panel_id}.png")


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
    prev_scene_id: str | None = None,
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

    if attach_prev_sheet and prev_scene_id:
        prev_entry = registry.sheet(prev_scene_id)
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


def build_panel_ref_urls(
    registry: AssetRegistry,
    *,
    scene_id: str,
    panel_id: str,
    character_ref_ids: list[str],
    location_ref_id: str | None = None,
    provider: str | None = None,
    ref_limit: int | None = None,
) -> list[str]:
    """Ordered refs for a panel upscale edit: crop -> chars -> location."""
    resolved = provider or config.get_panel_image_provider()
    limit = ref_limit if ref_limit is not None else config.get_image_ref_limit(resolved)
    urls: list[str] = []

    crop_entry = {"output_path": registry.panel_path(scene_id, panel_id), "fal_image_url": ""}
    crop_url = ensure_asset_url(crop_entry, provider=resolved)
    if crop_url:
        urls.append(crop_url)

    # Reserve one slot for the location lock when enabled.
    reserve_location = 1 if (config.UPSCALE_INCLUDE_LOCATION_REF and location_ref_id) else 0
    char_budget = max(0, limit - len(urls) - reserve_location)
    for cid in sorted(character_ref_ids or [], key=_char_sort_key):
        if char_budget <= 0:
            break
        url = ensure_asset_url(registry.character(cid), provider=resolved)
        if url and url not in urls:
            urls.append(url)
            char_budget -= 1

    if reserve_location and len(urls) < limit:
        loc_url = ensure_asset_url(registry.location(location_ref_id), provider=resolved)
        if loc_url and loc_url not in urls:
            urls.append(loc_url)
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
    *,
    prompt_text: str,
    character_ref_ids: list[str],
    location_ref_id: str | None = None,
    prev_scene_id: str | None = None,
    render_style: str = RENDER_STYLE,
    provider: str | None = None,
    attach_prev_sheet: bool = True,
) -> dict:
    """Generate one 2x4 storyboard album sheet (edit + refs). Returns entry."""
    backend = provider or config.get_storyboard_image_provider()
    ref_urls = build_sheet_ref_urls(
        registry,
        location_ref_id=location_ref_id,
        character_ref_ids=character_ref_ids,
        prev_scene_id=prev_scene_id,
        provider=backend,
        attach_prev_sheet=attach_prev_sheet,
    )
    out_path = registry.sheet_path(scene_id)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    result = _check(
        generate_grok_edit(
            prompt_text, ref_urls, out_path,
            size=config.STORYBOARD_SHEET_SIZE,
            quality=config.REPLICATE_SHEET_QUALITY,
            provider=backend,
        ),
        f"storyboard sheet {scene_id}",
    )
    entry = registry.sheet(scene_id)
    _registry_entry_from_result(entry, result)
    registry.save()
    return entry


def crop_panels(
    registry: AssetRegistry,
    scene_id: str,
    *,
    expected: int = panel_crop.SCENE_PANELS,
    cols: int = panel_crop.DEFAULT_COLS,
    mode: str | None = None,
) -> list[dict[str, Any]]:
    """Crop a scene's storyboard sheet into ``expected`` panel PNGs."""
    sheet_path = registry.sheet_path(scene_id)
    if not os.path.isfile(sheet_path):
        raise FileNotFoundError(f"storyboard sheet missing for {scene_id}: {sheet_path}")
    out_dir = os.path.join(registry.run_dir, "panels", scene_id)
    return panel_crop.crop_storyboard_sheet(
        sheet_path, out_dir, expected=expected, cols=cols, mode=mode,
    )


def upscale_panel(
    registry: AssetRegistry,
    scene_id: str,
    panel_id: str,
    *,
    prompt_text: str,
    character_ref_ids: list[str] | None = None,
    location_ref_id: str | None = None,
    provider: str | None = None,
) -> dict:
    """Pure upscale one 16:9 panel crop to PANEL_IMAGE_SIZE.

    The crop is already 16:9 (1280x720 from the 3×3 sheet), so no pre-pad or
    side-bar outpaint is needed. The crop is the only reference image; the
    model is locked to preserve composition, cast, and camera.
    """
    backend = provider or config.get_panel_image_provider()
    crop_path = registry.panel_path(scene_id, panel_id)
    if not os.path.isfile(crop_path):
        raise FileNotFoundError(f"panel crop missing: {crop_path}")

    # 1. Build ref URLs — the 16:9 crop itself.
    crop_entry = {"output_path": crop_path, "fal_image_url": ""}
    crop_url = ensure_asset_url(crop_entry, provider=backend)
    ref_urls = [crop_url] if crop_url else []

    # 2. Mechanical preservation lock for pure upscale.
    upscale_lock = (
        "The attached image is a 16:9 cinematic animation still. Uplift it to the "
        "requested resolution while preserving the exact composition, cast, poses, "
        "camera angle, lighting, and background. Enhance detail and texture only. "
        "Do not add, remove, or alter any character, prop, or background element. "
        "Do not re-frame, zoom, or change the camera. No text, no labels, no captions, "
        "no watermarks. "
    )
    full_prompt = upscale_lock + (prompt_text or "")

    out_path = registry.upscale_path(scene_id, panel_id)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    result = _check(
        generate_grok_edit(
            full_prompt, ref_urls, out_path,
            size=config.PANEL_IMAGE_SIZE,
            quality=config.REPLICATE_PANEL_QUALITY,
            provider=backend,
        ),
        f"upscale {scene_id}/{panel_id}",
    )
    return {"panel_id": panel_id, "output_path": out_path, "result": result}


# ---------------------------------------------------------------------------
# Prompt-file loading (Agent 4 writes these)
# ---------------------------------------------------------------------------

def image_prompts_dir(run_dir: str) -> str:
    return os.path.join(run_dir, "image_prompts")


def character_prompt_path(run_dir: str, cid: str) -> str:
    return os.path.join(image_prompts_dir(run_dir), "characters", f"{cid}.txt")


def location_prompt_path(run_dir: str, lid: str) -> str:
    return os.path.join(image_prompts_dir(run_dir), "locations", f"{lid}.txt")


def sheet_prompt_path(run_dir: str, scene_id: str) -> str:
    return os.path.join(image_prompts_dir(run_dir), scene_id, "storyboard_sheet.txt")


def panel_prompt_path(run_dir: str, scene_id: str, panel_id: str) -> str:
    return os.path.join(image_prompts_dir(run_dir), scene_id, f"{panel_id}.txt")


def read_prompt(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    return open(path, encoding="utf-8").read().strip()