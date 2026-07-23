"""Deterministic storyboard-sheet prompt builder (reel_v2 / research-aligned)."""
from __future__ import annotations

import os
import re
from typing import Any

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# From Research/story-board/Character-consistency.md — provider-facing age-neutral.
CHARACTER_CONSISTENCY_CANON: dict[str, str] = {
    "naila": (
        "Naila, matching the attached character reference: curly dark brown hair, "
        "expressive brown eyes, light brown skin, forest-green dress, barefoot."
    ),
    "father": (
        "Father, matching the attached character reference: kind forest caretaker in "
        "khaki ranger clothing with a medium beard."
    ),
    "azhagi": (
        "Azhagi, matching the attached character reference: fluffy golden retriever, "
        "protective and expressive."
    ),
    "neju": (
        "Neju, matching the attached character reference: colorful green parrot with an "
        "orange beak and blue wing tips."
    ),
}

ENVIRONMENT_CANON = (
    "A lush forest sanctuary with wooden shelters, giant trees, elephants, deer, birds, "
    "flower gardens, and warm golden morning light."
)

ENVIRONMENT_DETAILS = [
    "Large lush green forest sanctuary",
    "Wooden treehouse",
    "Animal shelters",
    "Elephants",
    "Birds",
    "Flower gardens",
    "Wooden fences",
    "Warm morning sunlight",
]


def _load_prompt_file(name: str, *, style_id: str | None = "reel_v2") -> str:
    style = (style_id or os.getenv("STORY_STYLE") or "").strip().lower()
    candidates: list[str] = []
    if style and style != "cinematic":
        candidates.append(os.path.join(_SKILL_DIR, "prompts", style, f"{name}.md"))
    candidates.append(os.path.join(_SKILL_DIR, "prompts", f"{name}.md"))
    for path in candidates:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
    raise FileNotFoundError(f"Prompt file not found for {name!r}; tried: {candidates}")


