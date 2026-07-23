#!/usr/bin/env python3
"""Run panel crop + panel regen only (no video, no sheet regen)."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(_SKILL_DIR), ".env"))
load_dotenv(os.path.join(_SKILL_DIR, ".env"))


async def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--only-scenes",
        default=None,
        help="Comma-separated scene ids (default: all scenes with sheets)",
    )
    parser.add_argument("--style-id", default="reel_v2")
    parser.add_argument(
        "--crops-only",
        action="store_true",
        help="Stop after panel crops (no panel regen / shot images)",
    )
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)
    plan_path = os.path.join(output_dir, "plan.json")
    specs_path = os.path.join(output_dir, "generation_specs.json")
    for path in (plan_path, specs_path):
        if not os.path.isfile(path):
            raise SystemExit(f"Missing required artifact: {path}")

    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    with open(specs_path, encoding="utf-8") as f:
        specs = json.load(f)

    only_scenes = None
    if args.only_scenes:
        only_scenes = [s.strip() for s in args.only_scenes.split(",") if s.strip()]

    class _Ctx:
        def __init__(self, state: dict):
            self.state = state
            self.route = None

    ctx = _Ctx(
        {
            "output_dir": output_dir,
            "style_id": args.style_id,
            "story_plan_content": json.dumps(plan, ensure_ascii=False),
            "video_shot_plan_content": json.dumps({"scenes": []}, ensure_ascii=False),
            "generation_specs_content": json.dumps(specs, ensure_ascii=False),
            "only_scenes": only_scenes,
            "stop_before_generation": True,
        }
    )

    from scripts.nodes.storyboard_nodes import panel_crop, panel_regen

    print("✂️  panel_crop …")
    await panel_crop(ctx)
    if args.crops_only:
        print("⏸️  crops-only — skipped panel regen")
        return 0

    print("🖼️  panel_regen (shot stills) …")
    await panel_regen(ctx)
    print("✅ panel crop + shot regen complete (no video)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
