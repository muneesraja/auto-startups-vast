#!/usr/bin/env python3
"""Materialize deterministic spatial continuity blocks into storyboard-sheet prompts.

Reads spatial_plan_sN.md + storyboard_sN.md and injects a generated
SPATIAL CONTINUITY LOCK block into each normal generation's
storyboard_sheet_gK.txt. No LLM calls, no image/video API calls.

  python3 scripts/materialize_spatial_prompts.py --output-dir <run> --scene s1
      # materialize all normal generations for scene s1

  python3 scripts/materialize_spatial_prompts.py --output-dir <run> --scene s1 --gen g2
      # materialize only g2

Legacy scenes without a spatial plan are left unchanged.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from tools import image_pipeline as ip  # noqa: E402
from tools import validators  # noqa: E402
from tools.spatial_validator import parse_spatial_plan  # noqa: E402
from tools.spatial_prompt_builder import materialize_sheet_prompt  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Materialize spatial continuity blocks into sheet prompts")
    ap.add_argument("--output-dir", required=True, help="Run directory (contains spatial_plan_sN.md, storyboard_sN.md)")
    ap.add_argument("--scene", required=True, help="Scene ID (e.g. s1)")
    ap.add_argument("--gen", default=None, help="Only materialize this generation (default: all normal gens)")
    args = ap.parse_args()

    run_dir = args.output_dir
    scene_id = args.scene

    # Load spatial plan
    plan_path = os.path.join(run_dir, f"spatial_plan_{scene_id}.md")
    if not os.path.isfile(plan_path):
        print(f"No spatial plan for {scene_id} ({plan_path}); nothing to materialize.")
        return
    plan = parse_spatial_plan(open(plan_path, encoding="utf-8").read())

    # Load storyboard
    sb_path = os.path.join(run_dir, f"storyboard_{scene_id}.md")
    if not os.path.isfile(sb_path):
        print(f"ERROR: storyboard not found: {sb_path}", file=sys.stderr)
        sys.exit(1)
    sb = validators.parse_storyboard(open(sb_path, encoding="utf-8").read())

    # Process normal generations
    count = 0
    for gen in sb["generations"]:
        if gen.get("is_bridge"):
            continue
        gid = gen["gen_id"]
        if args.gen and gid != args.gen:
            continue
        if gid not in plan["generations"]:
            print(f"  WARNING: {scene_id}/{gid} not in spatial plan; skipping.")
            continue

        sheet_path = ip.sheet_prompt_path(run_dir, scene_id, gid)
        if not os.path.isfile(sheet_path):
            print(f"  WARNING: sheet prompt not found: {sheet_path}; skipping.")
            continue

        prompt_text = ip.read_prompt(sheet_path)
        if not prompt_text:
            print(f"  WARNING: sheet prompt is empty: {sheet_path}; skipping.")
            continue

        materialized = materialize_sheet_prompt(prompt_text, plan, sb, gid)
        with open(sheet_path, "w", encoding="utf-8") as f:
            f.write(materialized)
        print(f"  {scene_id}/{gid}: materialized spatial block into {sheet_path}")
        count += 1

    if count == 0:
        print(f"No normal generations materialized for {scene_id}.")
    else:
        print(f"Done: materialized {count} sheet prompt(s) for {scene_id}.")


if __name__ == "__main__":
    main()
