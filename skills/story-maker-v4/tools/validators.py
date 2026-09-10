"""Deterministic validators for story-maker-v4 (Minimax H3 backend).

Run after each authoring agent to catch hallucination BEFORE any paid image /
render step. Each validator parses a markdown/text artifact, asserts the locked
schema, and returns a :class:`ValidationResult`. The CLI
(``scripts/validate.py``) writes ``<artifact>.validation.json`` and exits
nonzero on failure; Claude Code loops (write -> validate -> fix) until pass.

No LLM calls. Pure parsing + assertions.

Schemas enforced:
  scenes        -> scene_count>=1; each scene has scene_id/target_seconds/cast/location_id;
                   sum(targets) ~= run target.
  storyboard    -> scene split into generations (each 5-15s, contiguous, sum ==
                   target_seconds); shots contiguous within each generation and
                   NEVER straddling a generation boundary; panels sequential
                   (column-major: top-to-bottom within each column, then
                   left-to-right) and matching the panel_grid;
                   characters_present subset of cast.
  prompts       -> char/location prompt files + one storyboard sheet prompt per
                   generation exist and are non-empty.
  video_prompt  -> per-generation Minimax timeline prompt: SHOT lines match the
                   storyboard's generation-local shot ranges; has a Negative
                   Prompt section; references the storyboard; no char_NN tokens.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from . import duration_budget

# Minimax H3 camera motion vocabulary (Motion type dimension). Used as a
# warn-only check that shot `camera:` fields speak the model's language.
MINIMAX_MOTION_TERMS = (
    "zoom in", "zoom out", "push in", "pull out", "pan left", "pan right",
    "truck left", "truck right", "tilt up", "tilt down", "pedestal up",
    "pedestal down", "arc shot", "tracking shot", "static shot",
    "shake slightly", "shake strongly", "pov", "roll clockwise",
    "roll counterclockwise",
    # common free-form cinematic phrasing Minimax also follows well
    "dolly", "crane", "whip pan", "orbit", "handheld", "push-in", "pullback",
    "pull back", "zoom-in", "zoom-out",
)

SHOT_TRANSITIONS = (
    "continuous", "hard_cut", "cut_on_action", "reaction_cut",
    "match_cut", "whip_pan", "audio_led", "camera_move",
)

# Canonical control phrases rendered in the video prompt for each transition.
# `continuous` and `camera_move` render no cut phrase (camera_move is not a cut).
TRANSITION_PHRASES = {
    "hard_cut": "Hard cinematic cut.",
    "cut_on_action": "Cut on the action.",
    "reaction_cut": "Cut to the reaction.",
    "match_cut": "Match cut on ",  # completed with the matched element
    "whip_pan": "Whip pan transition.",
    "audio_led": "Audio leads the cut.",
}

# Shot size taxonomy (see assets/directors-guide.md Section 2).
SHOT_SIZES = (
    "extreme_wide", "wide", "full", "medium",
    "medium_closeup", "closeup", "extreme_closeup",
)

# Composition types (see assets/directors-guide.md Section 4).
COMPOSITION_TYPES = (
    "rule_of_thirds", "center", "symmetry", "leading_lines",
    "negative_space", "depth", "silhouette", "frame_within_frame",
    "visual_hierarchy", "headroom", "look_room", "screen_direction",
)

# Anime-studio screen-direction vocabulary for shot-level layout continuity.
SCREEN_DIRECTIONS = (
    "left_to_right", "right_to_left", "toward_camera", "away_from_camera",
    "held", "top_to_bottom", "bottom_to_top",
)

# Camera angle taxonomy for dynamic cinematic staging.
CAMERA_ANGLES = (
    "eye_level",
    "low_angle",
    "high_angle",
    "bird_eye",
    "birds_eye",
    "worm_eye",
    "worms_eye",
    "side_profile",
    "profile",
    "three_quarter",
    "three_quarter_front",
    "three_quarter_back",
    "over_the_shoulder",
    "dutch_angle",
    "reverse_shot",
    "pov",
    "top_down",
)

# Focus / depth of field taxonomy (see assets/directors-guide.md Section 2 and assets/cinematography-bible.md Section C-bis).
FOCUS_TYPES = (
    "shallow_focus",
    "deep_focus",
    "rack_focus",
    "soft_focus",
)

# Suggested emotion vocabulary for beat boards (warn-only — not enforced).
# See prompts/beat_board.md and assets/directors-guide.md Section 1.
BEAT_EMOTIONS = (
    "joy", "unease", "fear", "tension", "determination", "excitement",
    "shock", "chaos", "triumph", "sadness", "wonder", "relief",
    "anger", "tenderness", "suspense", "hope", "despair", "confusion",
    "awe", "disgust", "longing", "pride", "shame", "curiosity",
)

# Anime-studio scene-production metadata required by V4 scenes.md.
SCENE_PRODUCTION_FIELDS = (
    "style_target",
    "acting_beat",
    "layout_strategy",
    "visual_motif",
    "sound_world",
)


@dataclass
class ValidationResult:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        self.ok = False

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


# ---------------------------------------------------------------------------
# Inline value parsers (tolerant of unquoted JSON-ish markdown)
# ---------------------------------------------------------------------------

def _strip_brackets(text: str, open: str = "[", close: str = "]") -> str:
    t = (text or "").strip()
    if t.startswith(open) and t.endswith(close):
        t = t[1:-1]
    return t.strip()


def parse_cid_list(text: str) -> list[str]:
    """``[cid_a, cid_b]`` or ``cid_a, cid_b`` -> ['cid_a', 'cid_b']."""
    inner = _strip_brackets(text)
    if not inner:
        return []
    return [c.strip() for c in inner.split(",") if c.strip()]


def parse_int_list(text: str) -> list[int]:
    """``[1, 2, 3]`` -> [1, 2, 3]; unparseable entries become -1."""
    out: list[int] = []
    for tok in parse_cid_list(text):
        try:
            out.append(int(tok))
        except ValueError:
            out.append(-1)
    return out


def _kv_lines(block: str) -> dict[str, str]:
    """Parse ``key: value`` lines (ignoring tables/headers) into a dict."""
    out: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("|") or line.startswith("#") or line.startswith("-"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            out[key.strip()] = val.strip()
    return out


# time range like ``0.0-15.0s`` / ``0.0–15.0s`` / ``7.2 - 15s``
_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[–—-]\s*(\d+(?:\.\d+)?)\s*s?")


def _parse_range(text: str) -> tuple[float, float] | None:
    m = _RANGE_RE.search(text or "")
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


# ---------------------------------------------------------------------------
# Artifact parsers
# ---------------------------------------------------------------------------

def parse_scenes(md: str) -> dict[str, Any]:
    """Parse scenes.md -> {target_seconds, scene_budget, scenes: [...]}."""
    # Head = everything before the first "## Scene" header.
    first_scene = None
    for i, line in enumerate(md.splitlines()):
        if line.startswith("## Scene "):
            first_scene = i
            break
    head_text = "\n".join(md.splitlines()[:first_scene]) if first_scene is not None else md
    head_kv = _kv_lines(head_text)
    target = int(head_kv.get("target_seconds", "0") or 0)
    budget = int(head_kv.get("scene_budget", str(duration_budget.SCENE_BUDGET_DEFAULT)) or duration_budget.SCENE_BUDGET_DEFAULT)

    scenes: list[dict[str, Any]] = []
    blocks = re.split(r"^## Scene ", md, flags=re.M)
    for blk in blocks[1:]:
        head, _, rest = blk.partition("\n")
        scene_id = head.strip().split("—")[0].split("-")[0].strip()
        kv = _kv_lines(rest)
        sid = kv.get("scene_id", scene_id).strip()
        scenes.append({
            "scene_id": sid,
            "target_seconds": int(kv.get("target_seconds", "0") or 0),
            "cast": parse_cid_list(kv.get("cast", "")),
            "characters_present": parse_cid_list(kv.get("characters_present", kv.get("cast", ""))),
            "location_id": kv.get("location_id", "").strip(),
            "objects": parse_cid_list(kv.get("objects", "")),
            "beats": parse_int_list(kv.get("beats", "")),
            "beat": kv.get("beat", "").strip(),
            "style_target": kv.get("style_target", "").strip(),
            "acting_beat": kv.get("acting_beat", "").strip(),
            "layout_strategy": kv.get("layout_strategy", "").strip(),
            "visual_motif": kv.get("visual_motif", "").strip(),
            "sound_world": kv.get("sound_world", "").strip(),
        })
    return {"target_seconds": target, "scene_budget": budget, "scenes": scenes}


_BEAT_HEADER_RE = re.compile(r"^## Beat (\d+)\s*[—-]\s*(.*)$")


def parse_beat_board(md: str) -> dict[str, Any]:
    """Parse beat_board.md -> {target_seconds, beat_count, beats: [...]}."""
    lines = md.splitlines()
    head_end = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
    head_kv = _kv_lines("\n".join(lines[:head_end]))
    target = int(head_kv.get("target_seconds", "0") or 0)
    beat_count = int(head_kv.get("beat_count", "0") or 0)

    beats: list[dict[str, Any]] = []
    cur_beat: dict[str, Any] | None = None
    cur_block: list[str] = []

    def _flush() -> None:
        nonlocal cur_beat
        if cur_beat is None:
            return
        kv = _kv_lines("\n".join(cur_block))
        cur_beat["description"] = kv.get("description", "").strip()
        cur_beat["emotion"] = kv.get("emotion", "").strip().lower()
        try:
            cur_beat["estimated_seconds"] = int(kv.get("estimated_seconds", "0") or 0)
        except ValueError:
            cur_beat["estimated_seconds"] = 0
        beats.append(cur_beat)
        cur_beat = None

    for line in lines:
        bm = _BEAT_HEADER_RE.match(line)
        if bm:
            _flush()
            cur_beat = {
                "beat_num": int(bm.group(1)),
                "emotion_header": bm.group(2).strip(),
            }
            cur_block = []
            continue
        if line.startswith("## "):
            _flush()
            continue
        if cur_beat is not None:
            cur_block.append(line)
    _flush()

    return {"target_seconds": target, "beat_count": beat_count, "beats": beats}


def validate_beat_board(md: str, target_seconds: int | None = None) -> ValidationResult:
    res = ValidationResult()
    data = parse_beat_board(md)
    beats = data["beats"]
    declared_count = data["beat_count"]

    if not beats:
        res.error("no beats parsed")
        return res

    if len(beats) < 3:
        res.error(f"beat board has {len(beats)} beats; minimum is 3")

    if declared_count > 0 and declared_count != len(beats):
        res.error(
            f"beat_count ({declared_count}) != actual beat blocks ({len(beats)})"
        )

    # Sequential numbering
    for i, beat in enumerate(beats, start=1):
        if beat["beat_num"] != i:
            res.error(
                f"beat numbering not sequential: expected beat {i}, "
                f"found beat {beat['beat_num']}"
            )
            break

    seen_nums: set[int] = set()
    for beat in beats:
        num = beat["beat_num"]
        if num in seen_nums:
            res.error(f"duplicate beat number: {num}")
        seen_nums.add(num)

        label = f"beat {num}"
        if not beat["description"]:
            res.error(f"{label}: missing 'description:'")
        if not beat["emotion"]:
            res.error(f"{label}: missing 'emotion:'")
        elif beat["emotion"] not in BEAT_EMOTIONS:
            res.warn(
                f"{label}: emotion '{beat['emotion']}' not in suggested vocabulary "
                f"(accepted: {', '.join(BEAT_EMOTIONS[:8])}…)"
            )
        if beat["estimated_seconds"] <= 0:
            res.error(f"{label}: missing or invalid 'estimated_seconds:'")

    # Anti-sameness: 3+ consecutive identical emotions → warn
    for i in range(2, len(beats)):
        if (
            beats[i]["emotion"]
            and beats[i]["emotion"] == beats[i - 1]["emotion"] == beats[i - 2]["emotion"]
        ):
            res.warn(
                f"beats {i - 1}-{i + 1} all have emotion '{beats[i]['emotion']}' — "
                f"escalate or change the emotional register"
            )

    # Sum check (loose — 50% tolerance)
    if target_seconds and target_seconds > 0:
        total_est = sum(b["estimated_seconds"] for b in beats)
        if total_est > 0:
            ratio = total_est / target_seconds
            if ratio < 0.5 or ratio > 1.5:
                res.warn(
                    f"sum of estimated_seconds ({total_est}s) is outside 50% of "
                    f"target ({target_seconds}s)"
                )

    return res


_GEN_HEADER_RE = re.compile(r"^## Generation ([gb]\d+)\s*[—-]\s*(.*)$")
_SHOT_HEADER_RE = re.compile(r"^### Shot (\d+)\s*[—-]\s*([^()]*)(?:\((\w+)\))?\s*$")


def parse_storyboard(md: str) -> dict[str, Any]:
    """Parse storyboard_<scene>.md -> {scene_id, target_seconds, cast, generations}."""
    lines = md.splitlines()
    title = ""
    m = re.match(r"^# Scene (\S+)\s*[—-]\s*(.*)$", lines[0].strip()) if lines else None
    head_end = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
    head_kv = _kv_lines("\n".join(lines[:head_end]))
    scene_id = head_kv.get("scene_id", "").strip()
    if m:
        scene_id = scene_id or m.group(1)
        title = m.group(2).strip()

    generations: list[dict[str, Any]] = []
    handoff: dict[str, Any] = {}
    cur_gen: dict[str, Any] | None = None
    cur_shot: dict[str, Any] | None = None
    cur_block: list[str] = []
    in_handoff = False
    handoff_lines: list[str] = []

    def _flush_shot() -> None:
        nonlocal cur_shot
        if cur_shot is None:
            return
        kv = _kv_lines("\n".join(cur_block))
        cur_shot.update({
            "panels": parse_int_list(kv.get("panels", "")),
            "characters_present": parse_cid_list(kv.get("characters_present", "")),
            "action": kv.get("action", "").strip(),
            "camera": kv.get("camera", "").strip(),
            "audio": kv.get("audio", "").strip(),
            "dialogue": kv.get("dialogue", "").strip(),
            "shot_size": kv.get("shot_size", "").strip().lower(),
            "composition": [s.strip().lower() for s in kv.get("composition", "").split(",") if s.strip()],
            "acting_beat": kv.get("acting_beat", "").strip(),
            "layout": kv.get("layout", "").strip(),
            "screen_direction": kv.get("screen_direction", "").strip().lower(),
            "camera_angle": kv.get("camera_angle", "").strip().lower(),
            "focus": kv.get("focus", "").strip().lower(),
        })
        cur_gen["shots"].append(cur_shot)
        cur_shot = None

    def _flush_gen() -> None:
        nonlocal cur_gen
        _flush_shot()
        if cur_gen is not None:
            generations.append(cur_gen)
        cur_gen = None

    for line in lines:
        gm = _GEN_HEADER_RE.match(line)
        if gm:
            _flush_gen()
            in_handoff = False
            rng = _parse_range(gm.group(2))
            gid = gm.group(1)
            cur_gen = {
                "gen_id": gid,
                "is_bridge": gid.startswith("b"),
                "bridge_from": "",
                "bridge_to": "",
                "start": rng[0] if rng else None,
                "end": rng[1] if rng else None,
                "duration_seconds": None,
                "panel_grid": "",
                "shots": [],
            }
            cur_block = []
            continue
        if line.startswith("## "):
            _flush_gen()
            in_handoff = line[3:].strip().lower().startswith(("scene-end handoff", "handoff"))
            handoff_lines = []
            continue
        sm = _SHOT_HEADER_RE.match(line)
        if sm and cur_gen is not None:
            _flush_shot()
            rng = _parse_range(sm.group(2))
            cur_shot = {
                "shot": int(sm.group(1)),
                "start": rng[0] if rng else None,
                "end": rng[1] if rng else None,
                "transition": (sm.group(3) or "").strip().lower(),
            }
            cur_block = []
            continue
        if in_handoff:
            handoff_lines.append(line)
        if cur_gen is not None and cur_shot is None:
            kv = _kv_lines(line)
            if "duration_seconds" in kv:
                try:
                    cur_gen["duration_seconds"] = float(kv["duration_seconds"])
                except ValueError:
                    cur_gen["duration_seconds"] = -1.0
            if "panel_grid" in kv:
                cur_gen["panel_grid"] = kv["panel_grid"]
            if "bridge_from" in kv:
                cur_gen["bridge_from"] = kv["bridge_from"]
            if "bridge_to" in kv:
                cur_gen["bridge_to"] = kv["bridge_to"]
        cur_block.append(line)
    _flush_gen()

    if handoff_lines:
        hkv = _kv_lines("\n".join(handoff_lines))
        handoff = {
            "on_screen": parse_cid_list(hkv.get("on_screen", "")),
            "mood": hkv.get("mood", "").strip(),
            "transition": hkv.get("transition", "hard_cut").strip(),
        }
        nm = re.search(r"->\s*scene\s+(\S+)", "\n".join(handoff_lines))
        if nm:
            handoff["next_scene_id"] = nm.group(1).strip()

    return {
        "scene_id": scene_id,
        "title": title,
        "target_seconds": int(head_kv.get("target_seconds", "0") or 0),
        "cast": parse_cid_list(head_kv.get("cast", "")),
        "location_ref_id": head_kv.get("location_ref_id", "").strip(),
        "generations": generations,
        "handoff": handoff,
    }


def _parse_grid(text: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"(\d+)\s*[x×]\s*(\d+)", (text or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def validate_scenes(
    md: str,
    target_seconds: int | None = None,
    tolerance_percent: int = 15,
    beat_board_path: str | None = None,
) -> ValidationResult:
    res = ValidationResult()
    data = parse_scenes(md)
    scenes = data["scenes"]
    if not scenes:
        res.error("no scenes parsed")
        return res
    known_cids: set[str] = set()
    for sc in scenes:
        sid = sc["scene_id"]
        if not sid:
            res.error("a scene is missing scene_id")
        if sc["target_seconds"] <= 0:
            res.error(f"scene {sid}: target_seconds must be > 0")
        if not sc["cast"]:
            res.error(f"scene {sid}: cast is empty")
        if not sc["location_id"]:
            res.error(f"scene {sid}: location_id is missing")
        for field in SCENE_PRODUCTION_FIELDS:
            if not sc.get(field):
                res.error(
                    f"scene {sid}: {field} is missing — V4 scenes need anime-studio "
                    "style, acting, layout, motif, and sound direction"
                )
        known_cids.update(sc["cast"])
    if target_seconds is not None and target_seconds > 0:
        total = sum(sc["target_seconds"] for sc in scenes)
        if not duration_budget.within_tolerance(total, target_seconds, tolerance_percent):
            res.error(
                f"sum of scene targets ({total}s) is outside {tolerance_percent}% of run "
                f"target ({target_seconds}s)"
            )

    # Cross-check beats: field against beat_board.md if it exists
    beat_board_data: dict[str, Any] | None = None
    if beat_board_path and os.path.isfile(beat_board_path):
        beat_board_data = parse_beat_board(open(beat_board_path, encoding="utf-8").read())
    if beat_board_data and beat_board_data["beats"]:
        valid_beat_nums = {b["beat_num"] for b in beat_board_data["beats"]}
        covered: set[int] = set()
        for sc in scenes:
            for bn in sc.get("beats", []):
                if bn not in valid_beat_nums:
                    res.error(
                        f"scene {sc['scene_id']}: beats: references beat {bn} "
                        f"not in beat_board.md"
                    )
                if bn in covered:
                    res.error(
                        f"scene {sc['scene_id']}: beat {bn} already claimed by "
                        f"another scene — each beat belongs to exactly one scene"
                    )
                covered.add(bn)
        uncovered = valid_beat_nums - covered
        if uncovered:
            res.warn(
                f"beats {sorted(uncovered)} are not covered by any scene"
            )

    return res


def validate_storyboard(md: str, scenes: dict[str, Any] | None = None) -> ValidationResult:
    res = ValidationResult()
    sb = parse_storyboard(md)
    sid = sb["scene_id"] or "<unknown>"
    cast = set(sb["cast"])
    eps = duration_budget.TIME_EPS
    if not cast:
        res.error(f"scene {sid}: cast is empty")

    gens = sb["generations"]
    if not gens:
        res.error(f"scene {sid}: no '## Generation gN — a-b s' blocks parsed")
        return res

    prev_end = 0.0
    total = 0.0
    all_scene_panels: list[int] = []
    all_scene_shot_durations: list[float] = []  # ponytail: tracks shot lengths to detect mechanical uniform slicing across generations
    any_partial_gen_panels = False
    last_panel_count = None
    for gen in gens:
        gid = f"{sid}/{gen['gen_id']}"

        # --- Bridge generations are no longer supported ---
        if gen.get("is_bridge"):
            res.error(
                f"{gid}: bridge generations (bK) are no longer supported; "
                f"use sequential tail-video conditioning instead"
            )
            continue

        # --- Story generations: existing contiguity + duration checks ---
        if gen["start"] is None or gen["end"] is None:
            res.error(f"{gid}: header must carry a scene-relative time range (e.g. '## Generation g1 — 0.0-15.0s')")
            continue
        dur = gen["end"] - gen["start"]
        if abs(gen["start"] - prev_end) > eps:
            res.error(f"{gid}: starts at {gen['start']}s but previous generation ended at {prev_end}s (must be contiguous)")
        if not (duration_budget.GEN_MIN - eps <= dur <= duration_budget.GEN_MAX + eps):
            res.error(
                f"{gid}: duration {dur:.1f}s outside [{duration_budget.GEN_MIN:.0f},"
                f"{duration_budget.GEN_MAX:.0f}] — Minimax H3 renders at most "
                f"{duration_budget.GEN_MAX:.0f}s per generation"
            )
        if gen["duration_seconds"] is not None and abs(gen["duration_seconds"] - dur) > eps:
            res.error(f"{gid}: duration_seconds {gen['duration_seconds']} != header range ({dur:.1f}s)")
        grid = _parse_grid(gen["panel_grid"])
        panel_count = None
        if grid is None:
            res.error(f"{gid}: panel_grid missing or malformed (expected e.g. '2x3')")
        else:
            panel_count = grid[0] * grid[1]
            if not (duration_budget.PANELS_MIN <= panel_count <= duration_budget.PANELS_MAX):
                res.error(f"{gid}: panel_grid {gen['panel_grid']} gives {panel_count} panels, outside [{duration_budget.PANELS_MIN},{duration_budget.PANELS_MAX}]")

        shots = gen["shots"]
        if not shots:
            res.error(f"{gid}: no '### Shot N — a-b s (transition)' blocks")
        shot_prev_end = gen["start"]
        used_panels: list[int] = []
        gen_transitions: list[str] = []  # for anti-monotony
        prev_shot: dict[str, Any] | None = None
        for shot in shots:
            slabel = f"{gid} shot {shot['shot']}"
            if shot["start"] is None or shot["end"] is None:
                res.error(f"{slabel}: header must carry a time range")
                continue
            if abs(shot["start"] - shot_prev_end) > eps:
                res.error(f"{slabel}: starts at {shot['start']}s but previous shot ended at {shot_prev_end}s (shots must be contiguous)")
            if shot["end"] > gen["end"] + eps or shot["start"] < gen["start"] - eps:
                res.error(
                    f"{slabel}: range {shot['start']}-{shot['end']}s leaves generation "
                    f"{gen['start']}-{gen['end']}s — a shot must NEVER straddle a "
                    f"generation boundary; move it to the next generation"
                )
            shot_prev_end = shot["end"]
            trans = shot["transition"]
            if trans and trans not in SHOT_TRANSITIONS:
                res.error(f"{slabel}: transition {trans!r} not in {SHOT_TRANSITIONS}")
            if trans:
                gen_transitions.append(trans)

            # New-information rule (Ref2VA spec): a hard_cut between shots
            # sharing the same characters_present where only framing changes
            # should use camera_move / cut_on_action / reaction_cut instead.
            # With shot_size we can now distinguish:
            #   same chars + same shot_size + hard_cut → ERROR (framing-only)
            #   same chars + diff shot_size + hard_cut → OK (size change is new info)
            #   same chars + no shot_size + hard_cut → WARN (can't tell)
            if trans == "hard_cut" and prev_shot is not None:
                same_chars = set(shot.get("characters_present", [])) == set(prev_shot.get("characters_present", []))
                if same_chars:
                    prev_size = prev_shot.get("shot_size", "")
                    cur_size = shot.get("shot_size", "")
                    if prev_size and cur_size and prev_size == cur_size:
                        res.error(
                            f"{slabel}: hard_cut from shot {prev_shot['shot']} shares the same "
                            f"characters AND the same shot_size ({cur_size}) — this is a "
                            f"framing-only change. Use camera_move, cut_on_action, or "
                            f"reaction_cut instead."
                        )
                    elif not prev_size or not cur_size:
                        res.warn(
                            f"{slabel}: hard_cut from shot {prev_shot['shot']} shares the same "
                            f"characters — ensure the cut adds new information (subject, space, "
                            f"state, viewpoint, time). If only framing/angle changes, use "
                            f"camera_move, cut_on_action, or reaction_cut instead. "
                            f"Add shot_size to enable the definitive check."
                        )

            # match_cut must name the matched element in the action
            if trans == "match_cut" and not shot.get("action"):
                res.error(f"{slabel}: match_cut requires the matched element named in 'action:'")

            # audio_led requires the next shot's audio to be non-empty
            if trans == "audio_led" and not shot.get("audio"):
                res.error(f"{slabel}: audio_led transition requires a non-empty 'audio:' (the sound leads the cut)")

            # shot_size validation (optional but encouraged)
            ss = shot.get("shot_size", "")
            if ss and ss not in SHOT_SIZES:
                res.error(f"{slabel}: shot_size {ss!r} not in {SHOT_SIZES}")
            elif not ss:
                res.warn(f"{slabel}: missing 'shot_size:' (encouraged for new runs — see directors-guide Section 2)")

            # composition validation (optional but encouraged)
            comps = shot.get("composition", [])
            for comp in comps:
                if comp not in COMPOSITION_TYPES:
                    res.error(f"{slabel}: composition {comp!r} not in {COMPOSITION_TYPES}")
            if not comps:
                res.warn(f"{slabel}: missing 'composition:' (encouraged for new runs — see directors-guide Section 4)")

            # Anime-studio production fields turn action into stageable layout.
            if not shot.get("acting_beat"):
                res.error(f"{slabel}: missing 'acting_beat:' (anticipation → action → reaction/settle)")
            if not shot.get("layout"):
                res.error(f"{slabel}: missing 'layout:' (depth layers, eye path, silhouette)")
            direction = shot.get("screen_direction", "")
            if not direction:
                res.error(f"{slabel}: missing 'screen_direction:'")
            elif direction not in SCREEN_DIRECTIONS:
                res.error(f"{slabel}: screen_direction {direction!r} not in {SCREEN_DIRECTIONS}")

            ca = shot.get("camera_angle", "")
            if ca and ca not in CAMERA_ANGLES:
                res.error(f"{slabel}: camera_angle {ca!r} not in {CAMERA_ANGLES}")
            elif not ca:
                res.warn(f"{slabel}: missing 'camera_angle:' (encouraged for dynamic multi-angle cinematography)")

            # focus validation (advisory-only for missing, error if invalid value)
            foc = shot.get("focus", "")
            if foc and foc not in FOCUS_TYPES:
                res.error(f"{slabel}: focus {foc!r} not in {FOCUS_TYPES}")
            elif not foc:
                res.warn(f"{slabel}: missing 'focus:' (encouraged for cinematic depth control — see directors-guide Section 2)")
            if foc == "rack_focus" and shot.get("shot_size") == "extreme_closeup":
                res.warn(
                    f"{slabel}: rack_focus on an extreme_closeup has minimal focal depth — "
                    "rack focus typically requires medium, full, or wide staging across multiple planes"
                )

            if not shot["action"]:
                res.error(f"{slabel}: missing 'action:'")
            if not shot["camera"]:
                res.error(f"{slabel}: missing 'camera:'")
            elif not any(t in shot["camera"].lower() for t in MINIMAX_MOTION_TERMS):
                res.warn(f"{slabel}: camera has no recognized Minimax motion term (e.g. 'Push In', 'Tracking Shot', 'Static Shot')")
            if not shot["panels"] or -1 in shot["panels"]:
                res.error(f"{slabel}: missing/malformed 'panels:' list")
            else:
                used_panels.extend(shot["panels"])
            for c in shot["characters_present"]:
                if c not in cast:
                    res.error(f"{slabel}: characters_present has '{c}' not in scene cast")
            prev_shot = shot

        # Anti-monotony: 3+ consecutive identical transitions → warn
        if len(gen_transitions) >= 3:
            for i in range(len(gen_transitions) - 2):
                if gen_transitions[i] == gen_transitions[i + 1] == gen_transitions[i + 2]:
                    res.warn(
                        f"{gid}: shots {i+1}-{i+3} all use '{gen_transitions[i]}' — "
                        f"vary transitions to avoid monotony"
                    )
                    break
        # All transitions identical → warn
        if len(gen_transitions) >= 2 and len(set(gen_transitions)) == 1:
            res.warn(f"{gid}: all {len(gen_transitions)} transitions are '{gen_transitions[0]}' — vary transitions")

        # Anti-monotony: consecutive shots repeating eye_level camera angles
        for i in range(len(shots) - 1):
            ca1 = shots[i].get("camera_angle", "").strip()
            ca2 = shots[i + 1].get("camera_angle", "").strip()
            if ca1 and ca2 and ca1 == ca2 and ca1 == "eye_level":
                res.warn(
                    f"{gid}: consecutive shots {shots[i]['shot']} and {shots[i+1]['shot']} "
                    "both use 'eye_level' — static eye-level framing repeated across cuts reduces "
                    "cinematic dynamics; vary angles (e.g. low_angle, high_angle, three_quarter, dutch_angle)."
                )
                break

        # Anti-monotony: all shots in generation use identical camera angle
        gen_angles = [s.get("camera_angle", "").strip() for s in shots if s.get("camera_angle")]
        if len(shots) >= 2 and len(gen_angles) == len(shots) and len(set(gen_angles)) == 1:
            res.warn(
                f"{gid}: all {len(shots)} shots use identical camera_angle '{gen_angles[0]}' — "
                "vary camera angles (e.g. pair wide high-angle with low-angle or three-quarter close-up) "
                "for dynamic cinematography."
            )

        # Anti-monotony: all shots in generation use static camera framing
        gen_cameras = [s.get("camera", "").strip().lower() for s in shots if s.get("camera")]
        if len(shots) >= 2 and len(gen_cameras) == len(shots) and all("static shot" in c for c in gen_cameras):
            res.warn(
                f"{gid}: all {len(shots)} shots use static camera framing — incorporate motivated "
                "camera movement (e.g. Tracking Shot, Push In, Crane Up, Arc Shot) to enhance cinematic immersion."
            )

        # Anti-mechanical slicing: all shots in generation have identical duration
        gen_durations = [
            round(s["end"] - s["start"], 3)
            for s in shots
            if s.get("start") is not None and s.get("end") is not None
        ]
        all_scene_shot_durations.extend(gen_durations)
        if len(gen_durations) >= 3 and (max(gen_durations) - min(gen_durations)) < eps:
            res.warn(
                f"{gid}: all {len(gen_durations)} shots have identical duration ({gen_durations[0]:.1f}s) — "
                "avoid mechanical slicing; vary shot pacing according to dramatic tension and story rhythm."
            )

        if len(shots) > duration_budget.H3_RECOMMENDED_MAX_SHOTS:
            res.warn(
                f"{gid}: {len(shots)} shots exceed V4's recommended H3 pacing "
                f"limit of {duration_budget.H3_RECOMMENDED_MAX_SHOTS}; use dense "
                "cuts only for intentional montage."
            )
        for shot in shots:
            if shot["start"] is not None and shot["end"] is not None:
                shot_duration = shot["end"] - shot["start"]
                if shot_duration > duration_budget.H3_RECOMMENDED_MAX_SHOT_SECONDS:
                    res.warn(
                        f"{gid} shot {shot['shot']}: {shot_duration:.1f}s exceeds "
                        f"V4's recommended {duration_budget.H3_RECOMMENDED_MAX_SHOT_SECONDS:.1f}s "
                        "H3 shot length; use sustained action or camera progression."
                    )
        if shots and shots[-1]["end"] is not None and abs(shots[-1]["end"] - gen["end"]) > eps:
            res.error(f"{gid}: last shot ends at {shots[-1]['end']}s, generation ends at {gen['end']}s (must fill the generation)")
        if panel_count is not None and used_panels:
            last_panel_count = panel_count
            all_scene_panels.extend(used_panels)
            expected = list(range(1, panel_count + 1))
            if sorted(used_panels) != expected:
                is_valid_slice = (
                    sorted(used_panels) == list(range(min(used_panels), max(used_panels) + 1))
                    and 1 <= min(used_panels) and max(used_panels) <= panel_count
                )
                if is_valid_slice:
                    any_partial_gen_panels = True
                else:
                    res.error(f"{gid}: shots use panels {sorted(used_panels)}; must use each of 1..{panel_count} exactly once")
            if used_panels != sorted(used_panels):
                res.error(f"{gid}: panels must be assigned in column-major order (top-to-bottom within each column, then left-to-right) across shots")
        prev_end = gen["end"]
        total = gen["end"]

    if any_partial_gen_panels and last_panel_count is not None:
        expected_scene = list(range(1, last_panel_count + 1))
        if sorted(all_scene_panels) != expected_scene:
            res.error(
                f"scene {sid}: shots across all generations use panels {sorted(all_scene_panels)}; "
                f"must use each of 1..{last_panel_count} exactly once"
            )

    if not sb["handoff"]:
        res.error(f"scene {sid}: scene-end handoff block is missing")

    if sb["target_seconds"] > 0 and abs(total - sb["target_seconds"]) > eps:
        res.error(f"scene {sid}: generations cover {total:.1f}s != target_seconds ({sb['target_seconds']}s)")

    # Anti-mechanical slicing across generations in a scene
    # ponytail: O(N) duration spread scan to prevent uniform slicing across scenes
    if len(gens) >= 2 and len(all_scene_shot_durations) >= 4 and (max(all_scene_shot_durations) - min(all_scene_shot_durations)) < eps:
        res.warn(
            f"scene {sid}: mechanical uniform shot slicing detected across all {len(all_scene_shot_durations)} shots "
            f"({all_scene_shot_durations[0]:.1f}s each) — vary shot durations dynamically based on dramatic beats."
        )

    # Cross-check against scenes.md if provided.
    if scenes:
        scene_meta = next((s for s in scenes["scenes"] if s["scene_id"] == sid), None)
        if scene_meta is None:
            res.error(f"scene {sid}: not found in scenes.md")
        else:
            if abs(total - scene_meta["target_seconds"]) > eps:
                res.error(
                    f"scene {sid}: storyboard total {total:.1f}s != scenes.md target "
                    f"{scene_meta['target_seconds']}s"
                )
            if sb["location_ref_id"] and scene_meta["location_id"] and sb["location_ref_id"] != scene_meta["location_id"]:
                res.error(
                    f"scene {sid}: location_ref_id {sb['location_ref_id']!r} != scenes.md "
                    f"location_id {scene_meta['location_id']!r}"
                )
    return res


# ---------------------------------------------------------------------------
# Action drift detection — checks that key action words from the storyboard's
# `action:` fields appear in the corresponding image-prompt panel descriptions.
# ---------------------------------------------------------------------------

# Common English stop words to filter out when extracting significant words.
_DRIFT_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to", "for",
    "with", "by", "from", "as", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "can", "shall", "this", "that",
    "these", "those", "it", "its", "he", "she", "they", "them", "his", "her",
    "their", "our", "your", "my", "me", "him", "us", "i", "you", "we",
    "not", "no", "nor", "so", "than", "too", "very", "just", "also", "only",
    "up", "down", "out", "off", "over", "under", "into", "onto", "upon",
    "through", "between", "among", "during", "before", "after", "above",
    "below", "near", "far", "here", "there", "where", "when", "while",
    "about", "against", "around", "along", "across", "behind", "beside",
    "which", "who", "whom", "what", "whose", "how", "why",
    "all", "both", "each", "few", "more", "most", "other", "some", "such",
    "any", "every", "either", "neither", "one", "two", "three",
    "four", "five", "six", "seven", "eight", "nine", "ten",
    "s", "t", "d", "ll", "ve", "re", "m",
    "then", "now", "still", "back", "away",
})

_DRIFT_MIN_ACTION_WORDS = 3  # minimum significant words to check per shot
_DRIFT_MIN_HIT_FRACTION = 0.40  # at least 40% of action words must appear


def _extract_action_words(action_text: str) -> list[str]:
    """Extract significant words (verbs, adjectives, adverbs) from an action line.

    Filters out stop words and short tokens. Returns lowercase words in
    order of appearance, deduplicated.
    """
    raw = re.split(r"[^a-zA-Z]+", action_text.lower())
    seen: set[str] = set()
    words: list[str] = []
    for w in raw:
        if len(w) < 3:
            continue
        if w in _DRIFT_STOP_WORDS:
            continue
        if w in seen:
            continue
        seen.add(w)
        words.append(w)
    return words


def _extract_panel_text(prompt_text: str) -> str:
    """Extract the panel description text from a storyboard sheet prompt.

    Returns the text under each `### PANEL N` or `Panel N (...) :` heading
    (lowercased), which is where Agent 4 describes the visual content.
    """
    lines: list[str] = []
    in_panel = False
    for raw_line in prompt_text.splitlines():
        line = raw_line.rstrip()
        # Start of a panel direction block
        if re.match(r"###\s+PANEL\s+\d+", line, re.IGNORECASE):
            in_panel = True
            continue
        # Old-style "Panel N (...): description"
        m = re.match(r"Panel\s+\d+\s*\([^)]*\)\s*:\s*(.*)", line, re.IGNORECASE)
        if m:
            lines.append(m.group(1).strip())
            in_panel = False
            continue
        # End of panel directions when we hit another major heading
        if in_panel and re.match(r"^#{2,3}\s+", line):
            in_panel = False
        if in_panel and line:
            lines.append(line)
    return " ".join(lines).lower()


def check_action_drift(
    sb: dict[str, Any], gen: dict[str, Any], prompt_text: str,
) -> list[str]:
    """Check that key action words from the storyboard appear in the sheet prompt.

    Returns a list of warning messages (empty if no drift detected).
    """
    shots = gen["shots"]
    panel_text = _extract_panel_text(prompt_text)
    if not panel_text:
        return []  # can't check if no panel lines found

    warnings: list[str] = []
    for shot in shots:
        action = shot.get("action", "")
        if not action:
            continue
        action_words = _extract_action_words(action)
        if len(action_words) < _DRIFT_MIN_ACTION_WORDS:
            continue  # not enough significant words to check

        hits = sum(1 for w in action_words if w in panel_text)
        min_hits = max(1, int(len(action_words) * _DRIFT_MIN_HIT_FRACTION))
        if hits < min_hits:
            missing = [w for w in action_words if w not in panel_text][:5]
            warnings.append(
                f"action drift: shot {shot['shot']} action words not found in "
                f"panel descriptions: {missing}"
            )
    return warnings


def _check_prompt_quality(prompt_text: str) -> list[str]:
    """Return warnings for prompt-quality issues (brand refs, excessive negatives)."""
    warnings: list[str] = []
    lower = prompt_text.lower()
    # Brand/studio references: describe craft attributes, never imitate a named studio.
    for brand in _PROHIBITED_STYLE_BRANDS:
        if brand in lower:
            warnings.append(f"prompt uses brand reference '{brand}'; replace with concrete visual attributes")
    # Excessive negatives: find HARD EXCLUSIONS section and count "no ..." constraints
    section_lines: list[str] = []
    in_section = False
    for raw_line in prompt_text.splitlines():
        line = raw_line.rstrip()
        if not in_section and re.match(r"##\s+HARD\s+EXCLUSIONS\s*$", line, re.IGNORECASE):
            in_section = True
            continue
        if in_section:
            if re.match(r"##\s+", line) or line.startswith("SPATIAL CONTINUITY BIBLE") or line.startswith("END SPATIAL"):
                break
            if line:
                section_lines.append(line)
    section = " ".join(section_lines)
    no_count = len(re.findall(r"\bno\s+\w+", section, re.IGNORECASE))
    if no_count > 20:
        warnings.append(f"HARD EXCLUSIONS/negatives has {no_count} 'no ...' constraints; keep the list short and surgical")
    return warnings


def validate_prompts(
    run_dir: str,
    scene_id: str,
    sb: dict[str, Any] | None = None,
    object_ids: list[str] | None = None,
) -> ValidationResult:
    """Validate pre-generation prompts: char sheets + location lock + object
    sheets + one storyboard sheet prompt PER GENERATION.

    When a spatial plan exists, also validates that each normal generation's
    sheet prompt contains a materialized spatial continuity block.
    """
    from . import image_pipeline

    res = ValidationResult()
    if sb is None:
        res.error("prompts validation requires the parsed storyboard")
        return res
    cast = set(sb["cast"])
    loc = sb["location_ref_id"]

    for cid in cast:
        p = image_pipeline.character_prompt_path(run_dir, cid)
        if not os.path.isfile(p) or not image_pipeline.read_prompt(p):
            res.error(f"missing character prompt for {cid}: {p}")
    if loc:
        p = image_pipeline.location_prompt_path(run_dir, loc)
        if not os.path.isfile(p) or not image_pipeline.read_prompt(p):
            res.error(f"missing location prompt for {loc}: {p}")
    for oid in (object_ids or []):
        p = image_pipeline.object_prompt_path(run_dir, oid)
        if not os.path.isfile(p) or not image_pipeline.read_prompt(p):
            res.error(f"missing object prompt for {oid}: {p}")

    # Check for spatial plan and materialized blocks
    spatial_plan_path = os.path.join(run_dir, f"spatial_plan_{scene_id}.md")
    plan = None
    if os.path.isfile(spatial_plan_path):
        from .spatial_validator import parse_spatial_plan
        plan = parse_spatial_plan(open(spatial_plan_path, encoding="utf-8").read())

    seen_prompt_files: set[str] = set()
    for gen in sb["generations"]:
        gid = gen["gen_id"]
        sheet_p = image_pipeline.sheet_prompt_path(run_dir, scene_id, gid)
        if not os.path.isfile(sheet_p) or not image_pipeline.read_prompt(sheet_p):
            res.error(f"missing storyboard sheet prompt for {gid}: {sheet_p}")
            continue

        prompt_text = image_pipeline.read_prompt(sheet_p)

        # Validate materialized spatial block for normal generations
        if plan and not gen.get("is_bridge") and gid in plan.get("generations", {}):
            from .spatial_prompt_builder import validate_materialized_prompt
            errors = validate_materialized_prompt(prompt_text, plan, sb, gid)
            for e in errors:
                res.error(f"{scene_id}/{gid}: {e}")

        # Check for action drift (softening of storyboard action verbs)
        if not gen.get("is_bridge"):
            drift_warnings = check_action_drift(sb, gen, prompt_text)
            for w in drift_warnings:
                res.warn(f"{scene_id}/{gid}: {w}")

        # Prompt-quality checks (run once per distinct sheet prompt file)
        if sheet_p not in seen_prompt_files:
            seen_prompt_files.add(sheet_p)
            quality_warnings = _check_prompt_quality(prompt_text)
            for w in quality_warnings:
                res.warn(f"{scene_id}/{gid}: {w}")

    return res


_PROMPT_SHOT_RE = re.compile(
    r"^SHOT\s+(\d+)\s*[—-]\s*(\d+(?:\.\d+)?)\s*[–—-]\s*(\d+(?:\.\d+)?)\s*s",
    re.M | re.I,
)

_BRIEF_SHOT_RE = re.compile(
    r"^SHOT\s+(\d+)\s*[—–-]\s*(\d+(?:\.\d+)?)\s*[—–-]\s*(\d+(?:\.\d+)?)\s*s",
    re.M | re.I,
)

# 6-section Ref2VA contract — exact order, lowercase field names with colons.
_REF2VA_SECTIONS = (
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
)

# Valid task-type prefixes for the summary section (Ref2VA spec).
_REF2VA_TASK_TYPES = (
    "keyframe completion", "reference generation", "video editing",
    "video continuation", "audio reuse", "audio reference",
)

# Valid retention markers (Ref2VA spec SECTION 3).
_RETENTION_MARKERS_VISUAL = ("fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference")
_RETENTION_MARKERS_AUDIO = ("fully_copy", "partially_copy", "reference", "weak_reference")

# [Shot N] At MM:SS.mmm — generation-local timestamps in the detailed_description.
_REF2VA_SHOT_RE = re.compile(r"\[Shot\s+(\d+)\](?:\s+At\s+(\d{2}):(\d{2})\.(\d{3}))?", re.I)

# <Subject N> / <Picture N> / <Video N> / <Audio N> label references.
_LABEL_RE = re.compile(r"<(Subject|Picture|Video|Audio)\s+(\d+)>")

# <d>[Language] ... </d> dialogue tags.
_DIALOGUE_RE = re.compile(r"<d>\s*\[(\w+)\]\s*(.*?)\s*</d>", re.S)

# House style prohibits studio/brand imitation; describe craft attributes instead.
_PROHIBITED_STYLE_BRANDS = ("pixar", "disney", "dreamworks", "ghibli")

# Prompt-stuffing keywords discouraged in MiniMax H3 (community best practice).
_PROMPT_STUFFING_PATTERNS = [
    re.compile(r"\bmasterpiece\b", re.I),
    re.compile(r"\btrending on artstation\b", re.I),
    re.compile(r"\bunreal engine\b", re.I),
    re.compile(r"\boctane render\b", re.I),
    re.compile(r"\bhyperrealistic\b", re.I),
    re.compile(r"\b(?:4k|8k)\s+(?:resolution|uhd|quality)\b", re.I),
]


def validate_video_prompt_legacy(text: str, sb: dict[str, Any], gen_id: str) -> ValidationResult:
    """Legacy 4-part validator (Reference / Timeline / Negative Prompt).

    Retained for --legacy validation of pre-Ref2VA runs.
    """
    res = ValidationResult()
    eps = 0.15
    gen = next((g for g in sb.get("generations", []) if g["gen_id"] == gen_id), None)
    if gen is None:
        res.error(f"generation {gen_id!r} not found in storyboard")
        return res
    if not text.strip():
        res.error("video prompt is empty")
        return res

    low = text.lower()
    if "storyboard" not in low:
        res.error("prompt must instruct the model to use the provided storyboard as the visual reference")
    if "timeline" not in low:
        res.error("prompt must contain a 'Timeline' section")
    if "negative prompt" not in low:
        res.error("prompt must contain a 'Negative Prompt' section")
    for tok in sorted(set(re.findall(r"char_\d+", text))):
        res.error(f"prompt references internal id {tok!r} — describe characters by appearance instead")

    shots = _PROMPT_SHOT_RE.findall(text)
    sb_shots = gen["shots"]
    if len(shots) != len(sb_shots):
        res.error(f"prompt has {len(shots)} SHOT blocks, storyboard generation {gen_id} has {len(sb_shots)}")
    gen_start = gen["start"] or 0.0
    gen_dur = (gen["end"] or 0.0) - gen_start
    for (num, a, b), sb_shot in zip(shots, sb_shots):
        a, b = float(a), float(b)
        want_a = (sb_shot["start"] or 0.0) - gen_start
        want_b = (sb_shot["end"] or 0.0) - gen_start
        if abs(a - want_a) > eps or abs(b - want_b) > eps:
            res.error(
                f"SHOT {num}: prompt range {a}-{b}s != storyboard shot range "
                f"{want_a:.1f}-{want_b:.1f}s (generation-local seconds)"
            )
        if b > duration_budget.GEN_MAX + eps:
            res.error(f"SHOT {num}: ends at {b}s — beyond the {duration_budget.GEN_MAX:.0f}s Minimax limit")
    if shots:
        last_end = float(shots[-1][2])
        if abs(last_end - gen_dur) > eps:
            res.error(f"last SHOT ends at {last_end}s, generation duration is {gen_dur:.1f}s")
    return res


def _parse_ref2va_sections(text: str) -> dict[str, str]:
    """Split a Ref2VA prompt into its 6 sections. Returns {section_name: body}."""
    sections: dict[str, str] = {}
    # Find each section header at the start of a line (lowercase, ends with colon)
    positions: list[tuple[str, int]] = []
    for i, line in enumerate(text.splitlines()):
        stripped = line.strip().lower()
        for sec in _REF2VA_SECTIONS:
            if stripped == f"{sec}:" or stripped.startswith(f"{sec}:"):
                positions.append((sec, i))
                break
    for idx, (sec, line_i) in enumerate(positions):
        start = line_i + 1
        end = positions[idx + 1][1] if idx + 1 < len(positions) else len(text.splitlines())
        body = "\n".join(text.splitlines()[start:end]).strip()
        sections[sec] = body
    return sections

def is_directors_brief(text: str) -> bool:
    """Detect if a video prompt is in the Director's Brief format."""
    if "summary:" in text and "retention_analysis:" in text and "detailed_description:" in text:
        return False
    if "Timeline" in text or "timeline" in text.lower():
        if "negative prompt" not in text.lower():
            return True
    return bool(re.search(r"^\s*subject_definitions\s*:\s*Reference\b", text, re.M | re.I))


