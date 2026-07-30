"""Deterministic validators for story-maker-v3.

Run after each authoring agent to catch hallucination BEFORE any paid image /
render step. Each validator parses a markdown/JSON artifact, asserts the locked
schema, and returns a :class:`ValidationResult`. The CLI
(``scripts/validate.py``) writes ``<artifact>.validation.json`` and exits
nonzero on failure; Claude Code loops (write -> validate -> fix) until pass.

No LLM calls. Pure parsing + assertions.

Schemas enforced (see plan):
  scenes      -> scene_count>=1; each scene has scene_id/target_seconds/cast/location_id;
                 sum(targets) ~= run target.
  storyboard  -> exactly 8 cells (2 rows x 4 cols); all 13 fields; depth in 1-5;
                 position_xy in [0,1]; duration in [9,15]; row/scene sums = target_seconds;
                 characters_present subset of cast; both delta tables + handoff present.
  prompts     -> every panel has a prompt; references correct char cids + location id;
                 no invented characters.
  motion      -> every render_unit has guide_frames + motion_segments + valid enums;
                 row units share boundary panels (end(K)==start(K+1)); workflow not set
                 by agent; sum(unit durations) = scene target.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from . import duration_budget
from .ltx_render_params import (
    GUIDANCE_LEVELS,
    MOTION_CLASSES,
    _GUIDANCE_ALIASES,
    _MOTION_ALIASES,
)

# 13 storyboard cell columns (in order).
CELL_COLUMNS = [
    "col", "shot_id", "duration_seconds", "characters_present", "depth_per_char",
    "camera_angle", "position_xy", "looks_at", "expression", "mood", "intent",
    "facing", "angle", "spatial_relation", "must_not_show",
]

VALID_MOTION_CLASS_TOKENS = set(MOTION_CLASSES) | set(_MOTION_ALIASES.keys())
VALID_GUIDANCE_TOKENS = set(GUIDANCE_LEVELS) | set(_GUIDANCE_ALIASES.keys())


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


def parse_depth_map(text: str) -> dict[str, int]:
    """``{cid_a:2, cid_b:3}`` -> {'cid_a': 2, 'cid_b': 3}."""
    inner = _strip_brackets(text, "{", "}")
    out: dict[str, int] = {}
    if not inner:
        return out
    for pair in _split_top_level(inner, ","):
        if ":" not in pair:
            continue
        key, _, val = pair.partition(":")
        key = key.strip()
        try:
            out[key] = int(val.strip())
        except ValueError:
            out[key] = -1
    return out


def parse_position_map(text: str) -> dict[str, list[float]]:
    """``{cid_a:[0.5,0.5], cid_b:[0.7,0.5]}`` -> {'cid_a': [0.5, 0.5], ...}."""
    inner = _strip_brackets(text, "{", "}")
    out: dict[str, list[float]] = {}
    if not inner:
        return out
    # match key:[x, y]
    for m in re.finditer(r"([A-Za-z0-9_]+)\s*:\s*\[([^\]]*)\]", inner):
        key = m.group(1).strip()
        coords = [c.strip() for c in m.group(2).split(",") if c.strip()]
        try:
            out[key] = [float(c) for c in coords]
        except ValueError:
            out[key] = []
    return out


def parse_facing_map(text: str) -> dict[str, str]:
    """``{cid_a: left, cid_b: right}`` -> {'cid_a': 'left', ...}."""
    inner = _strip_brackets(text, "{", "}")
    out: dict[str, str] = {}
    if not inner:
        return out
    for pair in _split_top_level(inner, ","):
        if ":" not in pair:
            continue
        key, _, val = pair.partition(":")
        out[key.strip()] = val.strip()
    return out


def _split_top_level(text: str, sep: str) -> list[str]:
    """Split on ``sep`` but not inside [] or {}."""
    parts: list[str] = []
    depth = 0
    cur = ""
    for ch in text:
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


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


def _parse_table(block: str) -> tuple[list[str], list[list[str]]]:
    """Parse a markdown table inside ``block`` -> (headers, rows)."""
    headers: list[str] = []
    rows: list[list[str]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        # separator row like |---|---|
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c != ""):
            continue
        if not headers:
            headers = cells
            continue
        rows.append(cells)
    return headers, rows


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


def parse_storyboard(md: str) -> dict[str, Any]:
    """Parse storyboard_<scene>.md -> structured dict."""
    head_kv = _kv_lines(md.split("## Row", 1)[0])
    scene_id = head_kv.get("scene_id", "").strip()
    title = ""
    m = re.match(r"^# Scene (\S+)\s*[—-]\s*(.*)$", md.splitlines()[0].strip()) if md.splitlines() else None
    if m:
        scene_id = scene_id or m.group(1)
        title = m.group(2).strip()
    target = int(head_kv.get("target_seconds", "0") or 0)
    cast = parse_cid_list(head_kv.get("cast", ""))
    location_ref_id = head_kv.get("location_ref_id", "").strip()

    # Split into sections by ## headers.
    sections: dict[str, str] = {}
    cur_key = "_pre"
    cur_lines: list[str] = []
    for line in md.splitlines():
        if line.startswith("## "):
            cur_key = line[3:].strip().lower()
            cur_lines = []
            sections[cur_key] = cur_lines
        else:
            cur_lines.append(line)
    sections[cur_key] = cur_lines  # last

    def _row_cells(key: str) -> list[dict[str, str]]:
        block = "\n".join(sections.get(key, []))
        headers, rows = _parse_table(block)
        cells: list[dict[str, str]] = []
        for row in rows:
            cell = {h: v for h, v in zip(headers, row)}
            cells.append(cell)
        return cells

    row1 = _row_cells("row 1 (ltx session 1)") or _row_cells("row 1")
    row2 = _row_cells("row 2 (ltx session 2)") or _row_cells("row 2")
    deltas1 = _row_cells("inter-column motion deltas (row 1)")
    deltas2 = _row_cells("inter-column motion deltas (row 2)")

    handoff: dict[str, Any] = {}
    handoff_block: list[str] = []
    for key, lines in sections.items():
        if key.startswith("scene-end handoff") or key.startswith("handoff"):
            handoff_block = lines
            break
    if handoff_block:
        hkv = _kv_lines("\n".join(handoff_block))
        handoff = {
            "on_screen": parse_cid_list(hkv.get("on_screen", "")),
            "positions": parse_position_map(hkv.get("positions", "")),
            "facing": parse_facing_map(hkv.get("facing", "")),
            "mood": hkv.get("mood", "").strip(),
            "transition": hkv.get("transition", "hard_cut").strip(),
            "next_scene_id": (re.search(r"->\s*scene\s+(\S+)", "\n".join(handoff_block)) or [None, None])[1] if False else "",
        }
        nm = re.search(r"->\s*scene\s+(\S+)", "\n".join(handoff_block))
        if nm:
            handoff["next_scene_id"] = nm.group(1).strip()

    return {
        "scene_id": scene_id,
        "title": title,
        "target_seconds": target,
        "cast": cast,
        "location_ref_id": location_ref_id,
        "rows": [row1, row2],
        "deltas": [deltas1, deltas2],
        "handoff": handoff,
    }


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


def _validate_cell(res: ValidationResult, cell: dict[str, str], cast: set[str], scene_id: str, idx: int) -> int:
    """Validate one storyboard cell; return its duration_seconds (0 if invalid)."""
    label = f"{scene_id} cell {idx}"
    for col in CELL_COLUMNS:
        if col not in cell or not cell[col].strip():
            res.error(f"{label}: missing field '{col}'")
    dur_raw = cell.get("duration_seconds", "0").strip()
    try:
        dur = int(dur_raw)
    except ValueError:
        res.error(f"{label}: duration_seconds not an int ({dur_raw!r})")
        dur = 0
    if dur != 0 and not (duration_budget.PANEL_MIN <= dur <= duration_budget.PANEL_MAX):
        res.error(f"{label}: duration_seconds {dur} outside [{duration_budget.PANEL_MIN},{duration_budget.PANEL_MAX}]")
    chars = parse_cid_list(cell.get("characters_present", ""))
    for c in chars:
        if c and c not in cast:
            res.error(f"{label}: characters_present has '{c}' not in scene cast")
    depth = parse_depth_map(cell.get("depth_per_char", ""))
    for cid, d in depth.items():
        if not (1 <= d <= 5):
            res.error(f"{label}: depth for {cid} = {d} outside [1,5]")
    pos = parse_position_map(cell.get("position_xy", ""))
    for cid, coords in pos.items():
        if len(coords) != 2 or not all(0.0 <= v <= 1.0 for v in coords):
            res.error(f"{label}: position_xy for {cid} = {coords} not in [0,1]^2")
    return dur


def validate_storyboard(md: str, scenes: dict[str, Any] | None = None) -> ValidationResult:
    res = ValidationResult()
    sb = parse_storyboard(md)
    sid = sb["scene_id"] or "<unknown>"
    cast = set(sb["cast"])
    if not cast:
        res.error(f"scene {sid}: cast is empty")

    rows = sb["rows"]
    if len(rows) != 2:
        res.error(f"scene {sid}: expected 2 rows, got {len(rows)}")
    row_totals: list[int] = []
    for ri, row in enumerate(rows):
        if len(row) != duration_budget.ROW_PANELS:
            res.error(f"scene {sid} row {ri+1}: expected {duration_budget.ROW_PANELS} cells, got {len(row)}")
        rtotal = 0
        for ci, cell in enumerate(row):
            rtotal += _validate_cell(res, cell, cast, sid, ri * duration_budget.ROW_PANELS + ci + 1)
        row_totals.append(rtotal)
        if rtotal > duration_budget.ROW_MAX:
            res.error(f"scene {sid} row {ri+1}: row total {rtotal}s exceeds ROW_MAX {duration_budget.ROW_MAX}s")

    if len(sb["deltas"]) < 2 or not sb["deltas"][0] or not sb["deltas"][1]:
        res.error(f"scene {sid}: both inter-column motion delta tables must be present")
    if not sb["handoff"]:
        res.error(f"scene {sid}: scene-end handoff block is missing")

    scene_total = sum(row_totals)
    if sb["target_seconds"] > 0 and scene_total != sb["target_seconds"]:
        res.error(
            f"scene {sid}: sum of cell durations ({scene_total}s) != target_seconds ({sb['target_seconds']}s)"
        )

    # Cross-check against scenes.md if provided.
    if scenes:
        scene_meta = next((s for s in scenes["scenes"] if s["scene_id"] == sid), None)
        if scene_meta is None:
            res.error(f"scene {sid}: not found in scenes.md")
        else:
            if scene_total != scene_meta["target_seconds"]:
                res.error(
                    f"scene {sid}: storyboard total {scene_total}s != scenes.md target "
                    f"{scene_meta['target_seconds']}s"
                )
            if sb["location_ref_id"] and scene_meta["location_id"] and sb["location_ref_id"] != scene_meta["location_id"]:
                res.error(
                    f"scene {sid}: location_ref_id {sb['location_ref_id']!r} != scenes.md "
                    f"location_id {scene_meta['location_id']!r}"
                )
    return res


def validate_prompts(run_dir: str, scene_id: str, sb: dict[str, Any] | None = None) -> ValidationResult:
    """Validate that Agent 4 wrote a prompt per panel + char/location prompts.

    Checks file presence and that panel prompts reference only known char cids.
    """
    from . import image_pipeline

    res = ValidationResult()
    if sb is None:
        res.error("prompts validation requires the parsed storyboard")
        return res
    cast = set(sb["cast"])
    loc = sb["location_ref_id"]

    # Character + location prompt files.
    for cid in cast:
        p = image_pipeline.character_prompt_path(run_dir, cid)
        if not os.path.isfile(p) or not image_pipeline.read_prompt(p):
            res.error(f"missing character prompt for {cid}: {p}")
    if loc:
        p = image_pipeline.location_prompt_path(run_dir, loc)
        if not os.path.isfile(p) or not image_pipeline.read_prompt(p):
            res.error(f"missing location prompt for {loc}: {p}")

    # Sheet + per-panel prompts.
    sheet_p = image_pipeline.sheet_prompt_path(run_dir, scene_id)
    if not os.path.isfile(sheet_p) or not image_pipeline.read_prompt(sheet_p):
        res.error(f"missing storyboard sheet prompt: {sheet_p}")

    for ri in range(duration_budget.SCENE_ROWS):
        for ci in range(duration_budget.ROW_PANELS):
            panel_id = f"panel_{ri+1}{ci+1}"
            p = image_pipeline.panel_prompt_path(run_dir, scene_id, panel_id)
            if not os.path.isfile(p) or not image_pipeline.read_prompt(p):
                res.error(f"missing panel prompt for {panel_id}: {p}")
                continue
            text = image_pipeline.read_prompt(p)
            # No invented characters: any char_NN token in the prompt must be in cast.
            for tok in re.findall(r"char_\d+|[A-Za-z_][A-Za-z0-9_]*", text):
                if re.fullmatch(r"char_\d+", tok) and tok not in cast:
                    res.error(f"panel prompt {panel_id} references unknown character {tok}")
    return res


def validate_motion(motion_text: str, sb: dict[str, Any] | None = None) -> ValidationResult:
    """Validate motion_<scene>.json (Agent 5 Director timeline)."""
    res = ValidationResult()
    try:
        motion = json.loads(motion_text)
    except json.JSONDecodeError as e:
        res.error(f"motion JSON parse error: {e}")
        return res

    sid = motion.get("scene_id", "<unknown>")
    units = motion.get("render_units") or []
    if not units:
        res.error(f"scene {sid}: no render_units")
        return res

    total = 0
    prev_end_panel: str | None = None
    cur_row: int | None = None
    row_re = re.compile(r"r(\d+)", re.I)
    for ui, unit in enumerate(units):
        uid = unit.get("unit_id", f"unit_{ui}")
        # A row break is a deliberate cut — the FLF2V boundary rule only applies
        # WITHIN a row, so reset the chain when the row changes.
        rm = row_re.search(uid)
        if rm:
            row_n = int(rm.group(1))
            if cur_row is not None and row_n != cur_row:
                prev_end_panel = None
            cur_row = row_n
        if "workflow" in unit:
            res.error(f"{uid}: agent must NOT set 'workflow' (it is a code rule)")
        dur = unit.get("duration_seconds")
        is_batch = "batch" in uid.lower()
        max_dur = duration_budget.BATCH_MAX if is_batch else duration_budget.CLIP_MAX_BEATS
        if not isinstance(dur, int) or not (duration_budget.CLIP_MIN <= dur <= max_dur):
            res.error(f"{uid}: duration_seconds {dur!r} outside [9,{max_dur}]")
        else:
            total += dur

        mc = str(unit.get("motion_class", "")).strip().lower()
        if mc not in VALID_MOTION_CLASS_TOKENS:
            res.error(f"{uid}: invalid motion_class {mc!r}")
        gd = str(unit.get("guidance", "")).strip().lower()
        if gd not in VALID_GUIDANCE_TOKENS:
            res.error(f"{uid}: invalid guidance {gd!r}")

        guides = unit.get("guide_frames") or []
        if not isinstance(guides, list) or len(guides) < 1:
            res.error(f"{uid}: guide_frames missing/empty")
        else:
            start_panel = next((g.get("panel_id") for g in guides if isinstance(g, dict) and g.get("placement") == "start"), None)
            end_panel = next((g.get("panel_id") for g in guides if isinstance(g, dict) and (g.get("placement") == "end" or g.get("is_end_frame"))), None)
            if not start_panel:
                res.error(f"{uid}: guide_frames missing a 'start' placement")
            # Boundary continuity: this unit's start must equal previous unit's end.
            if prev_end_panel is not None and start_panel and start_panel != prev_end_panel:
                res.error(
                    f"{uid}: start panel {start_panel!r} != previous unit end panel "
                    f"{prev_end_panel!r} (FLF2V chain broken)"
                )
            prev_end_panel = end_panel or start_panel

        segs = unit.get("motion_segments") or []
        if not isinstance(segs, list) or not segs:
            res.error(f"{uid}: motion_segments missing/empty")
        else:
            for si, seg in enumerate(segs):
                if not isinstance(seg, dict):
                    res.error(f"{uid}: motion_segment {si} not an object")
                    continue
                sr = seg.get("start_ratio")
                er = seg.get("end_ratio")
                if not isinstance(sr, (int, float)) or not isinstance(er, (int, float)):
                    res.error(f"{uid}: motion_segment {si} needs numeric start_ratio/end_ratio")
                elif not (0.0 <= sr <= er <= 1.0):
                    res.error(f"{uid}: motion_segment {si} ratios out of order ({sr},{er})")

    if sb and sb.get("target_seconds"):
        if total != sb["target_seconds"]:
            res.error(
                f"scene {sid}: sum of unit durations ({total}s) != storyboard target "
                f"({sb['target_seconds']}s)"
            )
    return res


# ---------------------------------------------------------------------------
# Dispatch (used by scripts/validate.py)
# ---------------------------------------------------------------------------

def validate(artifact_path: str, schema: str, *, target_seconds: int | None = None,
             scenes_path: str | None = None, run_dir: str | None = None,
             scene_id: str | None = None) -> ValidationResult:
    text = open(artifact_path, encoding="utf-8").read() if os.path.isfile(artifact_path) else ""
    if schema == "scenes":
        return validate_scenes(text, target_seconds=target_seconds)
    if schema == "storyboard":
        scenes = None
        if scenes_path and os.path.isfile(scenes_path):
            scenes = parse_scenes(open(scenes_path, encoding="utf-8").read())
        return validate_storyboard(text, scenes=scenes)
    if schema == "motion":
        sb = None
        if scenes_path and os.path.isfile(scenes_path):
            # storyboard path derived from scene_id if not given explicitly
            pass
        return validate_motion(text, sb=sb)
    if schema == "prompts":
        if not run_dir or not scene_id:
            return ValidationResult(ok=False, errors=["prompts validation needs --run-dir and --scene"])
        sb_md_path = os.path.join(run_dir, f"storyboard_{scene_id}.md")
        sb = parse_storyboard(open(sb_md_path, encoding="utf-8").read()) if os.path.isfile(sb_md_path) else None
        return validate_prompts(run_dir, scene_id, sb=sb)
    return ValidationResult(ok=False, errors=[f"unknown schema: {schema!r}"])