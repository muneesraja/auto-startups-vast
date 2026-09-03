"""Deterministic spatial-continuity prompt materializer.

Reads a parsed spatial plan + storyboard and produces a natural-language
``SPATIAL CONTINUITY BIBLE`` block that is injected at the **top** of each
normal storyboard-sheet prompt file before the paid image-generation call.

No LLM calls. No image/video API calls. Pure text generation.

The block is idempotent: re-running on the same prompt replaces the
existing block rather than duplicating it.
"""

from __future__ import annotations

import re
from typing import Any

from .spatial_validator import (
    CAMERA_ZOOM_TERMS,
    PANO_W,
    parse_spatial_plan,
)
from .validators import parse_storyboard

# Stable delimiters for the generated block.
LOCK_START = "SPATIAL CONTINUITY BIBLE — generated; do not manually edit"
LOCK_END = "END SPATIAL CONTINUITY BIBLE"

# Regex to find an existing generated block (with optional surrounding blank lines).
# Supports both the old "LOCK" and new "BIBLE" markers for backward compatibility.
_LOCK_RE = re.compile(
    r"\n*(?:SPATIAL CONTINUITY (?:BIBLE|LOCK) — generated; do not manually edit)\n.*?\nEND SPATIAL CONTINUITY (?:BIBLE|LOCK)\n*",
    re.DOTALL,
)

# Zoom vocabulary mapped to camera-geometry prose (position + framing only).
# Facing/direction is added separately by _render_camera, so these strings
# should not repeat "looking toward" or "camera placed in".
_ZOOM_FRAMING = {
    "extreme_wide": (
        "well back in the scene, low or eye-level, "
        "extreme wide establishing view"
    ),
    "wide": (
        "back in the scene, eye-level, "
        "wide cinematic view"
    ),
    "full": (
        "at full-body distance, eye-level, "
        "showing the entire figure from head to toe"
    ),
    "medium": (
        "at chest to shoulder height, three-quarter view, "
        "50mm-like perspective, waist-up framing"
    ),
    "medium_closeup": (
        "at chest height, slightly below eye level, "
        "three-quarter view, chest-up framing"
    ),
    "closeup": (
        "close to the subject at eye level, "
        "tight framing on the face or hands"
    ),
    "extreme_closeup": (
        "very close to the subject, "
        "extreme tight framing on a single detail"
    ),
}

# Facing vocabulary mapped to natural-language body direction.
_FACING_PROSE = {
    "toward_camera": "facing toward camera",
    "away_from_camera": "facing away from camera",
    "profile_left": "in left-facing profile, looking screen-left",
    "profile_right": "in right-facing profile, looking screen-right",
}


def _horizontal_placement(x: float) -> str:
    """Convert panorama X coordinate to left/centre/right."""
    third = PANO_W / 3
    if x < third:
        return "left"
    if x < third * 2:
        return "centre"
    return "right"


def _depth_from_z(z: float, declared_depth: str = "") -> str:
    """Convert Z distance and/or declared depth suffix to depth prose."""
    if declared_depth:
        return declared_depth
    if z <= 2:
        return "foreground"
    if z <= 15:
        return "midground"
    return "background"


def _render_facing(direction: str, landmark_descs: dict[str, str]) -> str:
    """Render a character_facing value into natural-language prose."""
    if direction in _FACING_PROSE:
        return _FACING_PROSE[direction]
    for prefix, verb in (("toward_", "facing toward"), ("away_from_", "facing away from")):
        if direction.startswith(prefix):
            ref = direction[len(prefix):]
            desc = landmark_descs.get(ref, ref.replace("_", " "))
            return f"{verb} {desc}"
    return direction.replace("_", " ")


