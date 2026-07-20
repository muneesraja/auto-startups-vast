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

_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SKILL_DIR)

from profiles import PROFILES, resolve_style


def _apply_model_cli_overrides(argv: list[str] | None = None) -> None:
    """Set planning model env vars before agents bind models at import time."""
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--planning-model")
    pre.add_argument("--narrative-expander-model")
    pre.add_argument("--story-plan-model")
    pre.add_argument("--story-developer-model")
    pre.add_argument("--image-provider")
    pre.add_argument("--style")
    pre.add_argument("--sequential-shots", action="store_true", default=None)
    pre_args, _ = pre.parse_known_args(argv)
    if pre_args.planning_model:
        os.environ["PLANNING_MODEL"] = pre_args.planning_model
    if pre_args.narrative_expander_model:
        os.environ["NARRATIVE_EXPANDER_MODEL"] = pre_args.narrative_expander_model
    if pre_args.story_plan_model:
        os.environ["STORY_PLAN_MODEL"] = pre_args.story_plan_model
    if pre_args.story_developer_model:
        os.environ["STORY_DEVELOPER_MODEL"] = pre_args.story_developer_model
    if pre_args.image_provider:
        os.environ["PROVIDER"] = pre_args.image_provider
    if pre_args.style:
        os.environ["STORY_STYLE"] = pre_args.style.strip().lower()
    if pre_args.sequential_shots:
        os.environ["SEQUENTIAL_SHOT_PROMPTS"] = "1"


_apply_model_cli_overrides()

from google.adk import Workflow
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import START, JoinNode
from google.genai import types

import config
from scripts.nodes.resume_router import (
    resume_router_node,
    resume_prompters_entry_node,
)
from scripts.nodes.plan_pipeline_nodes import (
    sheet_map_builder_node,
    save_production_plan_node,
    persist_enriched_plan_node,
    build_generation_specs_from_plan_node,
    specs_entry_router_node,
)
from scripts.nodes.save_artifact_nodes import (
    save_developed_story_node,
    save_scene_paper_node,
    merge_generation_specs_node,
)
from scripts.nodes.timeline_enricher_node import timeline_enricher_node
from scripts.nodes.duration_budget_validator_node import duration_budget_validator_node
from scripts.nodes.reference_integrity_node import reference_integrity_node
from scripts.nodes.validate_specs_node import validate_generation_specs_node
from scripts.nodes.noop_node import pipeline_complete_node
from scripts.nodes.generation_nodes import (
    generation_router_node,
    background_generator_node,
    character_sheet_generator_node,
    location_sheet_generator_node,
    shot_image_generator_node,
    video_generator_node,
    concat_videos_node,
)
from scripts.nodes.sequential_shot_image_node import (
    image_generation_router_node,
    sequential_shot_image_generator_node,
)
from scripts.nodes.storyboard_nodes import (
    panel_crop_node,
    panel_regen_node,
    storyboard_sheet_generator_node,
    storyboard_sheet_planner_node,
)
from scripts.nodes.vision_motion_prompter_node import vision_motion_prompter_node
from scripts.nodes.image_qa_node import image_qa_node
from scripts.nodes.video_qa_node import video_qa_node
from scripts.nodes.cost_estimate_node import cost_estimate_node
from scripts.nodes.storyboard_director_nodes import (
    storyboard_director_planner_node,
    storyboard_video_router_node,
    storyboard_director_video_generator_node,
)

from agents.story_developer import story_developer_agent
from agents.scene_paper_author import scene_paper_author_agent
from agents.production_plan_author import production_plan_author_agent
from agents.character_sheet_prompter import character_sheet_prompter_agent
from agents.shot_reference_strategist import shot_reference_strategist_agent

join_prompters_node = JoinNode(name="join_prompters_node")


