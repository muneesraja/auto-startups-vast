"""Storyboard-sheet image pipeline for reel_v2."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil

try:
    from google.adk.agents.context import Context
    from google.adk.workflow import FunctionNode
except ImportError:  # pragma: no cover - test fallback without ADK installed
    class Context:  # type: ignore[override]
        pass

    class FunctionNode:  # type: ignore[override]
        def __init__(self, func, name: str):
            self.func = func
            self.name = name

import config
from profiles import get_profile
from tools.grok_tools import generate_grok_edit
from tools.vision_llm import vision_json_from_image
from ._json_util import clean_json_str
from ._shot_image_gen import retry_async, soften_moderation_prompt
from .generation_nodes import (
    _load_specs,
    _only_scenes,
    _save_specs,
    _scene_in_scope,
    _shot_in_scope,
    _url_reachable,
)
from .storyboard_sheet_builder import (
    album_grid_shape,
    build_panel_lines,
    build_storyboard_sheet_prompt as build_template_storyboard_prompt,
    continuity_mode_for,
)

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MAX_SHEET_CONCURRENCY = int(os.getenv("STORYBOARD_SHEET_CONCURRENCY", "2"))
_MAX_REGEN_CONCURRENCY = int(os.getenv("PANEL_REGEN_CONCURRENCY", "2"))
_PANEL_REGEN_ALLOW_SOFT_FAIL = os.getenv("PANEL_REGEN_ALLOW_SOFT_FAIL", "1").lower() in (
    "1",
    "true",
    "yes",
)


def _soften_storyboard_contact_language(prompt: str) -> str:
    """Make child/animal greeting boards resilient to GPT Image moderation.

    The board retains the story beat, but avoids close-contact anatomy language
    that GPT Image 2 can incorrectly flag in a multi-panel image-edit prompt.
    """
    text = prompt or ""
    replacements = (
        (r"\bintimate\b", "warm"),
        (r"\btender\b", "gentle"),
        (r"\bdelicate\b", "quiet"),
        (
            r"\b(?:the )?trunk tip nearing Naila['’]s cheek\b",
            "a friendly elephant standing near Naila",
        ),
        (
            r"\b(?:The )?character elephant softly touches Naila['’]s cheek\b",
            "The character elephant greets Naila calmly",
        ),
        (
            r"\bNaila['’]s hand rests lightly on the trunk\b",
            "Naila and the character elephant share a calm moment",
        ),
        (
            r"\bShe strokes the trunk slowly and carefully\b",
            "She offers a calm friendly gesture toward the elephant",
        ),
        (r"\bsmall hand against (?:the )?trunk\b", "clear size contrast"),
        (r"\b(?:first )?contact\b", "friendly greeting"),
        (r"\bFather supports her securely\b", "Father stands nearby"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return text


def _load_story(ctx: Context) -> dict:
    raw = ctx.state.get("story_plan_content")
    if not raw:
        path = os.path.join(ctx.state["output_dir"], "story_plan.json")
        with open(path, encoding="utf-8") as f:
            raw = json.dumps(json.load(f))
    return clean_json_str(raw) if isinstance(raw, str) else raw


def _load_prompt_file(name: str) -> str:
    style = (os.getenv("STORY_STYLE") or "").strip().lower()
    candidates: list[str] = []
    if style and style != "cinematic":
        candidates.append(os.path.join(_SKILL_DIR, "prompts", style, f"{name}.md"))
    candidates.append(os.path.join(_SKILL_DIR, "prompts", f"{name}.md"))
    for path in candidates:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
    raise FileNotFoundError(f"Prompt file not found for {name!r}; tried: {candidates}")


def _chunk_shots(shots: list[dict], size: int) -> list[list[dict]]:
    if size <= 0:
        return [shots]
    return [shots[i : i + size] for i in range(0, len(shots), size)]


def _panel_line(shot: dict, index: int) -> str:
    """Backward-compatible single-panel formatter."""
    return build_panel_lines([shot], start_index=index)


def build_storyboard_sheet_prompt(
    scene: dict,
    shots: list[dict],
    *,
    render_style: str,
    template: str | None = None,
    sheet_number: int = 1,
    panels_per_sheet: int = 8,
    story_characters: list[dict] | None = None,
    global_shot_offset: int = 0,
    style_id: str | None = "reel_v2",
    locations: list[dict] | None = None,
    continuity_from_sheet_id: str | None = None,
    has_location_ref: bool = False,
    has_previous_sheet_ref: bool = False,
    continuity_mode: str | None = None,
) -> str:
    return build_template_storyboard_prompt(
        scene,
        shots,
        sheet_number=sheet_number,
        panels_per_sheet=panels_per_sheet,
        render_style=render_style,
        story_characters=story_characters,
        global_shot_offset=global_shot_offset,
        template=template,
        style_id=style_id,
        locations=locations,
        continuity_from_sheet_id=continuity_from_sheet_id,
        has_location_ref=has_location_ref,
        has_previous_sheet_ref=has_previous_sheet_ref,
        continuity_mode=continuity_mode,
    )


def _ensure_asset_url(entry: dict, *, provider: str | None = None) -> str | None:
    """Upload local PNG if needed; return a URL the target image provider can fetch.

    Replicate Files API URLs are auth-gated — fal edit cannot download them — so when
    the target provider is ``fal`` we always re-upload locals via ``fal_client.upload_file``.
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
            from tools.grok_replicate import upload_local_image

            url = upload_local_image(local_path)
        entry["fal_image_url"] = url
    return url or None


def _character_ref_urls(
    specs: dict, character_ids: list[str], *, provider: str | None = None
) -> list[str]:
    urls: list[str] = []
    for cid in character_ids:
        entry = specs.get("character_sheets", {}).get(cid, {})
        url = _ensure_asset_url(entry, provider=provider)
        if url:
            urls.append(url)
    return urls


def _location_ref_url(
    specs: dict, location_id: str | None, *, provider: str | None = None
) -> str | None:
    if not location_id:
        return None
    entry = (specs.get("location_sheets") or {}).get(location_id, {})
    return _ensure_asset_url(entry, provider=provider)


def _previous_sheet_ref_url(
    specs: dict, sheet_id: str | None, *, provider: str | None = None
) -> str | None:
    if not sheet_id:
        return None
    entry = (specs.get("storyboard_sheets") or {}).get(sheet_id, {})
    return _ensure_asset_url(entry, provider=provider)


def _resolve_continuity_sheet_id(specs: dict, entry: dict) -> str | None:
    """Walk back past failed/missing sheets to the last usable continuity ref."""
    sheets = specs.get("storyboard_sheets") or {}
    cur = entry.get("continuity_from_sheet_id")
    seen: set[str] = set()
    while cur and cur not in seen:
        seen.add(cur)
        prev = sheets.get(cur) if isinstance(sheets.get(cur), dict) else {}
        status = (prev.get("status") or "").strip().lower()
        if status == "failed":
            cur = prev.get("continuity_from_sheet_id")
            continue
        path = prev.get("output_path")
        has_file = bool(path and os.path.isfile(path) and os.path.getsize(path) > 0)
        has_url = bool(prev.get("fal_image_url"))
        if has_file or has_url:
            return cur
        cur = prev.get("continuity_from_sheet_id")
    return None


