#!/usr/bin/env python3
"""Minimax H3 renderer + concat (the slow "hands" stage). No LLM calls.

Sequential single-pass render with tail-video conditioning:

  For each scene, render generations in order (g1, g2, ...).
  After rendering gK, extract its tail (3s) as a ref_video.
  When rendering g(K+1), pass the tail of gK as extra_reference_video_paths
  so the model sees the actual rendered ending of the previous clip.
  g1 has no tail ref (first generation of the run).
  Cross-scene: the tail of the last generation in scene N is passed to
  g1 of scene N+1.
  Concat: per scene, then scenes -> final_film.mp4, preserving Minimax's
  native stereo audio.

  python3 scripts/render_all.py --output-dir <run> [--only-scenes s1,s2]
      [--tail-ref-seconds 3]

Long-running (hours). Fire-and-forget; the SKILL.md launches it in the
background. Resume: existing clip files are skipped; only missing clips +
downstream concats re-execute.

Set ``NTFY_URL`` in the environment (e.g. ``ntfy.sh/topic``) to receive a
push notification after each generation, each scene, and the final film.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

import config  # noqa: E402
from tools import image_pipeline as ip  # noqa: E402
from tools import validators  # noqa: E402
from tools.minimax_workflow import render_generation  # noqa: E402
from tools.video_concat import concat_videos  # noqa: E402
from tools.video_frames import extract_tail  # noqa: E402


def _exists(path: str) -> bool:
    return bool(path) and os.path.isfile(path) and os.path.getsize(path) > 0


def _ntfy(message: str) -> None:
    """Send a push notification to ``NTFY_URL`` if it is set in the env."""
    ntfy_url = os.environ.get("NTFY_URL", os.environ.get("NTFY_TOPIC"))
    if not ntfy_url:
        return
    try:
        subprocess.run(
            ["curl", "-d", message, ntfy_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except Exception:
        pass


def _find_sheet(run_dir: str, scene_id: str, gen_id: str) -> str:
    """Find the storyboard sheet image for a generation."""
    for ext in ("webp", "png", "jpg", "jpeg"):
        sheet_path = os.path.join(run_dir, f"storyboard_sheet_{scene_id}_{gen_id}.{ext}")
        if _exists(sheet_path):
            return sheet_path
    raise FileNotFoundError(
        f"storyboard sheet missing: {run_dir}/storyboard_sheet_{scene_id}_{gen_id}.<ext>"
    )


def _find_audio_ref(run_dir: str, scene_id: str, gen_id: str) -> list[str] | None:
    """Find optional audio reference attachment for a generation."""
    audio_dir = os.path.join(run_dir, "audio")
    if not os.path.isdir(audio_dir):
        return None
    for ext in ("mp3", "wav", "m4a", "aac", "flac"):
        # 1. <scene_id>_<gen_id>.<ext> (e.g. s1_g1.mp3)
        p = os.path.join(audio_dir, f"{scene_id}_{gen_id}.{ext}")
        if _exists(p):
            return [p]
        # 2. <gen_id>.<ext> (e.g. g1.mp3)
        p = os.path.join(audio_dir, f"{gen_id}.{ext}")
        if _exists(p):
            return [p]
        # 3. <scene_id>.<ext> (e.g. s1.mp3)
        p = os.path.join(audio_dir, f"{scene_id}.{ext}")
        if _exists(p):
            return [p]
    return None


def _render_clip(
    run_dir: str, scene_id: str, gen: dict, clips_dir: str, *,
    seed: int, megapixels: float | None, aspect: str | None,
    extra_video_refs: list[str] | None = None,
) -> str:
    """Render one generation clip. Returns the output mp4 path."""
    gid = gen["gen_id"]
    out_path = os.path.join(clips_dir, f"{gid}.mp4")
    if _exists(out_path):
        print(f"  clip {scene_id}/{gid}: exists, skip")
        return out_path

    sheet_path = _find_sheet(run_dir, scene_id, gid)
    prompt = ip.read_prompt(ip.video_prompt_path(run_dir, scene_id, gid))
    if not prompt:
        raise FileNotFoundError(
            f"video prompt missing: {ip.video_prompt_path(run_dir, scene_id, gid)}"
        )
    extra_audio_refs = _find_audio_ref(run_dir, scene_id, gid)
    duration = (gen["end"] or 0.0) - (gen["start"] or 0.0)
    print(f"  clip {scene_id}/{gid}: rendering ({duration:.1f}s, audio_ref={'yes' if extra_audio_refs else 'no'}) ...")
    result = render_generation(
        sheet_path=sheet_path,
        prompt=prompt,
        duration_seconds=duration,
        output_path=out_path,
        seed=seed,
        megapixels=megapixels,
        aspect=aspect,
        extra_reference_video_paths=extra_video_refs,
        extra_reference_audio_paths=extra_audio_refs,
    )
    if result.get("status") != "success":
        _ntfy(f"[story-maker-v3] {scene_id}/{gid} render failed: {result.get('message', result)}")
        raise RuntimeError(f"clip {scene_id}/{gid} failed: {result.get('message', result)}")
    print(f"    done in {result.get('elapsed_seconds')}s -> {out_path}")
    _ntfy(f"[story-maker-v3] {scene_id}/{gid} render complete -> {out_path}")
    return out_path


def _extract_tail_ref(
    clip_path: str, ref_seconds: float, refs_dir: str, scene_id: str, gen_id: str,
) -> str | None:
    """Extract the tail of a clip for use as a ref_video by the next generation."""
    tail_name = f"tail_{scene_id}_{gen_id}.mp4"
    tail_path = os.path.join(refs_dir, tail_name)
    if _exists(tail_path):
        return tail_path
    if not extract_tail(clip_path, ref_seconds, tail_path):
        print(f"  WARNING: tail extraction failed for {scene_id}/{gen_id}, skipping ref")
        return None
    return tail_path


def render_scene(
    run_dir: str, scene_id: str, *, seed: int,
    megapixels: float | None, aspect: str | None,
    tail_ref_seconds: float = 3.0,
    prev_tail_ref: str | None = None,
) -> tuple[str, str | None]:
    """Render all generations for one scene sequentially with tail refs.

    Returns (scene_mp4_path, last_gen_tail_path) where the tail can be
    passed to the next scene's g1 for cross-scene continuity.
    """
    sb_path = os.path.join(run_dir, f"storyboard_{scene_id}.md")
    sb = validators.parse_storyboard(open(sb_path, encoding="utf-8").read())
    gens = sb["generations"]
    if not gens:
        raise SystemExit(f"storyboard_{scene_id}.md has no generations")

    clips_dir = os.path.join(run_dir, "clips", scene_id)
    os.makedirs(clips_dir, exist_ok=True)
    refs_dir = os.path.join(clips_dir, "refs")

    clip_paths: list[str] = []
    tail_ref = prev_tail_ref  # carries over from previous scene's last gen

    for gen in gens:
        gid = gen["gen_id"]

        # Skip bridge generations (no longer supported, but may exist in old storyboards)
        if gen.get("is_bridge"):
            print(f"  skip {scene_id}/{gid}: bridge generations are no longer supported")
            continue

        extra_video_refs = [tail_ref] if tail_ref else None
        clip_path = _render_clip(
            run_dir, scene_id, gen, clips_dir,
            seed=seed, megapixels=megapixels, aspect=aspect,
            extra_video_refs=extra_video_refs,
        )
        clip_paths.append(clip_path)

        # Extract tail for the next generation
        tail_ref = _extract_tail_ref(
            clip_path, tail_ref_seconds, refs_dir, scene_id, gid,
        )

    scene_mp4 = os.path.join(run_dir, f"scene_{scene_id}.mp4")
    print(f"  concat {len(clip_paths)} clips -> {scene_mp4}")
    res = concat_videos(clip_paths, scene_mp4)
    if res.get("status") != "success":
        _ntfy(f"[story-maker-v3] scene {scene_id} concat failed: {res.get('message')}")
        raise RuntimeError(f"scene concat failed for {scene_id}: {res.get('message')}")
    _ntfy(f"[story-maker-v3] scene {scene_id} complete -> {scene_mp4}")
    return scene_mp4, tail_ref


def main() -> int:
    p = argparse.ArgumentParser(description="Render Minimax H3 generations + concat (sequential with tail refs)")
    p.add_argument("--output-dir", required=True, help="run output dir")
    p.add_argument("--only-scenes", default="", help="comma-separated scene ids to render")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--megapixels", type=float, default=None,
                   help=f"output size in MP (default {config.MINIMAX_MEGAPIXELS}; e.g. 0.6 -> 1056x608)")
    p.add_argument("--aspect", default=None, help=f"aspect ratio (default {config.MINIMAX_ASPECT})")
    p.add_argument("--tail-ref-seconds", type=float, default=3.0,
                   help="seconds of tail to extract as ref video for the next generation (default 3.0)")
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

    # Sequential single-pass: render scenes in order, passing tail refs across scenes
    scene_mp4s: list[str] = []
    prev_tail_ref: str | None = None
    for sid in scene_ids:
        print(f"== scene {sid} ==")
        scene_mp4, prev_tail_ref = render_scene(
            run_dir, sid, seed=args.seed,
            megapixels=args.megapixels, aspect=args.aspect,
            tail_ref_seconds=args.tail_ref_seconds,
            prev_tail_ref=prev_tail_ref,
        )
        scene_mp4s.append(scene_mp4)

    final = os.path.join(run_dir, "final_film.mp4")
    if len(scene_mp4s) == 1:
        os.replace(scene_mp4s[0], final)
        print(f"final_film.mp4 -> {final}")
        _ntfy(f"[story-maker-v3] final film complete -> {final}")
    else:
        res = concat_videos(scene_mp4s, final)
        if res.get("status") != "success":
            _ntfy(f"[story-maker-v3] final concat failed: {res.get('message')}")
            raise SystemExit(f"final concat failed: {res.get('message')}")
        print(f"final_film.mp4 -> {final}")
        _ntfy(f"[story-maker-v3] final film complete -> {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
