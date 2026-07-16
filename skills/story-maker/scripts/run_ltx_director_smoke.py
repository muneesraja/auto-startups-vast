#!/usr/bin/env python3
"""Smoke test: LTX Director Hotfix workflow via ComfyUI /prompt (I2V or FLF).

Modes:
  1) Manual image pair (legacy):
       python scripts/run_ltx_director_smoke.py --mode flf --image ... --last-image ...

  2) From a saved Assistant Director plan (preferred for scene smoke):
       python scripts/run_ltx_director_smoke.py \\
         --from-spec ../../outputs/story-maker/story-naila-5m-v2 \\
         --scene scene_07 \\
         --clip-ids scene_07_seg_01_clip_01,scene_07_seg_02_clip_01,scene_07_seg_03_clip_01
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[1]
sys.path.insert(0, str(SKILL_ROOT))

import config  # noqa: E402
from tools.ltx_director_timeline import snap_ltx_frames  # noqa: E402
from tools.ltx_director_workflow import (  # noqa: E402
    DIRECTOR_FPS,
    generate_ltx_director_from_clip,
    generate_ltx_director_video,
)
from tools.ltx_render_params import resolve_clip_render_params  # noqa: E402


def _load_specs(output_dir: Path) -> dict:
    path = output_dir / "generation_specs.json"
    if not path.is_file():
        raise SystemExit(f"generation_specs.json not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _still_paths(specs: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for sid, entry in (specs.get("shot_images") or {}).items():
        if not isinstance(entry, dict):
            continue
        path = entry.get("output_path")
        if path and Path(path).is_file():
            out[sid] = path
    return out


def _scene_clips(specs: dict, scene_id: str) -> list[dict]:
    scenes = specs.get("storyboard_video_scenes") or {}
    scene = scenes.get(scene_id) or {}
    clips = scene.get("clips") or []
    if not clips and scene.get("segments"):
        clips = [
            c for seg in scene["segments"] for c in (seg.get("clips") or [])
        ]
    return clips


def _parse_clip_ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.replace(" ", ",").split(",") if part.strip()]


def _run_manual(args: argparse.Namespace) -> int:
    image_path = Path(args.image)
    if not image_path.is_file():
        print(f"Image not found: {image_path}")
        return 1

    print("COMFYUI_URL =", config.COMFYUI_URL)
    print("Mode:", args.mode)

    last_image = None
    if args.mode == "flf":
        last_path = Path(args.last_image)
        if not last_path.is_file():
            print(f"Last image not found: {last_path}")
            return 1
        last_image = str(last_path)

    duration_frames = snap_ltx_frames(args.seconds, fps=args.fps)
    print("Duration frames:", duration_frames)

    result = generate_ltx_director_video(
        first_frame_path=str(image_path),
        last_frame_path=last_image,
        output_path=args.out,
        motion_prompt=args.motion_prompt,
        duration_seconds=args.seconds,
        workflow="flf2v" if args.mode == "flf" else "i2v",
        global_prompt=args.global_prompt,
        first_guide_strength=args.guide_strength,
        last_guide_strength=args.last_guide_strength,
        cfg=args.cfg,
        fps=args.fps,
        width=args.width,
        height=args.height,
        seed=args.seed,
    )
    if result.get("status") != "success":
        print("FAILED:", result.get("message"))
        return 1
    out_path = Path(result["video_path"])
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"OK: {out_path} ({size_mb:.1f} MB)")
    return 0


def _run_from_spec(args: argparse.Namespace) -> int:
    output_dir = Path(args.from_spec).resolve()
    specs = _load_specs(output_dir)
    stills = _still_paths(specs)
    clips = _scene_clips(specs, args.scene)
    if not clips:
        raise SystemExit(f"No AD clips found for {args.scene} in {output_dir}")

    wanted = set(_parse_clip_ids(args.clip_ids))
    if wanted:
        clips = [c for c in clips if (c.get("clip_id") or "") in wanted]
        missing = wanted - {(c.get("clip_id") or "") for c in clips}
        if missing:
            raise SystemExit(f"Unknown clip ids: {sorted(missing)}")
        if not clips:
            raise SystemExit("No clips matched --clip-ids")

    smoke_dir = (
        Path(args.out_dir).resolve()
        if args.out_dir
        else REPO_ROOT / "outputs/story-maker/_smoke" / args.scene
    )
    smoke_dir.mkdir(parents=True, exist_ok=True)

    print("COMFYUI_URL =", config.COMFYUI_URL)
    print("from-spec =", output_dir)
    print("scene =", args.scene)
    print("clips =", [c.get("clip_id") for c in clips])
    print("out-dir =", smoke_dir)

    errors = 0
    for clip in clips:
        clip_id = clip.get("clip_id") or "clip"
        start_id = clip.get("start_panel_id") or clip.get("first_panel_id")
        end_id = clip.get("end_panel_id") or clip.get("last_panel_id") or start_id
        first_path = stills.get(start_id or "")
        last_path = stills.get(end_id or "")
        if not first_path:
            print(f"❌ {clip_id}: missing still {start_id}")
            errors += 1
            continue

        render = resolve_clip_render_params(clip, prefer_stored=True)
        workflow = (clip.get("workflow") or "i2v").lower()
        if workflow in ("i2v_hold", "i2v") or start_id == end_id:
            workflow = "i2v"
        else:
            workflow = "flf2v"
            if not last_path:
                print(f"❌ {clip_id}: missing still {end_id}")
                errors += 1
                continue

        out_path = smoke_dir / f"{clip_id}.mp4"
        print(
            f"▶ {clip_id} [{workflow}] {start_id} → {end_id} "
            f"dur={clip.get('duration_seconds')}s "
            f"class={render['motion_class']} strength={render['i2v_strength']} "
            f"cfg={render['cfg']}"
        )
        print(f"  stills: {first_path}" + (f" | {last_path}" if workflow == "flf2v" else ""))

        result = generate_ltx_director_from_clip(
            clip,
            first_frame_path=first_path,
            last_frame_path=last_path if workflow == "flf2v" else None,
            output_path=str(out_path),
            global_prompt=args.global_prompt,
            fps=args.fps,
            width=args.width,
            height=args.height,
            seed=args.seed,
        )
        if result.get("status") != "success":
            print(f"  ❌ {clip_id}: {result.get('message')}")
            errors += 1
            continue
        size_mb = out_path.stat().st_size / (1024 * 1024)
        print(
            f"  OK: {out_path} ({size_mb:.1f} MB) "
            f"frames={result.get('duration_frames')} "
            f"guide={result.get('guide_strength')}"
        )

    print(f"Done: ok={len(clips) - errors} err={errors}")
    return 0 if errors == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="LTX Director I2V/FLF smoke test")
    parser.add_argument(
        "--from-spec",
        default="",
        help="Story output dir containing generation_specs.json (AD plan smoke)",
    )
    parser.add_argument("--scene", default="scene_07")
    parser.add_argument(
        "--clip-ids",
        default="",
        help="Comma-separated clip ids to render (with --from-spec)",
    )
    parser.add_argument(
        "--out-dir",
        default="",
        help="Directory for --from-spec outputs (default: outputs/story-maker/_smoke/<scene>)",
    )
    parser.add_argument(
        "--mode",
        choices=("i2v", "flf"),
        default="i2v",
        help="Manual mode: i2v = single start frame; flf = first+last with isEndFrame",
    )
    parser.add_argument(
        "--image",
        default=str(
            REPO_ROOT
            / "outputs/story-maker/story-naila-5m-v2/panel_crops/scene_07_shot_01.png"
        ),
        help="Start panel (I2V) or first frame (FLF)",
    )
    parser.add_argument(
        "--last-image",
        default=str(
            REPO_ROOT
            / "outputs/story-maker/story-naila-5m-v2/panel_crops/scene_07_shot_02.png"
        ),
        help="Last frame panel (FLF only)",
    )
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--fps", type=int, default=DIRECTOR_FPS)
    parser.add_argument("--guide-strength", type=float, default=0.7)
    parser.add_argument("--last-guide-strength", type=float, default=0.85)
    parser.add_argument("--cfg", type=float, default=1.0)
    parser.add_argument(
        "--global-prompt",
        default="",
        help="Optional LTXDirector global_prompt (default empty for AD smoke)",
    )
    parser.add_argument(
        "--motion-prompt",
        default=(
            "A cinematic scene bridging two storyboard poses. Over the first two seconds "
            "the subject shifts weight and begins the transition. By the midpoint the "
            "body completes the main gesture. In the final seconds the pose settles toward "
            "the ending still. Static locked-off camera. Natural character animation."
        ),
    )
    parser.add_argument(
        "--out",
        default="",
        help="Manual-mode output mp4 path "
        "(default: outputs/story-maker/_smoke/ltx_director_{mode}_smoke.mp4)",
    )
    parser.add_argument("--width", type=int, default=config.VIDEO_WIDTH)
    parser.add_argument("--height", type=int, default=config.VIDEO_HEIGHT)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.from_spec:
        return _run_from_spec(args)

    if not args.out:
        name = (
            "ltx_director_flf_smoke.mp4"
            if args.mode == "flf"
            else "ltx_director_i2v_smoke.mp4"
        )
        args.out = str(REPO_ROOT / "outputs/story-maker/_smoke" / name)
    # Keep prior manual-smoke default look when no --global-prompt was intended:
    if args.global_prompt == "" and "--global-prompt" not in sys.argv:
        args.global_prompt = (
            "Cinematic 3D animation, warm natural lighting, shallow depth of field."
        )
    return _run_manual(args)


if __name__ == "__main__":
    raise SystemExit(main())