def build_storyboard_sheet_ref_urls(
    specs: dict,
    entry: dict,
    *,
    ref_limit: int | None = None,
    include_character_sheets: bool = True,
    provider: str | None = None,
) -> list[str]:
    """Ordered refs: location lock → previous sheet → character sheets (capped).

    Character sheets are sorted by ``char_NN`` id so lead characters (low ids)
    stay in-budget when the scene cast lists crowd animals first.

    Pass ``include_character_sheets=False`` for the credit-safe lean storyboard
    edit path (location + continuity only); identity locks in panel regen.
    """
    resolved = provider or config.get_storyboard_image_provider()
    limit = (
        ref_limit if ref_limit is not None else config.get_image_ref_limit(resolved)
    )
    urls: list[str] = []

    loc_url = _location_ref_url(
        specs, entry.get("location_ref_id"), provider=resolved
    )
    if loc_url:
        urls.append(loc_url)

    continuity_id = _resolve_continuity_sheet_id(specs, entry)
    continuity_mode = (entry.get("continuity_mode") or "").strip().lower()
    # Cross-scene sheets must not attach the previous sheet PNG — it causes
    # composition echo (scene_N remixing scene_N-1 panel layouts).
    attach_prev = continuity_mode != "cross_scene" and entry.get(
        "attach_previous_sheet_ref", True
    )
    if attach_prev:
        prev_url = _previous_sheet_ref_url(specs, continuity_id, provider=resolved)
        if prev_url and prev_url not in urls:
            urls.append(prev_url)

    if not include_character_sheets:
        return urls[:limit]

    char_ids = list(entry.get("character_ref_ids") or [])

    def _char_sort_key(cid: str) -> tuple[int, int | str]:
        m = re.match(r"char_(\d+)$", (cid or "").strip().lower())
        if m:
            return (0, int(m.group(1)))
        return (1, cid or "")

    char_ids = sorted(char_ids, key=_char_sort_key)
    for url in _character_ref_urls(specs, char_ids, provider=resolved):
        if url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break

    return urls[:limit]


