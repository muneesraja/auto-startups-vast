#!/usr/bin/env python3
"""Force-regenerate selected panel stills (deletes images, then runs panel_regen)."""
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
        "--shots",
        required=True,
        help="Comma-separated shot ids, e.g. scene_01_shot_08,scene_01_shot_09",
    )
    parser.add_argument("--style-id", default="reel_v2")
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)
    shots = [s.strip() for s in args.shots.split(",") if s.strip()]
    if not shots:
        raise SystemExit("No shots provided")

    plan_path = os.path.join(output_dir, "plan.json")
    specs_path = os.path.join(output_dir, "generation_specs.json")
    for path in (plan_path, specs_path):
        if not os.path.isfile(path):
            raise SystemExit(f"Missing required artifact: {path}")

    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    with open(specs_path, encoding="utf-8") as f:
        specs = json.load(f)

    images_dir = os.path.join(output_dir, "images")
    for shot_id in shots:
        path = os.path.join(images_dir, f"{shot_id}.png")
        if os.path.isfile(path):
            os.remove(path)
            print(f"🗑️  removed {path}")
        entry = (specs.get("shot_images") or {}).get(shot_id)
        if isinstance(entry, dict):
            entry["status"] = "pending"
            entry.pop("output_path", None)
            entry.pop("fal_image_url", None)

    with open(specs_path, "w", encoding="utf-8") as f:
        json.dump(specs, f, indent=2, ensure_ascii=False)
        f.write("\n")

    os.environ["PANEL_REGEN_SHOTS"] = ",".join(shots)
    os.environ.setdefault("STORYBOARD_VIDEO_MODE", "director")

    from scripts.nodes.storyboard_nodes import panel_regen

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
            "only_scenes": None,
        }
    )
    await panel_regen(ctx)  # type: ignore[arg-type]
    print("✅ regen complete for:", ", ".join(shots))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