def _normalize_id(character_id: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", (character_id or "").strip().lower()).strip("_")


def _strip_visual_prefix(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.lower().startswith("visual:"):
        return cleaned.split(":", 1)[1].strip()
    return cleaned


def _shot_camera(shot: dict[str, Any]) -> str:
    return (
        shot.get("camera_intent")
        or shot.get("frame_strategy")
        or "Medium Shot"
    ).strip()


def _shot_action(shot: dict[str, Any]) -> str:
    description = _strip_visual_prefix(shot.get("description", ""))
    motion = (shot.get("motion_intent") or "").strip()
    if description and motion:
        return f"{description} Motion: {motion}."
    return description or motion or "Story beat as planned."


def album_grid_shape(panel_count: int, *, cols: int = 2) -> tuple[int, int]:
    """Derive album rows×cols from painted panel count (reel_v2: full sheet → 4×2)."""
    count = max(0, int(panel_count))
    cols = max(1, int(cols))
    if count <= 0:
        return 1, cols
    rows = max(1, (count + cols - 1) // cols)
    return rows, cols


def build_grid_layout_instruction(panel_count: int, panels_per_sheet: int) -> str:
    """Require a fully painted photo-album board — no blank panel cells."""
    rows, cols = album_grid_shape(panel_count)
    grid_label = f"{rows} rows × {cols} columns"
    if panel_count >= panels_per_sheet:
        return (
            f"Arrange exactly {panel_count} cinematic stills in a {grid_label} grid "
            "on a mild portrait **8:9** page (photo album / contact sheet; NOT 9:16). "
            "Because the page is 8:9, each packed grid cell is approximately **16:9** landscape. "
            "Each panel frame itself must be a landscape 16:9 cinematic still (wider than tall), "
            "not a portrait frame. "
            "Use only thin uniform black or white gutters as separators. "
            "Every grid cell must contain a fully rendered cinematic panel with painted scene content. "
            "No text, labels, headers, captions, or timeline on the page."
        )
    return (
        f"Arrange exactly {panel_count} cinematic stills across a {grid_label} album grid "
        "on a mild portrait **8:9** page (NOT 9:16). "
        "Each panel frame itself must be a landscape 16:9 cinematic still (wider than tall), "
        "not a portrait frame. "
        "Column width drives panel width; keep each panel 16:9 and let leftover vertical space "
        "become the same thin gutter/background between rows — never fill with captions. "
        "CRITICAL: no blank, white, empty, or placeholder panel cells; no on-page typography."
    )


def build_shot_listing(shots: list[dict[str, Any]], *, start_index: int = 1) -> str:
    """Numbered shot list like Research/story-board/Compiled-storyboard-sheet-prompt.md.

    ``start_index`` is the on-sheet ordinal start (always 1 for a fresh album page).
    """
    lines: list[str] = []
    for offset, shot in enumerate(shots):
        index = start_index + offset
        camera = _shot_camera(shot)
        action = _shot_action(shot)
        lines.append(f"{index}. CAM: {camera} — {action}")
    return "\n".join(lines)


def build_panel_lines(
    shots: list[dict[str, Any]],
    *,
    start_index: int = 1,
    panels_per_row: int = 2,
) -> str:
    """Detailed per-panel blocks for crop alignment (Director-aware).

    Includes connecting motion, incoming/outgoing bridges so each album **row**
    paints as an FLF-compatible start→end pair (left=start, right=end).

    Grid row/col are ALWAYS computed from the panel's position on **this sheet**
    (offset 0 → row 1 col 1), never from a story-wide shot index. That keeps the
    album page a hard **N×2** sheet-local grid (full reel_v2 sheet → 4×2) even when
    earlier scenes already consumed prior story-wide shot ordinals.
    """
    blocks: list[str] = []
    for offset, shot in enumerate(shots):
        # On-sheet panel number (1..len(shots)); start_index defaults to 1.
        index = start_index + offset
        camera = _shot_camera(shot)
        duration = shot.get("duration_seconds")
        # Editorial board beat only — never an LTX render duration.
        beat_label = f"board beat ~{duration}s" if duration else "board beat"
        # Sheet-local grid only — do not use story-wide shot ordinals here.
        row = offset // panels_per_row + 1
        col = offset % panels_per_row + 1
        staging_bits = []
        for key in ("subject_position", "facing_direction", "eyeline", "background_region"):
            val = shot.get(key)
            if val:
                staging_bits.append(f"{key}: {val}")
        visual = _strip_visual_prefix(shot.get("description", ""))
        if staging_bits:
            visual = f"{visual} ({'; '.join(staging_bits)})"
        guide_role = (shot.get("director_guide_role") or "").strip()
        transition = (shot.get("director_transition_after") or "").strip()
        continuity = (shot.get("director_continuity_note") or "").strip()
        bridge_out = (shot.get("director_bridge_to_next") or "").strip()
        bridge_in = ""
        if offset > 0:
            bridge_in = (
                shots[offset - 1].get("director_bridge_to_next") or ""
            ).strip()
        group = shot.get("director_chain_group")
        block = [
            f"Panel {index} | grid row {row} col {col} | {beat_label}",
            f"CAM: {camera}",
            f"Visual: {visual}",
        ]
        motion = (shot.get("motion_intent") or "").strip()
        if motion:
            block.append(f"Motion (toward next panel): {motion}")
        if bridge_in:
            block.append(
                f"Incoming bridge (land this still as the end of prior morph): {bridge_in}"
            )
        if guide_role:
            block.append(f"Director guide role: {guide_role}")
        elif panels_per_row == 2:
            if col == 1:
                block.append(
                    "Preferred FLF role: start (left cell of this row pair)"
                )
            else:
                block.append(
                    "Preferred FLF role: end (right cell of this row pair)"
                )
        if transition:
            block.append(f"Continuity edge after panel: {transition}")
        if group is not None:
            block.append(f"Director chain group: {group}")
        if continuity:
            block.append(f"Director note: {continuity}")
        if bridge_out:
            block.append(f"Outgoing bridge → next panel: {bridge_out}")
        blocks.append("\n".join(block))
    return "\n\n".join(blocks)


def format_motion_spine_block(scene: dict[str, Any] | None) -> str:
    """Sheet-level motion spine guidance (never letter onto the page)."""
    spine = ""
    if isinstance(scene, dict):
        spine = str(scene.get("director_motion_spine") or "").strip()
    if not spine:
        return (
            "Motion spine: (none authored — keep each album row as an FLF "
            "start→end pair; hand off across rows on continue edges)."
        )
    return (
        "Scene motion spine (guidance only — do not letter onto the page; "
        "paint each row as an FLF start→end pair along this chain):\n"
        f"{spine}"
    )


def resolve_character_consistency(
    character_ids: list[str],
    story_characters: list[dict[str, Any]] | None = None,
) -> str:
    """Build character consistency block from research canon + story roster."""
    by_id = {
        _normalize_id(ch.get("id", "")): ch
        for ch in (story_characters or [])
        if isinstance(ch, dict) and ch.get("id")
    }
    lines: list[str] = []
    seen: set[str] = set()
    for raw_id in character_ids:
        cid = _normalize_id(raw_id)
        if not cid or cid in seen:
            continue
        seen.add(cid)
        if cid in CHARACTER_CONSISTENCY_CANON:
            lines.append(f"- {CHARACTER_CONSISTENCY_CANON[cid]}")
            continue
        ch = by_id.get(cid, {})
        name = (ch.get("name") or raw_id or cid).strip()
        appearance = (ch.get("appearance") or "consistent with prior panels").strip()
        lines.append(f"- {name}: {appearance}")
    if not lines:
        return "- Keep all named characters visually consistent with attached reference sheets."
    return "\n".join(lines)


def resolve_location_def(
    scene: dict[str, Any],
    locations: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Resolve plan location for a scene by location_id."""
    lid = (scene.get("location_id") or "").strip()
    if not lid or not locations:
        return None
    for loc in locations:
        if isinstance(loc, dict) and (loc.get("id") or "").strip() == lid:
            return loc
    return None


def resolve_environment_block(
    scene: dict[str, Any],
    locations: list[dict[str, Any]] | None = None,
) -> str:
    """Prefer plan location description; fall back to thin ENVIRONMENT_CANON details."""
    bits = [
        (scene.get("environment") or "").strip(),
        (scene.get("time_of_day") or "").strip(),
        (scene.get("lighting") or "").strip(),
        (scene.get("staging") or "").strip(),
    ]
    scene_text = ". ".join(bit for bit in bits if bit)
    loc = resolve_location_def(scene, locations)
    if loc:
        name = (loc.get("name") or loc.get("id") or "").strip()
        description = (loc.get("description") or name).strip()
        establishing = (loc.get("establishing_prompt") or "").strip()
        parts = [
            f"Location lock ({loc.get('id') or ''}): {name}.",
            description,
        ]
        if establishing:
            parts.append(establishing)
        if scene_text:
            parts.append(f"Scene-specific staging:\n{scene_text}")
        return "\n\n".join(p for p in parts if p)

    # Thin fallback when plan locations are absent (legacy Naila research canon).
    detail_lines = "\n".join(f"• {item}" for item in ENVIRONMENT_DETAILS)
    if scene_text:
        return f"{ENVIRONMENT_CANON}\n\nScene-specific staging:\n{scene_text}\n\n{detail_lines}"
    return f"{ENVIRONMENT_CANON}\n\n{detail_lines}"


def build_reference_roles_block(
    *,
    has_location: bool,
    has_previous_sheet: bool,
    character_ids: list[str],
    continuity_mode: str = "within_scene",
) -> str:
    """Label attached edit refs for the image model."""
    lines: list[str] = []
    idx = 1
    if has_location:
        lines.append(
            f"{idx}. LOCATION LOCK — match world geometry, landmarks, and lighting from this plate."
        )
        idx += 1
    if has_previous_sheet:
        if continuity_mode == "cross_scene":
            lines.append(
                f"{idx}. PREVIOUS STORYBOARD SHEET (cross-scene identity only) — carry wardrobe, "
                "character look, and world palette ONLY. Do NOT copy panel compositions, camera "
                "heights, or walk-away layouts from that sheet."
            )
        else:
            lines.append(
                f"{idx}. PREVIOUS STORYBOARD SHEET — continue visual continuity after its final "
                "panels (same world, character look, lighting language)."
            )
        idx += 1
    if character_ids:
        labels = ", ".join(character_ids)
        lines.append(
            f"{idx}. CHARACTER SHEETS ({labels}) — keep identity, wardrobe, and proportions locked."
        )
    if not lines:
        return "No reference images attached; invent a coherent world from the written brief."
    return "\n".join(lines)


def build_continuity_note(
    *,
    continuity_from_sheet_id: str | None,
    continuity_mode: str = "within_scene",
) -> str:
    if not continuity_from_sheet_id:
        return (
            "Continuity: this is the first storyboard sheet — establish the world cleanly from the "
            "location lock and character sheets. Vary camera height, angle, and subject scale across "
            "panels; never paint two near-identical walk-away / path compositions on the same page."
        )
    if continuity_mode == "cross_scene":
        return (
            f"Continuity mode: CROSS-SCENE after `{continuity_from_sheet_id}`. "
            "NEW SCENE — progress geography and story beats forward. Keep wardrobe and character "
            "identity, but invent a fresh camera grammar and panel mix. "
            "FORBIDDEN: remixing the previous sheet's panel layouts (same shoulder-carry walk-aways, "
            "same fence-path mid-wides, same elephant-horizon reveals in the same order). "
            "Each panel must read as a different lens choice (wide / medium / close / high / low / POV) "
            "matching the written shot list."
        )
    return (
        f"Continuity: continue immediately after previous sheet `{continuity_from_sheet_id}`. "
        "Preserve screen direction, wardrobe, and environment layout from that sheet's last panels, "
        "but still vary framing and camera height panel-to-panel."
    )


def continuity_mode_for(
    *,
    continuity_from_sheet_id: str | None,
    scene_id: str,
) -> str:
    """within_scene | cross_scene | none — drives prompt + whether to attach prev sheet PNG."""
    if not continuity_from_sheet_id:
        return "none"
    prev_scene = ""
    m = re.match(r"(scene_\d+)_sheet_", continuity_from_sheet_id or "")
    if m:
        prev_scene = m.group(1)
    if prev_scene and scene_id and prev_scene != scene_id:
        return "cross_scene"
    return "within_scene"


def build_storyboard_sheet_prompt(
    scene: dict[str, Any],
    shots: list[dict[str, Any]],
    *,
    sheet_number: int = 1,
    panels_per_sheet: int = 8,
    render_style: str,
    story_characters: list[dict[str, Any]] | None = None,
    global_shot_offset: int = 0,
    template: str | None = None,
    style_id: str | None = "reel_v2",
    locations: list[dict[str, Any]] | None = None,
    continuity_from_sheet_id: str | None = None,
    has_location_ref: bool = False,
    has_previous_sheet_ref: bool = False,
    continuity_mode: str | None = None,
) -> str:
    """Build a full production storyboard-sheet prompt for one sheet chunk."""
    from .reference_led_identity import normalize_provider_identity_language

    char_ids: list[str] = []
    for shot in shots:
        for cid in shot.get("characters_present", []):
            if cid and cid not in char_ids:
                char_ids.append(str(cid))

    mode = continuity_mode or continuity_mode_for(
        continuity_from_sheet_id=continuity_from_sheet_id,
        scene_id=str(scene.get("scene_id") or ""),
    )
    # Cross-scene: do not claim a previous-sheet image role unless it is actually attached.
    attach_prev = bool(has_previous_sheet_ref) and mode != "cross_scene"

    # ``global_shot_offset`` is ignored: each album page is numbered 1..N with
    # sheet-local N×2 grid coords (see build_panel_lines). Kept for call-site compat.
    _ = global_shot_offset
    start_index = 1
    template_text = template or _load_prompt_file("storyboard_sheet_template", style_id=style_id)
    prompt = template_text.format(
        sheet_number=f"{sheet_number:02d}",
        scene_title=scene.get("title", scene.get("scene_id", "Storyboard Sheet")),
        sheet_subtitle=scene.get("title", scene.get("scene_id", "Storyboard Sheet")),
        scene_id=scene.get("scene_id", ""),
        environment=scene.get("environment", "Forest sanctuary"),
        time_of_day=scene.get("time_of_day", "morning"),
        lighting=scene.get("lighting", "warm natural light"),
        staging=scene.get("staging", ""),
        panel_count=len(shots),
        panels_per_sheet=panels_per_sheet,
        grid_layout_instruction=build_grid_layout_instruction(len(shots), panels_per_sheet),
        character_consistency=resolve_character_consistency(char_ids, story_characters),
        environment_block=resolve_environment_block(scene, locations),
        reference_roles=build_reference_roles_block(
            has_location=has_location_ref,
            has_previous_sheet=attach_prev,
            character_ids=char_ids,
            continuity_mode=mode,
        ),
        continuity_note=build_continuity_note(
            continuity_from_sheet_id=continuity_from_sheet_id,
            continuity_mode=mode,
        ),
        shot_listing=build_shot_listing(shots, start_index=start_index),
        panel_lines=build_panel_lines(shots, start_index=start_index),
        motion_spine=format_motion_spine_block(scene),
        render_style=render_style,
    )
    return normalize_provider_identity_language(
        prompt,
        characters=story_characters,
        character_ids=char_ids,
        has_character_reference=bool(char_ids),
        preserve_safe_presentation=True,
    )
