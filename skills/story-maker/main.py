#!/usr/bin/env python3
"""Story Maker V2 — ADK Workflow graph pipeline."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google.adk import Workflow
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import START, JoinNode
from google.genai import types

import config
from agents.story_planner import story_planner_agent
from agents.audio_planner import audio_planner_agent
from agents.scene_asset_planner import scene_asset_planner_agent
from agents.character_sheet_prompter import character_sheet_prompter_agent
from agents.shot_reference_strategist import shot_reference_strategist_agent
from agents.motion_prompter import motion_prompter_agent

from scripts.nodes.resume_router import resume_router_node, resume_prompters_entry_node
from scripts.nodes.save_artifact_nodes import (
    save_story_plan_node,
    save_audio_plan_node,
    save_scene_assets_node,
    merge_generation_specs_node,
)
from scripts.nodes.timeline_enricher_node import timeline_enricher_node
from scripts.nodes.reference_integrity_node import reference_integrity_node
from scripts.nodes.validate_specs_node import validate_generation_specs_node
from scripts.nodes.noop_node import pipeline_complete_node
from scripts.nodes.generation_nodes import (
    generation_router_node,
    background_generator_node,
    character_sheet_generator_node,
    shot_image_generator_node,
    video_generator_node,
    concat_videos_node,
)

join_prompters_node = JoinNode(name="join_prompters_node")


def _build_pipeline() -> Workflow:
    edges = [
        (START, resume_router_node),
        (resume_router_node, {
            "story_plan": story_planner_agent,
            "audio_plan": audio_planner_agent,
            "scene_assets": scene_asset_planner_agent,
            "generation_specs": resume_prompters_entry_node,
            "generate": background_generator_node,
            "all_complete": pipeline_complete_node,
        }),
        # Planning chain
        (story_planner_agent, save_story_plan_node),
        (save_story_plan_node, timeline_enricher_node),
        (timeline_enricher_node, audio_planner_agent),
        (audio_planner_agent, save_audio_plan_node),
        (save_audio_plan_node, scene_asset_planner_agent),
        (scene_asset_planner_agent, save_scene_assets_node),
        (resume_prompters_entry_node, character_sheet_prompter_agent),
        (resume_prompters_entry_node, shot_reference_strategist_agent),
        (resume_prompters_entry_node, motion_prompter_agent),
        # Fan-out: three prompters in parallel
        (save_scene_assets_node, character_sheet_prompter_agent),
        (save_scene_assets_node, shot_reference_strategist_agent),
        (save_scene_assets_node, motion_prompter_agent),
        (character_sheet_prompter_agent, join_prompters_node),
        (shot_reference_strategist_agent, join_prompters_node),
        (motion_prompter_agent, join_prompters_node),
        # Fan-in + validate
        (join_prompters_node, merge_generation_specs_node),
        (merge_generation_specs_node, reference_integrity_node),
        (reference_integrity_node, validate_generation_specs_node),
        (validate_generation_specs_node, generation_router_node),
        (generation_router_node, {
            "generate": background_generator_node,
            "stop": pipeline_complete_node,
        }),
        # Generation chain
        (background_generator_node, character_sheet_generator_node),
        (character_sheet_generator_node, shot_image_generator_node),
        (shot_image_generator_node, video_generator_node),
        (video_generator_node, concat_videos_node),
    ]
    return Workflow(name="StoryMakerV2Pipeline", edges=edges)


def _read_story(story_arg: str | None, story_file: str | None) -> str:
    if story_file:
        with open(story_file, encoding="utf-8") as f:
            return f.read().strip()
    if story_arg:
        return story_arg.strip()
    raise ValueError("Provide --story or --story-file")


async def main_async():
    parser = argparse.ArgumentParser(description="Story Maker V2 — ADK multi-agent pipeline")
    parser.add_argument("--story", type=str, help="Raw story text")
    parser.add_argument("--story-file", type=str, help="Path to story text file")
    parser.add_argument("--name", type=str, required=True, help="Output directory name")
    parser.add_argument("--fresh", action="store_true", help="Wipe artifacts and replan")
    parser.add_argument(
        "--stop-before-generation",
        action="store_true",
        help="Run planning + specs only; skip fal/ComfyUI generation",
    )
    parser.add_argument(
        "--only-scenes",
        default=None,
        help="Comma-separated scene ids (reserved for partial generation)",
    )
    args = parser.parse_args()

    try:
        story_text = _read_story(args.story, args.story_file)
    except ValueError as e:
        parser.error(str(e))

    output_dir = os.path.join(config.DEFAULT_OUTPUT_BASE_DIR, args.name)
    os.makedirs(output_dir, exist_ok=True)

    only_scenes = None
    if args.only_scenes:
        only_scenes = [s.strip() for s in args.only_scenes.split(",") if s.strip()]

    initial_state = {
        "story_text": story_text,
        "output_dir": output_dir,
        "fresh": bool(args.fresh),
        "stop_before_generation": bool(args.stop_before_generation),
        "only_scenes": only_scenes,
    }

    pipeline = _build_pipeline()
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="story_maker_v2",
        user_id="director",
        session_id="session_1",
        state=initial_state,
    )

    runner = Runner(
        agent=pipeline,
        app_name="story_maker_v2",
        session_service=session_service,
    )

    print(f"\nStory Maker V2 output: {output_dir}")
    started = datetime.now(timezone.utc)

    try:
        async for event in runner.run_async(
            user_id="director",
            session_id="session_1",
            new_message=types.Content(parts=[types.Part(text=story_text)]),
        ):
            author = getattr(event, "author", "unknown")
            if hasattr(event, "content") and event.content and event.content.parts:
                text = "".join(p.text for p in event.content.parts if p.text)[:80]
                if text:
                    print(f"[{author}] {text}")

        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        print(f"\nDone in {elapsed:.1f}s.")
    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main_async())
