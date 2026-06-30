"""Post-video motion QA gate with bounded auto-retry."""
from __future__ import annotations

import asyncio
import os

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from tools.comfyui_tools import generate_ltx_i2v_video
from tools.motion_metrics import motion_energy_passes, strengthen_motion_prompt
from ._shot_image_gen import retry_async
from .generation_nodes import (
    _load_specs,
    _only_scenes,
    _save_specs,
    _shot_in_scope,
)

_MAX_CONCURRENCY = 4
_DEFAULT_MAX_RETRIES = 2


async def video_qa(ctx: Context) -> None:
    if bool(ctx.state.get("stop_before_generation", False)):
        return

    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    only_scenes = _only_scenes(ctx)
    videos_dir = os.path.join(output_dir, "videos")
    os.makedirs(videos_dir, exist_ok=True)
    max_retries = int(os.getenv("VIDEO_QA_MAX_RETRIES", str(_DEFAULT_MAX_RETRIES)))
    sem = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _one(shot_id: str, entry: dict):
        if not _shot_in_scope(shot_id, only_scenes):
            return
        out_path = entry.get("output_path") or os.path.join(videos_dir, f"{shot_id}.mp4")
        if entry.get("motion_qa_status") == "passed" and os.path.isfile(out_path):
            return
        if not os.path.isfile(out_path):
            raise RuntimeError(f"Missing video for motion QA: {shot_id}")

        motion = specs.get("motion", {}).get(shot_id, {})
        attempts = int(entry.get("motion_qa_attempts", 0))

        while True:
            async with sem:
                ok, energy = await asyncio.to_thread(motion_energy_passes, out_path)
            entry["motion_qa_energy"] = round(energy, 4)
            if ok:
                entry["motion_qa_status"] = "passed"
                entry["motion_qa_reason"] = f"motion energy {energy:.3f}"
                print(f"  ✅ motion QA pass: {shot_id} ({energy:.3f})")
                return

            reason = f"low motion energy {energy:.3f}"
            entry["motion_qa_status"] = "failed"
            entry["motion_qa_reason"] = reason
            attempts += 1
            entry["motion_qa_attempts"] = attempts
            print(f"  ❌ motion QA fail ({attempts}/{max_retries}): {shot_id} — {reason}")
            if attempts > max_retries:
                raise RuntimeError(f"motion QA exhausted retries for {shot_id}: {reason}")

            image_entry = specs.get("shot_images", {}).get(shot_id, {})
            image_path = image_entry.get("output_path")
            if not image_path or not os.path.isfile(image_path):
                raise RuntimeError(f"Missing image for video retry: {shot_id}")

            strengthened = strengthen_motion_prompt(motion.get("motion_prompt", ""))
            motion["motion_prompt"] = strengthened
            motion["motion_prompt_retry"] = strengthened
            duration = motion.get("duration_seconds", 8)

            async with sem:
                print(f"  Video retry I2V: {shot_id}")

                def _gen():
                    return generate_ltx_i2v_video(
                        image_path, strengthened, out_path, duration_seconds=duration
                    )

                result = await retry_async(_gen, f"video retry {shot_id}")
                entry["output_path"] = result["video_path"]
                entry["status"] = "completed"

    tasks = [
        _one(shot_id, entry)
        for shot_id, entry in specs.get("motion", {}).items()
        if isinstance(entry, dict)
    ]
    await asyncio.gather(*tasks)
    _save_specs(ctx, specs)
    print("✅ [video_qa] Motion QA complete")


video_qa_node = FunctionNode(func=video_qa, name="video_qa_node")