def _render_camera(camera_zone: str, camera_facing: str, camera_zoom: str,
                   zone_defs: dict[str, Any], landmark_descs: dict[str, str]) -> str:
    """Render camera placement, facing, and zoom into concrete geometry prose."""
    parts: list[str] = []

    # Camera zone
    zone_name = camera_zone.replace("_", " ") if camera_zone else "the scene"
    parts.append(f"camera placed in {zone_name}")

    # Camera facing
    facing_prose = camera_facing.replace("_", " ")
    for prefix, verb in (("toward_", "looking toward"), ("away_from_", "looking away from")):
        if camera_facing.startswith(prefix):
            ref = camera_facing[len(prefix):]
            desc = landmark_descs.get(ref, ref.replace("_", " "))
            facing_prose = f"{verb} {desc}"
            break
    parts.append(facing_prose)

    # Zoom / framing (position + lens/framing; no repeated facing)
    if camera_zoom in _ZOOM_FRAMING:
        parts.append(_ZOOM_FRAMING[camera_zoom])
    elif camera_zoom:
        parts.append(f"{camera_zoom.replace('_', ' ')} framing")

    return ", ".join(parts) + "."


def _render_landmarks(visible: list[str], landmark_defs: dict[str, Any]) -> str:
    """Render the landmark visibility rule for a shot."""
    if not visible:
        return "No specific landmarks are required in this panel; " \
               "landmarks from wider shots may be intentionally out of frame."
    parts: list[str] = []
    for lid in visible:
        ldef = landmark_defs.get(lid, {})
        desc = ldef.get("description", lid.replace("_", " "))
        parts.append(desc)
    return "Must show: " + "; ".join(parts) + "."


def _render_positions(positions: list[dict[str, Any]],
                      zone_defs: dict[str, Any],
                      facing: dict[str, str],
                      landmark_descs: dict[str, str]) -> str:
    """Render on-screen positions and facing for one shot (concise)."""
    lines: list[str] = []
    for pos in positions:
        cid = pos["cid"]
        placement = _horizontal_placement(pos["x"])
        depth = _depth_from_z(pos["z"], pos.get("depth", ""))
        # Find zone name
        zone_name = ""
        for zid, zdef in zone_defs.items():
            x_lo, x_hi = zdef.get("x_range", (0, 0))
            y_lo, y_hi = zdef.get("y_range", (0, 0))
            z_lo, z_hi = zdef.get("z_range", (0, 0))
            if x_lo <= pos["x"] <= x_hi and y_lo <= pos["y"] <= y_hi and z_lo <= pos["z"] <= z_hi:
                zone_name = zid.replace("_", " ")
                break
        if not zone_name:
            zone_name = "the scene"

        facing_dir = facing.get(cid, "")
        facing_prose = _render_facing(facing_dir, landmark_descs) if facing_dir else ""

        line = f"{cid} at {placement} {depth} of {zone_name}"
        if facing_prose:
            line += f", {facing_prose}"
        line += "."
        lines.append(line)
    return "\n".join(lines)


def _render_movement(movement_constraints: str) -> str:
    """Render movement constraints as a continuity bullet."""
    if not movement_constraints:
        return ""
    parts: list[str] = []
    for c in movement_constraints.split(";"):
        c = c.strip()
        if not c:
            continue
        actor = ""
        action = c
        if "=" in c:
            actor, action = c.split("=", 1)
            actor = actor.strip() + " "
        if "fixed_at(" in action:
            ref = re.search(r"fixed_at\(([^)]+)\)", action)
            ref_name = ref.group(1).replace("_", " ") if ref else "position"
            parts.append(f"{actor}remains fixed at {ref_name} throughout the generation")
        elif "approach(" in action:
            ref = re.search(r"approach\(([^)]+)\)", action)
            ref_name = ref.group(1).replace("_", " ") if ref else "the target"
            parts.append(f"{actor}moves toward {ref_name}, getting closer")
        elif "retreat(" in action:
            ref = re.search(r"retreat\(([^)]+)\)", action)
            ref_name = ref.group(1).replace("_", " ") if ref else "the target"
            parts.append(f"{actor}retreats from {ref_name}, getting farther")
        elif "never_enter(" in action:
            ref = re.search(r"never_enter\(([^)]+)\)", action)
            ref_name = ref.group(1).replace("_", " ") if ref else "the zone"
            parts.append(f"{actor}never enters {ref_name}")
        else:
            parts.append(c.replace("_", " "))
    if not parts:
        return ""
    return "; ".join(parts)


