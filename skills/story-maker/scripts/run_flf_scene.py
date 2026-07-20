#!/usr/bin/env python3
"""Plan + generate assistant-director I2V/FLF clips for a storyboard scene.

Examples:
  # Plan only (writes generation_specs.storyboard_video_scenes)
  VISION_MODEL=openai/gpt-5-mini \\
  .venv/bin/python scripts/run_flf_scene.py \\
    --output-dir ../../outputs/story-maker/story-naila-5m-v2 \\
    --scene scene_01 --plan-only

  # Plan + generate all clips
  VISION_MODEL=openai/gpt-5-mini \\
  .venv/bin/python scripts/run_flf_scene.py \\
    --output-dir ../../outputs/story-maker/story-naila-5m-v2 \\
    --scene scene_01

  # Generate from an existing saved plan
  .venv/bin/python scripts/run_flf_scene.py \\
    --output-dir ../../outputs/story-maker/story-naila-5m-v2 \\
    --scene scene_01 --generate-only

  # Director-v2 backend (LTX Director Hotfix), specific clips only
  STORY_MAKER_VIDEO_BACKEND=director_v2 \\
  .venv/bin/python scripts/run_flf_scene.py \\
    --output-dir ../../outputs/story-maker/story-naila-5m-v2 \\
    --scene scene_07 --generate-only \\
    --clip-ids scene_07_seg_01_clip_01,scene_07_seg_02_clip_01
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parents[1]
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))


def _parse_clip_ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.replace(" ", ",").split(",") if part.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Storyboard assistant-director I2V/FLF scene runner"
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--scene", default="scene_01")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument(
        "--clip-ids",
        default="",
        help="Comma-separated clip ids to generate (others left untouched)",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Regenerate even if clip mp4 already exists",
    )
    args = parser.parse_args(argv)

    output_dir = str(Path(args.output_dir).resolve())
    scene_id = args.scene
    clip_ids = _parse_clip_ids(args.clip_ids)

    import config
    from scripts.nodes.plan_io import load_plan
    from scripts.nodes.storyboard_director_nodes import (
        _load_scene_paper,
        _load_specs,
        _save_specs,
        generate_storyboard_video_clips,
        load_or_migrate_scene_plan,
        persist_scene_plan,
        plan_storyboard_video_scene,
    )

    print("COMFYUI_URL=", config.COMFYUI_URL)
    print("VISION_MODEL=", config.get_vision_model_id())
    print("FLF2V_TEMPLATE=", config.FLF2V_TEMPLATE_NAME)
    print("STORYBOARD_VIDEO_MODE=", config.STORYBOARD_VIDEO_MODE)
    print("STORY_MAKER_VIDEO_BACKEND=", config.STORY_MAKER_VIDEO_BACKEND)
    if clip_ids:
        print("CLIP_IDS=", clip_ids)

    specs = _load_specs(output_dir)
    plan = load_plan(output_dir) or {}
    scene_paper = _load_scene_paper(output_dir)
    scene = next(
        (s for s in (plan.get("scenes") or []) if s.get("scene_id") == scene_id),
        None,
    )
    if not scene:
        raise SystemExit(f"Scene {scene_id} not found in plan.json")

    scene_plan = None
    if args.generate_only:
        scene_plan = load_or_migrate_scene_plan(specs, scene_id, scene)
        if not scene_plan or not (scene_plan.get("clips") or scene_plan.get("segments")):
            raise SystemExit(
                f"No saved director plan for {scene_id}; run without --generate-only first"
            )
        print(
            f"Loaded plan clips={len(scene_plan.get('clips') or [])} "
            f"scene_total={scene_plan.get('duration_total_seconds')}s"
        )
    else:
        scene_plan = asyncio.run(
            plan_storyboard_video_scene(
                output_dir=output_dir,
                scene_id=scene_id,
                plan=plan,
                scene_paper=scene_paper,
                specs=specs,
            )
        )
        print(json.dumps(scene_plan, indent=2, ensure_ascii=False))
        from scripts.nodes.flf_storyboard_planner import sync_ad_durations_to_plan_scene
        from scripts.nodes.plan_io import save_plan_dict

        persist_scene_plan(specs, {**scene_plan, "status": "planned"})
        plan = sync_ad_durations_to_plan_scene(plan, scene_plan)
        save_plan_dict(output_dir, plan)
        _save_specs(output_dir, specs)
        print(f"Saved plan → generation_specs.storyboard_video_scenes.{scene_id}")
        print(
            f"Director scene total: {scene_plan.get('duration_total_seconds')}s "
            f"({len(scene_plan.get('clips') or [])} clips)"
        )
        if scene_plan.get("repairs"):
            print("Repairs:", scene_plan["repairs"])

    if args.plan_only:
        return 0

    n = len(clip_ids) if clip_ids else len(scene_plan.get("clips") or [])
    print(f"Generating {n} clip(s)...")
    out = generate_storyboard_video_clips(
        output_dir=output_dir,
        scene_plan=scene_plan,
        specs=specs,
        skip_existing=not args.no_skip_existing,
        clip_ids=clip_ids or None,
    )
    persist_scene_plan(specs, out)
    _save_specs(output_dir, specs)
    touched = (
        [c for c in out["clips"] if c.get("clip_id") in set(clip_ids)]
        if clip_ids
        else out["clips"]
    )
    ok = sum(1 for c in touched if c.get("status") in ("completed", "skipped_exists"))
    err = sum(1 for c in touched if c.get("status") == "error")
    print(f"Done: ok={ok} err={err} status={out.get('status')}")
    return 0 if err == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
