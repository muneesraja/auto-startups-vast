"""Sequential per-scene shot-image prompting and generation."""
from __future__ import annotations

import asyncio
import json
import os

try:
    from google.adk.agents.context import Context
    from google.adk.workflow import FunctionNode
except ImportError:  # pragma: no cover - test fallback without ADK installed
    class Context:  # type: ignore[override]
        pass

    class FunctionNode:  # type: ignore[override]
        def __init__(self, func, name: str):
            self.func = func
            self.name = name

from tools.vision_llm import vision_image_qa, vision_text_from_image
from profiles import get_profile
from ._json_util import clean_json_str
from ._shot_image_gen import generate_one_shot_image
from .generation_nodes import _load_specs, _only_scenes, _save_specs, _shot_in_scope
from .image_qa_node import strengthen_image_prompt
from .reference_integrity_node import reference_integrity
from .save_artifact_nodes import _apply_render_style

_MAX_SCENE_CONCURRENCY = 4
_DEFAULT_MAX_RETRIES = 2
_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_story(ctx: Context) -> dict:
    raw = ctx.state.get("story_plan_content")
    if not raw:
        path = os.path.join(ctx.state["output_dir"], "story_plan.json")
        with open(path, encoding="utf-8") as f:
            raw = json.dumps(json.load(f))
    return clean_json_str(raw) if isinstance(raw, str) else raw


def _load_system_prompt() -> str:
    style = (os.getenv("STORY_STYLE") or "").strip().lower()
    candidates: list[str] = []
    if style and style != "cinematic":
        candidates.append(os.path.join(_SKILL_DIR, "prompts", style, "shot_image_prompter.md"))
    candidates.append(os.path.join(_SKILL_DIR, "prompts", "shot_image_prompter.md"))
    for path in candidates:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
    raise FileNotFoundError(
        "Sequential shot image prompt file not found; tried: " + ", ".join(candidates)
    )


def build_shot_image_user_context(
    shot: dict,
    scene: dict,
    shot_index: int,
    previous_shot: dict | None,
    base_image_prompt: str,
) -> str:
    return f"""## Scene context
scene_id: {scene.get('scene_id')}
title: {scene.get('title')}
environment: {scene.get('environment')}
time_of_day: {scene.get('time_of_day')}
lighting: {scene.get('lighting')}
staging: {scene.get('staging', '')}
blocking: {json.dumps(scene.get('blocking', []), ensure_ascii=False)}

## Previous shot
previous_shot_id: {previous_shot.get('shot_id') if previous_shot else 'none'}
previous_description: {previous_shot.get('description', '') if previous_shot else ''}
previous_subject_position: {previous_shot.get('subject_position', '') if previous_shot else ''}
previous_facing_direction: {previous_shot.get('facing_direction', '') if previous_shot else ''}
previous_eyeline: {previous_shot.get('eyeline', '') if previous_shot else ''}
previous_background_region: {previous_shot.get('background_region', '') if previous_shot else ''}

## Current shot (shot {shot_index} of {len(scene.get('shots', []))})
shot_id: {shot.get('shot_id')}
duration_seconds: {shot.get('duration_seconds')}
pace: {shot.get('pace')}
ltx_shot_type: {shot.get('ltx_shot_type')}
ltx_complexity: {shot.get('ltx_complexity')}
frame_strategy: {shot.get('frame_strategy', 'unset')}
characters_present: {shot.get('characters_present', [])}
description: {shot.get('description', '')}
environment_state: {shot.get('environment_state', '')}
motion_intent: {shot.get('motion_intent', '')}
camera_intent: {shot.get('camera_intent', '')}
audio_intent: {shot.get('audio_intent', '')}
subject_position: {shot.get('subject_position', '')}
facing_direction: {shot.get('facing_direction', '')}
eyeline: {shot.get('eyeline', '')}
background_region: {shot.get('background_region', '')}

## Baseline image prompt from batch strategist
{base_image_prompt}

Write the final Grok image prompt for the current shot using the attached previous frame as continuity context."""


def _shot_brief(story: dict, shot_id: str) -> dict:
    for scene in story.get("scenes", []):
        for shot in scene.get("shots", []):
            if shot.get("shot_id") == shot_id:
                brief = dict(shot)
                brief["background_population"] = scene.get("background_population", "")
                return brief
    return {}


def _needs_sequential_prompt(entry: dict, previous_image_path: str | None) -> bool:
    if not previous_image_path:
        return False
    if not (entry.get("image_prompt") or "").strip():
        return True
    return entry.get("sequential_prompt_source_image") != previous_image_path


def _should_skip_existing(entry: dict, previous_image_path: str | None) -> bool:
    image_path = entry.get("output_path")
    if entry.get("image_qa_status") != "passed":
        return False
    if not image_path or not os.path.isfile(image_path):
        return False
    if previous_image_path and entry.get("sequential_prompt_source_image") != previous_image_path:
        return False
    return True


