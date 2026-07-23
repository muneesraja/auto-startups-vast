"""Storyboard assistant director: vision JSON → segment/clip plan → I2V/FLF2V."""
from __future__ import annotations

import json
import math
import os
import re
from typing import Any

from tools.ltx_render_params import resolve_clip_render_params
from tools.workflow_builder import snap_duration_seconds, snap_ltx_duration

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Legacy aliases kept for callers/tests
_MODE_I2V = "i2v"
_MODE_FLF = "flf2v"


def load_flf_planner_system_prompt() -> str:
    path = os.path.join(_SKILL_DIR, "prompts", "reel_v2", "flf_storyboard_planner.md")
    with open(path, encoding="utf-8") as f:
        return f.read()


def panel_ids_in_order(scene: dict) -> list[str]:
    return [sh.get("shot_id") for sh in scene.get("shots") or [] if sh.get("shot_id")]


def panel_cast_lookup(scene: dict) -> dict[str, frozenset[str]]:
    out: dict[str, frozenset[str]] = {}
    for sh in scene.get("shots") or []:
        sid = sh.get("shot_id")
        if not sid:
            continue
        out[sid] = frozenset(c for c in (sh.get("characters_present") or []) if c)
    return out


def _scene_number_from_id(scene_id: str) -> str:
    m = re.search(r"(\d+[a-z]?)$", scene_id or "", re.IGNORECASE)
    return m.group(1) if m else ""


def extract_scene_paper_block(scene_paper: str, scene_id: str) -> str:
    """Return the markdown block for one scene from scene_paper.md."""
    from scripts.nodes.sheet_map import _scene_blocks

    want = _scene_number_from_id(scene_id).lstrip("0") or _scene_number_from_id(scene_id)
    for number, title, body in _scene_blocks(scene_paper or ""):
        num = str(number).lstrip("0") or str(number)
        if num == want or str(number) == _scene_number_from_id(scene_id):
            header = f"## Scene {number} — {title}".rstrip(" —")
            return f"{header}\n{body}".strip()
    return ""


def scene_paper_duration_budget(scene_paper: str, scene_id: str) -> int | None:
    from scripts.nodes.sheet_map import _DURATION_RE, _scene_blocks

    want = _scene_number_from_id(scene_id).lstrip("0") or _scene_number_from_id(scene_id)
    for number, _title, body in _scene_blocks(scene_paper or ""):
        num = str(number).lstrip("0") or str(number)
        if num == want or str(number) == _scene_number_from_id(scene_id):
            m = _DURATION_RE.search(body)
            return int(m.group(1)) if m else None
    return None


def scene_paper_budgets(scene_paper: str) -> dict[str, int]:
    """Map scene_01 → duration from scene_paper.md."""
    from scripts.nodes.sheet_map import _DURATION_RE, _scene_blocks

    out: dict[str, int] = {}
    for number, _title, body in _scene_blocks(scene_paper or ""):
        m = _DURATION_RE.search(body)
        if not m:
            continue
        try:
            n = int(str(number).lstrip("0") or "0")
        except ValueError:
            continue
        out[f"scene_{n:02d}"] = int(m.group(1))
    return out


def apply_scene_paper_budgets_to_plan(plan: dict, scene_paper: str) -> dict:
    """Overwrite scene duration_budget_seconds from authoritative scene paper."""
    budgets = scene_paper_budgets(scene_paper)
    if not budgets:
        return plan
    for scene in plan.get("scenes") or []:
        sid = scene.get("scene_id")
        if sid in budgets:
            scene["duration_budget_seconds"] = budgets[sid]
    return plan


def resolve_scene_duration_budget(
    scene: dict,
    *,
    scene_paper: str | None = None,
    default: int = 24,
) -> int:
    if scene_paper:
        paper_budget = scene_paper_duration_budget(scene_paper, scene.get("scene_id") or "")
        if paper_budget and paper_budget > 0:
            return paper_budget
    raw = scene.get("duration_budget_seconds")
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return value if value > 0 else default


