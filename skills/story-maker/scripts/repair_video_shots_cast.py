#!/usr/bin/env python3
"""Repair reel_v2 video_shots for cast-coherent anchors without --fresh.

Usage (from skills/story-maker):

  .venv/bin/python scripts/repair_video_shots_cast.py \\
    ../../outputs/story-maker/story-naila-5m-v2

Rewrites plan.json video_shots via normalize (cast split), clears stale
generation_specs.motion *_vshot_* entries so vision re-prompts.
Leaves still images and obsolete video mp4 files on disk.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)


def repair_plan_video_shots_cast_coherence(output_dir: str) -> dict:
    """Normalize cast-coherent video_shots on an existing run directory.

    Returns a summary dict with before/after video_shot counts.
    """
    from scripts.nodes.plan_io import (
        apply_video_shots_to_plan,
        load_plan,
        save_plan_dict,
        story_plan_view,
        video_shot_plan_view,
    )
    from scripts.nodes.save_artifact_nodes import _normalize_video_shot_plan

    plan = load_plan(output_dir)
    if plan is None:
        raise FileNotFoundError(f"No plan.json in {output_dir}")

    before = sum(len(s.get("video_shots") or []) for s in plan.get("scenes") or [])
    story_view = story_plan_view(plan)
    video_raw = video_shot_plan_view(plan)
    normalized = _normalize_video_shot_plan(video_raw, story_view)
    plan = apply_video_shots_to_plan(plan, normalized)
    save_plan_dict(output_dir, plan)
    after = sum(len(s.get("video_shots") or []) for s in plan.get("scenes") or [])

    cleared = 0
    specs_path = os.path.join(output_dir, "generation_specs.json")
    if os.path.isfile(specs_path):
        with open(specs_path, encoding="utf-8") as f:
            specs = json.load(f)
        motion = specs.get("motion") or {}
        new_ids = {
            vs.get("video_shot_id")
            for sc in plan.get("scenes") or []
            for vs in (sc.get("video_shots") or [])
            if vs.get("video_shot_id")
        }
        keep: dict = {}
        for key, entry in motion.items():
            if "_vshot_" in key:
                cleared += 1
                continue
            keep[key] = entry
        # Drop orphaned completed entries that no longer exist in plan
        for key in list(keep):
            if "_vshot_" in key and key not in new_ids:
                keep.pop(key, None)
                cleared += 1
        specs["motion"] = keep
        with open(specs_path, "w", encoding="utf-8") as f:
            json.dump(specs, f, indent=2, ensure_ascii=False)

    # Also refresh video_shot_plan.json if present / for resume state
    vsp_path = os.path.join(output_dir, "video_shot_plan.json")
    with open(vsp_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)

    return {
        "output_dir": output_dir,
        "video_shots_before": before,
        "video_shots_after": after,
        "motion_vshot_entries_cleared": cleared,
        "plan_path": os.path.join(output_dir, "plan.json"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Repair video_shots for cast-coherent start frames"
    )
    parser.add_argument(
        "output_dir",
        help="Run directory containing plan.json (e.g. outputs/story-maker/story-naila-5m-v2)",
    )
    args = parser.parse_args(argv)
    out = os.path.abspath(args.output_dir)
    summary = repair_plan_video_shots_cast_coherence(out)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