def validate_video_prompt_brief(text: str, sb: dict[str, Any], gen_id: str) -> ValidationResult:
    """Validate a Director's Brief format video prompt against the storyboard.

    Format structure:
    - subject_definitions:Reference header
    - Identity statements ("Maintain the exact appearance of...")
    - Preamble with style & quality declarations (no prohibited brand names)
    - Optional g2+ continuation statement
    - Timeline section header
    - Contiguous SHOT blocks with timestamps (SHOT N — start–ends (Continuous Shot))
    - Dedicated Audio: line per shot
    - Dialogue formatting with speaker IDs
    """
    res = ValidationResult()
    eps = 0.15
    gen = next((g for g in sb.get("generations", []) if g["gen_id"] == gen_id), None)
    if gen is None:
        res.error(f"generation {gen_id!r} not found in storyboard")
        return res
    if not text.strip():
        res.error("video prompt is empty")
        return res

    # char_NN rejection
    for tok in sorted(set(re.findall(r"char_\d+", text))):
        res.error(f"prompt references internal id {tok!r} — describe characters by appearance instead")

    # Prohibited studio / brand names check
    for brand in _PROHIBITED_STYLE_BRANDS:
        if re.search(rf"\b{re.escape(brand)}\b", text, re.IGNORECASE):
            res.error(
                f"prompt uses brand reference '{brand}'; describe concrete animation "
                "craft (line, shape, color, timing, materials) instead"
            )

    # Header check
    if not re.search(r"^\s*subject_definitions\s*:\s*Reference\b", text, re.MULTILINE | re.IGNORECASE):
        if not re.search(r"^\s*subject_definitions\s*:", text, re.MULTILINE | re.IGNORECASE):
            res.error("prompt must start with 'subject_definitions:Reference'")

    # Visual guide reference to storyboard
    if "storyboard" not in text.lower():
        res.error("prompt must reference the provided storyboard as visual guide")

    # Timeline section header
    timeline_match = re.search(r"^\s*Timeline\s*$", text, re.MULTILINE | re.IGNORECASE)
    if not timeline_match:
        res.error("prompt must contain a 'Timeline' section header")
        return res

    timeline_start = timeline_match.end()
    timeline_text = text[timeline_start:]
    preamble_text = text[:timeline_match.start()]

    # Check for identity descriptions in preamble
    if "maintain the exact appearance" not in preamble_text.lower():
        res.warn("preamble should include 'Maintain the exact appearance of [Character]: ...' identity descriptions")

    # g2+ continuation check
    gen_index = next(
        (i for i, g in enumerate(sb.get("generations", [])) if g.get("gen_id") == gen_id),
        0,
    )
    if gen_index > 0:
        if "continuation" not in preamble_text.lower() and "continuation" not in timeline_text[:300].lower():
            res.error(
                f"generation {gen_id} must declare seamless continuation from the previous generation "
                "(e.g. 'This is a seamless continuation from the previous generation.')"
            )

    # Shots parsing in Timeline
    shot_headers = list(_BRIEF_SHOT_RE.finditer(timeline_text))
    sb_shots = gen.get("shots", [])
    if len(shot_headers) != len(sb_shots):
        res.error(
            f"Timeline has {len(shot_headers)} SHOT blocks, "
            f"storyboard generation {gen_id} has {len(sb_shots)}"
        )

    gen_start = gen.get("start") or 0.0
    gen_dur = (gen.get("end") or 0.0) - gen_start

    # Validate shot ranges and extract shot bodies
    prev_end = 0.0
    for i, m in enumerate(shot_headers):
        s_num = int(m.group(1))
        start = float(m.group(2))
        end = float(m.group(3))

        if s_num != i + 1:
            res.error(f"SHOT {s_num} out of order — expected SHOT {i+1}")

        if i == 0 and abs(start - 0.0) > eps:
            res.error(f"SHOT 1 must start at 0.0s (got {start}s)")
        elif i > 0 and abs(start - prev_end) > eps:
            res.error(f"SHOT {s_num} start {start}s != previous shot end {prev_end}s (shots must be contiguous)")

        if end <= start:
            res.error(f"SHOT {s_num} end {end}s must be greater than start {start}s")

        if i < len(sb_shots):
            want_start = (sb_shots[i].get("start") or 0.0) - gen_start
            want_end = (sb_shots[i].get("end") or 0.0) - gen_start
            if abs(start - want_start) > eps:
                res.error(
                    f"SHOT {s_num} start {start:.1f}s != storyboard shot start {want_start:.1f}s "
                    "(generation-local seconds)"
                )
            if abs(end - want_end) > eps:
                res.error(
                    f"SHOT {s_num} end {end:.1f}s != storyboard shot end {want_end:.1f}s "
                    "(generation-local seconds)"
                )

        if end > duration_budget.GEN_MAX + eps:
            res.error(f"SHOT {s_num} ends at {end}s — beyond the {duration_budget.GEN_MAX:.0f}s Minimax limit")

        prev_end = end

        # Extract shot body up to next shot header or end of timeline
        body_start = m.end()
        body_end = shot_headers[i + 1].start() if i + 1 < len(shot_headers) else len(timeline_text)
        shot_body = timeline_text[body_start:body_end]

        # Check for Audio line in shot body
        if not re.search(r"^\s*Audio\s*:", shot_body, re.MULTILINE | re.IGNORECASE):
            res.error(f"SHOT {s_num} missing an 'Audio:' line for Foley/sound/dialogue direction")

    if shot_headers:
        last_end = float(shot_headers[-1].group(3))
        if abs(last_end - gen_dur) > eps:
            res.error(f"last SHOT ends at {last_end:.1f}s, generation duration is {gen_dur:.1f}s")

    # Dialogue tags check
    for m in _DIALOGUE_RE.finditer(text):
        lang = m.group(1)
        if not lang:
            res.error(f"<d> tag missing language code: {m.group(0)[:50]}")
        pre = text[max(0, m.start() - 220):m.start()]
        if not re.search(r"\((?:S\d+,?)+\)", pre) and not re.search(r"\b(?:S\d+)\b", pre):
            res.error("dialogue must attribute a speaker ID like (S1) before each <d> tag")

    # Prompt stuffing patterns warning
    for pat in _PROMPT_STUFFING_PATTERNS:
        match = pat.search(text)
        if match:
            res.warn(
                f"prompt contains quality tag {match.group(0)!r}; MiniMax H3 adheres "
                "best to natural descriptive prose rather than prompt-stuffing tags"
            )

    # Word count check on Timeline
    timeline_words = len(timeline_text.split())
    if timeline_words < 120:
        res.warn(
            f"Timeline has {timeline_words} words; optimal depth for MiniMax H3 is "
            "350-500 words to guide Context-IR"
        )
    elif timeline_words > 650:
        res.warn(
            f"Timeline has {timeline_words} words; exceeding ~500-600 words may dilute "
            "temporal conditioning focus"
        )

    return res


