#!/usr/bin/env python3
"""Validate Director-native storyboards on scene_02 in a fresh output folder.

Steps:
1. Copy plan/specs/images/sheets from a source run into a fresh folder
2. Stamp migrated director_* metadata onto scene_02 shots
3. Re-plan AD chain units (plan-only by default)
4. Optionally render all chain units at 1280x704

Examples:
  .venv/bin/python scripts/run_scene02_director_native_validate.py
  .venv/bin/python scripts/run_scene02_director_native_validate.py --render
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parents[1]
_REPO = _SKILL_DIR.parents[1]
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))


def _copy_tree(src: Path, dst: Path, names: list[str]) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for name in names:
        s = src / name
        d = dst / name
        if not s.exists():
            print(f"  skip missing {name}")
            continue
        if s.is_dir():
            if d.exists():
                shutil.rmtree(d)
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
        print(f"  copied {name}")


def _stamp_director_metadata(plan: dict, scene_id: str) -> dict:
    from scripts.nodes.plan_pipeline_nodes import (
        migrate_director_panel_metadata,
        validate_director_panel_metadata,
    )

    out = dict(plan)
    scenes = []
    for scene in plan.get("scenes") or []:
        sc = dict(scene)
        if sc.get("scene_id") == scene_id:
            shots = migrate_director_panel_metadata(
                [dict(s) for s in (sc.get("shots") or []) if isinstance(s, dict)]
            )
            for issue in validate_director_panel_metadata(shots):
                print(f"  ⚠️ director metadata: {issue}")
            sc["shots"] = shots
            groups: dict[int, list[str]] = {}
            for s in shots:
                gid = s.get("director_chain_group")
                if gid is None:
                    continue
                groups.setdefault(int(gid), []).append(
                    f"{s['shot_id']}[{s.get('director_guide_role')}|{s.get('director_transition_after')}]"
                )
            print("  Authored / migrated Director groups:")
            for gid in sorted(groups):
                print(f"    group {gid}: {' → '.join(groups[gid])}")
        scenes.append(sc)
    out["scenes"] = scenes
    return out


def _summarize_scene_plan(scene_plan: dict) -> None:
    clips = scene_plan.get("clips") or []
    print(f"\nAD plan: {len(clips)} unit(s), total={scene_plan.get('duration_total_seconds')}s")
    for c in clips:
        guides = c.get("guide_frames") or []
        path = [g.get("panel_id") for g in guides if isinstance(g, dict)]
        print(
            f"  {c.get('clip_id')}: {c.get('duration_seconds')}s "
            f"path={path} cut_before={c.get('_cut_before')} "
            f"rationale={str(c.get('rationale') or '')[:80]}"
        )
    if scene_plan.get("repairs"):
        print("  repairs:", scene_plan["repairs"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=str(_REPO / "outputs/story-maker/story-naila-5m-v2"),
        help="Source run with plan.json + panel stills",
    )
    parser.add_argument(
        "--output-dir",
        default=str(_REPO / "outputs/story-maker/story-naila-scene02-director-native"),
        help="Fresh validation folder",
    )
    parser.add_argument("--scene", default="scene_02")
    parser.add_argument(
        "--render",
        action="store_true",
        help="Also render chain units (default is plan-only)",
    )
    parser.add_argument("--force-copy", action="store_true")
    args = parser.parse_args(argv)

    source = Path(args.source).resolve()
    output_dir = Path(args.output_dir).resolve()
    scene_id = args.scene
    plan_only = not args.render

    if not (source / "plan.json").is_file():
        raise SystemExit(f"Missing plan.json in {source}")

    if args.force_copy or not (output_dir / "plan.json").is_file():
        print(f"Preparing fresh folder {output_dir} from {source}")
        _copy_tree(
            source,
            output_dir,
            [
                "plan.json",
                "generation_specs.json",
                "scene_paper.md",
                "developed_story.md",
                "images",
                "panel_crops",
                "storyboard_sheets",
                "characters",
                "locations",
            ],
        )
        # Rewrite absolute paths inside generation_specs to the fresh folder.
        specs_path = output_dir / "generation_specs.json"
        if specs_path.is_file():
            text = specs_path.read_text(encoding="utf-8")
            specs_path.write_text(
                text.replace(str(source), str(output_dir)),
                encoding="utf-8",
            )
            print("  rewrote generation_specs paths → fresh folder")
    else:
        print(f"Reusing existing folder {output_dir} (pass --force-copy to refresh)")

    plan_path = output_dir / "plan.json"
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    plan = _stamp_director_metadata(plan, scene_id)
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    print(f"Wrote director-stamped plan → {plan_path}")

    specs_path = output_dir / "generation_specs.json"
    if specs_path.is_file():
        with open(specs_path, encoding="utf-8") as f:
            specs = json.load(f)
        scenes = specs.get("storyboard_video_scenes") or {}
        if scene_id in scenes:
            del scenes[scene_id]
            specs["storyboard_video_scenes"] = scenes
            with open(specs_path, "w", encoding="utf-8") as f:
                json.dump(specs, f, indent=2, ensure_ascii=False)
            print(f"Cleared prior AD plan for {scene_id}")

    os.environ.setdefault("STORYBOARD_VIDEO_MODE", "director")
    os.environ.setdefault("STORY_MAKER_VIDEO_BACKEND", "director_v2")
    os.environ.setdefault("STORY_MAKER_DIRECTOR_CHAIN", "1")
    # Avoid truncated VISION_MODEL values like "openai/gpt" from ambient shells.
    vision = (os.environ.get("VISION_MODEL") or "").strip()
    if not vision or vision.count("/") == 1 and vision.split("/")[-1] in ("gpt", "openai", ""):
        os.environ["VISION_MODEL"] = "openai/gpt-5-mini"

    from scripts.run_flf_scene import main as run_flf_main

    argv_flf = [
        "--output-dir",
        str(output_dir),
        "--scene",
        scene_id,
    ]
    if plan_only:
        argv_flf.append("--plan-only")
    print("\nRunning AD planner…")
    rc = run_flf_main(argv_flf)

    with open(specs_path, encoding="utf-8") as f:
        specs = json.load(f)
    scene_plan = (specs.get("storyboard_video_scenes") or {}).get(scene_id) or {}
    _summarize_scene_plan(scene_plan)

    compare = _REPO / "outputs/story-maker/story-naila-scene02-director-15s/generation_specs.json"
    if compare.is_file():
        with open(compare, encoding="utf-8") as f:
            old = json.load(f)
        old_plan = (old.get("storyboard_video_scenes") or {}).get(scene_id) or {}
        print("\nCompare vs story-naila-scene02-director-15s:")
        print(
            f"  old units={len(old_plan.get('clips') or [])} "
            f"total={old_plan.get('duration_total_seconds')}"
        )
        print(
            f"  new units={len(scene_plan.get('clips') or [])} "
            f"total={scene_plan.get('duration_total_seconds')}"
        )

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