def _build_pipeline() -> Workflow:
    edges = [
        (START, resume_router_node),
        (resume_router_node, {
            "developed_story": story_developer_agent,
            "scene_paper": scene_paper_author_agent,
            "plan": sheet_map_builder_node,
            "generation_specs": specs_entry_router_node,
            "generate": background_generator_node,
            "all_complete": pipeline_complete_node,
        }),
        # Planning: developed story → scene_paper → sheet map → production plan
        (story_developer_agent, save_developed_story_node),
        (save_developed_story_node, scene_paper_author_agent),
        (scene_paper_author_agent, save_scene_paper_node),
        (save_scene_paper_node, sheet_map_builder_node),
        (sheet_map_builder_node, production_plan_author_agent),
        (production_plan_author_agent, save_production_plan_node),
        (save_production_plan_node, timeline_enricher_node),
        (timeline_enricher_node, duration_budget_validator_node),
        (duration_budget_validator_node, persist_enriched_plan_node),
        (persist_enriched_plan_node, specs_entry_router_node),
        (specs_entry_router_node, {
            "storyboard": build_generation_specs_from_plan_node,
            "per_shot": resume_prompters_entry_node,
        }),
        (resume_prompters_entry_node, character_sheet_prompter_agent),
        (resume_prompters_entry_node, shot_reference_strategist_agent),
        (character_sheet_prompter_agent, join_prompters_node),
        (shot_reference_strategist_agent, join_prompters_node),
        (join_prompters_node, merge_generation_specs_node),
        # Specs validate
        (build_generation_specs_from_plan_node, reference_integrity_node),
        (merge_generation_specs_node, reference_integrity_node),
        (reference_integrity_node, validate_generation_specs_node),
        (validate_generation_specs_node, generation_router_node),
        (generation_router_node, {
            "generate": background_generator_node,
            "plan_only": cost_estimate_node,
        }),
        (cost_estimate_node, pipeline_complete_node),
        # Generation chain
        (background_generator_node, character_sheet_generator_node),
        (character_sheet_generator_node, location_sheet_generator_node),
        (location_sheet_generator_node, image_generation_router_node),
        (image_generation_router_node, {
            "parallel": shot_image_generator_node,
            "sequential": sequential_shot_image_generator_node,
            "storyboard": storyboard_sheet_planner_node,
        }),
        (storyboard_sheet_planner_node, storyboard_sheet_generator_node),
        (storyboard_sheet_generator_node, panel_crop_node),
        (panel_crop_node, panel_regen_node),
        (panel_regen_node, storyboard_video_router_node),
        (storyboard_video_router_node, {
            "director": storyboard_director_planner_node,
            "fallback": vision_motion_prompter_node,
        }),
        (storyboard_director_planner_node, storyboard_director_video_generator_node),
        (storyboard_director_video_generator_node, concat_videos_node),
        (shot_image_generator_node, image_qa_node),
        (image_qa_node, vision_motion_prompter_node),
        (sequential_shot_image_generator_node, vision_motion_prompter_node),
        (vision_motion_prompter_node, video_generator_node),
        (video_generator_node, video_qa_node),
        (video_qa_node, concat_videos_node),
    ]
    return Workflow(name="StoryMakerV2Pipeline", edges=edges)


def _read_story(story_arg: str | None, story_file: str | None) -> str:
    if story_file:
        with open(story_file, encoding="utf-8") as f:
            return f.read().strip()
    if story_arg:
        return story_arg.strip()
    raise ValueError("Provide --story or --story-file")


def resolve_output_layout(
    *,
    name: str | None,
    story_id: str | None,
    part: int | None,
    base_dir: str,
) -> tuple[str, str, str]:
    """Return ``(story_root, output_dir, asset_root)``.

    Series mode (``story_id`` + ``part``):
      story_root = asset_root = ``<base>/<story_id>``
      output_dir = ``<story_root>/part-<n>``

    Legacy flat mode (``name``):
      story_root = asset_root = output_dir = ``<base>/<name>``
    """
    has_name = bool((name or "").strip())
    has_series = bool((story_id or "").strip()) and part is not None
    if has_name and has_series:
        raise ValueError("Provide either --name OR (--story-id and --part), not both")
    if not has_name and not has_series:
        raise ValueError("Provide --name OR (--story-id and --part)")
    if has_series:
        if part is None or int(part) < 1:
            raise ValueError("--part must be a positive integer")
        sid = (story_id or "").strip().strip("/")
        if not sid:
            raise ValueError("--story-id must be non-empty")
        story_root = os.path.join(base_dir, sid)
        output_dir = os.path.join(story_root, f"part-{int(part)}")
        return story_root, output_dir, story_root
    flat = os.path.join(base_dir, (name or "").strip())
    return flat, flat, flat


def _parse_target_duration(value: str) -> int:
    s = value.strip().lower().replace(" ", "")
    if s.endswith("min"):
        return int(float(s[:-3]) * 60)
    if s.endswith("m") and not s.endswith("am") and not s.endswith("pm"):
        return int(float(s[:-1]) * 60)
    if s.endswith("s"):
        return int(float(s[:-1]))
    return int(float(s))