def validate_video_prompt(text: str, sb: dict[str, Any], gen_id: str) -> ValidationResult:
    """Validate a video prompt (Ref2VA or Director's Brief) against the storyboard."""
    if is_directors_brief(text):
        return validate_video_prompt_brief(text, sb, gen_id)

    res = ValidationResult()
    eps = 0.15
    gen = next((g for g in sb.get("generations", []) if g["gen_id"] == gen_id), None)
    if gen is None:
        res.error(f"generation {gen_id!r} not found in storyboard")
        return res
    if not text.strip():
        res.error("video prompt is empty")
        return res


    # char_NN rejection (carried from legacy)
    for tok in sorted(set(re.findall(r"char_\d+", text))):
        res.error(f"prompt references internal id {tok!r} — describe characters by appearance instead")

    # --- Section presence and order ---
    sections = _parse_ref2va_sections(text)
    found = list(sections.keys())
    if found != list(_REF2VA_SECTIONS):
        missing = set(_REF2VA_SECTIONS) - set(found)
        extra = set(found) - set(_REF2VA_SECTIONS)
        if missing:
            res.error(f"missing Ref2VA section(s): {sorted(missing)}")
        if extra:
            res.error(f"unexpected section(s): {sorted(extra)}")
        if found and found != list(_REF2VA_SECTIONS):
            res.error(f"sections out of order: {found} (expected {list(_REF2VA_SECTIONS)})")
        return res  # can't validate further without sections

    # --- summary: must open with a bracketed task-type prefix ---
    summary = sections["summary"]
    task_prefixes = re.findall(r"\[([^\]]+)\]", summary[:100])
    if not task_prefixes:
        res.error("summary must open with a bracketed task-type prefix (e.g. '[reference generation]')")
    else:
        for prefix in task_prefixes:
            parts = [p.strip() for p in prefix.split("+")]
            for p in parts:
                if p not in _REF2VA_TASK_TYPES:
                    res.error(f"summary task type {p!r} not in {_REF2VA_TASK_TYPES}")

    # --- subject_definitions: collect defined labels ---
    sd_text = sections["subject_definitions"]
    defined_labels: dict[str, str] = {}
    for m in _LABEL_RE.finditer(sd_text):
        defined_labels[f"{m.group(1)} {m.group(2)}"] = m.group(1)
    if "Picture 1" not in defined_labels:
        res.error("subject_definitions must define <Picture 1> as the storyboard sheet reference")
    else:
        pic_line = next(
            (line for line in sd_text.splitlines() if re.match(r"^\s*<\s*Picture\s+1\s*>", line)),
            "",
        )
        if "[Shot" not in pic_line or "storyboard" not in pic_line.lower():
            res.error(
                "<Picture 1> definition must map the storyboard to its shots "
                "(e.g. 'storyboard reference for [Shot 1] and [Shot 2], defining "
                "viewpoint, placement, and shot order')"
            )

    for section_name in ("summary", "detailed_description", "overall_soundscape", "non_diegetic_music"):
        for m in _LABEL_RE.finditer(sections[section_name]):
            label = f"{m.group(1)} {m.group(2)}"
            if label not in defined_labels:
                res.error(f"{section_name} references {m.group(0)} not defined in subject_definitions")

    gen_index = next(
        (i for i, g in enumerate(sb.get("generations", [])) if g.get("gen_id") == gen_id),
        0,
    )
    if gen_index > 0 and "Video 1" not in defined_labels:
        res.error(
            f"generation {gen_id} receives the previous rendered tail; define "
            "<Video 1> as that video-continuation reference"
        )
    if gen_index > 0 and "video continuation" not in summary.lower():
        res.error(
            f"generation {gen_id} summary must include the task type "
            "'video continuation' for its rendered tail reference"
        )

    for brand in _PROHIBITED_STYLE_BRANDS:
        if re.search(rf"\b{re.escape(brand)}\b", text, re.IGNORECASE):
            res.error(
                f"prompt uses brand reference '{brand}'; describe concrete animation "
                "craft (line, shape, color, timing, materials) instead"
            )

    # --- retention_analysis: check labels and fixed markers ---
    ra_text = sections["retention_analysis"]
    if not re.search(r"<Picture\s+1>.*(?:storyboard|panel|composition)", ra_text, re.IGNORECASE):
        res.error("retention_analysis must state that <Picture 1> preserves the storyboard panel sequence or composition")
    for label, kind in defined_labels.items():
        label_lines = [
            line for line in ra_text.splitlines()
            if re.search(rf"<\s*{kind}\s+{label.split()[1]}\s*>", line)
        ]
        if not label_lines:
            res.error(f"retention_analysis is missing an entry for <{label}>")
            continue
        allowed = _RETENTION_MARKERS_AUDIO if kind == "Audio" else _RETENTION_MARKERS_VISUAL
        if not any(any(marker in line for marker in allowed) for line in label_lines):
            res.error(f"retention_analysis for <{label}> lacks a fixed {kind} relationship marker")
    for line in ra_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Check for label presence
        for m in _LABEL_RE.finditer(line):
            label = f"{m.group(1)} {m.group(2)}"
            if label not in defined_labels:
                res.error(f"retention_analysis references {m.group(0)} not defined in subject_definitions")
        # Check markers
        for marker in _RETENTION_MARKERS_VISUAL + _RETENTION_MARKERS_AUDIO:
            if marker in line:
                break
        else:
            if line and not line.startswith("<"):
                pass  # not every line needs a marker

    # --- detailed_description: shots, timestamps, labels ---
    dd_text = sections["detailed_description"]
    dd_shots = _REF2VA_SHOT_RE.findall(dd_text)
    sb_shots = gen["shots"]
    if len(dd_shots) != len(sb_shots):
        res.error(
            f"detailed_description has {len(dd_shots)} [Shot N] blocks, "
            f"storyboard generation {gen_id} has {len(sb_shots)}"
        )

    # [Shot 1] must have no timestamp; later shots must have MM:SS.mmm
    gen_start = gen["start"] or 0.0
    gen_dur = (gen["end"] or 0.0) - gen_start
    prev_time = 0.0  # Shot 1 implicitly starts at 0.0
    for i, (num, mm, ss, mmm) in enumerate(dd_shots):
        shot_num = int(num)
        if shot_num != i + 1:
            res.error(f"[Shot {num}] out of order — expected [Shot {i+1}]")
        if i == 0:
            if mm:  # Shot 1 must not have a timestamp
                res.error(f"[Shot 1] must not carry a timestamp (got {mm}:{ss}.{mmm})")
        else:
            if not mm:
                res.error(f"[Shot {shot_num}] must have a timestamp 'At MM:SS.mmm'")
            else:
                t = int(mm) * 60 + int(ss) + int(mmm) / 1000.0
                if t <= prev_time:
                    res.error(f"[Shot {shot_num}] timestamp {mm}:{ss}.{mmm} not strictly increasing (prev was {prev_time:.3f}s)")
                # Check against storyboard shot start (generation-local)
                if i < len(sb_shots):
                    want = (sb_shots[i]["start"] or 0.0) - gen_start
                    if abs(t - want) > eps:
                        res.error(
                            f"[Shot {shot_num}] timestamp {t:.3f}s != storyboard shot start "
                            f"{want:.3f}s (generation-local)"
                        )
                prev_time = t

    # Check labels used in detailed_description are defined (also checked above).
    for m in _LABEL_RE.finditer(dd_text):
        label = f"{m.group(1)} {m.group(2)}"
        if label not in defined_labels:
            res.error(f"detailed_description references {m.group(0)} not defined in subject_definitions")

    # --- dialogue tags: <d>[Lang] ...</d> with stable speaker IDs ---
    for m in _DIALOGUE_RE.finditer(dd_text):
        lang = m.group(1)
        if not lang:
            res.error(f"<d> tag missing language code: {m.group(0)[:50]}")
        pre = dd_text[max(0, m.start() - 220):m.start()]
        if not re.search(r"\((?:S\d+,?)+\)", pre):
            res.error("dialogue must attribute a stable speaker ID like (S1) before each <d> tag")
        if "voiceover" in pre.lower():
            if "says in an off-screen voiceover" not in pre:
                res.error("voiceover must use the exact phrase 'says in an off-screen voiceover'")
            post = dd_text[m.end():m.end() + 160].lower()
            if "lips remain" not in post or "closed" not in post:
                res.error("voiceover must state that the on-screen character's lips remain closed")

    # --- audio layer separation (official guide) ---
    os_text = sections["overall_soundscape"]
    if re.search(r"\b(music|score|orchestral|strings|piano|melody|motif|tempo)\b", os_text, re.I):
        res.error("overall_soundscape contains score/music terms — move audience-only music to non_diegetic_music")
    music_text = sections["non_diegetic_music"].strip()
    if music_text and music_text.upper() != "N/A":
        if not re.search(r"\b(piano|strings|violin|cello|synth|drums?|percussion|guitar|flute|brass|choir|pulse|motif|tempo|bpm)\b", music_text, re.I):
            res.error("non_diegetic_music must name instrumentation and tempo/rhythm, not mood words")
        elif re.search(r"\b(uplifting|sad|happy|tense|emotional|heartwarming)\b", music_text, re.I):
            res.warn("non_diegetic_music uses abstract mood words; prefer instrumentation, tempo, and dynamics")

    # --- overall_soundscape and non_diegetic_music: must be present (N/A ok) ---
    if not sections["overall_soundscape"].strip():
        res.error("overall_soundscape section is empty")
    if not sections["non_diegetic_music"].strip():
        res.error("non_diegetic_music section is empty (use 'N/A' if no score)")

    # --- prompt stuffing tags check (warning) ---
    for pat in _PROMPT_STUFFING_PATTERNS:
        match = pat.search(text)
        if match:
            res.warn(
                f"prompt contains quality tag {match.group(0)!r}; MiniMax H3 adheres "
                "best to natural descriptive prose rather than prompt-stuffing tags"
            )

    # --- detailed_description depth / word count check (warning) ---
    dd_words = len(dd_text.split())
    if dd_words < 120:
        res.warn(
            f"detailed_description has {dd_words} words; optimal depth for MiniMax H3 is "
            "350-500 words to guide Context-IR"
        )
    elif dd_words > 650:
        res.warn(
            f"detailed_description has {dd_words} words; exceeding ~500-600 words may dilute "
            "temporal conditioning focus"
        )

    # --- g2+ continuation reference in detailed_description (warning) ---
    if gen_index > 0 and "<Video 1>" not in dd_text:
        res.warn(
            f"generation {gen_id} detailed_description does not reference <Video 1>; "
            "opening shot should explicitly describe seamless continuation from <Video 1>"
        )

    return res