def panel_grid_map(
    panel_ids: list[str],
    *,
    columns: int = 2,
) -> list[dict[str, int | str]]:
    """Map ordered panels to 1-based row/col on a row-major album grid."""
    cols = max(1, int(columns))
    out: list[dict[str, int | str]] = []
    for i, pid in enumerate(panel_ids):
        out.append(
            {
                "panel_id": pid,
                "index": i + 1,
                "row": (i // cols) + 1,
                "col": (i % cols) + 1,
            }
        )
    return out


def same_row_pairs(
    panel_ids: list[str],
    *,
    columns: int = 2,
) -> list[tuple[str, str]]:
    """Return left→right pairs that share a row on the album grid."""
    pairs: list[tuple[str, str]] = []
    grid = panel_grid_map(panel_ids, columns=columns)
    by_row: dict[int, list[str]] = {}
    for cell in grid:
        by_row.setdefault(int(cell["row"]), []).append(str(cell["panel_id"]))
    for _row, ids in sorted(by_row.items()):
        for a, b in zip(ids, ids[1:]):
            pairs.append((a, b))
    return pairs


def _format_motion_spine(scene: dict) -> str:
    spine = str(scene.get("director_motion_spine") or "").strip()
    if spine:
        return spine
    return "(none authored — invent Prompt Relay from panel Visual/Action and sheet)"


def _format_panel_bridges(scene: dict) -> str:
    lines: list[str] = []
    for shot in scene.get("shots") or []:
        if not isinstance(shot, dict):
            continue
        sid = str(shot.get("shot_id") or "").strip() or "?"
        bridge = str(shot.get("director_bridge_to_next") or "").strip()
        motion = str(shot.get("motion_intent") or "").strip()
        if not bridge and not motion:
            continue
        bits = [f"  - {sid}:"]
        if motion:
            bits.append(f"motion_intent={motion}")
        if bridge:
            bits.append(f"bridge_to_next={bridge}")
        lines.append(" ".join(bits))
    return "\n".join(lines) if lines else "  (none authored)"


def build_flf_planner_user_text(
    scene: dict,
    panel_ids: list[str],
    *,
    scene_paper_block: str = "",
    duration_budget_seconds: int | None = None,
    still_paths: dict[str, str] | None = None,
    grid_columns: int = 2,
) -> str:
    del duration_budget_seconds  # AD chooses durations; not driven by scene paper
    beat_lines = []
    grid = panel_grid_map(panel_ids, columns=grid_columns)
    grid_by_id = {str(c["panel_id"]): c for c in grid}
    shot_by_id = {
        str(s.get("shot_id")): s
        for s in (scene.get("shots") or [])
        if isinstance(s, dict) and s.get("shot_id")
    }
    ordered_shots = [shot_by_id[pid] for pid in panel_ids if pid in shot_by_id]
    has_director_meta = any(
        s.get("director_chain_group") is not None
        or s.get("director_transition_after")
        or s.get("director_guide_role")
        or s.get("director_bridge_to_next")
        or s.get("director_continuity_note")
        for s in ordered_shots
    ) or bool(str(scene.get("director_motion_spine") or "").strip())
    for i, sid in enumerate(panel_ids, start=1):
        shot = shot_by_id.get(sid) or {}
        still = (still_paths or {}).get(sid) or ""
        cell = grid_by_id.get(sid) or {}
        loc = (
            f"row {cell.get('row')} col {cell.get('col')}"
            if cell
            else f"index {i}"
        )
        dir_bits = []
        if shot.get("director_chain_group") is not None:
            dir_bits.append(f"group={shot.get('director_chain_group')}")
        if shot.get("director_guide_role"):
            dir_bits.append(f"guide={shot.get('director_guide_role')}")
        if shot.get("director_transition_after"):
            dir_bits.append(f"after={shot.get('director_transition_after')}")
        if shot.get("director_continuity_note"):
            dir_bits.append(f"note={shot.get('director_continuity_note')}")
        if shot.get("director_bridge_to_next"):
            dir_bits.append(f"bridge={shot.get('director_bridge_to_next')}")
        spatial = []
        for key in (
            "subject_position",
            "facing_direction",
            "eyeline",
            "background_region",
            "pace",
            "audio_intent",
            "frame_strategy",
        ):
            val = shot.get(key)
            if val:
                spatial.append(f"{key}={val}")
        # Cast delta vs previous panel
        cast_delta = ""
        if i > 1:
            prev = shot_by_id.get(panel_ids[i - 2]) or {}
            prev_cast = set(prev.get("characters_present") or [])
            cur_cast = set(shot.get("characters_present") or [])
            added = sorted(cur_cast - prev_cast)
            removed = sorted(prev_cast - cur_cast)
            if added or removed:
                cast_delta = f" | cast_delta=+{added}/-{removed}"
        # Cross-row adjacency hint
        cross_row = ""
        if cell and i < len(panel_ids):
            nxt_cell = grid_by_id.get(panel_ids[i]) or {}
            if cell.get("row") != nxt_cell.get("row") and nxt_cell:
                cross_row = " | cross_row_next=true"
        beat_lines.append(
            f"  {i}. [{loc}] {sid}: chars={list(shot.get('characters_present') or [])} | "
            f"{shot.get('description', '')} | motion={shot.get('motion_intent', '')} | "
            f"camera={shot.get('camera_intent', '')}"
            + (f" | director[{', '.join(dir_bits)}]" if dir_bits else "")
            + (f" | spatial[{', '.join(spatial)}]" if spatial else "")
            + cast_delta
            + cross_row
            + (f" | still={still}" if still else "")
        )
    pair_lines = [
        f"  - {a} → {b} (same row; strong FLF candidate if continuous or camera-motivated)"
        for a, b in same_row_pairs(panel_ids, columns=grid_columns)
    ]
    grid_lines = [
        f"  row {c['row']} col {c['col']}: {c['panel_id']}" for c in grid
    ]
    # Soft video_shots hints (non-authoritative)
    vshot_lines: list[str] = []
    for vs in scene.get("video_shots") or []:
        if not isinstance(vs, dict):
            continue
        vshot_lines.append(
            f"  - {vs.get('video_shot_id')}: panels={list(vs.get('panel_ids') or [])} "
            f"anchor={vs.get('anchor_panel_id')} dur={vs.get('duration_seconds')} "
            f"(soft hint only)"
        )
    staging_block = (
        f"staging: {scene.get('staging') or '(none)'}\n"
        f"blocking: {json.dumps(scene.get('blocking') or [], ensure_ascii=False)}"
    )
    paper = scene_paper_block.strip() or "(scene paper block unavailable — use plan beats)"
    authored_block = ""
    if has_director_meta:
        authored_block = """
## Authored Director metadata (AUTHORITATIVE unless contradicted by the sheet)
- Prefer authored `director_chain_group` / `director_transition_after` / `director_guide_role` when present.
- Build one multi-guide render_unit per chain group.
- On `match_cut`, keep the shared boundary panel (`end(K) == start(K+1)`).
- Fold `director_continuity_note` into unit rationale / Prompt Relay planning — do not dump into global_prompt.
- Treat `director_motion_spine` and per-shot `director_bridge_to_next` / connecting `motion_intent` as **AUTHORITATIVE high-level scene thought** for Prompt Relay and `beats[]` transition text — do not dump them into `global_prompt`.
- Prefer paper/plan `long_gap_bridge` edges for the bridge-guide / `beats[]` recipe; prefer `match_cut` when authored.
"""
    return f"""## Scene agenda (from scene_paper.md — editorial intent only)
{paper}

Ignore any "Duration budget" line in the scene paper for LTX clip timing.
You decide each clip's duration_seconds and the scene total.
{authored_block}
## Plan metadata
scene_id: {scene.get('scene_id')}
title: {scene.get('title')}
environment: {scene.get('environment')}
time_of_day: {scene.get('time_of_day')}
lighting: {scene.get('lighting')}
location_id: {scene.get('location_id')}
audio_scene: {json.dumps(scene.get('audio_scene') or {}, ensure_ascii=False)}
{staging_block}

## Director motion spine (AUTHORITATIVE high-level P01→…→PN thought — Prompt Relay / beats only)
{_format_motion_spine(scene)}

## Panel bridges + connecting motion (AUTHORITATIVE edge recipes)
{_format_panel_bridges(scene)}

## Storyboard grid (4×2 album — row-major)
columns: {grid_columns}
{chr(10).join(grid_lines)}

## Same-row FLF candidate pairs
{chr(10).join(pair_lines) if pair_lines else "  (none)"}

Prefer continuous FLF / multi-guide units on same-row pairs when action continues OR a
motivated camera pan/turn bridges them. Put the camera move into timed motion_segments.
Hard cuts start a new render_unit with cut_before=true.

## video_shots (soft / non-authoritative suggestions)
{chr(10).join(vshot_lines) if vshot_lines else "  (none)"}

## Duration guidance (LTX Director)
- Prefer 12–15s per render unit (use {{12, 15}}; 15s for multi-guide / late beats).
- Never below 9s (first→last needs time to land); never above 15s.
- YOU choose duration_total_seconds as the sum of unit durations (ignore scene-paper caps).
- Each render_unit is one Director timeline: guide_frames + motion_segments + global_prompt.

## Render knobs (required every unit)
Pick enums only — do not invent floats:
- motion_class: talking | walking | horse_riding | forest_exploration | large_reveal | fast_action | general
- guidance: balanced | prompt_follow | strong

## Director layers (required every render_unit)
- guide_frames: start-only, start+end, or start+middle+end panel stills
- motion_segments: 2–4 timed beats covering 0.0→1.0
- global_prompt: look/lighting only
- motion_prompt: flat join of beats + pace closing line

Prefer top-level render_units[] (scene-first). segments/clips remain acceptable.

## Allowed panel ids (story order)
{json.dumps(panel_ids, ensure_ascii=False)}

## Panel beats (plan.json)
{chr(10).join(beat_lines)}

Attached image is the full storyboard sheet for this scene.
Act as assistant director for LTX Director: plan the whole scene, then emit ordered
render_units with guides + Prompt Relay.
Return JSON only.
"""


def snap_director_clip_duration(raw_dur: int, *, fps: int = 25) -> int:
    """Snap AD clip durations into LTX-friendly 9–20s (prefer 12/15/20).

    20s is the ceiling for beats[] timelines with an AD-decided budget; plain
    render_units still default toward 12/15 unless the AD explicitly asks
    for a longer multi-beat arc.
    """
    value = int(raw_dur or 15)
    value = max(9, min(20, value))
    value = snap_ltx_duration(
        value,
        prefer_primary=True,
        primary=(12, 15, 20),
        allowed_min=9,
        allowed_max=20,
    )
    return snap_duration_seconds(value, fps=fps)


def director_chain_mode_enabled() -> bool:
    raw = os.getenv("STORY_MAKER_DIRECTOR_CHAIN")
    if raw is not None:
        return str(raw).strip().lower() not in ("0", "false", "off", "no")
    mode = str(os.getenv("STORYBOARD_VIDEO_MODE", "fallback")).strip().lower()
    return mode == "director"


def _order_index(panel_id: str, panel_ids: list[str]) -> int:
    try:
        return panel_ids.index(panel_id)
    except ValueError:
        return -1


def _default_hold_prompt(shot: dict | None, pace: str = "fast") -> str:
    shot = shot or {}
    motion = str(shot.get("motion_intent") or "Ambient environment micro-motion continues").strip()
    camera = str(shot.get("camera_intent") or "Locked framing with subtle drift").strip()
    closing = {
        "slow": "Deliberate emotional animation. Soft natural motion.",
        "medium": "Natural character animation. Expressive animated motion.",
        "fast": "Snappy energetic animation. Quick dynamic motion.",
    }.get(pace, "Snappy energetic animation. Quick dynamic motion.")
    return (
        f"A cinematic hold on the visible scene as {motion[0].lower() + motion[1:] if motion else 'light shifts'}. "
        f"Camera: {camera[0].lower() + camera[1:] if camera else 'subtle drift'}. "
        f"Continuous micro-motion of leaves, light, and fabric throughout. {closing}"
    )


def _default_pair_prompt(first: dict | None, last: dict | None, pace: str = "fast") -> str:
    first = first or {}
    last = last or {}
    a = str(first.get("motion_intent") or "the action begins").strip().rstrip(".")
    b = str(last.get("motion_intent") or "the action resolves").strip().rstrip(".")
    cam = str(first.get("camera_intent") or last.get("camera_intent") or "tracking move").strip()
    closing = {
        "slow": "Deliberate emotional animation. Soft natural motion.",
        "medium": "Natural character animation. Expressive animated motion.",
        "fast": "Snappy energetic animation. Quick dynamic motion.",
    }.get(pace, "Snappy energetic animation. Quick dynamic motion.")
    return (
        f"A cinematic continuation as {a[0].lower() + a[1:] if a else 'motion begins'}; "
        f"then {b[0].lower() + b[1:] if b else 'the beat resolves'}, "
        f"while the camera performs a {cam[0].lower() + cam[1:] if cam else 'smooth move'}. "
        f"Continuous micro-motion throughout. {closing}"
    )


def cast_allows_continuous(
    first_id: str,
    last_id: str,
    cast_by_panel: dict[str, frozenset[str]],
) -> bool:
    """Last-panel cast must be subset of first-panel cast (empty→cast never continuous)."""
    first_cast = cast_by_panel.get(first_id, frozenset())
    last_cast = cast_by_panel.get(last_id, frozenset())
    if not first_cast and last_cast:
        return False
    return last_cast.issubset(first_cast)


def allows_flf_continuous(
    first_id: str,
    last_id: str,
    panel_ids: list[str],
    cast_by_panel: dict[str, frozenset[str]],
    *,
    continuous: bool,
    grid_columns: int = 2,
) -> bool:
    """Whether a different-panel pair may stay continuous for FLF2V.

    Allows:
    - classic cast-subset continuity
    - adjacent motivated camera pans (esp. same-row), even with new end subjects
    Still blocks empty→cast and non-adjacent long spans.
    """
    if not continuous or first_id == last_id:
        return False
    first_cast = cast_by_panel.get(first_id, frozenset())
    last_cast = cast_by_panel.get(last_id, frozenset())
    if not first_cast and last_cast:
        return False
    if cast_allows_continuous(first_id, last_id, cast_by_panel):
        return True
    fi, li = _order_index(first_id, panel_ids), _order_index(last_id, panel_ids)
    if fi < 0 or li < 0 or li - fi != 1:
        return False
    # Adjacent pair: trust AD continuous flag for camera-motivated reveals.
    # Prefer same-row, but allow any adjacent story-order step.
    return True


def allows_multi_guide_continuous(
    first_id: str,
    last_id: str,
    guide_frames: list[dict],
    panel_ids: list[str],
    cast_by_panel: dict[str, frozenset[str]],
) -> bool:
    """Whether an explicit start/middle/end guide stack may stay one continuous unit.

    Requires ordered guides within the endpoint span, at least one strict mid
    waypoint, no empty→cast jump, and each adjacent guide hop to be allowable.
    """
    if first_id == last_id or len(guide_frames) < 3:
        return False
    first_cast = cast_by_panel.get(first_id, frozenset())
    last_cast = cast_by_panel.get(last_id, frozenset())
    if not first_cast and last_cast:
        return False
    fi, li = _order_index(first_id, panel_ids), _order_index(last_id, panel_ids)
    if fi < 0 or li < 0 or li <= fi:
        return False

    hops: list[str] = []
    for g in guide_frames:
        pid = str(g.get("panel_id") or "").strip()
        if not pid:
            return False
        idx = _order_index(pid, panel_ids)
        if idx < fi or idx > li:
            return False
        if hops and _order_index(hops[-1], panel_ids) > idx:
            return False
        if not hops or hops[-1] != pid:
            hops.append(pid)
    if hops[0] != first_id or hops[-1] != last_id:
        return False
    if not any(fi < _order_index(p, panel_ids) < li for p in hops):
        return False
    for a, b in zip(hops, hops[1:]):
        if not allows_flf_continuous(
            a, b, panel_ids, cast_by_panel, continuous=True
        ):
            return False
    return True


def panels_on_same_row(
    first_id: str,
    last_id: str,
    panel_ids: list[str],
    *,
    columns: int = 2,
) -> bool:
    grid = {str(c["panel_id"]): c for c in panel_grid_map(panel_ids, columns=columns)}
    a, b = grid.get(first_id), grid.get(last_id)
    if not a or not b:
        return False
    return int(a["row"]) == int(b["row"])


def _normalize_workflow(mode: str | None, first: str, last: str) -> str:
    raw = (mode or "").strip().lower()
    if first == last:
        return _MODE_I2V
    if raw in ("i2v", "i2v_hold"):
        # Different panels cannot be I2V — force FLF; continuity decided separately
        return _MODE_FLF
    return _MODE_FLF


def _clean_prompt(prompt: str) -> str:
    prompt = re.sub(
        r"\b(first frame|last frame|FLF2V|FLF)\b",
        "",
        prompt,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s{2,}", " ", prompt).strip()


def _normalize_motion_segments(
    raw_segments: Any,
    *,
    clip_id: str,
) -> tuple[list[dict], list[str]]:
    """Validate AD timed beats; return cleaned segments + repairs."""
    repairs: list[str] = []
    if not isinstance(raw_segments, list) or not raw_segments:
        return [], repairs

    cleaned: list[dict] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        prompt = _clean_prompt(str(item.get("prompt") or "").strip())
        if not prompt:
            continue
        try:
            start = float(item.get("start_ratio", 0.0))
            end = float(item.get("end_ratio", 1.0))
        except (TypeError, ValueError):
            repairs.append(f"drop invalid motion_segment ratios on {clip_id}")
            continue
        start = max(0.0, min(1.0, start))
        end = max(0.0, min(1.0, end))
        if end <= start:
            repairs.append(f"drop inverted motion_segment on {clip_id}")
            continue
        cleaned.append(
            {
                "start_ratio": round(start, 4),
                "end_ratio": round(end, 4),
                "prompt": prompt,
            }
        )

    cleaned.sort(key=lambda s: (s["start_ratio"], s["end_ratio"]))
    if len(cleaned) > 5:
        repairs.append(f"truncated motion_segments to 5 on {clip_id}")
        cleaned = cleaned[:5]

    if cleaned:
        if cleaned[0]["start_ratio"] > 0.05:
            cleaned[0]["start_ratio"] = 0.0
            repairs.append(f"snap first motion_segment to 0.0 on {clip_id}")
        if cleaned[-1]["end_ratio"] < 0.95:
            cleaned[-1]["end_ratio"] = 1.0
            repairs.append(f"snap last motion_segment to 1.0 on {clip_id}")

    return cleaned, repairs


def _clip_start(clip: dict) -> str:
    guides = clip.get("guide_frames") or []
    if isinstance(guides, list) and guides:
        ordered = sorted(
            [g for g in guides if isinstance(g, dict) and g.get("panel_id")],
            key=lambda g: float(g.get("start_ratio") or (0.0 if g.get("placement") == "start" else 0.5)),
        )
        if ordered:
            return str(ordered[0].get("panel_id") or "").strip()
    return str(
        clip.get("start_panel_id")
        or clip.get("first_panel_id")
        or ""
    ).strip()


def _clip_end(clip: dict) -> str:
    guides = clip.get("guide_frames") or []
    if isinstance(guides, list) and guides:
        endish = [
            g
            for g in guides
            if isinstance(g, dict)
            and g.get("panel_id")
            and (
                g.get("is_end_frame")
                or g.get("placement") == "end"
                or float(g.get("start_ratio") or 0) >= 0.999
            )
        ]
        if endish:
            return str(endish[-1].get("panel_id") or "").strip()
        ordered = sorted(
            [g for g in guides if isinstance(g, dict) and g.get("panel_id")],
            key=lambda g: float(g.get("start_ratio") or 0.0),
        )
        if ordered:
            return str(ordered[-1].get("panel_id") or "").strip()
    start = _clip_start(clip)
    return str(
        clip.get("end_panel_id")
        or clip.get("last_panel_id")
        or start
    ).strip()


def _normalize_guide_frames_for_clip(
    raw_guides: Any,
    *,
    first: str,
    last: str,
    panel_ids: list[str],
    clip_id: str,
    repairs: list[str],
) -> list[dict]:
    if not isinstance(raw_guides, list) or not raw_guides:
        # Synthesize classic start/end guides for legacy plans.
        if first == last:
            return [{"panel_id": first, "placement": "start", "start_ratio": 0.0, "is_end_frame": False}]
        return [
            {"panel_id": first, "placement": "start", "start_ratio": 0.0, "is_end_frame": False},
            {"panel_id": last, "placement": "end", "start_ratio": 1.0, "is_end_frame": True},
        ]

    cleaned: list[dict] = []
    for item in raw_guides:
        if not isinstance(item, dict):
            continue
        panel_id = str(item.get("panel_id") or "").strip()
        if panel_id not in panel_ids:
            repairs.append(f"drop unknown guide panel {panel_id} on {clip_id}")
            continue
        placement = str(item.get("placement") or "").strip().lower() or None
        try:
            ratio = item.get("start_ratio")
            ratio_f = float(ratio) if ratio is not None else None
        except (TypeError, ValueError):
            ratio_f = None
        is_end = bool(item.get("is_end_frame"))
        if placement == "start":
            ratio_f = 0.0
            is_end = False
        elif placement == "middle":
            ratio_f = 0.5 if ratio_f is None else max(0.05, min(0.95, ratio_f))
            is_end = False
        elif placement == "end":
            ratio_f = 1.0
            is_end = True
        elif ratio_f is None:
            ratio_f = 0.0
        ratio_f = max(0.0, min(1.0, float(ratio_f)))
        if ratio_f >= 0.999:
            is_end = True
            placement = placement or "end"
        cleaned.append(
            {
                "panel_id": panel_id,
                "placement": placement,
                "start_ratio": round(ratio_f, 4),
                "is_end_frame": is_end,
            }
        )
    cleaned.sort(key=lambda g: (g["start_ratio"], 1 if g["is_end_frame"] else 0))
    if not cleaned:
        return _normalize_guide_frames_for_clip(
            None, first=first, last=last, panel_ids=panel_ids, clip_id=clip_id, repairs=repairs
        )
    if cleaned[0]["start_ratio"] > 0.05 and cleaned[0]["placement"] != "start":
        cleaned[0]["placement"] = cleaned[0]["placement"] or "start"
        cleaned[0]["start_ratio"] = 0.0
    return cleaned


def _render_unit_to_clip(unit: dict, *, scene_id: str, index: int) -> dict:
    """Convert a scene-level render_unit into a clip-shaped dict."""
    unit_id = str(unit.get("unit_id") or unit.get("clip_id") or f"{scene_id}_unit_{index:02d}")
    guides = list(unit.get("guide_frames") or [])
    item = dict(unit)
    item["clip_id"] = unit_id
    item["guide_frames"] = guides
    item["_cut_before"] = bool(unit.get("cut_before", index > 1))
    item["_segment_id"] = str(unit.get("segment_id") or "")
    # Derive start/end from guides when omitted.
    if not item.get("start_panel_id") and guides:
        item["start_panel_id"] = _clip_start(item)
    if not item.get("end_panel_id") and guides:
        item["end_panel_id"] = _clip_end(item)
    return item


def _flatten_raw_clips(raw: dict | list) -> tuple[list[dict], list[str]]:
    """Accept render_units[], segments[], or flat clips[]; return (clips, repairs)."""
    repairs: list[str] = []
    if isinstance(raw, list):
        return [c for c in raw if isinstance(c, dict)], repairs
    if not isinstance(raw, dict):
        return [], repairs

    # Prefer scene-level render_units when present.
    render_units = raw.get("render_units")
    if isinstance(render_units, list) and render_units:
        scene_id = str(raw.get("scene_id") or "scene")
        flat = []
        for idx, unit in enumerate(render_units, start=1):
            if not isinstance(unit, dict):
                repairs.append(f"skip non-object render_unit at index {idx}")
                continue
            flat.append(_render_unit_to_clip(unit, scene_id=scene_id, index=idx))
        return flat, repairs

    segments = raw.get("segments")
    if isinstance(segments, list) and segments:
        flat: list[dict] = []
        for seg_idx, seg in enumerate(segments, start=1):
            if not isinstance(seg, dict):
                repairs.append(f"skip non-object segment at index {seg_idx}")
                continue
            seg_id = str(seg.get("segment_id") or f"seg_{seg_idx:02d}")
            cut_before = bool(seg.get("cut_before", seg_idx > 1))
            brief = str(seg.get("motion_brief") or seg.get("motion_prompt") or "").strip()
            clips = seg.get("clips") or []
            if not isinstance(clips, list):
                continue
            for c_idx, clip in enumerate(clips):
                if not isinstance(clip, dict):
                    continue
                item = dict(clip)
                item["_segment_id"] = seg_id
                item["_cut_before"] = cut_before if c_idx == 0 else False
                item["_segment_brief"] = brief
                flat.append(item)
        return flat, repairs

    clips_in = raw.get("clips") or []
    if isinstance(clips_in, list):
        return [c for c in clips_in if isinstance(c, dict)], repairs
    return [], repairs


def _normalize_beats_for_clip(
    raw_beats: Any,
    *,
    panel_ids: list[str],
    clip_id: str,
    repairs: list[str],
) -> list[dict]:
    """Clean an AD free-form beats[] timeline: durations on text, guides as instants.

    Returns [] when there is no usable guide beat so callers fall back to the
    legacy guide_frames/motion_segments path.
    """
    if not isinstance(raw_beats, list) or not raw_beats:
        return []

    cleaned: list[dict] = []
    guide_count = 0
    for item in raw_beats:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip().lower()
        if kind == "text":
            try:
                dur = float(item.get("duration_seconds") or 0.0)
            except (TypeError, ValueError):
                dur = 0.0
            prompt = _clean_prompt(str(item.get("prompt") or "").strip())
            if dur <= 0 or not prompt:
                repairs.append(f"drop empty text beat on {clip_id}")
                continue
            cleaned.append({"kind": "text", "duration_seconds": min(dur, 20.0), "prompt": prompt})
        elif kind == "guide":
            panel_id = str(item.get("panel_id") or "").strip()
            if panel_id not in panel_ids:
                repairs.append(f"drop guide beat with unknown panel {panel_id!r} on {clip_id}")
                continue
            if guide_count >= 4:
                repairs.append(f"drop extra guide beat beyond 4 on {clip_id}")
                continue
            role = str(item.get("role") or "").strip().lower() or None
            if role not in ("start", "bridge", "end"):
                role = None
            strength = item.get("guide_strength")
            try:
                strength = float(strength) if strength is not None else None
            except (TypeError, ValueError):
                strength = None
            if strength is not None:
                strength = max(0.3, min(1.0, strength))
            try:
                anchor = max(0.0, min(3.0, float(item.get("anchor_seconds") or 0.0)))
            except (TypeError, ValueError):
                anchor = 0.0
            is_end = bool(item.get("is_end_frame")) or role == "end"
            cleaned.append(
                {
                    "kind": "guide",
                    "panel_id": panel_id,
                    "role": role,
                    "guide_strength": strength,
                    "anchor_seconds": anchor,
                    "is_end_frame": is_end,
                }
            )
            guide_count += 1
        else:
            repairs.append(f"drop unrecognized beat kind {kind!r} on {clip_id}")

    if guide_count == 0:
        repairs.append(f"beats on {clip_id} had no usable guide; falling back to guide_frames")
        return []

    # DirectorClip schema requires sum(text) <= duration_seconds (<=20); scale
    # down proportionally so a slightly-over-budget AD timeline still renders
    # instead of failing validation outright.
    text_total = sum(b["duration_seconds"] for b in cleaned if b["kind"] == "text")
    if text_total > 20.0:
        scale = 20.0 / text_total
        for b in cleaned:
            if b["kind"] == "text":
                b["duration_seconds"] = round(b["duration_seconds"] * scale, 3)
        repairs.append(f"scaled beats duration on {clip_id} to fit 20s budget")

    return cleaned


def _beats_guide_frames_mirror(beats: list[dict]) -> list[dict]:
    """Ratio-shaped mirror of beats' guide instants for legacy coverage/chain helpers.

    Not used for rendering (the renderer consumes ``beats`` directly) — only
    keeps `_clip_panel_path` / coverage / splitting helpers working.
    """
    text_total = sum(b["duration_seconds"] for b in beats if b["kind"] == "text") or 1.0
    cursor = 0.0
    mirror: list[dict] = []
    for b in beats:
        if b["kind"] == "text":
            cursor += b["duration_seconds"]
            continue
        is_end = bool(b.get("is_end_frame"))
        ratio = 1.0 if is_end else max(0.0, min(0.999, cursor / text_total))
        placement = "end" if is_end else ("start" if ratio <= 0.001 else "middle")
        mirror.append(
            {
                "panel_id": b["panel_id"],
                "placement": placement,
                "start_ratio": round(ratio, 4),
                "is_end_frame": is_end,
            }
        )
    return mirror


def _beats_motion_segments_mirror(beats: list[dict]) -> list[dict]:
    """Ratio-shaped mirror of beats' text windows for legacy display/repair code."""
    text_total = sum(b["duration_seconds"] for b in beats if b["kind"] == "text") or 1.0
    cursor = 0.0
    segments: list[dict] = []
    for b in beats:
        if b["kind"] != "text":
            continue
        start_ratio = cursor / text_total
        cursor += b["duration_seconds"]
        end_ratio = min(1.0, cursor / text_total)
        if end_ratio <= start_ratio:
            end_ratio = min(1.0, start_ratio + 0.001)
        segments.append(
            {
                "start_ratio": round(start_ratio, 4),
                "end_ratio": round(end_ratio, 4),
                "prompt": b["prompt"],
            }
        )
    return segments


def _clip_from_beats(
    clip: dict,
    beats: list[dict],
    *,
    scene_id: str,
    index: int,
    repairs: list[str],
) -> dict:
    """Build a normalized clip dict from an AD-authored free-form beats[] timeline."""
    guide_beats = [b for b in beats if b["kind"] == "guide"]
    first = guide_beats[0]["panel_id"]
    end_guides = [b for b in guide_beats if b.get("is_end_frame")]
    last = end_guides[-1]["panel_id"] if end_guides else guide_beats[-1]["panel_id"]

    text_total = sum(b["duration_seconds"] for b in beats if b["kind"] == "text")
    duration = max(9, min(20, math.ceil(text_total))) if text_total > 0 else 9

    workflow = _MODE_FLF if (len(guide_beats) >= 2 or first != last) else _MODE_I2V
    continuous = len(guide_beats) >= 2

    pace = str(clip.get("pace") or "fast").strip().lower()
    if pace not in ("slow", "medium", "fast"):
        pace = "fast"

    global_prompt = _clean_prompt(str(clip.get("global_prompt") or "").strip())
    rationale = str(clip.get("rationale") or "").strip()
    render = resolve_clip_render_params(clip, prefer_stored=False)
    motion_prompt = _clean_prompt(
        " ".join(b["prompt"] for b in beats if b["kind"] == "text")
    )
    clip_id = str(clip.get("clip_id") or f"{scene_id}_clip_{index:02d}")

    if not rationale:
        n_bridge = sum(1 for b in guide_beats if b.get("role") == "bridge")
        rationale = (
            f"beats timeline ({len(guide_beats)} guides, {n_bridge} bridge)"
            if n_bridge
            else f"beats timeline ({len(guide_beats)} guides)"
        )

    return {
        "clip_id": clip_id,
        "segment_id": str(clip.get("_segment_id") or clip.get("segment_id") or ""),
        "start_panel_id": first,
        "end_panel_id": last,
        "first_panel_id": first,
        "last_panel_id": last,
        "continuous": continuous,
        "workflow": workflow,
        "mode": "i2v_hold" if workflow == _MODE_I2V else _MODE_FLF,
        "duration_seconds": duration,
        "pace": pace,
        "motion_class": render["motion_class"],
        "guidance": render["guidance"],
        "i2v_strength": render["i2v_strength"],
        "cfg": render["cfg"],
        "last_frame_strength": render["last_frame_strength"],
        "global_prompt": global_prompt,
        "motion_segments": _beats_motion_segments_mirror(beats),
        "guide_frames": _beats_guide_frames_mirror(beats),
        "motion_prompt": motion_prompt,
        "beats": beats,
        "negative_prompt": _clean_prompt(str(clip.get("negative_prompt") or "").strip()),
        "locked_cast": [str(c) for c in (clip.get("locked_cast") or []) if str(c).strip()],
        "rationale": rationale,
        "_cut_before": bool(clip.get("_cut_before", False)),
        "_segment_brief": str(clip.get("_segment_brief") or ""),
        "status": str(clip.get("status") or "pending"),
        "output_path": clip.get("output_path"),
    }


def _normalize_one_clip(
    clip: dict,
    *,
    scene_id: str,
    panel_ids: list[str],
    cast_by: dict[str, frozenset[str]],
    shot_lookup: dict[str, dict],
    fps: int,
    index: int,
    repairs: list[str],
) -> dict | None:
    raw_beats = clip.get("beats")
    if isinstance(raw_beats, list) and raw_beats:
        clip_id_hint = str(clip.get("clip_id") or f"{scene_id}_clip_{index:02d}")
        cleaned_beats = _normalize_beats_for_clip(
            raw_beats, panel_ids=panel_ids, clip_id=clip_id_hint, repairs=repairs
        )
        if cleaned_beats:
            return _clip_from_beats(
                clip, cleaned_beats, scene_id=scene_id, index=index, repairs=repairs
            )
        # No usable guide beat: fall through to the legacy guide_frames path below.

    first = _clip_start(clip)
    last = _clip_end(clip)
    if first not in panel_ids or last not in panel_ids:
        repairs.append(f"drop unknown panels {first}→{last}")
        return None
    fi, li = _order_index(first, panel_ids), _order_index(last, panel_ids)
    if li < fi:
        repairs.append(f"swap inverted pair {first}→{last}")
        first, last, fi, li = last, first, li, fi

    continuous = bool(clip.get("continuous", first != last))
    workflow = _normalize_workflow(
        clip.get("workflow") or clip.get("mode"), first, last
    )
    clip_id = str(clip.get("clip_id") or f"{scene_id}_clip_{index:02d}")
    raw_guides = clip.get("guide_frames")
    had_explicit_guides = isinstance(raw_guides, list) and len(raw_guides) >= 2
    guide_frames = _normalize_guide_frames_for_clip(
        raw_guides,
        first=first,
        last=last,
        panel_ids=panel_ids,
        clip_id=clip_id,
        repairs=repairs,
    )
    multi_guide = len(guide_frames) >= 2
    if first == last and not any(g.get("is_end_frame") for g in guide_frames):
        workflow = _MODE_I2V
        continuous = False
    else:
        workflow = _MODE_FLF if first != last or multi_guide else _MODE_I2V
        span = li - fi
        multi_ok = False
        if had_explicit_guides and len(guide_frames) >= 3 and first != last:
            multi_ok = allows_multi_guide_continuous(
                first, last, guide_frames, panel_ids, cast_by
            )
        # Explicit multi-guide (3+) may span >1 panel; classic FLF pairs stay adjacent.
        if continuous and span > 1 and not multi_ok:
            repairs.append(f"force cut for long span {first}→{last} (span={span})")
            continuous = False
        if continuous and not multi_ok and not allows_flf_continuous(
            first,
            last,
            panel_ids,
            cast_by,
            continuous=True,
        ):
            repairs.append(f"force cut for cast jump {first}→{last}")
            continuous = False
        if multi_ok:
            continuous = True
            workflow = _MODE_FLF
            repairs.append(
                f"keep multi-guide continuous unit {first}→{last} "
                f"({len(guide_frames)} guides)"
            )
        elif not continuous and first != last:
            repairs.append(
                f"reject non-continuous FLF {first}→{last}; will split to I2V standalones"
            )
        elif continuous and first != last and not cast_allows_continuous(
            first, last, cast_by
        ):
            repairs.append(
                f"allow adjacent camera-motivated FLF {first}→{last}"
                + (
                    " (same row)"
                    if panels_on_same_row(first, last, panel_ids)
                    else ""
                )
            )

    pace = str(clip.get("pace") or "fast").strip().lower() or "fast"
    if pace not in ("slow", "medium", "fast"):
        pace = "fast"
    raw_dur = int(clip.get("duration_seconds") or 6)
    duration = snap_director_clip_duration(raw_dur, fps=fps)
    motion_segments, seg_repairs = _normalize_motion_segments(
        clip.get("motion_segments"),
        clip_id=str(clip.get("clip_id") or f"{scene_id}_clip_{index:02d}"),
    )
    repairs.extend(seg_repairs)
    prompt = str(clip.get("motion_prompt") or "").strip()
    if not prompt and motion_segments:
        from tools.ltx_director_timeline import flatten_motion_segments_prompt

        prompt = flatten_motion_segments_prompt(motion_segments)
        repairs.append(f"derived motion_prompt from motion_segments for {first}→{last}")
    if not prompt:
        if first == last:
            prompt = _default_hold_prompt(shot_lookup.get(first), pace)
        else:
            prompt = _default_pair_prompt(
                shot_lookup.get(first), shot_lookup.get(last), pace
            )
        repairs.append(f"filled empty motion_prompt for {first}→{last}")
    prompt = _clean_prompt(prompt)
    if not motion_segments and prompt:
        # Legacy AD plans: synthesize one full-span beat so Director path always
        # has timed segments when re-rendered.
        motion_segments = [
            {"start_ratio": 0.0, "end_ratio": 1.0, "prompt": prompt}
        ]
        repairs.append(f"synthesized motion_segments from motion_prompt for {first}→{last}")
    global_prompt = _clean_prompt(str(clip.get("global_prompt") or "").strip())
    rationale = str(clip.get("rationale") or "").strip()
    render = resolve_clip_render_params(clip, prefer_stored=False)

    return {
        "clip_id": str(clip.get("clip_id") or f"{scene_id}_clip_{index:02d}"),
        "segment_id": str(clip.get("_segment_id") or clip.get("segment_id") or ""),
        "start_panel_id": first,
        "end_panel_id": last,
        # Compat aliases
        "first_panel_id": first,
        "last_panel_id": last,
        "continuous": continuous,
        "workflow": workflow,
        "mode": "i2v_hold" if workflow == _MODE_I2V else _MODE_FLF,
        "duration_seconds": duration,
        "pace": pace,
        "motion_class": render["motion_class"],
        "guidance": render["guidance"],
        "i2v_strength": render["i2v_strength"],
        "cfg": render["cfg"],
        "last_frame_strength": render["last_frame_strength"],
        "global_prompt": global_prompt,
        "motion_segments": motion_segments,
        "guide_frames": guide_frames,
        "motion_prompt": prompt,
        "rationale": rationale,
        "_cut_before": bool(clip.get("_cut_before", False)),
        "_segment_brief": str(clip.get("_segment_brief") or ""),
        "status": str(clip.get("status") or "pending"),
        "output_path": clip.get("output_path"),
    }


def _split_invalid_flf_pairs(clips: list[dict], repairs: list[str], scene_id: str) -> list[dict]:
    """Non-continuous different-panel pairs become two I2V standalones (editorial cut)."""
    out: list[dict] = []
    for clip in clips:
        guides = clip.get("guide_frames") or []
        keep_multi = bool(clip.get("continuous")) and len(guides) >= 3
        if (
            clip["start_panel_id"] != clip["end_panel_id"]
            and not clip["continuous"]
            and not keep_multi
        ):
            a, b = clip["start_panel_id"], clip["end_panel_id"]
            repairs.append(f"split non-continuous pair {a}→{b} into I2V standalones")
            for pid in (a, b):
                half = dict(clip)
                half["start_panel_id"] = pid
                half["end_panel_id"] = pid
                half["first_panel_id"] = pid
                half["last_panel_id"] = pid
                half["workflow"] = _MODE_I2V
                half["mode"] = "i2v_hold"
                half["continuous"] = False
                half["guide_frames"] = [
                    {
                        "panel_id": pid,
                        "placement": "start",
                        "start_ratio": 0.0,
                        "is_end_frame": False,
                    }
                ]
                half["clip_id"] = f"{scene_id}_clip_split_{pid}"
                out.append(half)
        else:
            out.append(clip)
    return out


def sync_ad_durations_to_plan_scene(plan: dict, scene_plan: dict) -> dict:
    """Write AD-chosen scene/shot wall-clock durations back onto plan.json scene."""
    scene_id = scene_plan.get("scene_id")
    if not scene_id or not isinstance(plan, dict):
        return plan
    total = int(scene_plan.get("duration_total_seconds") or 0)
    clips = scene_plan.get("clips") or []
    if not total and clips:
        total = sum(int(c.get("duration_seconds") or 0) for c in clips)
    for scene in plan.get("scenes") or []:
        if scene.get("scene_id") != scene_id:
            continue
        if total > 0:
            scene["duration_budget_seconds"] = total
        # Attribute each panel's duration from covering start units.
        by_start: dict[str, int] = {}
        for clip in clips:
            start = clip.get("start_panel_id") or clip.get("first_panel_id")
            dur = int(clip.get("duration_seconds") or 0)
            if start and dur > 0:
                by_start[start] = by_start.get(start, 0) + dur
        for shot in scene.get("shots") or []:
            sid = shot.get("shot_id")
            if sid in by_start:
                shot["duration_seconds"] = by_start[sid]
        break
    return plan


def _dedupe_standalones_prefer_chains(
    clips: list[dict], panel_ids: list[str]
) -> list[dict]:
    """If a panel is covered by a continuous FLF chain endpoint, drop redundant I2V holds."""
    chain_panels: set[str] = set()
    for c in clips:
        if c["workflow"] == _MODE_FLF and c["continuous"]:
            chain_panels.add(c["start_panel_id"])
            chain_panels.add(c["end_panel_id"])
    out: list[dict] = []
    seen_standalone: set[str] = set()
    for c in clips:
        if c["workflow"] == _MODE_I2V:
            pid = c["start_panel_id"]
            if pid in chain_panels:
                continue
            if pid in seen_standalone:
                continue
            seen_standalone.add(pid)
        out.append(c)
    out.sort(
        key=lambda c: (
            _order_index(c["start_panel_id"], panel_ids),
            _order_index(c["end_panel_id"], panel_ids),
            0 if c["workflow"] == _MODE_FLF else 1,
        )
    )
    return out


def _ensure_panel_coverage(
    clips: list[dict],
    *,
    scene_id: str,
    panel_ids: list[str],
    cast_by: dict[str, frozenset[str]],
    shot_lookup: dict[str, dict],
    fps: int,
    repairs: list[str],
) -> list[dict]:
    covered: set[str] = set()
    for c in clips:
        # Full guide path (not just start/end) so bridge/middle guides on
        # multi-guide and beats[] units count as covered — otherwise a
        # bridge-only panel wrongly looks "missing" and gets a redundant
        # filler clip synthesized on top of it.
        covered.update(_clip_panel_path(c, panel_ids))
        covered.add(c["start_panel_id"])
        covered.add(c["end_panel_id"])
    missing = [pid for pid in panel_ids if pid not in covered]
    if not missing:
        return clips

    repairs.append(f"coverage missing panels: {missing}")
    default_render = resolve_clip_render_params({}, prefer_stored=False)
    for pid in missing:
        i = panel_ids.index(pid)
        prev_id = panel_ids[i - 1] if i > 0 else None
        # Prefer attaching as continuous FLF from prev when cast-ok and prev exists
        if (
            prev_id
            and cast_allows_continuous(prev_id, pid, cast_by)
            and cast_by.get(prev_id, frozenset())
        ):
            clips.append(
                {
                    "clip_id": f"{scene_id}_clip_fill_{pid}",
                    "segment_id": "",
                    "start_panel_id": prev_id,
                    "end_panel_id": pid,
                    "first_panel_id": prev_id,
                    "last_panel_id": pid,
                    "continuous": True,
                    "workflow": _MODE_FLF,
                    "mode": _MODE_FLF,
                    "duration_seconds": snap_director_clip_duration(10, fps=fps),
                    "pace": "fast",
                    **default_render,
                    "motion_prompt": _default_pair_prompt(
                        shot_lookup.get(prev_id), shot_lookup.get(pid), "fast"
                    ),
                    "rationale": "coverage fill continuous",
                    "_cut_before": False,
                    "_segment_brief": "",
                    "status": "pending",
                    "output_path": None,
                }
            )
            repairs.append(f"added continuous fill {prev_id}→{pid}")
        else:
            clips.append(
                {
                    "clip_id": f"{scene_id}_clip_fill_{pid}",
                    "segment_id": "",
                    "start_panel_id": pid,
                    "end_panel_id": pid,
                    "first_panel_id": pid,
                    "last_panel_id": pid,
                    "continuous": False,
                    "workflow": _MODE_I2V,
                    "mode": "i2v_hold",
                    "duration_seconds": snap_director_clip_duration(10, fps=fps),
                    "pace": "fast",
                    **default_render,
                    "motion_prompt": _default_hold_prompt(shot_lookup.get(pid), "fast"),
                    "rationale": "coverage fill standalone I2V",
                    "_cut_before": True,
                    "_segment_brief": "",
                    "status": "pending",
                    "output_path": None,
                }
            )
            repairs.append(f"added i2v standalone for orphan {pid}")
    return clips


def _clip_panel_path(clip: dict, panel_ids: list[str]) -> list[str]:
    guides = [g for g in (clip.get("guide_frames") or []) if isinstance(g, dict)]
    path: list[str] = []
    if guides:
        ordered = sorted(
            guides,
            key=lambda g: (
                float(g.get("start_ratio", 0.0)),
                1 if bool(g.get("is_end_frame")) else 0,
            ),
        )
        for g in ordered:
            pid = str(g.get("panel_id") or "").strip()
            if pid in panel_ids and (not path or path[-1] != pid):
                path.append(pid)
    if not path:
        first, last = clip.get("start_panel_id"), clip.get("end_panel_id")
        if first in panel_ids:
            path.append(first)
        if last in panel_ids and last != first:
            path.append(last)
    return path


def _authored_chain_groups(
    panel_ids: list[str],
    shot_lookup: dict[str, dict],
) -> list[list[str]] | None:
    """Build unit paths from authored director_chain_group / transition metadata.

    Returns None when metadata is absent so callers fall back to heuristics.
    Shared boundary: on match_cut / group change, next unit starts with previous end.
    """
    if not panel_ids:
        return None
    has_meta = any(
        (shot_lookup.get(pid) or {}).get("director_chain_group") is not None
        or (shot_lookup.get(pid) or {}).get("director_transition_after")
        for pid in panel_ids
    )
    if not has_meta:
        return None

    groups: dict[int, list[str]] = {}
    ungrouped: list[str] = []
    for pid in panel_ids:
        shot = shot_lookup.get(pid) or {}
        gid = shot.get("director_chain_group")
        if gid is None:
            ungrouped.append(pid)
            continue
        try:
            gid_i = int(gid)
        except (TypeError, ValueError):
            ungrouped.append(pid)
            continue
        groups.setdefault(gid_i, []).append(pid)

    if not groups and ungrouped:
        return None

    # Prefer explicit groups in ascending group id, preserving panel order.
    units: list[list[str]] = []
    for gid in sorted(groups):
        path = groups[gid]
        if len(path) == 1:
            # Single-panel group still becomes a hold unit via path of 1 — chain
            # builder expects >=2, so borrow shared boundary from previous end.
            if units:
                path = [units[-1][-1], path[0]]
            elif len(panel_ids) >= 2:
                # Defer: keep as singleton for later pairing
                pass
        if len(path) >= 2:
            # Long-gap guard: authored director_chain_group is a coarse
            # grouping signal, not proof the keyframes are visually similar
            # enough for a 4-guide morph. Cap at 3 guides here too; a
            # deliberate 4-guide continuous take should be expressed via the
            # AD's beats[] timeline (explicit bridge + cast-lock), which
            # bypasses this heuristic path entirely.
            while len(path) > 3:
                units.append(path[:3])
                path = [path[2], *path[3:]]
            if len(path) >= 2:
                units.append(path)

    if ungrouped and units:
        # Attach leftover panels via shared-boundary continue of last unit edge.
        for pid in ungrouped:
            if units[-1][-1] != pid:
                if len(units[-1]) < 3:
                    units[-1].append(pid)
                else:
                    units.append([units[-1][-1], pid])
    elif ungrouped and not units:
        return None

    # Enforce shared boundary between consecutive units, then re-cap at 3 guides.
    fixed: list[list[str]] = []
    for path in units:
        if not fixed:
            fixed.append(path)
            continue
        if fixed[-1][-1] != path[0]:
            path = [fixed[-1][-1], *path]
        cleaned = [path[0]]
        for p in path[1:]:
            if p != cleaned[-1]:
                cleaned.append(p)
        while len(cleaned) > 3:
            fixed.append(cleaned[:3])
            cleaned = [cleaned[2], *cleaned[3:]]
        if len(cleaned) >= 2:
            fixed.append(cleaned)
    return fixed or None


def _build_chain_clips(
    *,
    scene_id: str,
    panel_ids: list[str],
    normalized: list[dict],
    cast_by: dict[str, frozenset[str]],
    shot_lookup: dict[str, dict],
    scene_global: str,
    fps: int,
    repairs: list[str],
) -> list[dict]:
    """Build one full-scene chain of units with shared boundary stills."""
    if len(panel_ids) < 2:
        return normalized

    # AD-authored beats[] timelines are explicit intent (bridge guides,
    # cast-lock text) — never rebuild them from cast/camera heuristics.
    # Heuristically chain only the panels the AD did not already cover,
    # split into contiguous runs so a beats-covered middle chunk doesn't
    # silently bridge two unrelated heuristic clusters on either side.
    beats_clips = [c for c in normalized if c.get("beats")]
    if beats_clips:
        other_clips = [c for c in normalized if not c.get("beats")]
        beats_covered: set[str] = set()
        for c in beats_clips:
            beats_covered.update(_clip_panel_path(c, panel_ids))
        remaining_panel_ids = [p for p in panel_ids if p not in beats_covered]
        if not remaining_panel_ids:
            repairs.append(
                f"beats-authored units cover all {len(panel_ids)} panels; skip heuristic chain"
            )
            return beats_clips

        runs: list[list[str]] = []
        for pid in remaining_panel_ids:
            idx = panel_ids.index(pid)
            if runs and panel_ids.index(runs[-1][-1]) == idx - 1:
                runs[-1].append(pid)
            else:
                runs.append([pid])

        default_render = resolve_clip_render_params({}, prefer_stored=False)
        heuristic_units: list[dict] = []
        for run in runs:
            if len(run) >= 2:
                heuristic_units.extend(
                    _build_chain_clips(
                        scene_id=scene_id,
                        panel_ids=run,
                        normalized=other_clips,
                        cast_by=cast_by,
                        shot_lookup=shot_lookup,
                        scene_global=scene_global,
                        fps=fps,
                        repairs=repairs,
                    )
                )
            else:
                pid = run[0]
                heuristic_units.append(
                    {
                        "clip_id": f"{scene_id}_clip_fill_{pid}",
                        "segment_id": "",
                        "start_panel_id": pid,
                        "end_panel_id": pid,
                        "first_panel_id": pid,
                        "last_panel_id": pid,
                        "continuous": False,
                        "workflow": _MODE_I2V,
                        "mode": "i2v_hold",
                        "duration_seconds": snap_director_clip_duration(10, fps=fps),
                        "pace": "fast",
                        **default_render,
                        "global_prompt": scene_global or "",
                        "motion_segments": [],
                        "guide_frames": [
                            {
                                "panel_id": pid,
                                "placement": "start",
                                "start_ratio": 0.0,
                                "is_end_frame": False,
                            }
                        ],
                        "motion_prompt": _default_hold_prompt(shot_lookup.get(pid), "fast"),
                        "rationale": "gap fill beside beats-authored units",
                        "_cut_before": True,
                        "_segment_brief": "",
                        "status": "pending",
                        "output_path": None,
                    }
                )
        repairs.append(
            f"beats-authored units cover {len(beats_covered)}/{len(panel_ids)} panels; "
            f"heuristically chained {len(remaining_panel_ids)} remaining"
        )
        return beats_clips + heuristic_units

    edge_hint: dict[tuple[str, str], dict] = {}
    for clip in normalized:
        path = _clip_panel_path(clip, panel_ids)
        if len(path) < 2:
            continue
        for a, b in zip(path, path[1:]):
            if a == b:
                continue
            key = (a, b)
            cont = bool(clip.get("continuous")) and clip.get("workflow") == _MODE_FLF
            prev = edge_hint.get(key)
            cand = {
                "continuous": cont,
                "motion_class": clip.get("motion_class"),
                "guidance": clip.get("guidance"),
                "global_prompt": clip.get("global_prompt") or scene_global or "",
                "pace": clip.get("pace") or "medium",
                "prompt": clip.get("motion_prompt") or "",
            }
            if prev is None or (not prev.get("continuous") and cont):
                edge_hint[key] = cand

    authored_units = _authored_chain_groups(panel_ids, shot_lookup)
    if authored_units:
        units = authored_units
        repairs.append(f"authored director groups units={len(units)}")
    else:
        transitions: list[bool] = []
        for a, b in zip(panel_ids, panel_ids[1:]):
            cont = False
            # Authored per-edge transition wins over cast heuristics when present.
            a_shot = shot_lookup.get(a) or {}
            authored_edge = str(a_shot.get("director_transition_after") or "").strip().lower()
            if authored_edge == "continue":
                cont = True
            elif authored_edge == "match_cut":
                cont = False
            else:
                if cast_allows_continuous(a, b, cast_by):
                    cont = True
                if allows_flf_continuous(a, b, panel_ids, cast_by, continuous=True):
                    cont = True
                hinted = edge_hint.get((a, b))
                if hinted and hinted.get("continuous"):
                    cont = True
            transitions.append(not cont)

        units = []
        current = [panel_ids[0]]
        for idx, nxt in enumerate(panel_ids[1:]):
            edge_is_transition = transitions[idx]
            # Keep continuation chains compact; split transitions into new units.
            if edge_is_transition and len(current) >= 2:
                units.append(current)
                current = [current[-1], nxt]
            else:
                if nxt != current[-1]:
                    current.append(nxt)
                # Long-gap guard: unauthored heuristic chains cap at 3 guides
                # (start+bridge+end). Beyond that, dissimilar keyframes give
                # LTX too much creative space and it invents extra subjects
                # to morph through — force a match_cut boundary instead of a
                # 4+ panel morph. AD-authored beats[] units may still use up
                # to 4 guides deliberately (see beats_clips branch above).
                if len(current) > 3:
                    repairs.append(
                        f"long-gap guard: match_cut split at {current[-1]} "
                        "(unauthored chain would exceed 3 guides)"
                    )
                    units.append(current[:-1])
                    current = [current[-2], current[-1]]
        if len(current) >= 2:
            units.append(current)

        if not units:
            units = [[panel_ids[0], panel_ids[1]]]

    default_render = resolve_clip_render_params({}, prefer_stored=False)
    out: list[dict] = []
    for i, path in enumerate(units, start=1):
        start, end = path[0], path[-1]
        cut_before = i > 1
        # match_cut on previous unit's last panel marks editorial cut.
        if i > 1:
            prev_end = units[i - 2][-1]
            prev_shot = shot_lookup.get(prev_end) or {}
            if str(prev_shot.get("director_transition_after") or "").lower() == "match_cut":
                cut_before = True
        edge_prompts: list[str] = []
        motion_class = default_render["motion_class"]
        guidance = default_render["guidance"]
        pace = "medium"
        global_prompt = scene_global
        continuity_notes: list[str] = []
        for a, b in zip(path, path[1:]):
            hint = edge_hint.get((a, b)) or {}
            a_shot = shot_lookup.get(a) or {}
            note = str(a_shot.get("director_continuity_note") or "").strip()
            if note:
                continuity_notes.append(note)
            if hint.get("prompt"):
                edge_prompts.append(str(hint["prompt"]).strip())
            else:
                edge_prompts.append(_default_pair_prompt(shot_lookup.get(a), shot_lookup.get(b), "medium"))
            motion_class = hint.get("motion_class") or motion_class
            guidance = hint.get("guidance") or guidance
            pace = hint.get("pace") or pace
            global_prompt = (hint.get("global_prompt") or global_prompt or "").strip()
        motion_segments = []
        n_edges = max(1, len(path) - 1)
        for j, prompt in enumerate(edge_prompts or [_default_pair_prompt(shot_lookup.get(start), shot_lookup.get(end), pace)]):
            s = j / n_edges
            e = (j + 1) / n_edges
            motion_segments.append({"start_ratio": round(s, 4), "end_ratio": round(e, 4), "prompt": prompt})
        motion_prompt = " ".join(p for p in edge_prompts if p).strip() or " ".join(
            str(s.get("prompt") or "").strip() for s in motion_segments
        ).strip()
        # Prefer the full 15s budget so multi-guide / late-scene beats have room.
        # 2-panel bridges stay at 12s; 3+ panel units use 15s.
        duration_seed = 15 if len(path) >= 3 else 12
        duration = snap_director_clip_duration(duration_seed, fps=fps)

        guides: list[dict] = []
        denom = max(1, len(path) - 1)
        for j, pid in enumerate(path):
            authored_role = str(
                (shot_lookup.get(pid) or {}).get("director_guide_role") or ""
            ).strip().lower()
            if j == 0:
                placement = "start"
                ratio = 0.0
                is_end = False
            elif j == len(path) - 1:
                placement = "end"
                ratio = 1.0
                is_end = True
            else:
                placement = "middle" if authored_role != "end" else "middle"
                ratio = round(j / denom, 4)
                is_end = False
            g = {"panel_id": pid, "placement": placement, "start_ratio": ratio, "is_end_frame": is_end}
            if placement == "start" and cut_before:
                g["guide_strength"] = 0.9
            guides.append(g)

        rationale = "scene chain unit"
        if continuity_notes:
            rationale = f"scene chain unit; continuity: {'; '.join(continuity_notes[:3])}"

        out.append(
            {
                "clip_id": f"{scene_id}_seg_{i:02d}_clip_01",
                "segment_id": f"{scene_id}_seg_{i:02d}",
                "start_panel_id": start,
                "end_panel_id": end,
                "first_panel_id": start,
                "last_panel_id": end,
                "continuous": True,
                "workflow": _MODE_FLF,
                "mode": _MODE_FLF,
                "duration_seconds": duration,
                "pace": pace,
                "motion_class": motion_class,
                "guidance": guidance,
                "i2v_strength": default_render["i2v_strength"],
                "cfg": default_render["cfg"],
                "last_frame_strength": default_render["last_frame_strength"],
                "global_prompt": global_prompt or "",
                "motion_segments": motion_segments,
                "guide_frames": guides,
                "motion_prompt": motion_prompt,
                "rationale": rationale,
                "_cut_before": cut_before,
                "_segment_brief": "",
                "status": "pending",
                "output_path": None,
            }
        )

    # Strengthen shared end boundary when followed by another unit.
    for i in range(len(out) - 1):
        last = out[i]["guide_frames"][-1]
        if isinstance(last, dict) and last.get("placement") == "end":
            last["guide_strength"] = max(float(last.get("guide_strength") or 0.0), 0.9)

    repairs.append(f"chain mode units={len(out)} full_coverage={len(panel_ids)}")
    return out


def derive_segments_from_clips(clips: list[dict], scene_id: str) -> list[dict]:
    """Group clips into hard-cut-separated segments with shared-endpoint chains."""
    if not clips:
        return []

    segments: list[dict] = []
    current: dict | None = None

    for clip in clips:
        start_new = False
        if current is None:
            start_new = True
        elif clip.get("_cut_before"):
            start_new = True
        elif not clip.get("continuous"):
            start_new = True
        elif current["clips"]:
            prev = current["clips"][-1]
            # Chain requires shared endpoint
            if prev["end_panel_id"] != clip["start_panel_id"]:
                start_new = True
            # I2V standalone always its own segment unless already alone continuous false
            if clip["workflow"] == _MODE_I2V:
                start_new = True
            if prev["workflow"] == _MODE_I2V:
                start_new = True

        if start_new:
            seg_id = (
                clip.get("segment_id")
                or f"{scene_id}_seg_{len(segments) + 1:02d}"
            )
            current = {
                "segment_id": seg_id,
                "cut_before": bool(clip.get("_cut_before") or len(segments) > 0),
                "motion_brief": clip.get("_segment_brief") or "",
                "clips": [],
            }
            segments.append(current)

        assert current is not None
        item = {k: v for k, v in clip.items() if not k.startswith("_")}
        item["segment_id"] = current["segment_id"]
        current["clips"].append(item)
        if not current["motion_brief"] and item.get("motion_prompt"):
            # Seed brief from first clip prompt (short)
            current["motion_brief"] = item["motion_prompt"][:180]

    # Validate chains; break on gap
    fixed: list[dict] = []
    for seg in segments:
        chain: list[dict] = []
        for clip in seg["clips"]:
            if not chain:
                chain = [clip]
                continue
            if (
                chain[-1]["end_panel_id"] == clip["start_panel_id"]
                and clip["workflow"] == _MODE_FLF
                and chain[-1]["workflow"] == _MODE_FLF
            ):
                chain.append(clip)
            else:
                fixed.append(
                    {
                        "segment_id": f"{scene_id}_seg_{len(fixed) + 1:02d}",
                        "cut_before": bool(fixed),
                        "motion_brief": seg.get("motion_brief") or "",
                        "clips": chain,
                    }
                )
                chain = [clip]
        if chain:
            fixed.append(
                {
                    "segment_id": f"{scene_id}_seg_{len(fixed) + 1:02d}",
                    "cut_before": bool(fixed) or bool(seg.get("cut_before")),
                    "motion_brief": seg.get("motion_brief") or "",
                    "clips": chain,
                }
            )

    # Re-id
    for i, seg in enumerate(fixed, start=1):
        seg["segment_id"] = f"{scene_id}_seg_{i:02d}"
        for j, clip in enumerate(seg["clips"], start=1):
            clip["segment_id"] = seg["segment_id"]
            clip["clip_id"] = f"{scene_id}_seg_{i:02d}_clip_{j:02d}"
            if j > 1:
                clip["continuous"] = True
            elif clip["workflow"] == _MODE_I2V:
                clip["continuous"] = False
    if fixed:
        fixed[0]["cut_before"] = False
    return fixed


def reconcile_clip_durations(
    clips: list[dict],
    budget: int | None = None,
    *,
    fps: int = 25,
    tolerance_percent: int = 15,
) -> tuple[list[dict], list[str]]:
    """Snap each clip to LTX-friendly durations; scene total = sum (AD-chosen).

    ``budget`` is ignored — kept for call-site compatibility.
    """
    del budget, tolerance_percent
    repairs: list[str] = []
    if not clips:
        return clips, repairs

    for clip in clips:
        d = int(clip.get("duration_seconds") or 6)
        clip["duration_seconds"] = snap_director_clip_duration(d, fps=fps)

    total = sum(int(c["duration_seconds"]) for c in clips)
    repairs.append(f"director scene total {total}s (sum of clip durations; no scene-paper budget)")
    return clips, repairs


def flatten_segments_to_clips(segments: list[dict]) -> list[dict]:
    clips: list[dict] = []
    for seg in segments:
        for clip in seg.get("clips") or []:
            clips.append(clip)
    return clips


def migrate_legacy_flf_scene(legacy: dict, scene: dict, *, fps: int = 25) -> dict:
    """Convert old flat flf2v_scenes plan into segment plan."""
    return normalize_flf_clip_plan(legacy, scene, fps=fps)


def normalize_flf_clip_plan(
    raw: dict | list,
    scene: dict,
    *,
    fps: int = 25,
    duration_budget_seconds: int | None = None,
    scene_paper: str | None = None,
    tolerance_percent: int | None = None,
) -> dict[str, Any]:
    """Validate and repair assistant-director plans for one scene.

    Returns segment plan plus flat ``clips`` for renderers/compat.
    Scene runtime is the sum of AD-chosen clip durations (not scene-paper budget).
    """
    del duration_budget_seconds, scene_paper, tolerance_percent
    scene_id = scene.get("scene_id") or ""
    panel_ids = panel_ids_in_order(scene)
    cast_by = panel_cast_lookup(scene)
    shot_lookup = {
        sh.get("shot_id"): sh
        for sh in (scene.get("shots") or [])
        if isinstance(sh, dict) and sh.get("shot_id")
    }
    repairs: list[str] = []

    flat_in, flat_repairs = _flatten_raw_clips(raw)
    repairs.extend(flat_repairs)

    # Prefer AD-declared total if present; still recompute from clips after snap
    declared_total = None
    if isinstance(raw, dict):
        for key in ("duration_total_seconds", "duration_budget_seconds"):
            if raw.get(key) is not None:
                try:
                    declared_total = int(raw[key])
                except (TypeError, ValueError):
                    declared_total = None
                break
    scene_global = ""
    if isinstance(raw, dict):
        scene_global = _clean_prompt(str(raw.get("scene_global_prompt") or "").strip())

    normalized: list[dict] = []
    for idx, clip in enumerate(flat_in, start=1):
        item = _normalize_one_clip(
            clip,
            scene_id=scene_id,
            panel_ids=panel_ids,
            cast_by=cast_by,
            shot_lookup=shot_lookup,
            fps=fps,
            index=idx,
            repairs=repairs,
        )
        if item:
            normalized.append(item)

    if director_chain_mode_enabled() and len(panel_ids) >= 2:
        normalized = _build_chain_clips(
            scene_id=scene_id,
            panel_ids=panel_ids,
            normalized=normalized,
            cast_by=cast_by,
            shot_lookup=shot_lookup,
            scene_global=scene_global,
            fps=fps,
            repairs=repairs,
        )
    else:
        normalized = _split_invalid_flf_pairs(normalized, repairs, scene_id)
        normalized = _ensure_panel_coverage(
            normalized,
            scene_id=scene_id,
            panel_ids=panel_ids,
            cast_by=cast_by,
            shot_lookup=shot_lookup,
            fps=fps,
            repairs=repairs,
        )
        normalized = _dedupe_standalones_prefer_chains(normalized, panel_ids)

    # Sort story order before segmenting
    normalized.sort(
        key=lambda c: (
            _order_index(c["start_panel_id"], panel_ids),
            _order_index(c["end_panel_id"], panel_ids),
            0 if c["workflow"] == _MODE_FLF else 1,
        )
    )

    # Mark cut_before when story order jumps or continuous false
    prev_end_idx = -1
    for i, clip in enumerate(normalized):
        start_idx = _order_index(clip["start_panel_id"], panel_ids)
        if i == 0:
            clip["_cut_before"] = False
        elif not clip.get("continuous"):
            clip["_cut_before"] = True
        elif start_idx > prev_end_idx + 1:
            clip["_cut_before"] = True
            clip["continuous"] = False
        else:
            clip["_cut_before"] = bool(clip.get("_cut_before"))
        prev_end_idx = max(
            prev_end_idx, _order_index(clip["end_panel_id"], panel_ids)
        )

    segments = derive_segments_from_clips(normalized, scene_id)
    clips = flatten_segments_to_clips(segments)
    clips, dur_repairs = reconcile_clip_durations(clips, fps=fps)
    repairs.extend(dur_repairs)

    # Write durations back into segments
    by_id = {c["clip_id"]: c for c in clips}
    for seg in segments:
        for clip in seg["clips"]:
            if clip["clip_id"] in by_id:
                clip["duration_seconds"] = by_id[clip["clip_id"]]["duration_seconds"]

    total = sum(int(c["duration_seconds"]) for c in clips)
    if declared_total and abs(declared_total - total) > 2:
        repairs.append(
            f"AD declared duration_total_seconds={declared_total}; "
            f"using snapped clip sum {total}s"
        )
    # Propagate scene global into clips that omitted their own.
    if scene_global:
        for clip in clips:
            if not (clip.get("global_prompt") or "").strip():
                clip["global_prompt"] = scene_global
        for seg in segments:
            for clip in seg.get("clips") or []:
                if not (clip.get("global_prompt") or "").strip():
                    clip["global_prompt"] = scene_global

    return {
        "scene_id": scene_id,
        "scene_global_prompt": scene_global,
        # duration_budget_seconds mirrors director-chosen scene total (not scene paper)
        "duration_budget_seconds": total,
        "duration_total_seconds": total,
        "segments": segments,
        "clips": clips,  # flat render order
        "render_units": [
            {
                "unit_id": c["clip_id"],
                "cut_before": bool(c.get("_cut_before")),
                "duration_seconds": c["duration_seconds"],
                "pace": c.get("pace") or "medium",
                "motion_class": c.get("motion_class"),
                "guidance": c.get("guidance"),
                "global_prompt": c.get("global_prompt") or "",
                "motion_segments": c.get("motion_segments") or [],
                "guide_frames": c.get("guide_frames") or [],
                "motion_prompt": c.get("motion_prompt") or "",
                "rationale": c.get("rationale") or "",
            }
            for c in clips
        ],
        "repairs": repairs,
        "status": "planned",
    }


async def plan_flf_clips_from_storyboard(
    *,
    sheet_path: str,
    scene: dict,
    panel_ids: list[str] | None = None,
    fps: int = 25,
    scene_paper: str | None = None,
    duration_budget_seconds: int | None = None,
    still_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Call vision on the storyboard sheet and normalize the director plan."""
    from tools.vision_llm import vision_json_from_image

    del duration_budget_seconds
    panel_ids = panel_ids or panel_ids_in_order(scene)
    system_prompt = load_flf_planner_system_prompt()
    paper_block = ""
    if scene_paper:
        paper_block = extract_scene_paper_block(scene_paper, scene.get("scene_id") or "")
    user_text = build_flf_planner_user_text(
        scene,
        panel_ids,
        scene_paper_block=paper_block,
        still_paths=still_paths,
    )
    raw = await vision_json_from_image(sheet_path, system_prompt, user_text)
    result = normalize_flf_clip_plan(raw, scene, fps=fps)
    result["sheet_path"] = sheet_path
    return result