async def main_async():
    parser = argparse.ArgumentParser(description="Story Maker V2 — ADK multi-agent pipeline")
    parser.add_argument("--story", type=str, help="Raw story text")
    parser.add_argument("--story-file", type=str, help="Path to story text file")
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Output directory name (legacy flat layout under outputs/story-maker/<name>)",
    )
    parser.add_argument(
        "--story-id",
        type=str,
        default=None,
        help="Story series id (e.g. story-naila). Use with --part for shared assets.",
    )
    parser.add_argument(
        "--part",
        type=int,
        default=None,
        help="Series part number (1, 2, …). Writes to <story-id>/part-<n>/.",
    )
    parser.add_argument("--fresh", action="store_true", help="Wipe artifacts and replan")
    parser.add_argument(
        "--skip-story-developer",
        action="store_true",
        help="Skip LLM story developer; copy raw story into developed_story.md",
    )
    parser.add_argument(
        "--target-duration",
        type=str,
        default=None,
        help="Target film length: seconds (300), or 5m / 5min",
    )
    parser.add_argument(
        "--duration-tolerance",
        type=int,
        default=15,
        help="Allowed deviation from target duration percent (default 15)",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Run planning and write cost_estimate.json; skip all paid generation",
    )
    parser.add_argument(
        "--stop-before-generation",
        action="store_true",
        help="Run through vision motion prompts; skip LTX video generation",
    )
    parser.add_argument(
        "--only-scenes",
        default=None,
        help="Comma-separated scene ids for partial generation",
    )
    parser.add_argument(
        "--style",
        type=str,
        default=None,
        choices=tuple(sorted(PROFILES.keys())),
        help="Story style profile (cinematic, reels, or reel_v2)",
    )
    parser.add_argument(
        "--sequential-shots",
        action="store_true",
        default=None,
        help="Sequentially author and render shot images within each scene using the previous frame as context",
    )
    parser.add_argument(
        "--planning-model",
        type=str,
        default=None,
        help="OpenRouter model for both narrative expander and shot director (e.g. z-ai/glm-5.2)",
    )
    parser.add_argument(
        "--narrative-expander-model",
        type=str,
        default=None,
        help="Override model for narrative_outline.json only",
    )
    parser.add_argument(
        "--story-plan-model",
        type=str,
        default=None,
        help="Override model for story_plan.json only",
    )
    parser.add_argument(
        "--image-provider",
        type=str,
        default=None,
        choices=("fal", "replicate"),
        help="Image backend (sets PROVIDER: replicate default, or legacy fal)",
    )
    args = parser.parse_args()
    profile = resolve_style(args.style, os.environ.get("STORY_STYLE"))
    os.environ["STORY_STYLE"] = profile.id
    sequential_shots = (
        bool(args.sequential_shots)
        if args.sequential_shots is not None
        else os.getenv("SEQUENTIAL_SHOT_PROMPTS", "").lower() in ("1", "true", "yes")
    )

    try:
        story_text = _read_story(args.story, args.story_file)
    except ValueError as e:
        parser.error(str(e))

    try:
        story_root, output_dir, asset_root = resolve_output_layout(
            name=args.name,
            story_id=args.story_id,
            part=args.part,
            base_dir=config.DEFAULT_OUTPUT_BASE_DIR,
        )
    except ValueError as e:
        parser.error(str(e))

    os.makedirs(story_root, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(asset_root, exist_ok=True)
    for shared in ("characters", "locations", "backgrounds"):
        os.makedirs(os.path.join(asset_root, shared), exist_ok=True)

    only_scenes = None
    if args.only_scenes:
        only_scenes = [s.strip() for s in args.only_scenes.split(",") if s.strip()]

    target_duration_seconds = None
    if args.target_duration:
        try:
            target_duration_seconds = _parse_target_duration(args.target_duration)
        except ValueError as e:
            parser.error(f"Invalid --target-duration: {e}")
    else:
        target_duration_seconds = profile.default_target_seconds

    initial_state = {
        "story_text": story_text,
        "developed_story_text": "",
        "developed_story_content": "",
        "story_sheet_scene_text": "",
        "sheet_map_context": "",
        "plan_content": "",
        "video_shot_plan_content": "",
        "output_dir": output_dir,
        "story_root": story_root,
        "asset_root": asset_root,
        "story_id": (args.story_id or args.name or "").strip() or None,
        "part": args.part,
        "fresh": bool(args.fresh),
        "skip_story_developer": bool(args.skip_story_developer),
        "plan_only": bool(args.plan_only),
        "stop_before_generation": bool(args.stop_before_generation),
        "only_scenes": only_scenes,
        "style_id": profile.id,
        "pipeline_mode": profile.pipeline_mode,
        "panels_per_sheet": profile.panels_per_sheet,
        "min_panels_per_sheet": profile.min_panels_per_sheet,
        "use_backgrounds": profile.use_backgrounds,
        "sequential_shots": sequential_shots,
        "min_shot_seconds": profile.min_shot_seconds,
        "max_shot_seconds": profile.max_shot_seconds,
        "default_pace": profile.default_pace,
        "target_duration_seconds": target_duration_seconds,
        "duration_tolerance_percent": args.duration_tolerance,
        "storyboard_video_mode": config.STORYBOARD_VIDEO_MODE,
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
    if asset_root != output_dir:
        print(f"Shared assets (asset_root): {asset_root}")
    if target_duration_seconds:
        print(f"Target duration: {target_duration_seconds}s (±{args.duration_tolerance}%)")
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
