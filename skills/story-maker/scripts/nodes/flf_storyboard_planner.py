"""Storyboard assistant director: vision JSON → segment/clip plan → I2V/FLF2V."""
from __future__ import annotations

import json
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
    for i, shot in enumerate(scene.get("shots") or [], start=1):
        sid = shot.get("shot_id")
        if sid not in panel_ids:
            continue
        still = (still_paths or {}).get(sid) or ""
        cell = grid_by_id.get(sid) or {}
        loc = (
            f"row {cell.get('row')} col {cell.get('col')}"
            if cell
            else f"index {i}"
        )
        beat_lines.append(
            f"  {i}. [{loc}] {sid}: chars={list(shot.get('characters_present') or [])} | "
            f"{shot.get('description', '')} | motion={shot.get('motion_intent', '')} | "
            f"camera={shot.get('camera_intent', '')}"
            + (f" | still={still}" if still else "")
        )
    pair_lines = [
        f"  - {a} → {b} (same row; strong FLF candidate if continuous or camera-motivated)"
        for a, b in same_row_pairs(panel_ids, columns=grid_columns)
    ]
    grid_lines = [
        f"  row {c['row']} col {c['col']}: {c['panel_id']}" for c in grid
    ]
    paper = scene_paper_block.strip() or "(scene paper block unavailable — use plan beats)"
    return f"""## Scene agenda (from scene_paper.md — editorial intent only)
{paper}

Ignore any "Duration budget" line in the scene paper for LTX clip timing.
You decide each clip's duration_seconds and the scene total.

## Plan metadata
scene_id: {scene.get('scene_id')}
title: {scene.get('title')}
environment: {scene.get('environment')}
time_of_day: {scene.get('time_of_day')}
lighting: {scene.get('lighting')}
location_id: {scene.get('location_id')}
audio_scene: {json.dumps(scene.get('audio_scene') or {}, ensure_ascii=False)}

## Storyboard grid (5×2 album — row-major)
columns: {grid_columns}
{chr(10).join(grid_lines)}

## Same-row FLF candidate pairs
{chr(10).join(pair_lines) if pair_lines else "  (none)"}

Prefer FLF2V on same-row pairs when action continues OR a motivated camera pan/turn
bridges them (e.g. child points in row4 col1 → camera pans along the gesture to deer in row4 col2).
Put the camera move into a timed motion_segments beat (not only global_prompt).

## Duration guidance (LTX 2.3 / Director)
- Prefer 6–10s per clip (best quality): use {{6, 8, 10}}.
- 3s only for a truly super-short beat; never above 10s.
- You choose the scene runtime as the sum of clip durations.
- Each clip is one Director timeline: global_prompt + motion_segments + panel guides.

## Render knobs (required every clip)
Pick enums only — do not invent floats:
- motion_class: talking | walking | horse_riding | forest_exploration | large_reveal | fast_action | general
  (talking=hold face; fast_action/large_reveal=more motion freedom / guide strength)
- guidance: balanced | prompt_follow | strong
  (default balanced; prompt_follow if timed beats are ignored; strong rarely)

## Director prompt layers (required every clip)
- global_prompt: 1–2 sentences of look/lighting/location context only
- motion_segments: 2–4 timed beats with start_ratio/end_ratio covering 0.0→1.0
  (action + camera + audio per window; ≥~2s per distinct beat when possible)
- motion_prompt: flat join of those beats + pace closing line (legacy fallback)

## Allowed panel ids (story order)
{json.dumps(panel_ids, ensure_ascii=False)}

## Panel beats (plan.json)
{chr(10).join(beat_lines)}

Attached image is the full storyboard sheet for this scene.
Act as assistant director for LTX Director: segment into I2V standalones and FLF2V
continuous chains with timed motion_segments.
Hard cuts start new segments — never FLF across unmotivated jumps.
Return JSON only.
"""


def snap_director_clip_duration(raw_dur: int, *, fps: int = 25) -> int:
    """Snap AD clip durations into LTX-friendly 3–10s (prefer 6/8/10)."""
    value = int(raw_dur or 6)
    value = max(3, min(10, value))
    if value <= 5:
        # Keep super-short band only when AD explicitly chose ≤5.
        value = snap_ltx_duration(
            value, prefer_primary=False, allowed_min=3, allowed_max=5
        )
    else:
        value = snap_ltx_duration(
            value, prefer_primary=True, primary=(6, 8, 10), allowed_min=6, allowed_max=10
        )
    return snap_duration_seconds(value, fps=fps)


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
    return str(
        clip.get("start_panel_id")
        or clip.get("first_panel_id")
        or ""
    ).strip()


def _clip_end(clip: dict) -> str:
    start = _clip_start(clip)
    return str(
        clip.get("end_panel_id")
        or clip.get("last_panel_id")
        or start
    ).strip()


def _flatten_raw_clips(raw: dict | list) -> tuple[list[dict], list[str]]:
    """Accept segments[] or flat clips[]; return (clips, repairs)."""
    repairs: list[str] = []
    if isinstance(raw, list):
        return [c for c in raw if isinstance(c, dict)], repairs
    if not isinstance(raw, dict):
        return [], repairs

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
                # cut_before starts a new segment; do NOT clear continuous on FLF pairs
                # (continuous describes the pair's physics, not the editorial cut).
                flat.append(item)
        return flat, repairs

    clips_in = raw.get("clips") or []
    if isinstance(clips_in, list):
        return [c for c in clips_in if isinstance(c, dict)], repairs
    return [], repairs


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
    if first == last:
        workflow = _MODE_I2V
        continuous = False
    else:
        workflow = _MODE_FLF
        span = li - fi
        if continuous and span > 1:
            repairs.append(f"force cut for long span {first}→{last} (span={span})")
            continuous = False
        if continuous and not allows_flf_continuous(
            first,
            last,
            panel_ids,
            cast_by,
            continuous=True,
        ):
            repairs.append(f"force cut for cast jump {first}→{last}")
            continuous = False
        # Non-continuous different-panel pairs are invalid FLF morphs —
        # split into editorial cut: keep as non-continuous flag for segment break,
        # but do not render FLF across the jump. Convert to two standalones later
        # if still marked non-continuous with different panels.
        if not continuous and first != last:
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
        if (
            clip["start_panel_id"] != clip["end_panel_id"]
            and not clip["continuous"]
        ):
            a, b = clip["start_panel_id"], clip["end_panel_id"]
            repairs.append(f"split non-continuous pair {a}→{b} into I2V standalones")
            for pid in (a, b):
                # Avoid duplicate if already covered as standalone later; still emit for now
                half = dict(clip)
                half["start_panel_id"] = pid
                half["end_panel_id"] = pid
                half["first_panel_id"] = pid
                half["last_panel_id"] = pid
                half["workflow"] = _MODE_I2V
                half["mode"] = "i2v_hold"
                half["continuous"] = False
                half["clip_id"] = f"{scene_id}_clip_split_{pid}"
                out.append(half)
        else:
            out.append(clip)
    return out


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
                    "duration_seconds": snap_director_clip_duration(6, fps=fps),
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
                    "duration_seconds": snap_director_clip_duration(6, fps=fps),
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
    return {
        "scene_id": scene_id,
        # duration_budget_seconds mirrors director-chosen scene total (not scene paper)
        "duration_budget_seconds": total,
        "duration_total_seconds": total,
        "segments": segments,
        "clips": clips,  # flat render order
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
