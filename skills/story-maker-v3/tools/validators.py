"""Deterministic validators for story-maker-v3 (Minimax H3 backend).

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

# Suggested emotion vocabulary for beat boards (warn-only — not enforced).
# See prompts/beat_board.md and assets/directors-guide.md Section 1.
BEAT_EMOTIONS = (
    "joy", "unease", "fear", "tension", "determination", "excitement",
    "shock", "chaos", "triumph", "sadness", "wonder", "relief",
    "anger", "tenderness", "suspense", "hope", "despair", "confusion",
    "awe", "disgust", "longing", "pride", "shame", "curiosity",
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
        if shots and shots[-1]["end"] is not None and abs(shots[-1]["end"] - gen["end"]) > eps:
            res.error(f"{gid}: last shot ends at {shots[-1]['end']}s, generation ends at {gen['end']}s (must fill the generation)")
        if panel_count is not None and used_panels:
            expected = list(range(1, panel_count + 1))
            if sorted(used_panels) != expected:
                res.error(f"{gid}: shots use panels {sorted(used_panels)}; must use each of 1..{panel_count} exactly once")
            if used_panels != sorted(used_panels):
                res.error(f"{gid}: panels must be assigned in column-major order (top-to-bottom within each column, then left-to-right) across shots")
        prev_end = gen["end"]
        total = gen["end"]

    if not sb["handoff"]:
        res.error(f"scene {sid}: scene-end handoff block is missing")

    if sb["target_seconds"] > 0 and abs(total - sb["target_seconds"]) > eps:
        res.error(f"scene {sid}: generations cover {total:.1f}s != target_seconds ({sb['target_seconds']}s)")

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
    # Brand references
    for brand in ("pixar", "disney", "dreamworks"):
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

        # Prompt-quality checks
        quality_warnings = _check_prompt_quality(prompt_text)
        for w in quality_warnings:
            res.warn(f"{scene_id}/{gid}: {w}")

    return res


_PROMPT_SHOT_RE = re.compile(
    r"^SHOT\s+(\d+)\s*[—-]\s*(\d+(?:\.\d+)?)\s*[–—-]\s*(\d+(?:\.\d+)?)\s*s",
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


def validate_video_prompt(text: str, sb: dict[str, Any], gen_id: str) -> ValidationResult:
    """Validate a 6-section Ref2VA video prompt against the storyboard.

    Sections (exact order): subject_definitions, summary, retention_analysis,
    detailed_description, overall_soundscape, non_diegetic_music.
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
    defined_labels: set[str] = set()
    for m in _LABEL_RE.finditer(sd_text):
        defined_labels.add(f"{m.group(1)} {m.group(2)}")

    # --- retention_analysis: check markers ---
    ra_text = sections["retention_analysis"]
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

    # Check labels used in detailed_description are defined
    for m in _LABEL_RE.finditer(dd_text):
        label = f"{m.group(1)} {m.group(2)}"
        if label not in defined_labels:
            res.error(f"detailed_description references {m.group(0)} not defined in subject_definitions")

    # --- dialogue tags: <d>[Lang] ...</d> ---
    for m in _DIALOGUE_RE.finditer(dd_text):
        lang = m.group(1)
        if not lang:
            res.error(f"<d> tag missing language code: {m.group(0)[:50]}")

    # --- overall_soundscape and non_diegetic_music: must be present (N/A ok) ---
    if not sections["overall_soundscape"].strip():
        res.error("overall_soundscape section is empty")
    if not sections["non_diegetic_music"].strip():
        res.error("non_diegetic_music section is empty (use 'N/A' if no score)")

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