def parse_story_constraints(story_path_or_text: str) -> list[dict]:
    """Parse constraints from story.json or developed_story.md ## Constraints."""
    trimmed = story_path_or_text.strip()
    if os.path.isfile(story_path_or_text):
        try:
            with open(story_path_or_text, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "constraints" in data:
                return data["constraints"]
        except Exception:
            pass
        text = open(story_path_or_text, encoding="utf-8").read()
    else:
        text = story_path_or_text

    if trimmed.startswith("{") and trimmed.endswith("}"):
        try:
            data = json.loads(trimmed)
            if isinstance(data, dict) and "constraints" in data:
                return data["constraints"]
        except Exception:
            pass

    constraints: list[dict] = []
    lines = text.splitlines()
    in_sec = False
    cur: dict = {}
    for line in lines:
        if line.startswith("## Constraints"):
            in_sec = True
            continue
        if in_sec and line.startswith("## "):
            break
        if not in_sec:
            continue
        if line.startswith("- id:"):
            if cur:
                constraints.append(cur)
            cur = {"id": line.split(":", 1)[1].strip()}
        elif cur and line.startswith("  "):
            k_v = line.strip().split(":", 1)
            if len(k_v) == 2:
                k = k_v[0].strip()
                v = k_v[1].strip()
                if v.startswith("[") and v.endswith("]"):
                    items = [x.strip() for x in v[1:-1].split(",") if x.strip()]
                    cur[k] = items
                else:
                    cur[k] = v
    if cur:
        constraints.append(cur)
    return constraints


def validate_constraints(
    story_path_or_text: str,
    scenes_path_or_text: str,
    run_dir: str | None = None,
) -> ValidationResult:
    """Validate hard negative constraints against scenes and storyboards."""
    res = ValidationResult()
    constraints = parse_story_constraints(story_path_or_text)
    if not constraints:
        return res

    if os.path.isfile(scenes_path_or_text):
        scenes_data = parse_scenes(open(scenes_path_or_text, encoding="utf-8").read())
    else:
        scenes_data = parse_scenes(scenes_path_or_text)
    scenes = scenes_data.get("scenes", [])

    scene_cast: dict[str, set[str]] = {}
    for s in scenes:
        sid = s["scene_id"]
        scene_cast[sid] = set(s.get("cast", []))

    storyboard_cast: dict[str, set[str]] = {}
    if run_dir and os.path.isdir(run_dir):
        for sid in scene_cast:
            sb_path = os.path.join(run_dir, f"storyboard_{sid}.md")
            if os.path.isfile(sb_path):
                sb = parse_storyboard(open(sb_path, encoding="utf-8").read())
                all_sb_chars: set[str] = set()
                for g in sb.get("generations", []):
                    for sh in g.get("shots", []):
                        all_sb_chars.update(sh.get("characters_present", []))
                storyboard_cast[sid] = all_sb_chars

    def scene_idx(s_id: str) -> int:
        m = re.search(r"\d+", s_id)
        return int(m.group(0)) if m else 999999

    for c in constraints:
        cid = c.get("id", "constraint")
        ctype = c.get("type", "")
        sev = str(c.get("severity", "BLOCKER")).upper()
        subjects = set(c.get("subjects", []))

        if ctype == "co_presence_exclusion" and len(subjects) >= 2:
            valid_until = c.get("valid_until_scene")
            valid_from = c.get("valid_from_scene")
            u_idx = scene_idx(valid_until) if valid_until else 999999
            f_idx = scene_idx(valid_from) if valid_from else -1

            for sid, cast in scene_cast.items():
                s_idx = scene_idx(sid)
                is_forbidden_scene = False
                if valid_until and s_idx <= u_idx:
                    is_forbidden_scene = True
                if valid_from and s_idx >= f_idx:
                    is_forbidden_scene = True

                if is_forbidden_scene:
                    if subjects.issubset(cast):
                        msg = f"{cid} [{sev}]: Co-presence exclusion violated in scene {sid} cast: {subjects}"
                        if sev == "BLOCKER":
                            res.error(msg)
                        else:
                            res.warn(msg)
                    sb_chars = storyboard_cast.get(sid, set())
                    if subjects.issubset(sb_chars):
                        msg = f"{cid} [{sev}]: Co-presence exclusion violated in storyboard {sid} shots: {subjects}"
                        if sev == "BLOCKER":
                            res.error(msg)
                        else:
                            res.warn(msg)

        elif ctype == "visibility_exclusion":
            excluded_scene = c.get("scene")
            if excluded_scene:
                cast = scene_cast.get(excluded_scene, set())
                for sub in subjects:
                    if sub in cast:
                        msg = f"{cid} [{sev}]: Visibility exclusion violated: {sub} present in scene {excluded_scene} cast"
                        if sev == "BLOCKER":
                            res.error(msg)
                        else:
                            res.warn(msg)
                    sb_chars = storyboard_cast.get(excluded_scene, set())
                    if sub in sb_chars:
                        msg = f"{cid} [{sev}]: Visibility exclusion violated: {sub} present in storyboard {excluded_scene} shots"
                        if sev == "BLOCKER":
                            res.error(msg)
                        else:
                            res.warn(msg)

    return res


def validate_render_manifest(manifest_path: str, run_dir: str | None = None) -> ValidationResult:
    """Validate approved render manifest against files and checksums."""
    res = ValidationResult()
    if not os.path.isfile(manifest_path):
        res.error(f"manifest file not found: {manifest_path}")
        return res

    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as exc:
        res.error(f"invalid manifest JSON: {exc}")
        return res

    base_dir = run_dir or os.path.dirname(manifest_path) or "."
    generations = manifest.get("generations", [])
    if not generations:
        res.error("manifest has no generations listed")
        return res

    def _file_hash(p: str) -> str:
        h = hashlib.sha256()
        with open(p, "rb") as fp:
            while chunk := fp.read(65536):
                h.update(chunk)
        return h.hexdigest()

    for gen in generations:
        sid = gen.get("scene_id", "?")
        gid = gen.get("gen_id", "?")
        tag = f"{sid}/{gid}"

        sheet_rel = gen.get("sheet_path")
        prompt_rel = gen.get("video_prompt_path")
        sheet_hash = gen.get("sheet_sha256")
        prompt_hash = gen.get("video_prompt_sha256")

        if not sheet_rel:
            res.error(f"{tag}: manifest missing sheet_path")
        else:
            sheet_full = os.path.join(base_dir, sheet_rel)
            if not (os.path.isfile(sheet_full) and os.path.getsize(sheet_full) > 0):
                res.error(f"{tag}: sheet file missing or empty: {sheet_full}")
            elif sheet_hash:
                actual_hash = _file_hash(sheet_full)
                if actual_hash != sheet_hash:
                    res.error(f"{tag}: sheet sha256 mismatch (manifest={sheet_hash[:10]}, actual={actual_hash[:10]})")

        if not prompt_rel:
            res.error(f"{tag}: manifest missing video_prompt_path")
        else:
            prompt_full = os.path.join(base_dir, prompt_rel)
            if not (os.path.isfile(prompt_full) and os.path.getsize(prompt_full) > 0):
                res.error(f"{tag}: prompt file missing or empty: {prompt_full}")
            elif prompt_hash:
                actual_hash = _file_hash(prompt_full)
                if actual_hash != prompt_hash:
                    res.error(f"{tag}: video prompt sha256 mismatch (manifest={prompt_hash[:10]}, actual={actual_hash[:10]})")

        dur = gen.get("duration_seconds", 0.0)
        if dur < 4.9 or dur > 15.1:
            res.warn(f"{tag}: duration {dur}s outside normal 5-15s bounds")

    return res


# ---------------------------------------------------------------------------
# Screenplay format validation
# ---------------------------------------------------------------------------

# Regex for standard sluglines: INT./EXT. LOCATION - TIME
_SLUGLINE_RE = re.compile(
    r"^\s*(INT\.|EXT\.|INT\./EXT\.)\s+.+\s*-\s*(DAY|NIGHT|DAWN|DUSK|CONTINUOUS|MOMENTS LATER|SAME|MONTAGE)",
    re.IGNORECASE,
)

# Regex for secondary sluglines (POV, BACK TO, PULL BACK TO REVEAL, etc.)
_SECONDARY_SLUG_RE = re.compile(
    r"^\s*([A-Z][A-Z ']+(?:'S)?\s+POV|BACK TO\s|BACK ON\s|PULL BACK TO REVEAL|CUT TO:|SMASH CUT TO:|FADE (?:IN|OUT))",
)

# Regex for character dialogue cues: CHARACTER NAME on its own line, all caps
_DIALOGUE_CUE_RE = re.compile(
    r"^\s*([A-Z][A-Z ]+(?:\s*\(CONT'D\))?)\s*$",
)

# Regex for ALL-CAPS sound cues in action lines (2+ consecutive caps letters)
_CAPS_SOUND_RE = re.compile(r"\b[A-Z][A-Z!?-]{2,}\b")

# Required metadata sections at the end of developed_story.md
_REQUIRED_SECTIONS = ("## Characters", "## Locations")
_OPTIONAL_SECTIONS = ("## Objects", "## Constraints")


def validate_screenplay(md: str) -> ValidationResult:
    """Validate that developed_story.md follows animation screenplay format.

    Checks:
    - At least one master slugline (INT./EXT.) exists.
    - No prose walls (paragraphs > 5 non-blank lines).
    - Character dialogue cues exist (ALL-CAPS character names).
    - ALL-CAPS sound cues present in action lines.
    - Required metadata sections (## Characters, ## Locations) present.
    """
    res = ValidationResult()
    lines = md.split("\n")

    # --- Extract screenplay body (inside ```text fenced block or the whole file) ---
    # ponytail: look for fenced text block first; fall back to whole file
    in_code_block = False
    screenplay_lines: list[str] = []
    found_fenced = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```text") and not in_code_block:
            in_code_block = True
            found_fenced = True
            continue
        if stripped == "```" and in_code_block:
            in_code_block = False
            continue
        if in_code_block:
            screenplay_lines.append(line)

    # If no fenced block, use lines before the first ## section as screenplay body
    if not found_fenced:
        for line in lines:
            if line.strip().startswith("## Characters") or line.strip().startswith("## Locations"):
                break
            screenplay_lines.append(line)

    screenplay_text = "\n".join(screenplay_lines)

    # --- Check 1: Master sluglines ---
    slugline_count = sum(1 for l in screenplay_lines if _SLUGLINE_RE.match(l))
    if slugline_count == 0:
        res.error("No master sluglines found (expected INT./EXT. LOCATION - TIME).")
    elif slugline_count < 2:
        res.warn(f"Only {slugline_count} slugline found; most screenplays have multiple scenes.")

    # --- Check 2: Prose walls (paragraphs > 5 non-blank lines) ---
    paragraphs: list[list[str]] = []
    current_para: list[str] = []
    for line in screenplay_lines:
        if line.strip() == "":
            if current_para:
                paragraphs.append(current_para)
                current_para = []
        else:
            current_para.append(line)
    if current_para:
        paragraphs.append(current_para)

    wall_count = 0
    for para in paragraphs:
        # Skip dialogue blocks (first line is a character cue)
        if para and _DIALOGUE_CUE_RE.match(para[0]):
            continue
        # Skip sluglines
        if para and (_SLUGLINE_RE.match(para[0]) or _SECONDARY_SLUG_RE.match(para[0])):
            continue
        if len(para) > 5:
            wall_count += 1
    if wall_count > 0:
        res.warn(f"{wall_count} prose wall(s) detected (action paragraphs > 5 lines). "
                 "Break into 1-3 line paragraphs for proper screenplay pacing.")

    # --- Check 3: Dialogue cues ---
    dialogue_cues = [l for l in screenplay_lines if _DIALOGUE_CUE_RE.match(l)]
    # Filter out sluglines and secondary slugs that happen to be all-caps
    dialogue_cues = [
        l for l in dialogue_cues
        if not _SLUGLINE_RE.match(l) and not _SECONDARY_SLUG_RE.match(l)
    ]
    if not dialogue_cues:
        res.warn("No dialogue character cues found (ALL-CAPS character names). "
                 "Dialogue-free screenplays are valid but unusual.")

    # --- Check 4: ALL-CAPS sound cues ---
    # Scan action lines (not dialogue, not sluglines) for capitalized sound events
    in_dialogue = False
    sound_cue_count = 0
    for line in screenplay_lines:
        stripped = line.strip()
        if _DIALOGUE_CUE_RE.match(stripped):
            in_dialogue = True
            continue
        if stripped == "" or _SLUGLINE_RE.match(stripped) or _SECONDARY_SLUG_RE.match(stripped):
            in_dialogue = False
            continue
        if stripped.startswith("(") and stripped.endswith(")"):
            # parenthetical
            continue
        if in_dialogue:
            continue
        # Action line — look for CAPS sound cues
        # Exclude common non-sound caps: INT, EXT, CONT'D, POV, MONTAGE, BACK, etc.
        exclusions = {"INT", "EXT", "POV", "BACK", "PULL", "CUT", "FADE", "SMASH", "MONTAGE",
                      "SAME", "DAY", "NIGHT", "DAWN", "DUSK", "CONTINUOUS"}
        caps_matches = _CAPS_SOUND_RE.findall(stripped)
        for m in caps_matches:
            word = m.rstrip("!?-")
            if word not in exclusions:
                sound_cue_count += 1
    if sound_cue_count == 0:
        res.warn("No ALL-CAPS sound cues found in action lines (e.g. SPLASH!, CREAK, SNAP!). "
                 "Sound cues help downstream agents build accurate foley.")

    # --- Check 5: Required metadata sections ---
    for section in _REQUIRED_SECTIONS:
        if section not in md:
            res.error(f"Missing required section: '{section}'.")

    for section in _OPTIONAL_SECTIONS:
        if section not in md:
            res.warn(f"Missing optional section: '{section}'.")

    return res


# ---------------------------------------------------------------------------
# Dispatch (used by scripts/validate.py)
# ---------------------------------------------------------------------------

def validate(artifact_path: str, schema: str, *, target_seconds: int | None = None,
             scenes_path: str | None = None, run_dir: str | None = None,
             scene_id: str | None = None, gen_id: str | None = None,
             legacy: bool = False, question_bank_path: str | None = None) -> ValidationResult:
    text = open(artifact_path, encoding="utf-8").read() if os.path.isfile(artifact_path) else ""
    if schema == "critique":
        from .critique_validator import validate_critique_report
        bank_md = ""
        if question_bank_path and os.path.isfile(question_bank_path):
            bank_md = open(question_bank_path, encoding="utf-8").read()
        return validate_critique_report(text, question_bank_md=bank_md or None)
    if schema == "constraints":
        s_path = scenes_path or (os.path.join(run_dir, "scenes.md") if run_dir else "")
        if not s_path:
            return ValidationResult(ok=False, errors=["constraints schema requires --scenes-path or --run-dir"])
        return validate_constraints(artifact_path, s_path, run_dir=run_dir)
    if schema == "manifest":
        return validate_render_manifest(artifact_path, run_dir=run_dir)
    if schema == "screenplay":
        return validate_screenplay(text)
    if schema == "beat_board":
        return validate_beat_board(text, target_seconds=target_seconds)
    if schema == "scenes":
        beat_board_path = None
        if run_dir:
            bb = os.path.join(run_dir, "beat_board.md")
            if os.path.isfile(bb):
                beat_board_path = bb
        return validate_scenes(text, target_seconds=target_seconds, beat_board_path=beat_board_path)
    if schema == "storyboard":
        scenes = None
        if scenes_path and os.path.isfile(scenes_path):
            scenes = parse_scenes(open(scenes_path, encoding="utf-8").read())
        return validate_storyboard(text, scenes=scenes)
    if schema == "prompts":
        if not run_dir or not scene_id:
            return ValidationResult(ok=False, errors=["prompts validation needs --run-dir and --scene"])
        sb_md_path = os.path.join(run_dir, f"storyboard_{scene_id}.md")
        sb = parse_storyboard(open(sb_md_path, encoding="utf-8").read()) if os.path.isfile(sb_md_path) else None
        return validate_prompts(run_dir, scene_id, sb=sb)
    if schema == "video_prompt":
        if not run_dir or not scene_id:
            return ValidationResult(ok=False, errors=["video_prompt validation needs --run-dir and --scene"])
        gid = gen_id
        if not gid:
            m = re.search(r"_([gb]\d+)\.txt$", os.path.basename(artifact_path))
            if m:
                gid = m.group(1)
        if not gid:
            return ValidationResult(ok=False, errors=["video_prompt validation needs --gen (or a <scene>_<gen>.txt filename)"])
        sb_md_path = os.path.join(run_dir, f"storyboard_{scene_id}.md")
        if not os.path.isfile(sb_md_path):
            return ValidationResult(ok=False, errors=[f"storyboard not found: {sb_md_path}"])
        sb = parse_storyboard(open(sb_md_path, encoding="utf-8").read())
        if legacy:
            return validate_video_prompt_legacy(text, sb, gid)
        return validate_video_prompt(text, sb, gid)
    if schema == "spatial_plan":
        from .spatial_validator import validate_spatial_plan
        sb = None
        scenes = None
        if run_dir and scene_id:
            sb_md_path = os.path.join(run_dir, f"storyboard_{scene_id}.md")
            if os.path.isfile(sb_md_path):
                sb = parse_storyboard(open(sb_md_path, encoding="utf-8").read())
            scenes_md_path = os.path.join(run_dir, "scenes.md")
            if os.path.isfile(scenes_md_path):
                scenes = parse_scenes(open(scenes_md_path, encoding="utf-8").read())
        elif scenes_path and os.path.isfile(scenes_path):
            scenes = parse_scenes(open(scenes_path, encoding="utf-8").read())
        return validate_spatial_plan(text, storyboard=sb, scenes=scenes)
    if schema == "spatial_qa":
        from .spatial_validator import validate_spatial_qa_report
        expected_sheets: list[str] | None = None
        if run_dir and scene_id:
            sb_md_path = os.path.join(run_dir, f"storyboard_{scene_id}.md")
            if os.path.isfile(sb_md_path):
                sb = parse_storyboard(open(sb_md_path, encoding="utf-8").read())
                expected_sheets = [
                    f"{scene_id}/{g['gen_id']}"
                    for g in sb.get("generations", [])
                    if not g.get("is_bridge")
                ]
        return validate_spatial_qa_report(text, expected_sheets=expected_sheets)
    return ValidationResult(ok=False, errors=[f"unknown schema: {schema!r}"])
