"""Deterministic validators for spatial_plan_sN.md and spatial_qa_report.md.

Parses and validates:
  1. Spatial plans — the 2.5D coordinate contract authored by Agent 3a.
  2. Spatial QA reports — the post-sheet visual check authored by Agent 7.

No LLM calls. Pure parsing + assertions. Used by ``scripts/validate.py`` via
the ``spatial_plan`` and ``spatial_qa`` schemas.

Coordinate system (2.5D):
  X: 0–3840  image-space horizontal pixel position in the panorama
  Y: 0–2160  image-space vertical pixel position in the panorama
  Z: ≥0      world-space approximate meters from the anchor landmark
"""

from __future__ import annotations

import re
from typing import Any

from .validators import (
    ValidationResult,
    _kv_lines,
    parse_cid_list,
    parse_storyboard,
)

# Panorama bounds (matches config.STORYBOARD_SHEET_SIZE / BACKGROUND_IMAGE_SIZE).
PANO_W = 3840
PANO_H = 2160

# Teleport thresholds for the no-teleport check between continuous shots.
TELEPORT_X_THRESHOLD = 500  # px
TELEPORT_Z_THRESHOLD = 10  # meters

# Character facing vocabulary for per-shot character_facing field.
# A character may face toward/away from a landmark, toward/away from camera,
# or in a profile direction (screen left/right).
CHARACTER_FACING_TERMS = (
    "toward_camera", "away_from_camera",
    "profile_left", "profile_right",
    "toward_", "away_from_",  # prefix for toward_<landmark> / away_from_<landmark>
)

# Camera zoom vocabulary for per-shot camera_zoom field.
# Maps to the shot_size taxonomy but expressed as zoom level.
CAMERA_ZOOM_TERMS = (
    "extreme_wide", "wide", "full", "medium",
    "medium_closeup", "closeup", "extreme_closeup",
)

# Regex for parsing coordinate values: x=1920,y=2000,z=0
_COORD_RE = re.compile(r"[xyz]\s*=\s*(\d+(?:\.\d+)?)", re.I)

# Regex for parsing coordinate ranges: 1600-2400
_RANGE_FIELD_RE = re.compile(r"^(\d+)\s*-\s*(\d+)$")

# Regex for parsing panorama_xy: 1920, 2050
_XY_RE = re.compile(r"^(\d+)\s*,\s*(\d+)$")


def _parse_coord_tuple(text: str) -> tuple[float, float, float] | None:
    """Parse ``x=1920,y=2000,z=0`` -> (1920.0, 2000.0, 0.0)."""
    matches = _COORD_RE.findall(text or "")
    if len(matches) < 3:
        return None
    # Order is x, y, z as they appear in the string
    vals = [float(m) for m in matches]
    # Map by looking at the prefix letters
    coords: dict[str, float] = {}
    for m in re.finditer(r"([xyz])\s*=\s*(\d+(?:\.\d+)?)", text or "", re.I):
        coords[m.group(1).lower()] = float(m.group(2))
    if "x" not in coords or "y" not in coords or "z" not in coords:
        return None
    return coords["x"], coords["y"], coords["z"]


def _parse_range_field(text: str) -> tuple[float, float] | None:
    """Parse ``1600-2400`` -> (1600.0, 2400.0)."""
    m = _RANGE_FIELD_RE.match((text or "").strip())
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def _parse_xy(text: str) -> tuple[float, float] | None:
    """Parse ``[1920, 2050]`` or ``1920, 2050`` -> (1920.0, 2050.0)."""
    t = (text or "").strip()
    if t.startswith("[") and t.endswith("]"):
        t = t[1:-1].strip()
    m = _XY_RE.match(t)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def _parse_position_entry(text: str) -> dict[str, Any] | None:
    """Parse a single position entry like ``char_01=x=1920,y=2000,z=0``.

    Returns {cid: str, x: float, y: float, z: float} or None.
    """
    text = text.strip()
    if not text or "=" not in text:
        return None
    # Split on first = to get cid
    cid, _, rest = text.partition("=")
    cid = cid.strip()
    if not cid:
        return None
    coords = _parse_coord_tuple(rest)
    if coords is None:
        return None
    return {"cid": cid, "x": coords[0], "y": coords[1], "z": coords[2]}