def _normalize_panels(data: dict, expected: int) -> list[dict]:
    panels = data.get("panels")
    if not isinstance(panels, list):
        raise ValueError(f"Crop analyzer JSON missing panels list: {data!r}")
    if len(panels) != expected:
        raise ValueError(
            f"Crop analyzer returned {len(panels)} panels, expected {expected}"
        )
    normalized: list[dict] = []
    for idx, panel in enumerate(panels):
        if not isinstance(panel, dict):
            raise ValueError(f"Panel {idx} is not an object: {panel!r}")
        try:
            x = float(panel["x"])
            y = float(panel["y"])
            w = float(panel["w"])
            h = float(panel["h"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid bbox for panel {idx}: {panel!r}") from exc
        normalized.append({"x": x, "y": y, "w": w, "h": h})
    return normalized


def _grid_bbox_row_major(
    panel_index: int, *, cols: int = 2, rows: int | None = None, panel_count: int | None = None
) -> dict[str, float]:
    """Deterministic N×2 row-major fallback when vision crop bboxes are invalid."""
    if rows is None:
        count = panel_count if panel_count is not None else max(panel_index + 1, 1)
        rows, cols = album_grid_shape(count, cols=cols)
    col = panel_index % cols
    row = panel_index // cols
    w = 1.0 / cols
    h = 1.0 / rows
    return {"x": col * w, "y": row * h, "w": w, "h": h}


def _sanitize_panel_bboxes(bboxes: list[dict]) -> list[dict]:
    """Replace zero-area vision bboxes with grid fallbacks."""
    rows, cols = album_grid_shape(len(bboxes))
    fixed: list[dict] = []
    for idx, bbox in enumerate(bboxes):
        w = float(bbox.get("w", 0))
        h = float(bbox.get("h", 0))
        if w <= 0 or h <= 0:
            fallback = _grid_bbox_row_major(idx, cols=cols, rows=rows)
            print(
                f"  ⚠️ Panel {idx + 1} bbox invalid ({bbox}) — using grid fallback {fallback}"
            )
            fixed.append(fallback)
        else:
            fixed.append(bbox)
    return fixed


def _contiguous_bands(indices: list[int]) -> list[tuple[int, int]]:
    """Collapse sorted indices into inclusive (start, end) runs."""
    if not indices:
        return []
    bands: list[tuple[int, int]] = []
    start = prev = indices[0]
    for idx in indices[1:]:
        if idx == prev + 1:
            prev = idx
            continue
        bands.append((start, prev))
        start = prev = idx
    bands.append((start, prev))
    return bands


def _axis_white_fractions(
    image,
    *,
    axis: str,
    sample_step: int = 8,
    white_threshold: int = 240,
) -> list[float]:
    """Fraction of near-white samples along each row (axis='y') or column (axis='x')."""
    width, height = image.size
    pixels = image.load()
    if axis == "y":
        length = height
        cross = width
    elif axis == "x":
        length = width
        cross = height
    else:
        raise ValueError(f"Unsupported axis: {axis!r}")

    fractions: list[float] = []
    for i in range(length):
        bright = 0
        samples = 0
        for j in range(0, cross, sample_step):
            if axis == "y":
                r, g, b = pixels[j, i][:3]
            else:
                r, g, b = pixels[i, j][:3]
            if r >= white_threshold and g >= white_threshold and b >= white_threshold:
                bright += 1
            samples += 1
        fractions.append(bright / samples if samples else 0.0)
    return fractions


def _select_gutter_bands(
    bands: list[tuple[int, int]],
    *,
    expected: int,
    size: int,
    cells: int,
    max_thickness: int = 8,
) -> list[tuple[int, int]] | None:
    """Pick exactly `expected` thin gutters nearest the uniform grid separators."""
    thin = [(a, b) for a, b in bands if 1 <= (b - a + 1) <= max_thickness]
    if expected <= 0:
        return []
    if len(thin) < expected:
        return None

    targets = [((i + 1) * size / cells) - 0.5 for i in range(expected)]

    def center(band: tuple[int, int]) -> float:
        return (band[0] + band[1]) / 2.0

    remaining = list(thin)
    chosen: list[tuple[int, int]] = []
    for target in targets:
        best_idx = min(range(len(remaining)), key=lambda i: abs(center(remaining[i]) - target))
        chosen.append(remaining.pop(best_idx))
    chosen.sort(key=lambda band: band[0])

    # Reject if two chosen bands collide or sit too close (degenerate cells).
    min_gap = max(8, size // (cells * 8))
    for left, right in zip(chosen, chosen[1:]):
        if right[0] - left[1] < min_gap:
            return None
    return chosen


def _cell_edges_from_gutters(
    size: int,
    gutters: list[tuple[int, int]],
    *,
    cells: int,
) -> list[tuple[int, int]] | None:
    """Convert gutter bands into inclusive cell ranges covering [0, size)."""
    if len(gutters) != cells - 1:
        return None
    edges: list[tuple[int, int]] = []
    cursor = 0
    for start, end in gutters:
        if start <= cursor:
            return None
        edges.append((cursor, start - 1))
        cursor = end + 1
    if cursor >= size:
        return None
    edges.append((cursor, size - 1))
    if len(edges) != cells:
        return None
    if any(b < a for a, b in edges):
        return None
    return edges


def detect_album_panel_bboxes(
    image_path: str,
    expected: int,
    *,
    cols: int | None = None,
    rows: int | None = None,
    inset_px: int = 2,
    white_threshold: int = 240,
    white_fraction: float = 0.85,
    max_gutter_thickness: int = 8,
) -> list[dict[str, float]] | None:
    """Detect panel boxes from thin white gutters on an album storyboard sheet.

    Returns normalized {x,y,w,h} boxes in row-major order, or None if gutters
    cannot be resolved confidently.
    """
    from PIL import Image

    if expected <= 0:
        return []
    derived_rows, derived_cols = album_grid_shape(expected)
    rows = derived_rows if rows is None else int(rows)
    cols = derived_cols if cols is None else int(cols)
    max_panels = cols * rows
    if expected > max_panels:
        raise ValueError(f"expected={expected} exceeds {rows}x{cols} grid ({max_panels})")

    with Image.open(image_path) as img:
        image = img.convert("RGB")
        width, height = image.size
        row_frac = _axis_white_fractions(
            image, axis="y", white_threshold=white_threshold
        )
        col_frac = _axis_white_fractions(
            image, axis="x", white_threshold=white_threshold
        )

    row_hits = [i for i, frac in enumerate(row_frac) if frac >= white_fraction]
    col_hits = [i for i, frac in enumerate(col_frac) if frac >= white_fraction]
    row_bands = _contiguous_bands(row_hits)
    col_bands = _contiguous_bands(col_hits)

    row_gutters = _select_gutter_bands(
        row_bands,
        expected=rows - 1,
        size=height,
        cells=rows,
        max_thickness=max_gutter_thickness,
    )
    col_gutters = _select_gutter_bands(
        col_bands,
        expected=cols - 1,
        size=width,
        cells=cols,
        max_thickness=max_gutter_thickness,
    )
    if row_gutters is None or col_gutters is None:
        return None

    row_edges = _cell_edges_from_gutters(height, row_gutters, cells=rows)
    col_edges = _cell_edges_from_gutters(width, col_gutters, cells=cols)
    if row_edges is None or col_edges is None:
        return None

    inset = max(0, int(inset_px))
    bboxes: list[dict[str, float]] = []
    for panel_index in range(expected):
        col = panel_index % cols
        row = panel_index // cols
        x0, x1 = col_edges[col]
        y0, y1 = row_edges[row]
        left = x0 + inset
        top = y0 + inset
        right = x1 - inset
        bottom = y1 - inset
        if right <= left or bottom <= top:
            return None
        bboxes.append(
            {
                "x": left / width,
                "y": top / height,
                "w": (right - left + 1) / width,
                "h": (bottom - top + 1) / height,
            }
        )
    return bboxes


def resolve_panel_bboxes(
    image_path: str,
    expected: int,
    *,
    mode: str | None = None,
) -> tuple[list[dict[str, float]], str]:
    """Resolve panel bboxes. Returns (bboxes, method) where method is
    'gutter' | 'grid' | 'vision' depending on path used by the caller.

    For mode 'python' (default): try white-gutter detection, else uniform grid.
    Vision is handled separately by panel_crop when mode == 'vision'.
    """
    crop_mode = (mode or os.getenv("STORYBOARD_CROP_MODE") or "python").strip().lower()
    if crop_mode not in {"python", "vision", "auto"}:
        crop_mode = "python"

    if crop_mode in {"python", "auto"}:
        detected = detect_album_panel_bboxes(image_path, expected)
        if detected is not None and len(detected) == expected:
            return detected, "gutter"
        return _fallback_panel_bboxes(expected), "grid"

    # vision mode: caller runs vision; provide grid as local helper fallback
    return _fallback_panel_bboxes(expected), "grid"


def _load_video_shot_plan(ctx: Context) -> dict:
    raw = ctx.state.get("video_shot_plan_content")
    if not raw:
        path = os.path.join(ctx.state["output_dir"], "video_shot_plan.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                raw = f.read()
    if not raw:
        return {"scenes": []}
    return clean_json_str(raw) if isinstance(raw, str) else raw


def _crop_panel(image_path: str, bbox: dict, out_path: str) -> None:
    from PIL import Image

    with Image.open(image_path) as img:
        width, height = img.size
        left = max(0, int(bbox["x"] * width))
        top = max(0, int(bbox["y"] * height))
        right = min(width, int((bbox["x"] + bbox["w"]) * width))
        bottom = min(height, int((bbox["y"] + bbox["h"]) * height))
        if right <= left or bottom <= top:
            raise ValueError(f"Invalid crop box {bbox} for image {width}x{height}")
        crop = img.crop((left, top, right, bottom))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        crop.save(out_path)


def _character_display_labels(
    character_ids: list[str],
    story_characters: list[dict] | None = None,
) -> dict[str, str]:
    """Map char id → short label for prompts (name if known, else id)."""
    names: dict[str, str] = {}
    for ch in story_characters or []:
        if not isinstance(ch, dict):
            continue
        cid = ch.get("id")
        if not cid:
            continue
        name = (ch.get("name") or "").strip()
        names[cid] = name or cid
    return {cid: names.get(cid, cid) for cid in character_ids if cid}


def _filter_chars_with_sheets(specs: dict, character_ids: list[str]) -> list[str]:
    """Keep only character ids that have a usable character sheet asset."""
    sheets = specs.get("character_sheets") or {}
    out: list[str] = []
    for cid in character_ids:
        if not cid or cid in out:
            continue
        entry = sheets.get(cid)
        if not isinstance(entry, dict):
            continue
        path = entry.get("output_path") or ""
        url = entry.get("fal_image_url") or ""
        if (path and os.path.isfile(path) and os.path.getsize(path) > 0) or url:
            out.append(cid)
    return out


def _prioritize_panel_regen_chars(
    character_ids: list[str],
    story_characters: list[dict] | None,
    *,
    budget: int,
    description: str = "",
    camera_intent: str = "",
) -> list[str]:
    """Prefer human heroes; defer animals unless the beat names them.

    Close father/child panels often trip moderation when unused animal sheets
    are attached alongside the crop.
    """
    if budget <= 0 or not character_ids:
        return []
    by_id = {
        str(ch.get("id") or "").strip(): ch
        for ch in (story_characters or [])
        if isinstance(ch, dict) and ch.get("id")
    }
    desc = (description or "").lower()
    cam = (camera_intent or "").lower()
    close_or_profile = any(
        token in cam for token in ("close", "profile", "portrait", "reaction", "cu")
    )
    humans: list[str] = []
    animals: list[str] = []
    for cid in character_ids:
        ch = by_id.get(cid) or {}
        appearance = f"{ch.get('name', '')} {ch.get('appearance', '')}".lower()
        name = str(ch.get("name") or cid).lower()
        is_animal = any(
            token in appearance
            for token in ("dog", "parrot", "bird", "elephant", "retriever", "animal")
        ) or cid in ("char_03", "char_04", "azhagi", "neju")
        named_in_beat = bool(name and name in desc)
        if is_animal and named_in_beat:
            humans.append(cid)
            continue
        if is_animal and close_or_profile and not named_in_beat:
            # Skip unused animals on close/profile panels (E005 risk).
            continue
        (animals if is_animal else humans).append(cid)
    ordered = humans + [c for c in animals if c not in humans]
    return ordered[:budget]


def build_panel_regen_prompt(
    shot: dict,
    *,
    render_style: str,
    character_labels: dict[str, str] | None = None,
    story_characters: list[dict] | None = None,
) -> str:
    from .reference_led_identity import normalize_provider_identity_language
    from .save_artifact_nodes import _apply_render_style

    char_ids = [cid for cid in (shot.get("characters_present") or []) if cid]
    description = (shot.get("description") or "").strip()
    camera = shot.get("camera_intent") or shot.get("frame_strategy") or "medium shot"
    labels = character_labels or {}
    guide_role = str(shot.get("director_guide_role") or "").strip().lower()
    continuity = str(shot.get("director_continuity_note") or "").strip()
    transition = str(shot.get("director_transition_after") or "").strip().lower()
    bridge = str(shot.get("director_bridge_to_next") or "").strip()
    motion = str(shot.get("motion_intent") or "").strip()

    if char_ids:
        slot_lines: list[str] = []
        for i, cid in enumerate(char_ids, start=2):
            label = labels.get(cid) or cid
            if label != cid:
                slot_lines.append(f"Image {i} = {cid} ({label}) character sheet")
            else:
                slot_lines.append(f"Image {i} = {cid} character sheet")
        slots = "; ".join(slot_lines)
        char_line = (
            f"Attachment map: Image 1 = panel crop; {slots}. "
            "IDENTITY-ONLY edit: retexture face, hair, skin tone, wardrobe, accessories, "
            "and footwear of each hero already visible in the crop using their character sheet. "
            "CROP is absolute authority for: who is present, how many figures, composition, "
            "camera, geography, limb pose, carry/ride relationships (including one person "
            "carrying another), screen direction, and expression. "
            "NEVER remove a person or animal visible in the crop. "
            "NEVER convert a carry/ride pose into separate standing figures. "
            "NEVER invent additional heroes or swap identities. "
            "Do NOT restyle body proportions in a way that breaks the crop pose. "
            "Keep the exact facial expression already visible in the crop."
        )
    else:
        char_line = (
            "Environment / empty-stage panel — no named heroes. "
            "Do not invent people, animals, or creatures."
        )

    role_line = ""
    if guide_role == "end":
        role_line = (
            "Director role: END / destination keyframe — prioritize a landable end composition "
            "with clear silhouette and settled pose. "
        )
    elif guide_role == "middle":
        role_line = (
            "Director role: MIDDLE / waypoint — preserve geography, screen direction, and "
            "pose continuity for a bridge still. "
        )
    elif guide_role == "start":
        role_line = (
            "Director role: START keyframe — clear readable opening composition for a unit. "
        )
    if transition == "match_cut":
        role_line += (
            "Match-cut boundary: preserve the shared composition so the next unit can start "
            "from this still. "
        )
    if continuity:
        role_line += f"Continuity lock: {continuity}. "
    if bridge:
        role_line += (
            f"Outgoing bridge toward next panel (keep this still a valid start for that morph): "
            f"{bridge}. "
        )
    if motion:
        role_line += f"Connecting motion intent: {motion}. "

    # Name the cast in soft guidance so ambient descriptions don't drop heroes.
    cast_names = []
    for cid in char_ids:
        cast_names.append(labels.get(cid) or cid)
    cast_hint = ""
    if cast_names:
        cast_hint = f" Keep every visible cast member from the crop ({', '.join(cast_names)})."

    prompt = (
        "Upscale and recreate this storyboard panel as a single full-frame cinematic "
        "animation still at high resolution. "
        "The FIRST attached image is the panel crop — match its exact composition, "
        "camera angle, framing, screen direction, body poses, cast count, and environment. "
        "CRITICAL: do not add or remove people, animals, props, landmarks, or objects; "
        "do not change geography or invent new subjects. "
        f"Camera: {camera}. "
        f"{role_line}"
        f"Soft visual guidance (crop wins for layout/pose/cast; sheets only retexture "
        f"identity): {description or 'as shown in crop'}.{cast_hint} "
        f"{char_line} "
        "No text, labels, captions, shot numbers, or watermarks."
    )
    styled = _apply_render_style(prompt, render_style)
    return normalize_provider_identity_language(
        styled,
        characters=story_characters,
        character_ids=char_ids,
        has_character_reference=bool(char_ids),
        preserve_safe_presentation=True,
    )


def _build_safe_panel_regen_prompt(
    shot: dict,
    *,
    render_style: str,
    character_labels: dict[str, str] | None = None,
) -> str:
    from .save_artifact_nodes import _apply_render_style

    description = (shot.get("description") or "").strip()
    camera = shot.get("camera_intent") or shot.get("frame_strategy") or "medium shot"
    char_ids = [cid for cid in (shot.get("characters_present") or []) if cid]
    labels = character_labels or {}
    if char_ids:
        named = []
        for cid in char_ids:
            label = labels.get(cid) or cid
            named.append(f"{cid} ({label})" if label != cid else cid)
        char_note = (
            f"Keep only characters already in the crop ({', '.join(named)}). "
            "Retexture face, wardrobe, accessories, and footwear from attached character "
            "sheets when present. Preserve crop cast count, carry/ride pose, body pose, "
            "and facial expression exactly."
        )
    else:
        char_note = "Empty-stage / environment panel — no people or animals."
    prompt = (
        "Recreate this single storyboard panel as a family-friendly stylized animated still. "
        "Match the attached panel crop for composition, body pose, cast, and expression. "
        "When character sheets are attached, sheets retexture identity only — crop wins "
        "for pose, cast count, and carry/ride relationships. "
        "Do not add people, animals, props, or landmarks not visible in the crop. "
        f"Camera: {camera}. Soft guidance: {description or 'as shown in crop'}. "
        f"{char_note} "
        "No text, labels, captions, or watermarks."
    )
    softened = soften_moderation_prompt(prompt, aggressive=True)
    return _apply_render_style(softened, render_style)


def _panel_regen_character_slots(character_ids: list[str]) -> list[dict]:
    return [
        {"role": "character_sheet", "asset_id": cid, "priority": i}
        for i, cid in enumerate(character_ids)
        if cid
    ]


async def storyboard_sheet_planner(ctx: Context) -> None:
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    story = _load_story(ctx)
    only_scenes = _only_scenes(ctx)
    panels_per_sheet = int(ctx.state.get("panels_per_sheet") or 8)
    style_id = (ctx.state.get("style_id") or "reel_v2").strip().lower()
    profile = get_profile(style_id)
    render_style = profile.render_style
    story_characters = [
        ch for ch in story.get("characters", []) if isinstance(ch, dict)
    ]
    locations = [loc for loc in (story.get("locations") or []) if isinstance(loc, dict)]
    previous_sheet_id: str | None = None

    # Preserve sheets for scenes outside --only-scenes so partial runs don't wipe them.
    existing_sheets = {
        sid: entry
        for sid, entry in (specs.get("storyboard_sheets") or {}).items()
        if isinstance(entry, dict)
    }
    storyboard_sheets: dict[str, dict] = {
        sid: entry
        for sid, entry in existing_sheets.items()
        if only_scenes and not _scene_in_scope(str(entry.get("scene_id") or ""), only_scenes)
    }
    # Continuity: last sheet of the prior scene when that sheet already exists on disk/specs.
    def _last_sheet_for_scene(scene_id: str) -> str | None:
        matches = [
            sid
            for sid, entry in {**existing_sheets, **storyboard_sheets}.items()
            if entry.get("scene_id") == scene_id
        ]
        return sorted(matches)[-1] if matches else None

    previous_scene_id: str | None = None
    for scene in story.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        scene_id = scene.get("scene_id")
        if not scene_id:
            continue
        if not _scene_in_scope(scene_id, only_scenes):
            # Still advance continuity anchor from preserved sheets.
            prev = _last_sheet_for_scene(scene_id)
            if prev:
                previous_sheet_id = prev
                previous_scene_id = scene_id
            continue
        shots = [
            shot
            for shot in scene.get("shots", [])
            if isinstance(shot, dict)
            and shot.get("shot_id")
            and _shot_in_scope(shot["shot_id"], only_scenes)
        ]
        if not shots:
            continue
        # Cross-scene continuity from the previous scene's last sheet when present.
        if previous_scene_id and previous_scene_id != scene_id and not previous_sheet_id:
            previous_sheet_id = _last_sheet_for_scene(previous_scene_id)
        location_ref_id = (scene.get("location_id") or "").strip() or None
        for sheet_index, chunk in enumerate(_chunk_shots(shots, panels_per_sheet), start=1):
            sheet_id = f"{scene_id}_sheet_{sheet_index:02d}"
            char_ids: list[str] = []
            for shot in chunk:
                for cid in shot.get("characters_present", []):
                    if cid and cid not in char_ids:
                        char_ids.append(cid)
            if not char_ids:
                # Fallback when plan omitted characters_present
                char_ids = [
                    cid
                    for cid, entry in (specs.get("character_sheets") or {}).items()
                    if isinstance(entry, dict)
                ]
            has_location_ref = bool(
                location_ref_id and (specs.get("location_sheets") or {}).get(location_ref_id)
            )
            continuity_from = previous_sheet_id
            cont_mode = continuity_mode_for(
                continuity_from_sheet_id=continuity_from,
                scene_id=str(scene_id),
            )
            # Cross-scene: keep text continuity note but do not attach prev sheet PNG.
            attach_prev_ref = bool(continuity_from) and cont_mode != "cross_scene"
            sheet_prompt = build_storyboard_sheet_prompt(
                scene,
                chunk,
                render_style=render_style,
                sheet_number=sheet_index,
                panels_per_sheet=panels_per_sheet,
                story_characters=story_characters,
                style_id=style_id,
                locations=locations,
                continuity_from_sheet_id=continuity_from,
                has_location_ref=has_location_ref,
                has_previous_sheet_ref=attach_prev_ref,
                continuity_mode=cont_mode,
            )
            # Keep completed sheet artifacts when re-planning the same id.
            prior = existing_sheets.get(sheet_id) or {}
            rows, cols = album_grid_shape(len(chunk))
            storyboard_sheets[sheet_id] = {
                "sheet_id": sheet_id,
                "scene_id": scene_id,
                "panel_shot_ids": [shot["shot_id"] for shot in chunk],
                "character_ref_ids": char_ids,
                "location_ref_id": location_ref_id,
                "continuity_from_sheet_id": continuity_from,
                "continuity_mode": cont_mode,
                "attach_previous_sheet_ref": attach_prev_ref,
                "panel_count": len(chunk),
                "grid": f"{rows}x{cols}",
                "sheet_prompt": sheet_prompt,
                "output_path": os.path.join(
                    output_dir, "storyboard_sheets", f"{sheet_id}.png"
                ),
                "fal_image_url": prior.get("fal_image_url"),
                "panel_bboxes": prior.get("panel_bboxes") or [],
                "status": prior.get("status") or "pending",
            }
            if prior.get("output_path") and os.path.isfile(prior["output_path"]):
                storyboard_sheets[sheet_id]["output_path"] = prior["output_path"]
                if prior.get("status") == "completed":
                    storyboard_sheets[sheet_id]["status"] = "completed"
            previous_sheet_id = sheet_id
        previous_scene_id = scene_id

    specs["storyboard_sheets"] = storyboard_sheets
    _save_specs(ctx, specs)
    print(
        f"📋 [storyboard_sheet_planner] Planned {len(storyboard_sheets)} storyboard sheet(s)"
    )


async def storyboard_sheet_generator(ctx: Context) -> None:
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    only_scenes = _only_scenes(ctx)
    sheets_dir = os.path.join(output_dir, "storyboard_sheets")
    os.makedirs(sheets_dir, exist_ok=True)
    sb_provider = config.get_storyboard_image_provider()
    ref_limit = config.get_image_ref_limit(sb_provider)
    # fal GPT Image 2 handles character-sheet refs well; Replicate stays lean
    # (location + prev sheet) to avoid E005 credit burns on montage refs.
    include_chars = sb_provider == "fal"
    # Drop legacy T2I mode flag — storyboards must always use edit + refs.
    meta = specs.get("_meta")
    if isinstance(meta, dict) and meta.get("storyboard_generation_mode") == "t2i":
        meta.pop("storyboard_generation_mode", None)
        _save_specs(ctx, specs)

    sheets = specs.get("storyboard_sheets", {})
    smoke_max_sheets = int(os.getenv("SMOKE_MAX_STORYBOARD_SHEETS", "0") or "0")
    sheet_items = list(sheets.items())
    if smoke_max_sheets > 0:
        sheet_items = sheet_items[:smoke_max_sheets]
        print(f"  ⏭️ Smoke limit: generating {len(sheet_items)} storyboard sheet(s)")

    # Sequential generation so each sheet can use the previous sheet PNG as a continuity ref.
    for sheet_id, entry in sheet_items:
        scene_id = entry.get("scene_id")
        if not _scene_in_scope(scene_id, only_scenes):
            continue
        out_path = entry.get("output_path") or os.path.join(sheets_dir, f"{sheet_id}.png")
        if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
            entry["output_path"] = out_path
            entry["status"] = "completed"
            # Ensure URL exists for downstream continuity refs.
            _ensure_asset_url(entry, provider=sb_provider)
            _save_specs(ctx, specs)
            continue

        ref_ids = list(entry.get("character_ref_ids") or [])
        if not ref_ids:
            ref_ids = [
                cid
                for cid, centry in (specs.get("character_sheets") or {}).items()
                if isinstance(centry, dict)
            ]
            entry["character_ref_ids"] = ref_ids

        # Soften before any paid call — age labels often trip GPT Image 2.
        prompt = _soften_storyboard_contact_language(
            soften_moderation_prompt(entry.get("sheet_prompt", ""), aggressive=True)
        )
        if prompt != (entry.get("sheet_prompt") or ""):
            entry["sheet_prompt"] = prompt

        ref_urls = build_storyboard_sheet_ref_urls(
            specs,
            entry,
            ref_limit=ref_limit,
            include_character_sheets=include_chars,
            provider=sb_provider,
        )
        if not ref_urls:
            entry["status"] = "failed"
            entry["error"] = "storyboard edit requires reference image URLs"
            _save_specs(ctx, specs)
            print(
                f"⚠️ [storyboard_sheet_generator] {sheet_id} failed (no refs) — "
                "continuing without T2I fallback"
            )
            continue

        model_id = (
            (os.getenv("GROK_FAL_MODEL") or config.GROK_REPLICATE_MODEL)
            if sb_provider == "fal"
            else config.GROK_REPLICATE_MODEL
        )
        edit_label = "full edit" if include_chars else "lean edit"
        print(
            f"  Storyboard sheet: {sheet_id} "
            f"({edit_label} {len(ref_urls)} ref(s); provider={sb_provider}; "
            f"loc={entry.get('location_ref_id')}, "
            f"prev={entry.get('continuity_from_sheet_id')}) "
            f"model={model_id} quality={config.REPLICATE_SHEET_QUALITY} "
            f"size={config.STORYBOARD_SHEET_SIZE} text_policy=no_text"
        )

        def _gen(urls=ref_urls, prompt_text=prompt, path=out_path):
            return generate_grok_edit(
                prompt_text,
                urls,
                path,
                size=config.STORYBOARD_SHEET_SIZE,
                quality=config.REPLICATE_SHEET_QUALITY,
                text_policy="no_text",
                provider=sb_provider,
            )

        try:
            # Edit-only: no T2I fallback. On failure mark failed and continue.
            result = await retry_async(
                _gen,
                f"storyboard sheet {sheet_id}",
                on_sensitive=None,
                max_sensitive_retries=0,
            )
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = str(exc)
            _save_specs(ctx, specs)
            print(
                f"⚠️ [storyboard_sheet_generator] {sheet_id} failed "
                f"(no T2I fallback) — continuing: {exc}"
            )
            continue

        entry["output_path"] = result["generated_image_path"]
        entry["fal_image_url"] = result["fal_image_url"]
        if result.get("revised_prompt"):
            entry["revised_prompt"] = result["revised_prompt"]
        entry["status"] = "completed"
        entry.pop("error", None)
        _save_specs(ctx, specs)

    failed = [
        sid
        for sid, e in sheets.items()
        if isinstance(e, dict) and e.get("status") == "failed"
    ]
    _save_specs(ctx, specs)
    if failed:
        print(
            f"⚠️ [storyboard_sheet_generator] Done with {len(failed)} failed sheet(s): "
            f"{', '.join(failed)}"
        )
    else:
        print("✅ [storyboard_sheet_generator] Storyboard sheet generation complete")


def _fallback_panel_bboxes(expected: int) -> list[dict[str, float]]:
    rows, cols = album_grid_shape(expected)
    return [_grid_bbox_row_major(i, cols=cols, rows=rows) for i in range(expected)]


async def panel_crop(ctx: Context) -> None:
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    only_scenes = _only_scenes(ctx)
    crops_dir = os.path.join(output_dir, "panel_crops")
    os.makedirs(crops_dir, exist_ok=True)
    crop_mode = (os.getenv("STORYBOARD_CROP_MODE") or "python").strip().lower()
    if crop_mode not in {"python", "vision", "auto"}:
        crop_mode = "python"

    analyzer_prompt = None
    crop_model = crop_key = crop_base = None
    if crop_mode == "vision":
        analyzer_prompt = _load_prompt_file("storyboard_crop_analyzer")
        crop_model, crop_key, crop_base = config.get_crop_analysis_model_config()

    smoke_max_sheets = int(os.getenv("SMOKE_MAX_STORYBOARD_SHEETS", "0") or "0")
    sheet_entries = list(specs.get("storyboard_sheets", {}).items())
    if smoke_max_sheets > 0:
        sheet_entries = sheet_entries[:smoke_max_sheets]
    for sheet_id, entry in sheet_entries:
        scene_id = entry.get("scene_id")
        if not _scene_in_scope(scene_id, only_scenes):
            continue
        if (entry.get("status") or "").strip().lower() == "failed":
            print(f"  Panel crop skip (failed sheet): {sheet_id}")
            continue
        sheet_path = entry.get("output_path")
        if not sheet_path or not os.path.isfile(sheet_path):
            raise FileNotFoundError(f"Storyboard sheet image missing for {sheet_id}")

        shot_ids = entry.get("panel_shot_ids", [])
        expected = int(entry.get("panel_count") or len(shot_ids))
        crop_map = entry.get("panel_crops") or {}
        if (
            entry.get("panel_bboxes")
            and len(entry.get("panel_bboxes", [])) == expected
            and all(
                os.path.isfile(crop_map.get(sid, "")) and os.path.getsize(crop_map.get(sid, "")) > 0
                for sid in shot_ids
            )
        ):
            print(f"  Panel crop skip (on disk): {sheet_id}")
            continue

        print(f"  Panel crop ({crop_mode}): {sheet_id} ({expected} panels)")
        method = "grid"
        rows, cols = album_grid_shape(expected)
        if crop_mode == "vision":
            user_text = json.dumps(
                {
                    "expected_panels": expected,
                    "grid": f"{rows} rows x {cols} columns, row-major order",
                    "sheet_id": sheet_id,
                },
                ensure_ascii=False,
            )
            try:
                data = await vision_json_from_image(
                    sheet_path,
                    analyzer_prompt,
                    user_text,
                    model=crop_model,
                    api_key=crop_key,
                    api_base=crop_base,
                )
                bboxes = _sanitize_panel_bboxes(_normalize_panels(data, expected))
                method = "vision"
            except Exception as exc:
                print(
                    f"  ⚠️ Panel crop vision failed for {sheet_id} ({exc}) — "
                    "trying python gutter/grid"
                )
                bboxes, method = resolve_panel_bboxes(
                    sheet_path, expected, mode="python"
                )
        else:
            bboxes, method = resolve_panel_bboxes(sheet_path, expected, mode=crop_mode)
            if method == "grid":
                print(
                    f"  ⚠️ Gutter detect missed for {sheet_id} — "
                    f"using uniform {rows}×{cols} grid"
                )
            else:
                print(f"  Panel crop gutters OK: {sheet_id}")

        entry["panel_bboxes"] = bboxes
        entry["panel_crop_method"] = method
        panel_crops: dict[str, str] = {}
        for shot_id, bbox in zip(shot_ids, bboxes, strict=True):
            crop_path = os.path.join(crops_dir, f"{shot_id}.png")
            _crop_panel(sheet_path, bbox, crop_path)
            panel_crops[shot_id] = crop_path
            shot_entry = specs.get("shot_images", {}).get(shot_id, {})
            if isinstance(shot_entry, dict):
                shot_entry["panel_crop_path"] = crop_path
                shot_entry["storyboard_sheet_id"] = sheet_id
        entry["panel_crops"] = panel_crops
        entry["status"] = "cropped"

    _save_specs(ctx, specs)
    print("✅ [panel_crop] Panel cropping complete")


async def panel_regen(ctx: Context) -> None:
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    story = _load_story(ctx)
    video_shot_plan = _load_video_shot_plan(ctx)
    only_scenes = _only_scenes(ctx)
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    style_id = (ctx.state.get("style_id") or "reel_v2").strip().lower()
    render_style = get_profile(style_id).render_style
    story_characters = [
        ch for ch in story.get("characters", []) if isinstance(ch, dict)
    ]
    story_shots: dict[str, dict] = {}
    for scene in story.get("scenes", []):
        for shot in scene.get("shots", []):
            story_shots[shot["shot_id"]] = shot

    # Panel stills: PROVIDER / PANEL_IMAGE_PROVIDER primary; optional fal fallback.
    panel_provider = config.get_panel_image_provider()
    fallback_provider = config.get_panel_image_fallback_provider()

    def _upload_panel_ref(local_path: str, provider: str) -> str:
        if provider == "fal":
            import fal_client

            if not os.environ.get("FAL_KEY"):
                os.environ["FAL_KEY"] = config.FAL_KEY or ""
            return fal_client.upload_file(local_path)
        from tools.grok_replicate import upload_local_image

        return upload_local_image(local_path)

    def _build_ref_urls(
        *,
        provider: str,
        crop_path: str,
        char_ids: list[str],
    ) -> tuple[list[str], str]:
        ref_limit = config.get_image_ref_limit(provider)
        char_urls = _character_ref_urls(specs, char_ids, provider=provider)
        # upload is sync; callers wrap in to_thread when needed
        crop_url = _upload_panel_ref(crop_path, provider)
        return [crop_url, *char_urls][:ref_limit], crop_url

    anchor_to_motion_arc: dict[str, str] = {}
    if video_shot_plan.get("scenes"):
        for scene in video_shot_plan.get("scenes", []):
            for vshot in scene.get("video_shots", []):
                anchor = vshot.get("anchor_panel_id")
                if anchor:
                    anchor_to_motion_arc[anchor] = str(vshot.get("motion_arc") or "").strip()

    sem = asyncio.Semaphore(_MAX_REGEN_CONCURRENCY)
    shot_failures: list[tuple[str, str]] = []
    smoke_max_panels = int(os.getenv("SMOKE_MAX_PANEL_REGENS", "0") or "0")
    smoke_per_sheet = int(os.getenv("SMOKE_MAX_PANELS_PER_SHEET", "0") or "0")
    regen_all = os.getenv("PANEL_REGEN_ALL", "").lower() in ("1", "true", "yes")
    try:
        from .storyboard_director_nodes import is_director_video_mode

        if is_director_video_mode(ctx):
            regen_all = True
    except Exception:
        pass
    smoke_bypass_anchor = smoke_max_panels > 0 or smoke_per_sheet > 0 or regen_all
    only_regen_shots = {
        s.strip()
        for s in (os.getenv("PANEL_REGEN_SHOTS") or "").split(",")
        if s.strip()
    }
    if regen_all:
        print("  ⏭️ PANEL_REGEN_ALL / director mode — generating all panels with crops (not anchors-only)")
    if only_regen_shots:
        print(f"  ⏭️ PANEL_REGEN_SHOTS={sorted(only_regen_shots)}")
    fb_label = fallback_provider or "none"
    print(
        f"  Panel regen provider={panel_provider} fallback={fb_label} "
        f"quality={config.REPLICATE_PANEL_QUALITY} size={config.PANEL_IMAGE_SIZE}"
    )

    async def _one(shot_id: str, entry: dict) -> None:
        if not _shot_in_scope(shot_id, only_scenes):
            return
        if only_regen_shots and shot_id not in only_regen_shots:
            return
        if (
            not smoke_bypass_anchor
            and anchor_to_motion_arc
            and shot_id not in anchor_to_motion_arc
        ):
            entry["status"] = "skipped_non_anchor"
            return
        out_path = os.path.join(images_dir, f"{shot_id}.png")
        if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
            entry["output_path"] = out_path
            entry["status"] = "completed"
            return

        crop_path = entry.get("panel_crop_path")
        if not crop_path or not os.path.isfile(crop_path):
            crop_path = os.path.join(output_dir, "panel_crops", f"{shot_id}.png")
        if not crop_path or not os.path.isfile(crop_path):
            entry["status"] = "skipped_missing_crop"
            print(f"  ⚠️ Panel regen skip (missing crop): {shot_id}")
            return
        entry["panel_crop_path"] = crop_path

        shot = dict(story_shots.get(shot_id, {}))
        shot["video_motion_arc"] = anchor_to_motion_arc.get(shot_id, "")
        requested_char_ids = [
            cid
            for cid in (
                shot.get("characters_present")
                or entry.get("characters_present")
                or []
            )
            if cid
        ]
        # Only attach character sheets that actually exist (smoke / partial runs).
        available_char_ids = _filter_chars_with_sheets(specs, requested_char_ids)
        dropped = [cid for cid in requested_char_ids if cid not in available_char_ids]
        if dropped:
            print(
                f"  ⚠️ Panel regen {shot_id}: skipping missing character sheets "
                f"{dropped}"
            )
        # Cap character sheets so crop + chars stay within provider ref limit.
        # Prefer humans named in the beat over unused animal sheets (E005 risk).
        primary_ref_limit = config.get_image_ref_limit(panel_provider)
        char_budget = max(0, primary_ref_limit - 1)
        char_ids = _prioritize_panel_regen_chars(
            available_char_ids,
            story_characters,
            budget=char_budget,
            description=str(shot.get("description") or ""),
            camera_intent=str(shot.get("camera_intent") or ""),
        )
        shot["characters_present"] = char_ids
        entry["characters_present"] = char_ids
        entry["reference_slots"] = _panel_regen_character_slots(char_ids)
        entry["reference_strategy"] = "char_sheets_only"
        entry["generation_mode"] = "grok_edit"
        entry["image_provider"] = panel_provider
        entry["reference_images"] = [
            f"{{{{character_sheets.{cid}.fal_image_url}}}}" for cid in char_ids
        ]

        char_labels = _character_display_labels(char_ids, story_characters)
        ref_urls, crop_url = await asyncio.to_thread(
            _build_ref_urls,
            provider=panel_provider,
            crop_path=crop_path,
            char_ids=char_ids,
        )
        prompt_box = [
            build_panel_regen_prompt(
                shot,
                render_style=render_style,
                character_labels=char_labels,
                story_characters=story_characters,
            )
        ]
        entry["image_prompt"] = prompt_box[0]
        print(
            f"  Panel regen: {shot_id} ({len(ref_urls)} ref(s); chars={char_ids}; "
            f"provider={panel_provider})"
        )

        def _soften(_err: str, attempt: int) -> None:
            from .reference_led_identity import (
                log_provider_sensitivity_failure,
                normalize_provider_identity_language,
                soften_carry_contact_language,
            )

            before = prompt_box[0]
            log_provider_sensitivity_failure(
                prompt_class="panel_regen_named_reference",
                retry_route="soften_moderation_prompt+carry_safe",
                provider=panel_provider,
            )
            softened = soften_moderation_prompt(before, aggressive=attempt >= 2)
            softened = soften_carry_contact_language(softened)
            prompt_box[0] = normalize_provider_identity_language(
                softened,
                characters=story_characters,
                character_ids=char_ids,
                has_character_reference=bool(char_ids),
                preserve_safe_presentation=True,
            )
            if prompt_box[0] != before:
                entry["image_prompt"] = prompt_box[0]

        async def _edit_once(
            *,
            provider: str,
            urls: list[str],
            label: str,
            text_policy: str = "default",
        ) -> dict:
            async with sem:
                def _gen():
                    return generate_grok_edit(
                        prompt_box[0],
                        urls,
                        out_path,
                        size=config.PANEL_IMAGE_SIZE,
                        quality=config.REPLICATE_PANEL_QUALITY,
                        text_policy=text_policy,
                        provider=provider,
                    )

                return await retry_async(
                    _gen, label, on_sensitive=_soften
                )

        result: dict | None = None
        primary_error: str | None = None
        try:
            result = await _edit_once(
                provider=panel_provider,
                urls=ref_urls,
                label=f"panel regen {shot_id}",
            )
        except Exception as first_exc:
            primary_error = str(first_exc)
            # Primary safe: softened prompt + crop-only on same provider.
            prompt_box[0] = _build_safe_panel_regen_prompt(
                shot, render_style=render_style, character_labels=char_labels
            )
            entry["image_prompt"] = prompt_box[0]
            print(
                f"  ⚠️ Panel regen primary failed for {shot_id}; "
                f"retrying safe crop-only on {panel_provider}"
            )
            try:
                result = await _edit_once(
                    provider=panel_provider,
                    urls=[crop_url],
                    label=f"panel regen safe {shot_id}",
                    text_policy="no_text",
                )
            except Exception as safe_exc:
                primary_error = f"{primary_error} | {safe_exc}"
                result = None

        # Cross-provider fal fallback (edit + refs; never bare T2I).
        if result is None and fallback_provider:
            print(
                f"  ⚠️ Panel regen falling back to {fallback_provider} for {shot_id} "
                f"(after {panel_provider} failure)"
            )
            try:
                fb_urls, fb_crop_url = await asyncio.to_thread(
                    _build_ref_urls,
                    provider=fallback_provider,
                    crop_path=crop_path,
                    char_ids=char_ids,
                )
                crop_url = fb_crop_url
                # Restore a full (softened) prompt for fallback full-ref attempt.
                prompt_box[0] = soften_moderation_prompt(
                    build_panel_regen_prompt(
                        shot,
                        render_style=render_style,
                        character_labels=char_labels,
                        story_characters=story_characters,
                    ),
                    aggressive=True,
                )
                entry["image_prompt"] = prompt_box[0]
                print(
                    f"  Panel regen fallback: {shot_id} "
                    f"({len(fb_urls)} ref(s); provider={fallback_provider})"
                )
                result = await _edit_once(
                    provider=fallback_provider,
                    urls=fb_urls,
                    label=f"panel regen fallback {shot_id}",
                )
                entry["image_provider"] = fallback_provider
                entry["fallback_mode"] = "fal_after_primary_failure"
                entry["fallback_reason"] = primary_error
            except Exception as fb_exc:
                print(
                    f"  ⚠️ Panel regen {fallback_provider} full-ref failed for "
                    f"{shot_id}; trying crop-only on {fallback_provider}"
                )
                try:
                    crop_url = await asyncio.to_thread(
                        _upload_panel_ref, crop_path, fallback_provider
                    )
                    prompt_box[0] = _build_safe_panel_regen_prompt(
                        shot,
                        render_style=render_style,
                        character_labels=char_labels,
                    )
                    entry["image_prompt"] = prompt_box[0]
                    result = await _edit_once(
                        provider=fallback_provider,
                        urls=[crop_url],
                        label=f"panel regen fallback safe {shot_id}",
                        text_policy="no_text",
                    )
                    entry["image_provider"] = fallback_provider
                    entry["fallback_mode"] = "fal_crop_only_after_primary_failure"
                    entry["fallback_reason"] = (
                        f"{primary_error} | fallback_full={fb_exc}"
                    )
                except Exception as fb_safe_exc:
                    primary_error = (
                        f"{primary_error} | fallback={fb_exc} | "
                        f"fallback_safe={fb_safe_exc}"
                    )
                    result = None

        if result is None:
            if not _PANEL_REGEN_ALLOW_SOFT_FAIL:
                raise RuntimeError(
                    f"panel regen {shot_id} failed on "
                    f"{panel_provider}"
                    + (f"+{fallback_provider}" if fallback_provider else "")
                    + f": {primary_error}"
                )
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            shutil.copy2(crop_path, out_path)
            entry["output_path"] = out_path
            entry["fal_image_url"] = None
            entry["panel_crop_url"] = crop_url
            entry["status"] = "completed"
            entry["fallback_mode"] = "copied_panel_crop_after_moderation_failure"
            entry["fallback_reason"] = primary_error or "unknown"
            shot_failures.append((shot_id, entry["fallback_reason"]))
            print(
                f"  ⚠️ Panel regen soft-fail for {shot_id}: copied crop "
                "(all providers exhausted)."
            )
            return

        entry["image_prompt"] = prompt_box[0]
        entry["output_path"] = result["generated_image_path"]
        entry["fal_image_url"] = result["fal_image_url"]
        entry["panel_crop_url"] = crop_url
        if result.get("revised_prompt"):
            entry["revised_prompt"] = result["revised_prompt"]
        entry["status"] = "completed"
        if entry.get("fallback_mode") not in {
            "fal_after_primary_failure",
            "fal_crop_only_after_primary_failure",
        }:
            entry.pop("error", None)
            entry.pop("fallback_mode", None)
            entry.pop("fallback_reason", None)

    smoke_max_panels = int(os.getenv("SMOKE_MAX_PANEL_REGENS", "0") or "0")
    smoke_per_sheet = int(os.getenv("SMOKE_MAX_PANELS_PER_SHEET", "0") or "0")
    panel_items = [
        (sid, entry)
        for sid, entry in specs.get("shot_images", {}).items()
        if isinstance(entry, dict)
    ]
    if smoke_per_sheet > 0:
        selected: list[tuple[str, dict]] = []
        smoke_max_sheets = int(os.getenv("SMOKE_MAX_STORYBOARD_SHEETS", "0") or "0")
        sheet_entries = list((specs.get("storyboard_sheets") or {}).items())
        if smoke_max_sheets > 0:
            sheet_entries = sheet_entries[:smoke_max_sheets]
        seen: set[str] = set()
        for sheet_id, sheet in sheet_entries:
            for sid in (sheet.get("panel_shot_ids") or [])[:smoke_per_sheet]:
                entry = (specs.get("shot_images") or {}).get(sid)
                if not isinstance(entry, dict) or sid in seen:
                    continue
                selected.append((sid, entry))
                seen.add(sid)
        panel_items = selected
        print(
            f"  ⏭️ Smoke limit: regenerating {len(panel_items)} panel image(s) "
            f"({smoke_per_sheet} per sheet)"
        )
    elif smoke_max_panels > 0:
        # Prefer ordered first in-scope shot ids
        panel_items = panel_items[:smoke_max_panels]
        print(
            f"  ⏭️ Smoke limit: regenerating {len(panel_items)} panel image(s)"
        )
    tasks = [_one(sid, entry) for sid, entry in panel_items]
    await asyncio.gather(*tasks)
    _save_specs(ctx, specs)
    if shot_failures:
        print(
            f"⚠️ [panel_regen] Used crop fallback for {len(shot_failures)} shot(s): "
            + ", ".join(sid for sid, _ in shot_failures)
        )
    print("✅ [panel_regen] Panel regeneration complete")


storyboard_sheet_planner_node = FunctionNode(
    func=storyboard_sheet_planner, name="storyboard_sheet_planner_node"
)
storyboard_sheet_generator_node = FunctionNode(
    func=storyboard_sheet_generator, name="storyboard_sheet_generator_node"
)
panel_crop_node = FunctionNode(func=panel_crop, name="panel_crop_node")
panel_regen_node = FunctionNode(func=panel_regen, name="panel_regen_node")
