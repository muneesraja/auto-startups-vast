#!/usr/bin/env python3
"""LTX Director renderer + concat (the slow "hands" stage). No LLM calls.

Reads each scene's ``motion_<scene>.json`` (Agent 5 Director timeline), renders
every ``render_unit`` via the LTX Director Hotfix workflow, then concatenates
row clips -> ``scene_<scene>.mp4`` and scenes -> ``final_film.mp4``.

The I2V-vs-FLF2V choice is a CODE rule derived from guide_frames (the agent must
NOT set ``workflow``): one start guide -> I2V; start + end guide -> FLF2V.
Adjacent units in a row share a boundary panel (end(K)==start(K+1)) — that shared
still is what makes the row a seamless FLF2V chain.

  python3 scripts/render_all.py --output-dir <run> [--only-scenes s1,s2]

Long-running (hours). Fire-and-forget; the SKILL.md launches it in the background.
Resume: existing clip files are skipped; only missing clips + downstream concats
re-execute.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

import config  # noqa: E402
from tools import duration_budget  # noqa: E402
from tools.ltx_director_workflow import (  # noqa: E402
    DIRECTOR_FPS,
    generate_ltx_director_from_clip,
)
from tools.video_concat import concat_videos  # noqa: E402

PANEL_FILE_RE = re.compile(r"^panel_(\d)(\d)$")
SHOTID_RE = re.compile(r"_p(\d+)$")
UNIT_RC_RE = re.compile(r"r(\d+).*c(\d+)", re.I)


def _panel_file(run_dir: str, scene_id: str, panel_id: str) -> str:
    """Resolve a guide-frame panel_id to its image file (upscale preferred)."""
    pid = (panel_id or "").strip()
    r = c = None
    m = PANEL_FILE_RE.match(pid)
    if m:
        r, c = int(m.group(1)), int(m.group(2))
    else:
        m = SHOTID_RE.search(pid)
        if m:
            idx = int(m.group(1))  # 1..8
            r, c = (idx - 1) // duration_budget.ROW_PANELS + 1, (idx - 1) % duration_budget.ROW_PANELS + 1
    if r is None or c is None:
        raise ValueError(f"cannot resolve panel_id {pid!r} to a row/col")
    base = os.path.join(run_dir, "panels", scene_id)
    upscale = os.path.join(base, f"upscale_panel_{r}{c}.png")
    if os.path.isfile(upscale):
        return upscale
    crop = os.path.join(base, f"panel_{r}{c}.png")
    if os.path.isfile(crop):
        return crop
    raise FileNotFoundError(f"panel image missing for {scene_id}/{pid} (tried {upscale} and {crop})")


def _guide_panel_ids(unit: dict) -> tuple[str | None, str | None, list[str]]:
    """Return (start_panel, end_panel, all_panel_ids) from a unit's guide_frames."""
    start = end = None
    all_ids: list[str] = []
    for g in unit.get("guide_frames") or []:
        if not isinstance(g, dict):
            continue
        pid = str(g.get("panel_id") or "").strip()
        if not pid:
            continue
        all_ids.append(pid)
        placement = str(g.get("placement") or "").strip().lower()
        if placement == "start":
            start = pid
        elif placement == "end" or g.get("is_end_frame"):
            end = pid
    if start is None and all_ids:
        start = all_ids[0]
    return start, end, all_ids