def _parse_positions(text: str) -> list[dict[str, Any]]:
    """Parse ``char_01=x=1920,y=2000,z=0; char_05=x=3400,y=1700,z=40`` -> list."""
    entries = []
    for part in (text or "").split(";"):
        entry = _parse_position_entry(part)
        if entry:
            entries.append(entry)
    return entries


def _parse_on_screen_position(text: str) -> dict[str, Any] | None:
    """Parse ``char_05=x=3400,y=1700,z=40:foreground`` -> {cid, x, y, z, depth}."""
    text = text.strip()
    if not text:
        return None
    depth = ""
    if ":" in text:
        pos_part, _, depth = text.rpartition(":")
        depth = depth.strip()
    else:
        pos_part = text
    entry = _parse_position_entry(pos_part)
    if entry is None:
        return None
    entry["depth"] = depth
    return entry


def _parse_on_screen_positions(text: str) -> list[dict[str, Any]]:
    """Parse semicolon-separated on_screen_positions."""
    entries = []
    for part in (text or "").split(";"):
        entry = _parse_on_screen_position(part)
        if entry:
            entries.append(entry)
    return entries


def _parse_character_facing(text: str) -> dict[str, str]:
    """Parse ``char_01=toward_lamp_01; char_05=away_from_lamp_01`` -> {cid: direction}."""
    out: dict[str, str] = {}
    for part in (text or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        cid, _, direction = part.partition("=")
        out[cid.strip()] = direction.strip()
    return out


# ---------------------------------------------------------------------------
# Spatial plan parser
# ---------------------------------------------------------------------------

_LANDMARK_HEADER_RE = re.compile(r"^##\s+Landmark\s+(\S+)\s*$")
_ZONE_HEADER_RE = re.compile(r"^##\s+Zone\s+(\S+)\s*$")
_GEN_HEADER_RE = re.compile(r"^##\s+Generation\s+(\S+)\s*$")
_SHOT_HEADER_RE = re.compile(r"^###\s+Shot\s+(\d+)\s*$")


def parse_spatial_plan(md: str) -> dict[str, Any]:
    """Parse spatial_plan_sN.md -> structured dict.

    Returns:
        {
            scene_id, location_ref_id, panorama_resolution, world_axis,
            primary_anchor, landmarks: [str], zones: [str],
            landmark_defs: {id: {zone, panorama_xy, description}},
            zone_defs: {id: {relative_to, distance_from_anchor_m,
                             x_range, y_range, z_range, lighting}},
            generations: {gen_id: {location_reference, spatial_anchor,
                                   anchor_view, start_positions, end_positions,
                                   movement_constraints, shots: {shot_num: {...}}}}
        }
    """
    lines = md.splitlines()
    # Head = everything before the first "## " header
    head_end = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
    head_kv = _kv_lines("\n".join(lines[:head_end]))

    result: dict[str, Any] = {
        "scene_id": head_kv.get("scene_id", "").strip(),
        "location_ref_id": head_kv.get("location_ref_id", "").strip(),
        "panorama_resolution": head_kv.get("panorama_resolution", "").strip(),
        "world_axis": head_kv.get("world_axis", "").strip(),
        "primary_anchor": head_kv.get("primary_anchor", "").strip(),
        "landmarks": parse_cid_list(head_kv.get("landmarks", "")),
        "zones": parse_cid_list(head_kv.get("zones", "")),
        "landmark_defs": {},
        "zone_defs": {},
        "generations": {},
    }

    cur_section: str = ""  # "landmark", "zone", "generation", "shot"
    cur_id: str = ""
    cur_block: list[str] = []
    cur_gen_id: str = ""
    cur_shot_num: str = ""

    def _flush() -> None:
        nonlocal cur_section, cur_id, cur_block
        if not cur_section or not cur_id:
            cur_block = []
            return
        kv = _kv_lines("\n".join(cur_block))
        if cur_section == "landmark":
            xy = _parse_xy(kv.get("panorama_xy", ""))
            result["landmark_defs"][cur_id] = {
                "zone": kv.get("zone", "").strip(),
                "panorama_xy": xy,
                "description": kv.get("description", "").strip(),
            }
        elif cur_section == "zone":
            xr = _parse_range_field(kv.get("x_range", ""))
            yr = _parse_range_field(kv.get("y_range", ""))
            zr = _parse_range_field(kv.get("z_range", ""))
            try:
                dist = float(kv.get("distance_from_anchor_m", "0") or "0")
            except ValueError:
                dist = -1.0
            result["zone_defs"][cur_id] = {
                "relative_to": kv.get("relative_to", "").strip(),
                "distance_from_anchor_m": dist,
                "x_range": xr,
                "y_range": yr,
                "z_range": zr,
                "lighting": kv.get("lighting", "").strip(),
            }
        elif cur_section == "generation":
            result["generations"][cur_id] = {
                "location_reference": kv.get("location_reference", "").strip(),
                "spatial_anchor": kv.get("spatial_anchor", "").strip(),
                "anchor_view": kv.get("anchor_view", "").strip(),
                "generation_geography": kv.get("generation_geography", "").strip(),
                "start_positions": _parse_positions(kv.get("start_positions", "")),
                "end_positions": _parse_positions(kv.get("end_positions", "")),
                "movement_constraints": kv.get("movement_constraints", "").strip(),
                "shots": {},
            }
        elif cur_section == "shot":
            if cur_gen_id and cur_gen_id in result["generations"]:
                result["generations"][cur_gen_id]["shots"][cur_id] = {
                    "on_screen_positions": _parse_on_screen_positions(
                        kv.get("on_screen_positions", "")
                    ),
                    "camera_zone": kv.get("camera_zone", "").strip(),
                    "camera_facing": kv.get("camera_facing", "").strip(),
                    "camera_zoom": kv.get("camera_zoom", "").strip(),
                    "character_facing": _parse_character_facing(
                        kv.get("character_facing", "")
                    ),
                    "visible_landmarks": parse_cid_list(kv.get("visible_landmarks", "")),
                }
        cur_block = []

    for line in lines:
        lm = _LANDMARK_HEADER_RE.match(line)
        if lm:
            _flush()
            cur_section = "landmark"
            cur_id = lm.group(1)
            continue
        zm = _ZONE_HEADER_RE.match(line)
        if zm:
            _flush()
            cur_section = "zone"
            cur_id = zm.group(1)
            continue
        gm = _GEN_HEADER_RE.match(line)
        if gm:
            _flush()
            cur_section = "generation"
            cur_id = gm.group(1)
            cur_gen_id = cur_id
            continue
        sm = _SHOT_HEADER_RE.match(line)
        if sm:
            _flush()
            cur_section = "shot"
            cur_id = sm.group(1)
            continue
        if line.startswith("## "):
            _flush()
            cur_section = ""
            cur_id = ""
            continue
        if cur_section:
            cur_block.append(line)
    _flush()
    return result


# ---------------------------------------------------------------------------
# Spatial plan validator
# ---------------------------------------------------------------------------

def _coords_in_zone(
    x: float, y: float, z: float, zone_def: dict[str, Any]
) -> bool:
    """Check if coordinates fall within a zone's ranges."""
    for axis, val in (("x_range", x), ("y_range", y), ("z_range", z)):
        rng = zone_def.get(axis)
        if rng is None:
            continue
        lo, hi = rng
        if not (lo <= val <= hi):
            return False
    return True


def _find_char_zone(
    cid: str, positions: list[dict[str, Any]],
    zone_defs: dict[str, Any]
) -> str | None:
    """Find which zone a character's position falls into."""
    for pos in positions:
        if pos["cid"] != cid:
            continue
        for zid, zdef in zone_defs.items():
            if _coords_in_zone(pos["x"], pos["y"], pos["z"], zdef):
                return zid
    return None


def validate_spatial_plan(
    md: str,
    *,
    storyboard: dict[str, Any] | None = None,
    scenes: dict[str, Any] | None = None,
) -> ValidationResult:
    """Validate a spatial plan.

    Args:
        md: The spatial plan markdown text.
        storyboard: Parsed storyboard (from parse_storyboard) for cross-checking.
        scenes: Parsed scenes (from parse_scenes) for metadata cross-check.
    """
    res = ValidationResult()
    plan = parse_spatial_plan(md)

    sid = plan["scene_id"]
    if not sid:
        res.error("spatial plan: missing scene_id")

    # Cross-check scene_id against storyboard/scenes if provided
    if storyboard and storyboard.get("scene_id") and storyboard["scene_id"] != sid:
        res.error(
            f"spatial plan scene_id ({sid}) != storyboard scene_id "
            f"({storyboard['scene_id']})"
        )
    if scenes:
        scene_meta = next(
            (s for s in scenes.get("scenes", []) if s["scene_id"] == sid), None
        )
        if scene_meta is None:
            res.error(f"spatial plan scene_id {sid} not found in scenes.md")
        elif plan["location_ref_id"] and scene_meta.get("location_id"):
            if plan["location_ref_id"] != scene_meta["location_id"]:
                res.error(
                    f"spatial plan location_ref_id ({plan['location_ref_id']}) "
                    f"!= scenes.md location_id ({scene_meta['location_id']})"
                )

    # Check panorama_resolution
    pano = plan["panorama_resolution"]
    if not pano:
        res.error("spatial plan: missing panorama_resolution")
    elif pano not in (f"{PANO_W}x{PANO_H}", f"{PANO_W}×{PANO_H}"):
        res.error(
            f"spatial plan: panorama_resolution ({pano}) != expected {PANO_W}x{PANO_H}"
        )

    # Check landmarks
    landmark_ids = set(plan["landmark_defs"].keys())
    declared_landmarks = set(plan["landmarks"])
    if not landmark_ids:
        res.error("spatial plan: no landmark definitions found")
    if landmark_ids != declared_landmarks:
        missing = declared_landmarks - landmark_ids
        extra = landmark_ids - declared_landmarks
        if missing:
            res.error(f"spatial plan: landmarks listed but not defined: {sorted(missing)}")
        if extra:
            res.error(f"spatial plan: landmarks defined but not listed: {sorted(extra)}")

    # Check landmark panorama_xy bounds
    for lid, ldef in plan["landmark_defs"].items():
        xy = ldef.get("panorama_xy")
        if xy is None:
            res.error(f"landmark {lid}: missing panorama_xy")
        else:
            x, y = xy
            if not (0 <= x <= PANO_W and 0 <= y <= PANO_H):
                res.error(
                    f"landmark {lid}: panorama_xy ({x},{y}) outside "
                    f"bounds (0-{PANO_W}, 0-{PANO_H})"
                )

    # Check zones
    zone_ids = set(plan["zone_defs"].keys())
    declared_zones = set(plan["zones"])
    if not zone_ids:
        res.error("spatial plan: no zone definitions found")
    if zone_ids != declared_zones:
        missing = declared_zones - zone_ids
        extra = zone_ids - declared_zones
        if missing:
            res.error(f"spatial plan: zones listed but not defined: {sorted(missing)}")
        if extra:
            res.error(f"spatial plan: zones defined but not listed: {sorted(extra)}")

    # Check zone fields and bounds
    zone_x_ranges: list[tuple[str, float, float]] = []
    for zid, zdef in plan["zone_defs"].items():
        rel = zdef.get("relative_to", "")
        if not rel:
            res.error(f"zone {zid}: missing relative_to")
        elif rel not in landmark_ids:
            res.error(f"zone {zid}: relative_to '{rel}' is not a declared landmark")

        dist = zdef.get("distance_from_anchor_m", -1)
        if dist < 0:
            res.error(f"zone {zid}: distance_from_anchor_m must be >= 0 (got {dist})")

        for axis, axis_name, pano_max in (
            ("x_range", "x", PANO_W),
            ("y_range", "y", PANO_H),
            ("z_range", "z", None),
        ):
            rng = zdef.get(axis)
            if rng is None:
                res.error(f"zone {zid}: missing {axis}")
                continue
            lo, hi = rng
            if lo > hi:
                res.error(f"zone {zid}: {axis} lo ({lo}) > hi ({hi})")
            if pano_max is not None and (lo < 0 or hi > pano_max):
                res.error(
                    f"zone {zid}: {axis} ({lo}-{hi}) outside panorama bounds "
                    f"(0-{pano_max})"
                )
            if axis == "x_range":
                zone_x_ranges.append((zid, lo, hi))

    # Check non-overlapping X ranges between zones
    for i in range(len(zone_x_ranges)):
        for j in range(i + 1, len(zone_x_ranges)):
            zid_a, lo_a, hi_a = zone_x_ranges[i]
            zid_b, lo_b, hi_b = zone_x_ranges[j]
            if lo_a < hi_b and lo_b < hi_a:
                res.error(
                    f"zones {zid_a} (x:{lo_a}-{hi_a}) and {zid_b} (x:{lo_b}-{hi_b}) "
                    f"have overlapping X ranges"
                )

    # Check generations
    plan_gens = set(plan["generations"].keys())
    if not plan_gens:
        res.error("spatial plan: no generation blocks found")
        return res

    # Cross-check against storyboard generations
    sb_story_gens: set[str] = set()
    if storyboard:
        for g in storyboard.get("generations", []):
            if not g.get("is_bridge"):
                sb_story_gens.add(g["gen_id"])
        if sb_story_gens and plan_gens != sb_story_gens:
            missing = sb_story_gens - plan_gens
            extra = plan_gens - sb_story_gens
            if missing:
                res.error(
                    f"spatial plan: storyboard generations missing from plan: "
                    f"{sorted(missing)}"
                )
            if extra:
                res.error(
                    f"spatial plan: plan has generations not in storyboard: "
                    f"{sorted(extra)}"
                )

    # Validate each generation
    cast = set(storyboard.get("cast", [])) if storyboard else set()
    is_first_gen = True
    for gid, gdef in plan["generations"].items():
        glabel = f"spatial plan gen {gid}"

        # location_reference
        loc_ref = gdef.get("location_reference", "")
        if not loc_ref:
            res.error(f"{glabel}: missing location_reference (attach or omit)")
        elif loc_ref not in ("attach", "omit"):
            res.error(f"{glabel}: location_reference must be 'attach' or 'omit' (got {loc_ref!r})")
        elif is_first_gen and loc_ref != "attach":
            res.error(f"{glabel}: g1 must set location_reference: attach")
        is_first_gen = False

        # spatial_anchor (deprecated — warn only)
        anchor = gdef.get("spatial_anchor", "")
        if anchor and anchor != "required":
            res.warn(f"{glabel}: spatial_anchor is deprecated (got {anchor!r}); ignored")

        # generation_geography (preferred) or anchor_view (legacy alias)
        geography = gdef.get("generation_geography", "")
        anchor_view = gdef.get("anchor_view", "")
        if not geography and not anchor_view:
            res.error(f"{glabel}: missing generation_geography (or legacy anchor_view)")
        elif not geography and anchor_view:
            res.warn(f"{glabel}: uses deprecated anchor_view; rename to generation_geography")

        # start/end positions
        for phase in ("start_positions", "end_positions"):
            positions = gdef.get(phase, [])
            if not positions:
                res.error(f"{glabel}: missing {phase}")
                continue
            for pos in positions:
                cid = pos["cid"]
                if cast and cid not in cast:
                    res.error(f"{glabel} {phase}: character {cid} not in scene cast")
                # Check coordinates fall within a declared zone
                found_zone = False
                for zid, zdef in plan["zone_defs"].items():
                    if _coords_in_zone(pos["x"], pos["y"], pos["z"], zdef):
                        found_zone = True
                        break
                if not found_zone:
                    res.error(
                        f"{glabel} {phase}: {cid} at ({pos['x']},{pos['y']},{pos['z']}) "
                        f"does not fall within any declared zone"
                    )

        # Movement constraints — monotonic Z check
        constraints = gdef.get("movement_constraints", "")
        start = {p["cid"]: p for p in gdef.get("start_positions", [])}
        end = {p["cid"]: p for p in gdef.get("end_positions", [])}
        for cid in set(start.keys()) & set(end.keys()):
            s, e = start[cid], end[cid]
            cid_constraints = [
                c.strip() for c in constraints.split(";") if c.strip() and cid in c
            ]
            for c in cid_constraints:
                if "approach(" in c:
                    if e["z"] > s["z"]:
                        res.error(
                            f"{glabel}: {cid} has approach constraint but Z increases "
                            f"({s['z']} -> {e['z']})"
                        )
                elif "retreat(" in c:
                    if e["z"] < s["z"]:
                        res.error(
                            f"{glabel}: {cid} has retreat constraint but Z decreases "
                            f"({s['z']} -> {e['z']})"
                        )
                elif "fixed_at(" in c:
                    if s["x"] != e["x"] or s["y"] != e["y"] or s["z"] != e["z"]:
                        res.error(
                            f"{glabel}: {cid} has fixed_at constraint but position changes "
                            f"({s['x']},{s['y']},{s['z']} -> {e['x']},{e['y']},{e['z']})"
                        )

        # Shots
        plan_shots = set(gdef.get("shots", {}).keys())
        if not plan_shots:
            res.warn(f"{glabel}: no shot-level spatial blocks found")

        # Per-shot field validation (runs with or without storyboard)
        for shot_num, sp_shot in gdef.get("shots", {}).items():
            # Check character_facing vocabulary + landmark references
            facing = sp_shot.get("character_facing", {})
            for cid, direction in facing.items():
                if not direction:
                    res.error(
                        f"{glabel} shot {shot_num}: {cid} has empty "
                        f"character_facing direction"
                    )
                    continue
                valid = (
                    direction in CHARACTER_FACING_TERMS
                    or any(direction.startswith(p) for p in ("toward_", "away_from_"))
                )
                if not valid:
                    res.error(
                        f"{glabel} shot {shot_num}: {cid} character_facing "
                        f"'{direction}' is not a valid direction "
                        f"(use toward_<landmark>, away_from_<landmark>, "
                        f"toward_camera, away_from_camera, profile_left, "
                        f"profile_right)"
                    )
                # If toward_/away_from_ a landmark, check it exists
                for prefix in ("toward_", "away_from_"):
                    if direction.startswith(prefix):
                        ref_landmark = direction[len(prefix):]
                        if ref_landmark and ref_landmark not in landmark_ids:
                            res.error(
                                f"{glabel} shot {shot_num}: {cid} "
                                f"character_facing references unknown "
                                f"landmark '{ref_landmark}'"
                            )

            # Check camera_zoom vocabulary
            zoom = sp_shot.get("camera_zoom", "")
            if zoom and zoom not in CAMERA_ZOOM_TERMS:
                res.error(
                    f"{glabel} shot {shot_num}: camera_zoom '{zoom}' "
                    f"is not valid (use one of: "
                    f"{', '.join(CAMERA_ZOOM_TERMS)})"
                )

        # Cross-check shots against storyboard if available
        if storyboard:
            sb_gen = next(
                (g for g in storyboard.get("generations", []) if g["gen_id"] == gid),
                None,
            )
            if sb_gen:
                sb_shot_nums = {str(s["shot"]) for s in sb_gen.get("shots", [])}
                if sb_shot_nums and plan_shots != sb_shot_nums:
                    missing = sb_shot_nums - plan_shots
                    extra = plan_shots - sb_shot_nums
                    if missing:
                        res.error(
                            f"{glabel}: storyboard shots missing from spatial plan: "
                            f"{sorted(missing)}"
                        )
                    if extra:
                        res.error(
                            f"{glabel}: spatial plan has shots not in storyboard: "
                            f"{sorted(extra)}"
                        )

                # Check characters_present coverage
                for sb_shot in sb_gen.get("shots", []):
                    shot_num = str(sb_shot["shot"])
                    if shot_num not in gdef.get("shots", {}):
                        continue
                    sp_shot = gdef["shots"][shot_num]
                    sb_chars = set(sb_shot.get("characters_present", []))
                    sp_cids = {p["cid"] for p in sp_shot.get("on_screen_positions", [])}
                    missing_chars = sb_chars - sp_cids
                    if missing_chars:
                        res.error(
                            f"{glabel} shot {shot_num}: characters_present "
                            f"{sorted(missing_chars)} missing from on_screen_positions"
                        )

                    # Check on_screen_positions coordinates fall within zones
                    for pos in sp_shot.get("on_screen_positions", []):
                        found_zone = False
                        for zid, zdef in plan["zone_defs"].items():
                            if _coords_in_zone(pos["x"], pos["y"], pos["z"], zdef):
                                found_zone = True
                                break
                        if not found_zone:
                            res.error(
                                f"{glabel} shot {shot_num}: {pos['cid']} at "
                                f"({pos['x']},{pos['y']},{pos['z']}) does not fall "
                                f"within any declared zone"
                            )

                    # Warn if on-screen characters are missing from
                    # character_facing (only if some facings are declared)
                    sp_cids = {p["cid"] for p in sp_shot.get("on_screen_positions", [])}
                    facing = sp_shot.get("character_facing", {})
                    missing_facing = sp_cids - set(facing.keys())
                    if missing_facing and facing:
                        res.warn(
                            f"{glabel} shot {shot_num}: characters "
                            f"{sorted(missing_facing)} missing from "
                            f"character_facing"
                        )

                # No-teleport check between consecutive continuous shots
                sb_shots = sb_gen.get("shots", [])
                for i in range(1, len(sb_shots)):
                    prev_shot = sb_shots[i - 1]
                    cur_shot = sb_shots[i]
                    if cur_shot.get("transition") != "continuous":
                        continue
                    prev_num = str(prev_shot["shot"])
                    cur_num = str(cur_shot["shot"])
                    if prev_num not in gdef.get("shots", {}) or cur_num not in gdef.get("shots", {}):
                        continue
                    prev_positions = {
                        p["cid"]: p
                        for p in gdef["shots"][prev_num].get("on_screen_positions", [])
                    }
                    cur_positions = {
                        p["cid"]: p
                        for p in gdef["shots"][cur_num].get("on_screen_positions", [])
                    }
                    shared_cids = set(prev_positions.keys()) & set(cur_positions.keys())
                    for cid in shared_cids:
                        p_prev = prev_positions[cid]
                        p_cur = cur_positions[cid]
                        dx = abs(p_cur["x"] - p_prev["x"])
                        dz = abs(p_cur["z"] - p_prev["z"])
                        if dx > TELEPORT_X_THRESHOLD:
                            res.error(
                                f"{glabel}: {cid} teleports X by {dx:.0f}px between "
                                f"shot {prev_num} and shot {cur_num} (continuous, "
                                f"max {TELEPORT_X_THRESHOLD}px)"
                            )
                        if dz > TELEPORT_Z_THRESHOLD:
                            res.error(
                                f"{glabel}: {cid} teleports Z by {dz:.0f}m between "
                                f"shot {prev_num} and shot {cur_num} (continuous, "
                                f"max {TELEPORT_Z_THRESHOLD}m)"
                            )

                    # Character facing continuity: a character should not
                    # reverse facing direction between continuous shots
                    # (180° rule). Reversing is allowed on a cut.
                    prev_facing = gdef["shots"][prev_num].get("character_facing", {})
                    cur_facing = gdef["shots"][cur_num].get("character_facing", {})
                    for cid in set(prev_facing.keys()) & set(cur_facing.keys()):
                        pf, cf = prev_facing[cid], cur_facing[cid]
                        if not pf or not cf:
                            continue
                        # profile_left <-> profile_right is a reversal
                        if {pf, cf} == {"profile_left", "profile_right"}:
                            res.error(
                                f"{glabel}: {cid} reverses facing direction "
                                f"({pf} -> {cf}) between continuous shots "
                                f"{prev_num} and {cur_num} (180° rule violation)"
                            )
                        # toward_X <-> away_from_X is a reversal
                        for prefix in ("toward_", "away_from_"):
                            anti = "away_from_" if prefix == "toward_" else "toward_"
                            if pf.startswith(prefix) and cf.startswith(anti):
                                ref_p = pf[len(prefix):]
                                ref_c = cf[len(anti):]
                                if ref_p and ref_p == ref_c:
                                    res.error(
                                        f"{glabel}: {cid} reverses facing "
                                        f"direction ({pf} -> {cf}) between "
                                        f"continuous shots {prev_num} and "
                                        f"{cur_num} (180° rule violation)"
                                    )

                    # Camera zoom continuity: zoom should not jump more than
                    # 2 steps on the zoom ladder between continuous shots.
                    prev_zoom = gdef["shots"][prev_num].get("camera_zoom", "")
                    cur_zoom = gdef["shots"][cur_num].get("camera_zoom", "")
                    if prev_zoom and cur_zoom:
                        try:
                            pi = CAMERA_ZOOM_TERMS.index(prev_zoom)
                            ci = CAMERA_ZOOM_TERMS.index(cur_zoom)
                            if abs(ci - pi) > 2:
                                res.error(
                                    f"{glabel}: camera_zoom jumps {abs(ci - pi)} "
                                    f"steps ({prev_zoom} -> {cur_zoom}) between "
                                    f"continuous shots {prev_num} and {cur_num} "
                                    f"(max 2 steps for continuous)"
                                )
                        except ValueError:
                            pass  # invalid zoom values caught above

    return res


# ---------------------------------------------------------------------------
# Spatial QA report parser and validator
# ---------------------------------------------------------------------------

_QA_SHEET_HEADER_RE = re.compile(r"^##\s+(.+?)\s*$")
_QA_STATUS_RE = re.compile(r"^-\s*Status:\s*(PASS|WARN)\s*$", re.IGNORECASE)


def parse_spatial_qa_report(md: str) -> dict[str, Any]:
    """Parse spatial_qa_report.md -> {summary, sheets: [...]}.

    Each sheet is {id, status, expected, observed, recommendation}.
    """
    lines = md.splitlines()
    summary: dict[str, int] = {"Pass": 0, "Warn": 0}
    sheets: list[dict] = []
    cur_sheet: dict | None = None

    for line in lines:
        # Summary lines
        sm = re.match(r"^-\s*(Pass|Warn):\s*(\d+)\s*$", line, re.IGNORECASE)
        if sm:
            key = sm.group(1).capitalize()
            summary[key] = int(sm.group(2))
            continue

        # Sheet header
        sh = _QA_SHEET_HEADER_RE.match(line)
        if sh and not line.startswith("###") and sh.group(1).lower() != "summary":
            if cur_sheet is not None:
                sheets.append(cur_sheet)
            cur_sheet = {
                "id": sh.group(1).strip(),
                "status": "",
                "expected": "",
                "observed": "",
                "recommendation": "",
            }
            continue

        # Status line
        stm = _QA_STATUS_RE.match(line)
        if stm and cur_sheet is not None:
            cur_sheet["status"] = stm.group(1).upper()
            continue

        # Other fields
        if cur_sheet is not None and line.startswith("- "):
            field_line = line[2:].strip()
            if field_line.startswith("expected:"):
                cur_sheet["expected"] = field_line[len("expected:"):].strip()
            elif field_line.startswith("observed:"):
                cur_sheet["observed"] = field_line[len("observed:"):].strip()
            elif field_line.startswith("recommendation:"):
                cur_sheet["recommendation"] = field_line[len("recommendation:"):].strip()

    if cur_sheet is not None:
        sheets.append(cur_sheet)

    return {"summary": summary, "sheets": sheets}


def validate_spatial_qa_report(
    md: str,
    *,
    expected_sheets: list[str] | None = None,
) -> ValidationResult:
    """Validate a spatial QA report.

    Args:
        md: The QA report markdown text.
        expected_sheets: List of sheet IDs (e.g. ['s1/g1', 's1/g2', ...]) that
            must all be covered. If None, coverage is not checked.
    """
    res = ValidationResult()
    data = parse_spatial_qa_report(md)
    sheets = data["sheets"]
    summary = data["summary"]

    if not sheets:
        res.error("spatial QA report: no sheet entries parsed")
        return res

    pass_count = 0
    warn_count = 0
    report_ids: set[str] = set()

    for sheet in sheets:
        sid = sheet["id"]
        report_ids.add(sid)

        if not sheet["status"]:
            res.error(f"{sid}: missing 'Status:' line")
            continue

        if sheet["status"] == "PASS":
            pass_count += 1
        elif sheet["status"] == "WARN":
            warn_count += 1
            if not sheet["observed"]:
                res.error(f"{sid}: WARN but missing 'observed:' line")
            if not sheet["recommendation"]:
                res.error(f"{sid}: WARN but missing 'recommendation:' line")
            # Warnings go to res.warnings, not res.errors
            res.warn(f"{sid}: {sheet['observed'][:80]}")

    # Check coverage
    if expected_sheets:
        expected_set = set(expected_sheets)
        missing = expected_set - report_ids
        if missing:
            res.error(
                f"spatial QA report: {len(missing)} sheet(s) missing from report: "
                f"{sorted(missing)}"
            )

    # Check summary counts
    if any(summary.values()):
        if summary.get("Pass", 0) != pass_count:
            res.error(
                f"spatial QA summary Pass ({summary['Pass']}) != actual ({pass_count})"
            )
        if summary.get("Warn", 0) != warn_count:
            res.error(
                f"spatial QA summary Warn ({summary['Warn']}) != actual ({warn_count})"
            )

    return res