def _find_zone_name(x: float, y: float, z: float, zone_defs: dict[str, Any]) -> str:
    """Return the zone name for a given coordinate, or 'the scene'."""
    for zid, zdef in zone_defs.items():
        x_lo, x_hi = zdef.get("x_range", (0, 0))
        y_lo, y_hi = zdef.get("y_range", (0, 0))
        z_lo, z_hi = zdef.get("z_range", (0, 0))
        if x_lo <= x <= x_hi and y_lo <= y <= y_hi and z_lo <= z <= z_hi:
            return zid.replace("_", " ")
    return "the scene"


def _render_character_positions(
    positions: list[dict[str, Any]],
    zone_defs: dict[str, Any],
) -> str:
    """Render concise start/end position lines for continuity rules."""
    lines: list[str] = []
    for pos in positions:
        cid = pos["cid"]
        x, y, z = pos["x"], pos["y"], pos["z"]
        placement = _horizontal_placement(x)
        depth = _depth_from_z(z, pos.get("depth", ""))
        zone_name = _find_zone_name(x, y, z, zone_defs)
        lines.append(f"{cid} begins/ends at {placement} {depth} of {zone_name}.")
    return "\n".join(lines)


def build_spatial_block(
    plan: dict[str, Any],
    storyboard: dict[str, Any],
    gen_id: str,
) -> str:
    """Build the spatial continuity bible text for one generation.

    Args:
        plan: Parsed spatial plan (from parse_spatial_plan).
        storyboard: Parsed storyboard (from parse_storyboard).
        gen_id: Generation ID (e.g. "g1", "g2").

    Returns:
        The full generated block text (including start/end markers).

    Raises:
        ValueError: If the generation is not found in the plan or storyboard,
            or if the plan has no shots for this generation.
    """
    gdef = plan["generations"].get(gen_id)
    if not gdef:
        raise ValueError(f"generation {gen_id} not found in spatial plan")
    if not gdef.get("shots"):
        raise ValueError(f"generation {gen_id} has no shot-level spatial blocks")

    # Find the storyboard generation
    sb_gen = next(
        (g for g in storyboard.get("generations", []) if g["gen_id"] == gen_id),
        None,
    )
    if not sb_gen:
        raise ValueError(f"generation {gen_id} not found in storyboard")

    landmark_defs = plan["landmark_defs"]
    zone_defs = plan["zone_defs"]
    landmark_descs = {lid: ldef.get("description", lid.replace("_", " "))
                      for lid, ldef in landmark_defs.items()}

    # Generation geography
    geography = gdef.get("anchor_view", "")
    if not geography:
        geography = gdef.get("generation_geography", "")
    if not geography:
        geography = f"Wide staging of {gen_id}."

    # Collect lighting from all zones for the environment bible
    zone_lightings: set[str] = set()
    for zdef in zone_defs.values():
        lighting = zdef.get("lighting", "")
        if lighting:
            zone_lightings.add(lighting)

    lines: list[str] = [LOCK_START, ""]

    # ------------------------------------------------------------------
    # ENVIRONMENT BIBLE
    # ------------------------------------------------------------------
    lines.append("## ENVIRONMENT BIBLE")
    lines.append("")
    lines.append(f"- Setting: {geography}")
    if zone_lightings:
        # List all distinct zone lightings (usually one per scene)
        lines.append(f"- Lighting: {'; '.join(sorted(zone_lightings))}")
    if landmark_descs:
        lines.append("- Landmarks:")
        for lid, desc in sorted(landmark_descs.items()):
            lines.append(f"  - {desc}")
    if plan.get("world_axis"):
        lines.append(f"- World axis: {plan['world_axis']}")
    lines.append("")

    # ------------------------------------------------------------------
    # CONTINUITY RULES
    # ------------------------------------------------------------------
    lines.append("## CONTINUITY RULES")
    lines.append("")

    movement = _render_movement(gdef.get("movement_constraints", ""))
    if movement:
        lines.append(f"- {movement}")

    start_positions = gdef.get("start_positions", [])
    end_positions = gdef.get("end_positions", [])
    if start_positions:
        lines.append("- Character start positions:")
        pos_text = _render_character_positions(start_positions, zone_defs)
        for line in pos_text.split("\n"):
            lines.append(f"  - {line}")
    if end_positions:
        lines.append("- Character end positions:")
        pos_text = _render_character_positions(end_positions, zone_defs)
        for line in pos_text.split("\n"):
            lines.append(f"  - {line}")

    # Landmark visibility rules (per panel range) are listed here as rules
    for sb_shot in sb_gen.get("shots", []):
        shot_num = str(sb_shot["shot"])
        panels = sb_shot.get("panels", [])
        if not panels:
            continue
        sp_shot = gdef["shots"].get(shot_num)
        if not sp_shot:
            continue

        if len(panels) == 1:
            panel_label = f"Panel {panels[0]}"
        else:
            panel_label = f"Panels {panels[0]}–{panels[-1]}"

        visible = sp_shot.get("visible_landmarks", [])
        lines.append(f"- {panel_label}: {_render_landmarks(visible, landmark_defs)}")

    lines.append("")

    # ------------------------------------------------------------------
    # PANEL STAGING
    # ------------------------------------------------------------------
    lines.append("## PANEL STAGING")
    lines.append("")

    for sb_shot in sb_gen.get("shots", []):
        shot_num = str(sb_shot["shot"])
        panels = sb_shot.get("panels", [])
        if not panels:
            continue

        sp_shot = gdef["shots"].get(shot_num)
        if not sp_shot:
            # Shot not in spatial plan — skip (validator catches this)
            continue

        if len(panels) == 1:
            panel_label = f"Panel {panels[0]}"
        else:
            panel_label = f"Panels {panels[0]}–{panels[-1]}"

        transition = sb_shot.get("transition", "")
        shot_label = f"### {panel_label} — Shot {shot_num}"
        if transition and transition != "continuous":
            shot_label += f" ({transition.replace('_', ' ')} cut)"
        lines.append(shot_label)
        lines.append("")

        # Camera geometry
        camera_text = _render_camera(
            sp_shot.get("camera_zone", ""),
            sp_shot.get("camera_facing", ""),
            sp_shot.get("camera_zoom", ""),
            zone_defs,
            landmark_descs,
        )
        lines.append(f"- Camera: {camera_text}")

        # Subject staging
        positions = sp_shot.get("on_screen_positions", [])
        facing = sp_shot.get("character_facing", {})
        if positions:
            pos_text = _render_positions(positions, zone_defs, facing, landmark_descs)
            for pos_line in pos_text.split("\n"):
                lines.append(f"- Subject staging: {pos_line}")

        lines.append("")

    lines.append(LOCK_END)
    return "\n".join(lines)