def _row_clip(unit_id: str, fallback_row: int, fallback_clip: int) -> tuple[int, int]:
    m = UNIT_RC_RE.search(unit_id or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    return fallback_row, fallback_clip


def _exists(path: str) -> bool:
    return bool(path) and os.path.isfile(path) and os.path.getsize(path) > 0


def render_scene(run_dir: str, scene_id: str, *, fps: int, width: int, height: int, seed: int) -> str:
    """Render all clips for one scene; return the scene mp4 path."""
    motion_path = os.path.join(run_dir, f"motion_{scene_id}.json")
    if not os.path.isfile(motion_path):
        raise SystemExit(f"motion_{scene_id}.json not found: {motion_path}")
    motion = json.loads(open(motion_path, encoding="utf-8").read())
    units = motion.get("render_units") or []
    if not units:
        raise SystemExit(f"motion_{scene_id}.json has no render_units")

    scene_global = motion.get("scene_global_prompt") or ""
    clips_dir = os.path.join(run_dir, "clips", scene_id)
    os.makedirs(clips_dir, exist_ok=True)

    # Group units into rows by parsing unit_id; fallback: chain-break detection.
    clip_paths: list[str] = []
    cur_row = 1
    cur_clip = 0
    prev_end: str | None = None
    for unit in units:
        uid = unit.get("unit_id", "")
        start, end, all_ids = _guide_panel_ids(unit)
        # Chain-break: a new row starts when this unit's start != previous end.
        if prev_end is not None and start and start != prev_end:
            cur_row += 1
            cur_clip = 0
        cur_clip += 1
        row, clip = _row_clip(uid, cur_row, cur_clip)
        out_path = os.path.join(clips_dir, f"row{row}_clip{clip}.mp4")

        if _exists(out_path):
            print(f"  clip {scene_id}/row{row}_clip{clip}: exists, skip")
            clip_paths.append(out_path)
            prev_end = end or start
            continue

        start_panel = start or all_ids[0]
        first_path = _panel_file(run_dir, scene_id, start_panel)
        last_path = _panel_file(run_dir, scene_id, end) if end else None
        guide_paths = {pid: _panel_file(run_dir, scene_id, pid) for pid in all_ids}

        # Derive start/end panel ids on the clip so the workflow function maps guides.
        clip = dict(unit)
        clip["start_panel_id"] = start_panel
        clip["end_panel_id"] = end or start_panel
        clip.pop("workflow", None)  # code rule — never trust the agent here

        print(f"  clip {scene_id}/row{row}_clip{clip}: rendering ({start_panel} -> {end or start_panel}) ...")
        result = generate_ltx_director_from_clip(
            clip,
            first_frame_path=first_path,
            last_frame_path=last_path,
            guide_frame_paths=guide_paths,
            output_path=out_path,
            global_prompt=scene_global,
            fps=fps,
            width=width,
            height=height,
            seed=seed,
        )
        if result.get("status") != "success":
            raise RuntimeError(
                f"clip {scene_id}/row{row}_clip{clip} failed: {result.get('message', result)}"
            )
        clip_paths.append(out_path)
        prev_end = end or start

    scene_mp4 = os.path.join(run_dir, f"scene_{scene_id}.mp4")
    print(f"  concat {len(clip_paths)} clips -> {scene_mp4}")
    res = concat_videos(clip_paths, scene_mp4)
    if res.get("status") != "success":
        raise RuntimeError(f"scene concat failed for {scene_id}: {res.get('message')}")
    return scene_mp4


def main() -> int:
    p = argparse.ArgumentParser(description="Render LTX Director clips + concat")
    p.add_argument("--output-dir", required=True, help="run output dir")
    p.add_argument("--only-scenes", default="", help="comma-separated scene ids to render")
    p.add_argument("--fps", type=int, default=DIRECTOR_FPS)
    p.add_argument("--width", type=int, default=None)
    p.add_argument("--height", type=int, default=None)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    run_dir = os.path.abspath(args.output_dir)
    width = args.width if args.width is not None else config.DIRECTOR_VIDEO_WIDTH
    height = args.height if args.height is not None else config.DIRECTOR_VIDEO_HEIGHT

    only = {s.strip() for s in args.only_scenes.split(",") if s.strip()}

    # Discover scenes from motion_*.json files.
    scene_ids = sorted(
        m.group(1)
        for f in os.listdir(run_dir)
        if (m := re.fullmatch(r"motion_(.+)\.json", f)) and os.path.isfile(os.path.join(run_dir, f"motion_{m.group(1)}.json"))
    )
    if only:
        scene_ids = [s for s in scene_ids if s in only]
    if not scene_ids:
        raise SystemExit(f"no motion_*.json scenes found in {run_dir}")

    scene_mp4s: list[str] = []
    for sid in scene_ids:
        print(f"== scene {sid} ==")
        scene_mp4s.append(render_scene(run_dir, sid, fps=args.fps, width=width, height=height, seed=args.seed))

    if len(scene_mp4s) == 1:
        final = os.path.join(run_dir, "final_film.mp4")
        os.replace(scene_mp4s[0], final)
        print(f"final_film.mp4 -> {final}")
    else:
        final = os.path.join(run_dir, "final_film.mp4")
        print(f"== concat {len(scene_mp4s)} scenes -> {final} ==")
        res = concat_videos(scene_mp4s, final)
        if res.get("status") != "success":
            raise RuntimeError(f"final concat failed: {res.get('message')}")
    print("render done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())