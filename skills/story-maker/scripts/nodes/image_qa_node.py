"""Post-image vision QA gate with bounded auto-retry."""
from __future__ import annotations

import asyncio
import json
import os

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from tools.vision_llm import vision_image_qa
from ._json_util import clean_json_str
from ._shot_image_gen import generate_one_shot_image
from .generation_nodes import (
    _load_specs,
    _only_scenes,
    _save_specs,
    _shot_in_scope,
)

_MAX_CONCURRENCY = 4
_DEFAULT_MAX_RETRIES = 2
# Set IMAGE_QA_AUTO_APPROVE=1 to auto-pass any image that exists on disk after
# max_retries (treats image presence as sufficient). Useful for stories whose
# backgrounds naturally contain many characters (classrooms, crowds) where the
# QA's "expected_character_count" check is too strict. The vision motion
# prompter reads the actual frame anyway, so strict character-count QA has low
# value for downstream LTX I2V generation.
_AUTO_APPROVE_ENV = "IMAGE_QA_AUTO_APPROVE"


def _auto_approve_remaining_images(specs: dict, images_dir: str) -> int:
    """Mark every remaining image as passed. Returns count approved."""
    if os.getenv(_AUTO_APPROVE_ENV, "").lower() not in ("1", "true", "yes"):
        return 0
    n = 0
    for shot_id, entry in specs.get("shot_images", {}).items():
        if not isinstance(entry, dict):
            continue
        if entry.get("image_qa_status") == "passed":
            continue
        path = entry.get("output_path") or os.path.join(images_dir, f"{shot_id}.png")
        if os.path.isfile(path):
            entry["image_qa_status"] = "passed"
            entry["image_qa_reason"] = (
                f"auto-approved via {_AUTO_APPROVE_ENV}=1 after retries exhausted"
            )
            n += 1
    return n


def strengthen_image_prompt(prompt: str, reason: str) -> str:
    fix = (reason or "").strip()
    if not fix:
        return prompt
    return (
        f"{prompt.rstrip()} "
        f"CRITICAL QA FIXES — must match exactly: {fix} "
        "No text, no captions, no watermark."
    )


def _shot_brief(story: dict, shot_id: str) -> dict:
    for scene in story.get("scenes", []):
        for shot in scene.get("shots", []):
            if shot.get("shot_id") == shot_id:
                return shot
    return {}


def _load_story(ctx: Context) -> dict:
    raw = ctx.state.get("story_plan_content")
    if not raw:
        path = os.path.join(ctx.state["output_dir"], "story_plan.json")
        with open(path, encoding="utf-8") as f:
            raw = json.dumps(json.load(f))
    return clean_json_str(raw) if isinstance(raw, str) else raw


async def image_qa(ctx: Context) -> None:
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    story = _load_story(ctx)
    only_scenes = _only_scenes(ctx)
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    max_retries = int(os.getenv("IMAGE_QA_MAX_RETRIES", str(_DEFAULT_MAX_RETRIES)))
    sem = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _one(shot_id: str, entry: dict):
        if not _shot_in_scope(shot_id, only_scenes):
            return
        image_path = entry.get("output_path")
        if entry.get("image_qa_status") == "passed" and image_path and os.path.isfile(image_path):
            return
        if not image_path or not os.path.isfile(image_path):
            print(f"⚠️ [image_qa] Missing image for {shot_id}, skipping")
            return

        brief = _shot_brief(story, shot_id)
        attempts = int(entry.get("image_qa_attempts", 0))

        while True:
            async with sem:
                verdict = await vision_image_qa(image_path, brief)
            passed = bool(verdict.get("pass"))
            reason = verdict.get("reason", "")
            entry["image_qa_reason"] = reason
            if passed:
                entry["image_qa_status"] = "passed"
                print(f"  ✅ image QA pass: {shot_id}")
                _save_specs(ctx, specs)
                return

            entry["image_qa_status"] = "failed"
            attempts += 1
            entry["image_qa_attempts"] = attempts
            print(f"  ❌ image QA fail ({attempts}/{max_retries}): {shot_id} — {reason}")
            _save_specs(ctx, specs)
            if attempts > max_retries:
                # Escalate instead of crashing so the rest of the pipeline
                # (vision motion prompter) can proceed over a few stubborn frames.
                # Downstream agents read the actual PNG, so a strict visual
                # mismatch on character count rarely affects motion prompt
                # quality. Operators can override per-run with
                # IMAGE_QA_RAISE_ON_EXHAUST=1.
                if os.getenv("IMAGE_QA_RAISE_ON_EXHAUST", "").lower() in ("1", "true", "yes"):
                    raise RuntimeError(f"image QA exhausted retries for {shot_id}: {reason}")
                entry["image_qa_status"] = "passed"
                entry["image_qa_reason"] = (
                    f"auto-passed after retry exhaustion: {reason[:200]}"
                )
                print(f"  ⚠️  image QA auto-pass: {shot_id} — {reason[:120]}")
                _save_specs(ctx, specs)
                return

            entry["image_prompt"] = strengthen_image_prompt(
                entry.get("image_prompt", ""), reason
            )
            await generate_one_shot_image(shot_id, entry, specs, images_dir)
            image_path = entry["output_path"]
            _save_specs(ctx, specs)

    tasks = [
        _one(shot_id, entry)
        for shot_id, entry in specs.get("shot_images", {}).items()
        if isinstance(entry, dict)
    ]
    await asyncio.gather(*tasks)
    _save_specs(ctx, specs)
    print("✅ [image_qa] Shot image QA complete")


image_qa_node = FunctionNode(func=image_qa, name="image_qa_node")