def inject_spatial_block(prompt_text: str, block_text: str) -> str:
    """Inject or replace the spatial continuity bible in a prompt text.

    Removes any existing generated block, then inserts the new one at the
    **top** of the prompt, immediately after any ``ref_images:`` line. This
    makes the spatial contract the foundation for the creative sections.

    Args:
        prompt_text: The original prompt text (may or may not have a block).
        block_text: The generated block text (including start/end markers).

    Returns:
        The prompt text with the block injected at the top.
    """
    # Remove existing block (old or new marker)
    cleaned = _LOCK_RE.sub("\n\n", prompt_text).strip()

    # If the prompt begins with a ref_images: line, keep it at the very top
    lines = cleaned.splitlines()
    if lines and lines[0].strip().lower().startswith("ref_images:"):
        header = lines[0]
        body = "\n".join(lines[1:]).strip()
        if body:
            return f"{header}\n\n{block_text}\n\n{body}\n"
        return f"{header}\n\n{block_text}\n"

    return f"{block_text}\n\n{cleaned}\n"


def materialize_sheet_prompt(
    prompt_text: str,
    plan: dict[str, Any],
    storyboard: dict[str, Any],
    gen_id: str,
) -> str:
    """Materialize the spatial bible into a sheet prompt.

    Convenience wrapper: build the block and inject it at the top.

    Args:
        prompt_text: The authored sheet prompt text.
        plan: Parsed spatial plan.
        storyboard: Parsed storyboard.
        gen_id: Generation ID.

    Returns:
        The prompt text with the spatial bible injected at the top.
    """
    block = build_spatial_block(plan, storyboard, gen_id)
    return inject_spatial_block(prompt_text, block)


