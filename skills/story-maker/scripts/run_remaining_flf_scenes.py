#!/usr/bin/env python3
"""Generate remaining storyboard director scenes, then concat final film."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parents[1]
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _scene_ids(output_dir: Path) -> list[str]:
    plan = json.loads((output_dir / "plan.json").read_text(encoding="utf-8"))
    return [s["scene_id"] for s in plan.get("scenes") or [] if s.get("scene_id")]


def _scene_complete(output_dir: Path, scene_id: str) -> bool:
    specs = json.loads((output_dir / "generation_specs.json").read_text(encoding="utf-8"))
    scene_plan = (specs.get("storyboard_video_scenes") or {}).get(scene_id) or {}
    clips = scene_plan.get("clips") or []
    if not clips:
        return False
    if scene_plan.get("status") != "completed":
        # still allow if all clip files exist
        pass
    for clip in clips:
        path = clip.get("output_path")
        if not path or not os.path.isfile(path) or os.path.getsize(path) <= 0:
            return False
        if clip.get("status") not in ("completed", "skipped_exists"):
            return False
    return True


def _run_scene(output_dir: Path, scene_id: str, *, skip_existing: bool) -> None:
    cmd = [
        sys.executable,
        str(_SKILL_DIR / "scripts" / "run_flf_scene.py"),
        "--output-dir",
        str(output_dir),
        "--scene",
        scene_id,
    ]
    if not skip_existing:
        cmd.append("--no-skip-existing")
    print(f"======== START {scene_id} {_utc()} ========", flush=True)
    proc = subprocess.run(cmd, cwd=str(_SKILL_DIR))
    print(f"======== END {scene_id} exit={proc.returncode} {_utc()} ========", flush=True)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def _collect_paths(output_dir: Path) -> list[str]:
    specs = json.loads((output_dir / "generation_specs.json").read_text(encoding="utf-8"))
    plan = json.loads((output_dir / "plan.json").read_text(encoding="utf-8"))
    sb = specs.get("storyboard_video_scenes") or {}
    paths: list[str] = []
    for scene in plan.get("scenes") or []:
        sid = scene.get("scene_id")
        scene_plan = sb.get(sid) or {}
        clips = scene_plan.get("clips") or []
        if not clips and scene_plan.get("segments"):
            clips = [
                c
                for seg in scene_plan["segments"]
                for c in (seg.get("clips") or [])
            ]
        for clip in clips:
            path = clip.get("output_path")
            cid = clip.get("clip_id")
            if not path or not os.path.isfile(path):
                raise SystemExit(f"Missing video for {sid} {cid}: {path}")
            paths.append(path)
    return paths


def _concat(output_dir: Path, paths: list[str], final_name: str) -> Path:
    from tools.video_concat import concat_videos

    final = output_dir / final_name
    print(f"Concat {len(paths)} clips -> {final}", flush=True)
    result = concat_videos(paths, str(final))
    print(result, flush=True)
    if result.get("status") != "success":
        raise SystemExit(result.get("message") or "concat failed")
    return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--from-scene",
        default="scene_03",
        help="First scene to generate (inclusive)",
    )
    parser.add_argument(
        "--skip-existing-scenes",
        action="store_true",
        help="Skip scenes that already have all clip mp4s",
    )
    parser.add_argument(
        "--no-skip-existing-clips",
        action="store_true",
        help="Force regenerate each clip even if mp4 exists",
    )
    parser.add_argument("--final-name", default="final_film_director.mp4")
    parser.add_argument("--concat-only", action="store_true")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).resolve()
    scenes = _scene_ids(output_dir)
    if args.from_scene not in scenes:
        raise SystemExit(f"Unknown --from-scene {args.from_scene}; have {scenes}")

    if not args.concat_only:
        start = scenes.index(args.from_scene)
        for scene_id in scenes[start:]:
            if args.skip_existing_scenes and _scene_complete(output_dir, scene_id):
                print(f"⏭️ skip complete {scene_id}", flush=True)
                continue
            _run_scene(
                output_dir,
                scene_id,
                skip_existing=not args.no_skip_existing_clips,
            )
            if not _scene_complete(output_dir, scene_id):
                raise SystemExit(f"Scene {scene_id} incomplete after generate")
        print("ALL_SCENES_DONE", flush=True)

    paths = _collect_paths(output_dir)
    final = _concat(output_dir, paths, args.final_name)
    print("FINAL_OK", final, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
