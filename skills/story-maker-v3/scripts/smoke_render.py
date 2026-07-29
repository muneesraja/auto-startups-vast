#!/usr/bin/env python3
"""Smoke test: render ONE LTX Director Hotfix clip via ComfyUI /prompt.

Verifies the Phase-1 "hands" stack (config + comfyui_tools + ltx_director_*
tools) against a real ComfyUI running the repo-root Hotfix workflow, before any
agent/image plumbing is wired.

  I2V  (single start frame):
    python3 scripts/smoke_render.py --mode i2v --image path/to/start.png

  FLF2V (start + end frame guides):
    python3 scripts/smoke_render.py --mode flf --image path/to/start.png \\
        --last-image path/to/end.png

Trimmed from skills/story-maker/scripts/run_ltx_director_smoke.py: the
--from-spec AD-plan mode was dropped (v3 uses motion_<scene>.json with
render_units[], rendered by scripts/render_all.py, not this smoke).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[1]
sys.path.insert(0, str(SKILL_ROOT))

import config  # noqa: E402
from tools.ltx_director_timeline import snap_ltx_frames  # noqa: E402
from tools.ltx_director_workflow import (  # noqa: E402
    DIRECTOR_FPS,
    generate_ltx_director_video,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="LTX Director single-clip smoke test")
    parser.add_argument(
        "--mode",
        choices=("i2v", "flf"),
        default="i2v",
        help="i2v = single start frame; flf = first+last with isEndFrame (FLF2V)",
    )
    parser.add_argument("--image", required=True, help="Start frame (I2V) or first frame (FLF)")
    parser.add_argument("--last-image", default="", help="Last frame panel (FLF only)")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--fps", type=int, default=DIRECTOR_FPS)
    parser.add_argument("--guide-strength", type=float, default=0.7)
    parser.add_argument("--last-guide-strength", type=float, default=0.85)
    parser.add_argument("--cfg", type=float, default=1.0)
    parser.add_argument(
        "--global-prompt",
        default="Cinematic 3D animation, warm natural lighting, shallow depth of field.",
        help="LTXDirector global_prompt",
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
        help="Output mp4 path (default: outputs/story-maker-v3/_smoke/ltx_director_{mode}_smoke.mp4)",
    )
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.width is None:
        args.width = config.DIRECTOR_VIDEO_WIDTH
    if args.height is None:
        args.height = config.DIRECTOR_VIDEO_HEIGHT

    image_path = Path(args.image)
    if not image_path.is_file():
        print(f"Image not found: {image_path}")
        return 1

    last_image = None
    if args.mode == "flf":
        if not args.last_image:
            print("--mode flf requires --last-image")
            return 1
        last_path = Path(args.last_image)
        if not last_path.is_file():
            print(f"Last image not found: {last_path}")
            return 1
        last_image = str(last_path)

    if not args.out:
        name = (
            "ltx_director_flf_smoke.mp4"
            if args.mode == "flf"
            else "ltx_director_i2v_smoke.mp4"
        )
        args.out = str(REPO_ROOT / "outputs/story-maker-v3/_smoke" / name)

    print("COMFYUI_URL =", config.COMFYUI_URL)
    print("Mode:", args.mode)
    print("Duration frames:", snap_ltx_frames(args.seconds, fps=args.fps))

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


if __name__ == "__main__":
    raise SystemExit(main())