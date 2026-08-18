"""Image media pipeline for story-maker-v3 (the "hands").

Deterministic image generation. No LLM calls. Agent 4 (Claude) authors prompt
*text* into ``<run_dir>/image_prompts/...``; this module reads those prompts,
assembles reference-image URLs, and dispatches to the ``generate_grok_t2i`` /
``generate_grok_edit`` backend (replicate / fal).

Asset layout:
  <assets_dir>/characters/<cid>.<ext>     shared character sheets (T2I, once)
  <assets_dir>/locations/<lid>.<ext>       shared location locks  (T2I, once)
  <run_dir>/storyboard_sheet_<scene>_<gen>.<ext>  per-generation clean-panel
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


def _img_ext() -> str:
    """File extension matching the configured Replicate output format."""
    return getattr(config, "REPLICATE_OUTPUT_FORMAT", "webp") or "webp"

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
    """Upload a local image if needed; return a URL the target provider can fetch.

    Provider-native URL routing:
      - For ``fal``: ensure a native fal.media URL.
      - For ``replicate``: ensure a native api.replicate.com/v1/files/ URL.
    """
    if not isinstance(entry, dict):
        return None
    url = entry.get("fal_image_url") or ""
    local_path = entry.get("output_path")
    resolved = (provider or config.get_image_provider()).strip().lower()
    replicate_gated = "api.replicate.com/v1/files/" in url
    fal_hosted = "fal.media" in url

    needs_upload = (
        not url
        or "replicate.delivery/" in url
        or (resolved == "fal" and not fal_hosted)
        or (resolved == "replicate" and not replicate_gated)
        or (
            local_path
            and os.path.isfile(local_path)
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
    """Tracks output_path + hosted URL for char sheets, location locks, object
    sheets, and storyboard sheets.

    Persisted at ``<assets_dir>/asset_registry.json`` (story-level, shared
    across all episodes) so resume and cross-episode reuse can find hosted URLs
    without re-uploading. In-memory entries are mutated by
    :func:`ensure_asset_url` (which sets ``fal_image_url``); call :meth:`save`
    after a generation op.
    """

    def __init__(self, run_dir: str, assets_dir: str):
        self.run_dir = run_dir
        self.assets_dir = assets_dir
        self.path = os.path.join(assets_dir, "asset_registry.json")
        # Auto-migrate from per-episode registry if needed
        self._maybe_migrate()
        self.data: dict[str, dict[str, dict]] = self._load()

    def _maybe_migrate(self) -> None:
        """If a per-episode registry exists at <run_dir>/asset_registry.json
        and the story-level one doesn't, copy it over (adding the objects section)."""
        old_path = os.path.join(self.run_dir, "asset_registry.json")
        if os.path.isfile(old_path) and not os.path.isfile(self.path):
            try:
                with open(old_path, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    if "objects" not in loaded:
                        loaded["objects"] = {}
                    os.makedirs(self.assets_dir, exist_ok=True)
                    with open(self.path, "w", encoding="utf-8") as f:
                        json.dump(loaded, f, indent=2, ensure_ascii=False)
            except (json.JSONDecodeError, OSError):
                pass  # leave old file in place; load will handle it

    def _load(self) -> dict[str, dict[str, dict]]:
        if os.path.isfile(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    return {
                        "characters": loaded.get("characters", {}) or {},
                        "locations": loaded.get("locations", {}) or {},
                        "objects": loaded.get("objects", {}) or {},
                        "sheets": loaded.get("sheets", {}) or {},
                    }
            except (json.JSONDecodeError, OSError):
                pass
        # Fallback: try the old per-episode path
        old_path = os.path.join(self.run_dir, "asset_registry.json")
        if os.path.isfile(old_path):
            try:
                with open(old_path, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    return {
                        "characters": loaded.get("characters", {}) or {},
                        "locations": loaded.get("locations", {}) or {},
                        "objects": loaded.get("objects", {}) or {},
                        "sheets": loaded.get("sheets", {}) or {},
                    }
            except (json.JSONDecodeError, OSError):
                pass
        return {"characters": {}, "locations": {}, "objects": {}, "sheets": {}}

    def save(self) -> None:
        os.makedirs(self.assets_dir, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # -- accessors ---------------------------------------------------------
    def character(self, cid: str) -> dict:
        return self.data["characters"].setdefault(cid, {"output_path": "", "fal_image_url": ""})

    def location(self, lid: str) -> dict:
        return self.data["locations"].setdefault(lid, {"output_path": "", "fal_image_url": ""})

    def object(self, oid: str) -> dict:
        return self.data["objects"].setdefault(oid, {"output_path": "", "fal_image_url": ""})

    def sheet(self, sheet_id: str) -> dict:
        """``sheet_id`` is ``<scene_id>_<gen_id>`` (e.g. ``s1_g2``)."""
        return self.data["sheets"].setdefault(sheet_id, {"output_path": "", "fal_image_url": ""})

    def character_path(self, cid: str) -> str:
        return os.path.join(self.assets_dir, "characters", f"{cid}.{_img_ext()}")

    def location_path(self, lid: str) -> str:
        return os.path.join(self.assets_dir, "locations", f"{lid}.{_img_ext()}")

    def object_path(self, oid: str) -> str:
        return os.path.join(self.assets_dir, "objects", f"{oid}.{_img_ext()}")

    def sheet_path(self, scene_id: str, gen_id: str) -> str:
        return os.path.join(self.run_dir, f"storyboard_sheet_{scene_id}_{gen_id}.{_img_ext()}")

    def resolve_ref_name(self, name: str) -> str | None:
        """Resolve a ref_images name to a hosted URL.

        Resolution order: objects → locations → characters → sheets.
        Returns the fal_image_url (or ensures it) or None if not found.
        """
        name = name.strip()
        if not name:
            return None
        for section in ("objects", "locations", "characters", "sheets"):
            entry = self.data[section].get(name)
            if entry and entry.get("output_path"):
                url = ensure_asset_url(entry)
                if url:
                    return url
        return None


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
    extra_ref_urls: list[str] | None = None,
    attach_location: bool = True,
) -> list[str]:
    """Ordered refs for a storyboard sheet edit.

    Reference ordering (identity-first):
      prev sheet -> conditional location -> chars -> extras

    For g1 (no prev sheet): location -> chars -> extras.
    ``attach_location=False`` skips the location panorama (used for later
    generations whose spatial plan sets ``location_reference: omit``).
    """
    resolved = provider or config.get_storyboard_image_provider()
    limit = ref_limit if ref_limit is not None else config.get_image_ref_limit(resolved)
    urls: list[str] = []

    if attach_prev_sheet and prev_sheet_id:
        prev_entry = registry.sheet(prev_sheet_id)
        if prev_entry.get("output_path") and os.path.isfile(prev_entry.get("output_path", "")):
            prev_url = ensure_asset_url(prev_entry, provider=resolved)
            if prev_url and prev_url not in urls:
                urls.append(prev_url)

    if attach_location and location_ref_id:
        loc_url = ensure_asset_url(registry.location(location_ref_id), provider=resolved)
        if loc_url and loc_url not in urls:
            urls.append(loc_url)

    for cid in sorted(character_ref_ids or [], key=_char_sort_key):
        url = ensure_asset_url(registry.character(cid), provider=resolved)
        if url and url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break

    for url in (extra_ref_urls or []):
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
    ref_urls: list[str] | None = None,
) -> dict:
    """Generate one character sheet (T2I, optional refs). Returns the registry entry."""
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
            ref_urls=ref_urls,
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
    ref_urls: list[str] | None = None,
) -> dict:
    """Generate one location lock plate (T2I empty stage, optional refs). Returns registry entry."""
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
            ref_urls=ref_urls,
        ),
        f"location lock {lid}",
    )
    entry = registry.location(lid)
    _registry_entry_from_result(entry, result)
    registry.save()
    return entry