def has_spatial_block(prompt_text: str) -> bool:
    """Check if a prompt text already contains a generated spatial block."""
    return bool(_LOCK_RE.search(prompt_text))


def validate_materialized_prompt(
    prompt_text: str,
    plan: dict[str, Any],
    storyboard: dict[str, Any],
    gen_id: str,
) -> list[str]:
    """Validate that a materialized prompt has correct spatial coverage.

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []

    if not has_spatial_block(prompt_text):
        errors.append(f"missing spatial continuity bible for {gen_id}")
        return errors

    # Extract the block content (new or old marker)
    m = re.search(
        r"(?:SPATIAL CONTINUITY (?:BIBLE|LOCK) — generated; do not manually edit)\n(.*?)\nEND SPATIAL CONTINUITY (?:BIBLE|LOCK)",
        prompt_text,
        re.DOTALL,
    )
    if not m:
        errors.append(f"malformed spatial continuity bible for {gen_id}")
        return errors

    block = m.group(1)

    gdef = plan["generations"].get(gen_id)
    if not gdef:
        errors.append(f"generation {gen_id} not in spatial plan")
        return errors

    sb_gen = next(
        (g for g in storyboard.get("generations", []) if g["gen_id"] == gen_id),
        None,
    )
    if not sb_gen:
        errors.append(f"generation {gen_id} not in storyboard")
        return errors

    # Check required sections
    if "## ENVIRONMENT BIBLE" not in block:
        errors.append(f"spatial bible for {gen_id} missing ENVIRONMENT BIBLE")
    if "## CONTINUITY RULES" not in block:
        errors.append(f"spatial bible for {gen_id} missing CONTINUITY RULES")
    if "## PANEL STAGING" not in block:
        errors.append(f"spatial bible for {gen_id} missing PANEL STAGING")

    # Check each storyboard shot with panels is covered
    for sb_shot in sb_gen.get("shots", []):
        shot_num = str(sb_shot["shot"])
        panels = sb_shot.get("panels", [])
        if not panels:
            continue
        sp_shot = gdef["shots"].get(shot_num)
        if not sp_shot:
            continue  # validator catches missing shots

        # Check that the panel range is mentioned
        if len(panels) == 1:
            panel_ref = f"Panel {panels[0]}"
        else:
            panel_ref = f"Panels {panels[0]}"

        if panel_ref not in block:
            errors.append(
                f"spatial bible for {gen_id} missing panel coverage for "
                f"shot {shot_num} ({panel_ref})"
            )

        # Check camera is mentioned
        camera_zone = sp_shot.get("camera_zone", "")
        if camera_zone and camera_zone.replace("_", " ") not in block.lower():
            errors.append(
                f"spatial bible for {gen_id} shot {shot_num} missing camera zone"
            )

    return errors
