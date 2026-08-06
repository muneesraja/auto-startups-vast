#!/usr/bin/env python3
"""Minimax H3 renderer + concat (the slow "hands" stage). No LLM calls.

For each scene's ``storyboard_<scene>.md``, renders every generation via the
Minimax H3 R2V ComfyUI workflow — the generation's storyboard sheet is the
ONLY reference image, the Agent-authored ``video_prompts/<scene>_<gen>.txt``
is the timeline prompt, and the duration comes from the storyboard (5-15s,
the Minimax hard limit). Then concatenates generation clips ->
``scene_<scene>.mp4`` and scenes -> ``final_film.mp4``, preserving Minimax's
native stereo audio.

  python3 scripts/render_all.py --output-dir <run> [--only-scenes s1,s2]

Long-running (hours). Fire-and-forget; the SKILL.md launches it in the
background. Resume: existing clip files are skipped; only missing clips +
downstream concats re-execute.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

import config  # noqa: E402
from tools import image_pipeline as ip  # noqa: E402
from tools import validators  # noqa: E402
from tools.minimax_workflow import render_generation  # noqa: E402
from tools.video_concat import concat_videos  # noqa: E402


def _exists(path: str) -> bool:
    return bool(path) and os.path.isfile(path) and os.path.getsize(path) > 0


def render_scene(run_dir: str, scene_id: str, *, seed: int,
                 megapixels: float | None, aspect: str | None) -> str:
    """Render all generations for one scene; return the scene mp4 path."""
    sb_path = os.path.join(run_dir, f"storyboard_{scene_id}.md")
    sb = validators.parse_storyboard(open(sb_path, encoding="utf-8").read())
    gens = sb["generations"]
    if not gens:
        raise SystemExit(f"storyboard_{scene_id}.md has no generations")

    clips_dir = os.path.join(run_dir, "clips", scene_id)
    os.makedirs(clips_dir, exist_ok=True)

    clip_paths: list[str] = []
    for gen in gens:
        gid = gen["gen_id"]
        out_path = os.path.join(clips_dir, f"{gid}.mp4")
        if _exists(out_path):
            print(f"  clip {scene_id}/{gid}: exists, skip")
            clip_paths.append(out_path)
            continue

        for ext in ("webp", "png", "jpg", "jpeg"):
            sheet_path = os.path.join(run_dir, f"storyboard_sheet_{scene_id}_{gid}.{ext}")
            if _exists(sheet_path):
                break
        else:
            raise FileNotFoundError(
                f"storyboard sheet missing: {run_dir}/storyboard_sheet_{scene_id}_{gid}.<ext>"
            )
        prompt = ip.read_prompt(ip.video_prompt_path(run_dir, scene_id, gid))
        if not prompt:
            raise FileNotFoundError(
                f"video prompt missing: {ip.video_prompt_path(run_dir, scene_id, gid)}"
            )
        duration = (gen["end"] or 0.0) - (gen["start"] or 0.0)
        print(f"  clip {scene_id}/{gid}: rendering ({duration:.1f}s) ...")
        result = render_generation(
            sheet_path=sheet_path,
            prompt=prompt,
            duration_seconds=duration,
            output_path=out_path,
            seed=seed,
            megapixels=megapixels,
            aspect=aspect,
        )
        if result.get("status") != "success":
            raise RuntimeError(f"clip {scene_id}/{gid} failed: {result.get('message', result)}")
        print(f"    done in {result.get('elapsed_seconds')}s -> {out_path}")
        clip_paths.append(out_path)

    scene_mp4 = os.path.join(run_dir, f"scene_{scene_id}.mp4")
    print(f"  concat {len(clip_paths)} clips -> {scene_mp4}")
    res = concat_videos(clip_paths, scene_mp4)
    if res.get("status") != "success":
        raise RuntimeError(f"scene concat failed for {scene_id}: {res.get('message')}")
    return scene_mp4


def main() -> int:
    p = argparse.ArgumentParser(description="Render Minimax H3 generations + concat")
    p.add_argument("--output-dir", required=True, help="run output dir")
    p.add_argument("--only-scenes", default="", help="comma-separated scene ids to render")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--megapixels", type=float, default=None,
                   help=f"output size in MP (default {config.MINIMAX_MEGAPIXELS}; e.g. 0.6 -> 1056x608)")
    p.add_argument("--aspect", default=None, help=f"aspect ratio (default {config.MINIMAX_ASPECT})")
    args = p.parse_args()

    run_dir = os.path.abspath(args.output_dir)
    only = {s.strip() for s in args.only_scenes.split(",") if s.strip()}

    # Discover scenes from storyboard_*.md files.
    scene_ids = sorted(
        m.group(1)
        for f in os.listdir(run_dir)
        if (m := re.fullmatch(r"storyboard_([^.]+)\.md", f))
    )
    if only:
        scene_ids = [s for s in scene_ids if s in only]
    if not scene_ids:
        raise SystemExit(f"no storyboard_*.md scenes found in {run_dir}")

    scene_mp4s: list[str] = []
    for sid in scene_ids:
        print(f"== scene {sid} ==")
        scene_mp4s.append(render_scene(
            run_dir, sid, seed=args.seed,
            megapixels=args.megapixels, aspect=args.aspect,
        ))

    final = os.path.join(run_dir, "final_film.mp4")
    if len(scene_mp4s) == 1:
        os.replace(scene_mp4s[0], final)
        print(f"final_film.mp4 -> {final}")
    else:
        res = concat_videos(scene_mp4s, final)
        if res.get("status") != "success":
            raise SystemExit(f"final concat failed: {res.get('message')}")
        print(f"final_film.mp4 -> {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