def generate_object_sheet(
    registry: AssetRegistry,
    oid: str,
    *,
    prompt_text: str | None = None,
    object_fields: dict[str, Any] | None = None,
    render_style: str = RENDER_STYLE,
    provider: str | None = None,
    ref_urls: list[str] | None = None,
) -> dict:
    """Generate one object/prop sheet (T2I, optional refs). Returns the registry entry."""
    from . import object_sheet_builder
    backend = provider or config.get_image_provider()
    if not prompt_text:
        if not object_fields:
            raise ValueError(f"object sheet {oid}: need prompt_text or object_fields")
        prompt_text = object_sheet_builder.build_object_sheet_prompt(
            {"id": oid, **object_fields}, render_style=render_style,
        )
    out_path = registry.object_path(oid)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    result = _check(
        generate_grok_t2i(
            prompt_text, out_path,
            size=config.STORYBOARD_SHEET_SIZE,
            quality=config.REPLICATE_SHEET_QUALITY,
            provider=backend,
            ref_urls=ref_urls,
        ),
        f"object sheet {oid}",
    )
    entry = registry.object(oid)
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
    extra_ref_urls: list[str] | None = None,
    attach_location: bool = True,
) -> dict:
    """Generate one generation's clean-panel storyboard sheet (edit + refs).

    ``prev_sheet_id`` is the preceding sheet key (previous generation of the
    same scene, or the last generation of the previous scene) so continuity
    carries across the 15s Minimax boundary. ``extra_ref_urls`` are agent-named
    refs from the ``ref_images:`` prompt line. ``attach_location`` controls
    whether the location panorama is attached (False for later generations
    whose spatial plan sets ``location_reference: omit``).
    Returns the registry entry.
    """
    backend = provider or config.get_storyboard_image_provider()
    ref_urls = build_sheet_ref_urls(
        registry,
        location_ref_id=location_ref_id,
        character_ref_ids=character_ref_ids,
        prev_sheet_id=prev_sheet_id,
        provider=backend,
        attach_prev_sheet=attach_prev_sheet,
        extra_ref_urls=extra_ref_urls,
        attach_location=attach_location,
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


def object_prompt_path(run_dir: str, oid: str) -> str:
    return os.path.join(image_prompts_dir(run_dir), "objects", f"{oid}.txt")


def sheet_prompt_path(run_dir: str, scene_id: str, gen_id: str) -> str:
    return os.path.join(image_prompts_dir(run_dir), scene_id, f"storyboard_sheet_{gen_id}.txt")


def parse_ref_images(prompt_text: str) -> tuple[list[str], str]:
    """Extract a ``ref_images:`` line from a prompt file.

    Returns ``(ref_names, prompt_without_ref_line)``. The ref_images line is
    a comma-separated list of asset names (e.g. ``ref_images: loc_kitchen, char_01``).
    """
    lines = prompt_text.splitlines()
    ref_names: list[str] = []
    out_lines: list[str] = []
    for line in lines:
        stripped = line.strip().lower()
        if stripped.startswith("ref_images:"):
            raw = line.split(":", 1)[1] if ":" in line else ""
            ref_names = [n.strip() for n in raw.split(",") if n.strip()]
        else:
            out_lines.append(line)
    return ref_names, "\n".join(out_lines).strip()


def resolve_ref_names(registry: AssetRegistry, names: list[str], *, limit: int = 10) -> list[str]:
    """Resolve a list of ref_images names to hosted URLs via the registry.

    Resolution order per name: objects → locations → characters → sheets.
    Deduplicates and caps at ``limit``.
    """
    urls: list[str] = []
    seen: set[str] = set()
    for name in names:
        url = registry.resolve_ref_name(name)
        if url and url not in seen:
            urls.append(url)
            seen.add(url)
        if len(urls) >= limit:
            break
    return urls


def video_prompt_path(run_dir: str, scene_id: str, gen_id: str) -> str:
    """Minimax H3 timeline prompt for one generation (Agent 5 authors this)."""
    return os.path.join(run_dir, "video_prompts", f"{scene_id}_{gen_id}.txt")


def read_prompt(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    return open(path, encoding="utf-8").read().strip()