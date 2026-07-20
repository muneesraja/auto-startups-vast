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


def build_grid_layout_instruction(panel_count: int, panels_per_sheet: int) -> str:
    """Require a fully painted photo-album board — no blank panel cells."""
    if panel_count >= panels_per_sheet:
        return (
            f"Arrange exactly {panel_count} cinematic stills in a 5 rows × 2 columns grid "
            "on a tall 9:16 portrait page (photo album / contact sheet). "
            "Each panel frame itself must be a landscape 16:9 cinematic still (wider than tall), "
            "not a portrait frame. "
            "Use only thin uniform black or white gutters as separators. "
            "Every grid cell must contain a fully rendered cinematic panel with painted scene content. "
            "No text, labels, headers, captions, or timeline on the page."
        )
    return (
        f"Arrange exactly {panel_count} cinematic stills across a 5 rows × 2 columns album grid "
        "on a tall 9:16 portrait page. "
        "Each panel frame itself must be a landscape 16:9 cinematic still (wider than tall), "
        "not a portrait frame. "
        "Column width drives panel width; keep each panel 16:9 and let leftover vertical space "
        "become the same thin gutter/background between rows — never fill with captions. "
        "CRITICAL: no blank, white, empty, or placeholder panel cells; no on-page typography."
    )


def build_shot_listing(shots: list[dict[str, Any]], *, start_index: int = 1) -> str:
    """Numbered shot list like Research/story-board/Compiled-storyboard-sheet-prompt.md."""
    lines: list[str] = []
    for offset, shot in enumerate(shots):
        index = start_index + offset
        camera = _shot_camera(shot)
        action = _shot_action(shot)
        lines.append(f"{index}. CAM: {camera} — {action}")
    return "\n".join(lines)


def build_panel_lines(shots: list[dict[str, Any]], *, start_index: int = 1) -> str:
    """Detailed per-panel blocks for crop alignment (Director-aware)."""
    blocks: list[str] = []
    for offset, shot in enumerate(shots):
        index = start_index + offset
        camera = _shot_camera(shot)
        action = _shot_action(shot)
        duration = shot.get("duration_seconds")
        # Editorial board beat only — never an LTX render duration.
        beat_label = f"board beat ~{duration}s" if duration else "board beat"
        row = (index - 1) // 2 + 1
        col = (index - 1) % 2 + 1
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
        group = shot.get("director_chain_group")
        block = [
            f"Panel {index} | grid row {row} col {col} | {beat_label}",
            f"CAM: {camera}",
            f"Visual: {visual}",
        ]
        motion = (shot.get("motion_intent") or "").strip()
        if motion:
            block.append(f"Motion: {motion}")
        if guide_role:
            block.append(f"Director guide role: {guide_role}")
        if transition:
            block.append(f"Continuity edge after panel: {transition}")
        if group is not None:
            block.append(f"Director chain group: {group}")
        if continuity:
            block.append(f"Director note: {continuity}")
        blocks.append("\n".join(block))
    return "\n\n".join(blocks)


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
        lines.append(
            f"{idx}. PREVIOUS STORYBOARD SHEET — continue visual continuity after its final panels "
            "(same world, character look, lighting language)."
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


def build_continuity_note(*, continuity_from_sheet_id: str | None) -> str:
    if not continuity_from_sheet_id:
        return (
            "Continuity: this is the first storyboard sheet — establish the world cleanly from the "
            "location lock and character sheets."
        )
    return (
        f"Continuity: continue immediately after previous sheet `{continuity_from_sheet_id}`. "
        "Preserve screen direction, wardrobe, and environment layout from that sheet's last panels."
    )


def build_storyboard_sheet_prompt(
    scene: dict[str, Any],
    shots: list[dict[str, Any]],
    *,
    sheet_number: int = 1,
    panels_per_sheet: int = 10,
    render_style: str,
    story_characters: list[dict[str, Any]] | None = None,
    global_shot_offset: int = 0,
    template: str | None = None,
    style_id: str | None = "reel_v2",
    locations: list[dict[str, Any]] | None = None,
    continuity_from_sheet_id: str | None = None,
    has_location_ref: bool = False,
    has_previous_sheet_ref: bool = False,
) -> str:
    """Build a full production storyboard-sheet prompt for one sheet chunk."""
    from .reference_led_identity import normalize_provider_identity_language

    char_ids: list[str] = []
    for shot in shots:
        for cid in shot.get("characters_present", []):
            if cid and cid not in char_ids:
                char_ids.append(str(cid))

    start_index = global_shot_offset + 1
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
            has_previous_sheet=has_previous_sheet_ref,
            character_ids=char_ids,
        ),
        continuity_note=build_continuity_note(
            continuity_from_sheet_id=continuity_from_sheet_id
        ),
        shot_listing=build_shot_listing(shots, start_index=start_index),
        panel_lines=build_panel_lines(shots, start_index=start_index),
        render_style=render_style,
    )
    return normalize_provider_identity_language(
        prompt,
        characters=story_characters,
        character_ids=char_ids,
        has_character_reference=bool(char_ids),
        preserve_safe_presentation=True,
    )
