"""Post-image vision motion prompt authoring for LTX I2V."""
from __future__ import annotations

import asyncio
import json
import os

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from tools.vision_llm import vision_motion_prompt
from ._json_util import clean_json_str
from .generation_nodes import _load_specs, _only_scenes, _save_specs, _shot_in_scope

_MAX_CONCURRENCY = 4
_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_system_prompt() -> str:
    path = os.path.join(_SKILL_DIR, "prompts", "vision_motion_prompter.md")
    with open(path, encoding="utf-8") as f:
        return f.read()


def build_vision_user_context(
    shot: dict,
    scene: dict,
    shot_index: int,
    audio_shot: dict | None,
    characters: list[dict],
) -> str:
    """Assemble per-shot user text for the vision LLM (testable, no image)."""
    beat_list = []
    for i, s in enumerate(scene.get("shots", []), start=1):
        marker = " <-- THIS SHOT" if s.get("shot_id") == shot.get("shot_id") else ""
        beat_list.append(
            f"  {i}. {s.get('shot_id')}: {s.get('description', '')}{marker}"
        )

    char_lines = []
    for c in characters:
        char_lines.append(
            f"- {c.get('id')}: {c.get('name')} — {c.get('appearance', '')}"
        )

    audio_block = json.dumps(audio_shot or {}, indent=2, ensure_ascii=False)

    return f"""## Scene context
scene_id: {scene.get('scene_id')}
title: {scene.get('title')}
environment: {scene.get('environment')}
time_of_day: {scene.get('time_of_day')}
lighting: {scene.get('lighting')}

### Beat sequence in this scene
{chr(10).join(beat_list)}

## This shot (shot {shot_index} of {len(scene.get('shots', []))})
shot_id: {shot.get('shot_id')}
duration_seconds: {shot.get('duration_seconds')}
pace: {shot.get('pace')}
ltx_shot_type: {shot.get('ltx_shot_type')}
ltx_complexity: {shot.get('ltx_complexity')}
scene_time_offset_seconds: {shot.get('scene_time_offset_seconds', 0)}
continuity_from_previous: {shot.get('continuity_from_previous', False)}
characters_present: {shot.get('characters_present', [])}
description: {shot.get('description', '')}
environment_state: {shot.get('environment_state', '')}
motion_intent: {shot.get('motion_intent', '')}
camera_intent: {shot.get('camera_intent', '')}
audio_intent: {shot.get('audio_intent', '')}

## Character roster (map audio character_id to on-screen roles — do not use names in motion text)
{chr(10).join(char_lines)}

## Audio plan for this shot
{audio_block}

Write the LTX motion_prompt paragraph for the attached starting frame."""


def _find_shot_context(story: dict, shot_id: str) -> tuple[dict, dict, int] | None:
    for scene in story.get("scenes", []):
        for index, shot in enumerate(scene.get("shots", []), start=1):
            if shot.get("shot_id") == shot_id:
                return scene, shot, index
    return None


def _needs_vision_prompt(motion_entry: dict, image_path: str) -> bool:
    if not motion_entry.get("vision_confirmed"):
        return True
    if motion_entry.get("vision_source_image") != image_path:
        return True
    if not (motion_entry.get("motion_prompt") or "").strip():
        return True
    return False


async def vision_motion_prompter(ctx: Context) -> None:
    output_dir = ctx.state.get("output_dir")
    specs = _load_specs(ctx)
    only_scenes = _only_scenes(ctx)

    story_raw = ctx.state.get("story_plan_content")
    if not story_raw:
        path = os.path.join(output_dir, "story_plan.json")
        with open(path, encoding="utf-8") as f:
            story_raw = json.dumps(json.load(f))
    story = clean_json_str(story_raw) if isinstance(story_raw, str) else story_raw

    audio_raw = ctx.state.get("audio_plan_content")
    if not audio_raw:
        audio_path = os.path.join(output_dir, "audio_plan.json")
        if os.path.isfile(audio_path):
            with open(audio_path, encoding="utf-8") as f:
                audio_raw = json.dumps(json.load(f))
    audio_plan = clean_json_str(audio_raw) if audio_raw else {}
    audio_shots = audio_plan.get("shots", {}) if isinstance(audio_plan, dict) else {}

    system_prompt = _load_system_prompt()
    characters = story.get("characters", [])
    sem = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _one(shot_id: str) -> None:
        if not _shot_in_scope(shot_id, only_scenes):
            return
        image_entry = specs.get("shot_images", {}).get(shot_id, {})
        image_path = image_entry.get("output_path")
        if not image_path or not os.path.isfile(image_path):
            print(f"  ⏭️ [vision_motion] skip {shot_id} — no image yet")
            return

        motion_entry = specs.setdefault("motion", {}).setdefault(
            shot_id,
            {"shot_id": shot_id, "status": "pending"},
        )
        if not _needs_vision_prompt(motion_entry, image_path):
            return

        found = _find_shot_context(story, shot_id)
        if not found:
            print(f"  ⚠️ [vision_motion] {shot_id} not in story plan")
            return
        scene, shot, shot_index = found
        user_text = build_vision_user_context(
            shot,
            scene,
            shot_index,
            audio_shots.get(shot_id),
            characters,
        )

        async with sem:
            print(f"  Vision motion: {shot_id}")
            prompt = await vision_motion_prompt(
                image_path,
                system_prompt,
                user_text,
            )

        motion_entry["motion_prompt"] = prompt
        motion_entry["vision_confirmed"] = True
        motion_entry["vision_source_image"] = image_path
        motion_entry["status"] = "prompted"
        motion_entry.setdefault("shot_id", shot_id)
        motion_entry.setdefault("duration_seconds", shot.get("duration_seconds", 8))
        motion_entry.setdefault(
            "scene_time_offset_seconds", shot.get("scene_time_offset_seconds", 0)
        )
        motion_entry.setdefault("pace", shot.get("pace", "medium"))
        motion_entry.setdefault("motion_intent", shot.get("motion_intent", ""))
        motion_entry.setdefault("camera_intent", shot.get("camera_intent", ""))
        motion_entry.setdefault("audio_intent", shot.get("audio_intent", ""))

    tasks = [
        _one(shot_id)
        for shot_id in specs.get("shot_images", {})
        if isinstance(specs["shot_images"].get(shot_id), dict)
    ]
    await asyncio.gather(*tasks)
    _save_specs(ctx, specs)
    print("✅ [vision_motion_prompter] Motion prompts updated from starting frames")


vision_motion_prompter_node = FunctionNode(
    func=vision_motion_prompter, name="vision_motion_prompter_node"
)
