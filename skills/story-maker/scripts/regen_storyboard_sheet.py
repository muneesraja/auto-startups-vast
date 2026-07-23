#!/usr/bin/env python3
"""Force-regenerate one storyboard sheet only (no panel crops / panel regen)."""
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
        "--sheet",
        required=True,
        help="Sheet id, e.g. scene_02_sheet_01",
    )
    parser.add_argument("--style-id", default="reel_v2")
    parser.add_argument(
        "--location-id",
        default=None,
        help="Optional override for this sheet's location_ref_id (e.g. loc_02)",
    )
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)
    sheet_id = args.sheet.strip()
    plan_path = os.path.join(output_dir, "plan.json")
    specs_path = os.path.join(output_dir, "generation_specs.json")
    for path in (plan_path, specs_path):
        if not os.path.isfile(path):
            raise SystemExit(f"Missing required artifact: {path}")

    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    with open(specs_path, encoding="utf-8") as f:
        specs = json.load(f)

    scene_id = "_".join(sheet_id.split("_")[:2])  # scene_02_sheet_01 → scene_02
    only_scenes = [scene_id]

    class _Ctx:
        def __init__(self, state: dict):
            self.state = state
            self.route = None

    from profiles import get_profile

    profile = get_profile(args.style_id)
    ctx = _Ctx(
        {
            "output_dir": output_dir,
            "style_id": args.style_id,
            "story_plan_content": json.dumps(plan, ensure_ascii=False),
            "generation_specs_content": json.dumps(specs, ensure_ascii=False),
            "only_scenes": only_scenes,
            "panels_per_sheet": profile.panels_per_sheet or 8,
        }
    )

    from scripts.nodes.storyboard_nodes import (
        storyboard_sheet_generator,
        storyboard_sheet_planner,
    )

    # Replan sheets (preserves out-of-scope sheets) then force-regenerate target.
    await storyboard_sheet_planner(ctx)
    specs = json.loads(ctx.state["generation_specs_content"])
    entry = (specs.get("storyboard_sheets") or {}).get(sheet_id)
    if not isinstance(entry, dict):
        raise SystemExit(f"Sheet {sheet_id} missing after planner")

    if args.location_id:
        entry["location_ref_id"] = args.location_id
        # Rebuild prompt with the new location using planner fields already on entry.
        from scripts.nodes.storyboard_nodes import build_storyboard_sheet_prompt

        scene = next(
            (s for s in plan.get("scenes", []) if s.get("scene_id") == scene_id),
            None,
        )
        if not scene:
            raise SystemExit(f"Scene {scene_id} not in plan.json")
        scene = dict(scene)
        scene["location_id"] = args.location_id
        shot_ids = entry.get("panel_shot_ids") or []
        shots_by_id = {
            sh["shot_id"]: sh
            for sc in plan.get("scenes", [])
            for sh in (sc.get("shots") or [])
            if isinstance(sh, dict) and sh.get("shot_id")
        }
        chunk = [shots_by_id[sid] for sid in shot_ids if sid in shots_by_id]
        entry["sheet_prompt"] = build_storyboard_sheet_prompt(
            scene,
            chunk,
            render_style=get_profile(args.style_id).render_style,
            sheet_number=int(sheet_id.rsplit("_", 1)[-1]),
            story_characters=plan.get("characters") or [],
            style_id=args.style_id,
            locations=plan.get("locations") or [],
            continuity_from_sheet_id=entry.get("continuity_from_sheet_id"),
            has_location_ref=True,
            has_previous_sheet_ref=bool(entry.get("attach_previous_sheet_ref")),
            continuity_mode=entry.get("continuity_mode"),
        )

    out_path = entry.get("output_path") or os.path.join(
        output_dir, "storyboard_sheets", f"{sheet_id}.png"
    )
    if os.path.isfile(out_path):
        os.remove(out_path)
        print(f"🗑️  removed {out_path}")
    entry["status"] = "pending"
    entry.pop("fal_image_url", None)
    entry["panel_bboxes"] = []
    specs["storyboard_sheets"][sheet_id] = entry
    with open(specs_path, "w", encoding="utf-8") as f:
        json.dump(specs, f, indent=2, ensure_ascii=False)
        f.write("\n")
    ctx.state["generation_specs_content"] = json.dumps(specs, ensure_ascii=False)

    print(
        f"🎬 regenerating {sheet_id} "
        f"(mode={entry.get('continuity_mode')}, "
        f"attach_prev={entry.get('attach_previous_sheet_ref')}, "
        f"loc={entry.get('location_ref_id')})"
    )
    await storyboard_sheet_generator(ctx)
    print(f"✅ sheet-only regen complete: {sheet_id}")
    print("⏸️  stopped before panel crops / panel regen (confirm before continuing)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