async def _qa_until_pass(
    ctx: Context,
    story: dict,
    specs: dict,
    shot_id: str,
    entry: dict,
    images_dir: str,
) -> None:
    max_retries = int(os.getenv("IMAGE_QA_MAX_RETRIES", str(_DEFAULT_MAX_RETRIES)))
    brief = _shot_brief(story, shot_id)
    attempts = int(entry.get("image_qa_attempts", 0))

    while True:
        image_path = entry.get("output_path")
        if not image_path or not os.path.isfile(image_path):
            raise RuntimeError(f"Missing image for QA: {shot_id}")

        verdict = await vision_image_qa(image_path, brief)
        passed = bool(verdict.get("pass"))
        reason = verdict.get("reason", "")
        entry["image_qa_reason"] = reason
        if passed:
            entry["image_qa_status"] = "passed"
            _save_specs(ctx, specs)
            return

        entry["image_qa_status"] = "failed"
        attempts += 1
        entry["image_qa_attempts"] = attempts
        _save_specs(ctx, specs)
        if attempts > max_retries:
            if os.getenv("IMAGE_QA_RAISE_ON_EXHAUST", "").lower() in ("1", "true", "yes"):
                raise RuntimeError(f"image QA exhausted retries for {shot_id}: {reason}")
            entry["image_qa_status"] = "passed"
            entry["image_qa_reason"] = f"auto-passed after retry exhaustion: {reason[:200]}"
            _save_specs(ctx, specs)
            return

        entry["image_prompt"] = strengthen_image_prompt(entry.get("image_prompt", ""), reason)
        await generate_one_shot_image(shot_id, entry, specs, images_dir)
        _save_specs(ctx, specs)


async def image_generation_router(ctx: Context) -> None:
    pipeline_mode = ctx.state.get("pipeline_mode", "per_shot")
    if pipeline_mode == "storyboard":
        ctx.route = "storyboard"
    elif bool(ctx.state.get("sequential_shots", False)):
        ctx.route = "sequential"
    else:
        ctx.route = "parallel"


async def sequential_shot_image_generator(ctx: Context) -> None:
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    story = _load_story(ctx)
    only_scenes = _only_scenes(ctx)
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    system_prompt = _load_system_prompt()
    style_id = (ctx.state.get("style_id") or "cinematic").strip().lower()
    render_style = get_profile(style_id).render_style
    sem = asyncio.Semaphore(_MAX_SCENE_CONCURRENCY)

    await reference_integrity(ctx)
    specs = _load_specs(ctx)

    async def _scene(scene: dict) -> None:
        scene_id = scene.get("scene_id")
        if only_scenes and scene_id not in only_scenes:
            return
        previous_image_path: str | None = None
        previous_shot: dict | None = None
        async with sem:
            for shot_index, shot in enumerate(scene.get("shots", []), start=1):
                shot_id = shot.get("shot_id")
                if not shot_id or not _shot_in_scope(shot_id, only_scenes):
                    continue
                entry = specs.get("shot_images", {}).get(shot_id)
                if not isinstance(entry, dict):
                    raise ValueError(f"Missing shot_images entry for {shot_id}")

                entry.setdefault("base_image_prompt", entry.get("image_prompt", ""))

                if _should_skip_existing(entry, previous_image_path):
                    previous_image_path = entry.get("output_path")
                    previous_shot = shot
                    continue

                if _needs_sequential_prompt(entry, previous_image_path):
                    user_text = build_shot_image_user_context(
                        shot,
                        scene,
                        shot_index,
                        previous_shot,
                        entry.get("base_image_prompt", entry.get("image_prompt", "")),
                    )
                    prompt = await vision_text_from_image(
                        previous_image_path,
                        system_prompt,
                        user_text,
                    )
                    entry["image_prompt"] = _apply_render_style(prompt, render_style)
                    entry["sequential_prompt_source_image"] = previous_image_path
                    entry["sequential_prompt_source_shot"] = (
                        previous_shot.get("shot_id") if previous_shot else None
                    )
                    _save_specs(ctx, specs)
                    await reference_integrity(ctx)
                    specs.update(_load_specs(ctx))

                await generate_one_shot_image(shot_id, entry, specs, images_dir)
                _save_specs(ctx, specs)
                await _qa_until_pass(ctx, story, specs, shot_id, entry, images_dir)
                previous_image_path = entry.get("output_path")
                previous_shot = shot

    tasks = [_scene(scene) for scene in story.get("scenes", []) if isinstance(scene, dict)]
    await asyncio.gather(*tasks)
    _save_specs(ctx, specs)
    print("✅ [sequential_shot_image_generator] Sequential scene image generation complete")


image_generation_router_node = FunctionNode(
    func=image_generation_router, name="image_generation_router_node"
)
sequential_shot_image_generator_node = FunctionNode(
    func=sequential_shot_image_generator,
    name="sequential_shot_image_generator_node",
)
