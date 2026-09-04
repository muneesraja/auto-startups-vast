"""Deterministic validators for story-maker-v4c (Minimax H3 backend).

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
                   NEVER straddling a generation boundary; panels sequential and
                   matching the panel_grid; characters_present subset of cast.
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

SHOT_TRANSITIONS = ("continuous", "hard_cut")


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
            "beat": kv.get("beat", "").strip(),
        })
    return {"target_seconds": target, "scene_budget": budget, "scenes": scenes}


_GEN_HEADER_RE = re.compile(r"^## Generation (g\d+)\s*[—-]\s*(.*)$")
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
            cur_gen = {
                "gen_id": gm.group(1),
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

def validate_scenes(md: str, target_seconds: int | None = None, tolerance_percent: int = 15) -> ValidationResult:
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
            if shot["transition"] and shot["transition"] not in SHOT_TRANSITIONS:
                res.error(f"{slabel}: transition {shot['transition']!r} not in {SHOT_TRANSITIONS}")
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
        if shots and shots[-1]["end"] is not None and abs(shots[-1]["end"] - gen["end"]) > eps:
            res.error(f"{gid}: last shot ends at {shots[-1]['end']}s, generation ends at {gen['end']}s (must fill the generation)")
        if panel_count is not None and used_panels:
            expected = list(range(1, panel_count + 1))
            if sorted(used_panels) != expected:
                res.error(f"{gid}: shots use panels {sorted(used_panels)}; must use each of 1..{panel_count} exactly once")
            if used_panels != sorted(used_panels):
                res.error(f"{gid}: panels must be assigned in reading order across shots")
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


def validate_prompts(run_dir: str, scene_id: str, sb: dict[str, Any] | None = None) -> ValidationResult:
    """Validate pre-generation prompts: char sheets + location lock + one
    storyboard sheet prompt PER GENERATION."""
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

    for gen in sb["generations"]:
        sheet_p = image_pipeline.sheet_prompt_path(run_dir, scene_id, gen["gen_id"])
        if not os.path.isfile(sheet_p) or not image_pipeline.read_prompt(sheet_p):
            res.error(f"missing storyboard sheet prompt for {gen['gen_id']}: {sheet_p}")
    return res


_PROMPT_SHOT_RE = re.compile(
    r"^SHOT\s+(\d+)\s*[—-]\s*(\d+(?:\.\d+)?)\s*[–—-]\s*(\d+(?:\.\d+)?)\s*s",
    re.M | re.I,
)


def validate_video_prompt(text: str, sb: dict[str, Any], gen_id: str) -> ValidationResult:
    """Validate one generation's Minimax H3 timeline prompt against the storyboard."""
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


# ---------------------------------------------------------------------------
# Dispatch (used by scripts/validate.py)
# ---------------------------------------------------------------------------

def validate(artifact_path: str, schema: str, *, target_seconds: int | None = None,
             scenes_path: str | None = None, run_dir: str | None = None,
             scene_id: str | None = None, gen_id: str | None = None) -> ValidationResult:
    text = open(artifact_path, encoding="utf-8").read() if os.path.isfile(artifact_path) else ""
    if schema == "scenes":
        return validate_scenes(text, target_seconds=target_seconds)
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
            m = re.search(r"_(g\d+)\.txt$", os.path.basename(artifact_path))
            if m:
                gid = m.group(1)
        if not gid:
            return ValidationResult(ok=False, errors=["video_prompt validation needs --gen (or a <scene>_<gen>.txt filename)"])
        sb_md_path = os.path.join(run_dir, f"storyboard_{scene_id}.md")
        if not os.path.isfile(sb_md_path):
            return ValidationResult(ok=False, errors=[f"storyboard not found: {sb_md_path}"])
        sb = parse_storyboard(open(sb_md_path, encoding="utf-8").read())
        return validate_video_prompt(text, sb, gid)
    return ValidationResult(ok=False, errors=[f"unknown schema: {schema!r}"])
