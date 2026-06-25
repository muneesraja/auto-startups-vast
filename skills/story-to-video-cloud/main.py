"""Graph-native Story-to-Video cloud pipeline entrypoint.

Pipeline graph:
    START -> resume_router_node
    resume_router_node -> {
        'fresh' or 'director_script' or 'fflf_plan' or 'blueprint_structure' or 'blueprint' or 'prompts':
            <entry-point LlmAgent in the linear chain>,
        'wave_payloads': wave_organizer_node,
        'all_complete': wave_executor_node,
    }
    <linear chain>: director_script_agent -> save_director_script_node
        -> fflf_visual_planner_agent -> save_fflf_plan_node
        -> blueprint_structure_agent -> parse_blueprint_structure_node -> save_blueprint_structure_node
        -> blueprint_visuals_agent -> parse_blueprint_node -> save_blueprint_node
        -> character_sheet_prompter -> char_spatial_mapper_agent
        -> parse_character_spatial_map_node -> save_character_spatial_map_node
        -> ff_shot_prompter -> reference_integrity_ff_node
        -> lf_delta_planner_agent -> parse_lf_delta_plan_node -> save_lf_delta_plan_node
        -> lf_shot_prompter -> reference_integrity_lf_node
        -> motion_prompter -> save_prompts_node
        -> validate_prompts_node -> wave_organizer_node -> wave_executor_node
"""
import os
import sys
import logging
import traceback
import argparse
import asyncio
from datetime import datetime, timezone

# Make the skill package root importable so agents/nodes resolve correctly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class _TeeWriter:
    """Writes to both the original stream and a log file simultaneously."""
    def __init__(self, original, log_file):
        self._orig = original
        self._log = log_file

    def write(self, data):
        self._orig.write(data)
        self._log.write(data)
        self._log.flush()

    def flush(self):
        self._orig.flush()
        self._log.flush()

    def __getattr__(self, name):
        return getattr(self._orig, name)


def _setup_logging(output_dir: str) -> str:
    """Configure file logging and tee stdout/stderr into a timestamped log."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(output_dir, f"pipeline_{ts}.log")
    log_fh = open(log_path, "w", encoding="utf-8", buffering=1)  # line-buffered

    # Tee stdout + stderr so every print() and exception lands in the log too
    sys.stdout = _TeeWriter(sys.__stdout__, log_fh)
    sys.stderr = _TeeWriter(sys.__stderr__, log_fh)

    # Route Python logging (ADK internals use this) to the same file
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.__stdout__),  # terminal (unforked)
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
        force=True,
    )
    # Silence extremely chatty third-party loggers that add noise without value
    for noisy in ("httpx", "httpcore", "urllib3", "openai", "litellm"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return log_path

from google.adk import Workflow
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import START, JoinNode
from google.genai import types

from config import DEFAULT_OUTPUT_BASE_DIR
from agents.step1_director_script import director_script_agent
from agents.step1_5_fflf_visual_planner import fflf_visual_planner_agent
from agents.step2a_blueprint_structure import blueprint_structure_agent
from agents.step2b_blueprint_visuals import blueprint_visuals_agent
from agents.step3_character_prompter import character_sheet_prompter
from agents.step4_5_char_spatial_mapper import char_spatial_mapper_agent
from agents.step4_ff_prompter import ff_shot_prompter
from agents.step5_lf_delta_planner import lf_delta_planner_agent
from agents.step5_5_lf_prompter import lf_shot_prompter
from agents.step6_motion_prompter import motion_prompter

from scripts.nodes.resume_router import resume_router_node
from scripts.nodes.parse_json_node import (
    parse_blueprint_structure_node,
    parse_blueprint_node,
    parse_lf_delta_plan_node,
    parse_character_spatial_map_node,
)
from scripts.nodes.save_artifact_nodes import (
    save_director_script_node,
    save_fflf_plan_node,
    save_blueprint_structure_node,
    save_blueprint_node,
    save_lf_delta_plan_node,
    save_character_spatial_map_node,
    save_prompts_node,
)
from scripts.nodes.reference_integrity_node import reference_integrity_ff_node, reference_integrity_lf_node
from scripts.nodes.validate_prompts_node import validate_prompts_node
from scripts.nodes.character_ref_validator_node import character_ref_validator_node
from scripts.nodes.wave_nodes import wave_organizer_node, wave_executor_node

# Fan-in join node — waits for all 4 post-blueprint parallel branches
join_prompts_node = JoinNode(name="join_prompts_node")


def _build_pipeline(output_dir: str, fresh: bool) -> Workflow:
    """Assemble the full prompt-generation + wave pipeline as a single Workflow."""
    edges = [
        # 0. Resume entry point
        (START, resume_router_node),

        # Resume router jumps directly to the entry-point node
        (resume_router_node, {
            "director_script": director_script_agent,
            "fflf_plan": fflf_visual_planner_agent,
            "blueprint_structure": blueprint_structure_agent,
            "blueprint": blueprint_visuals_agent,
            "prompts": save_blueprint_node,
            "wave_payloads": wave_organizer_node,
            "all_complete": wave_executor_node,
        }),
    ]

    # Linear chain LLM agents + save/parse nodes
    edges += [
        (director_script_agent, save_director_script_node),
        (save_director_script_node, fflf_visual_planner_agent),

        (fflf_visual_planner_agent, save_fflf_plan_node),
        (save_fflf_plan_node, blueprint_structure_agent),

        (blueprint_structure_agent, parse_blueprint_structure_node),
        (parse_blueprint_structure_node, save_blueprint_structure_node),
        (save_blueprint_structure_node, blueprint_visuals_agent),

        (blueprint_visuals_agent, parse_blueprint_node),
        (parse_blueprint_node, save_blueprint_node),
        # --- Fan-out: 4 parallel branches from blueprint ---

        # Branch 1: Character Sheet Prompter (standalone)
        (save_blueprint_node, character_sheet_prompter),

        # Branch 2: Spatial Mapper → FF Prompter → Reference Integrity FF
        (save_blueprint_node, char_spatial_mapper_agent),
        (char_spatial_mapper_agent, parse_character_spatial_map_node),
        (parse_character_spatial_map_node, save_character_spatial_map_node),
        (save_character_spatial_map_node, ff_shot_prompter),
        (ff_shot_prompter, reference_integrity_ff_node),

        # Branch 3: LF Delta Planner → LF Prompter → Reference Integrity LF
        (save_blueprint_node, lf_delta_planner_agent),
        (lf_delta_planner_agent, parse_lf_delta_plan_node),
        (parse_lf_delta_plan_node, save_lf_delta_plan_node),
        (save_lf_delta_plan_node, lf_shot_prompter),
        (lf_shot_prompter, reference_integrity_lf_node),

        # Branch 4: Motion Prompter (standalone)
        (save_blueprint_node, motion_prompter),

        # --- Fan-in: JoinNode waits for all 4 branches ---
        (character_sheet_prompter, join_prompts_node),
        (reference_integrity_ff_node, join_prompts_node),
        (reference_integrity_lf_node, join_prompts_node),
        (motion_prompter, join_prompts_node),

        # --- Continue serial chain ---
        (join_prompts_node, save_prompts_node),
        (save_prompts_node, character_ref_validator_node),
        (character_ref_validator_node, validate_prompts_node),
        (validate_prompts_node, wave_organizer_node),
        (wave_organizer_node, wave_executor_node),
    ]

    return Workflow(name="StoryToVideoCloudPipeline", edges=edges)


async def main_async():
    parser = argparse.ArgumentParser(description="Cloud Story-to-Video Pipeline")
    parser.add_argument("--story", required=True, help="Story text or path to file containing story text")
    parser.add_argument("--name", required=True, help="Name of the story output directory")
    parser.add_argument("--dir", default=None, help="Custom absolute path to output directory")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Wipe pipeline-owned artifacts and run all steps from scratch.",
    )
    parser.add_argument(
        "--stop-before-generation",
        action="store_true",
        help="Run prompt generation + wave organizer, then stop before any ComfyUI/fal.ai generation.",
    )
    parser.add_argument(
        "--stop-after-char-sheets",
        action="store_true",
        help="Generate character sheets via fal.ai, then stop before generating scenes or videos.",
    )
    parser.add_argument(
        "--only-shots",
        default=None,
        help="Comma-separated list of shot IDs to execute (e.g. scene_01_shot_01).",
    )
    parser.add_argument(
        "--only-scenes",
        default=None,
        help="Comma-separated list of scene IDs to execute (e.g. scene_01).",
    )
    parser.add_argument(
        "--eager-video",
        action="store_true",
        help="Queue video nodes eagerly as soon as their first and last frames are ready.",
    )
    parser.add_argument(
        "--skip-video",
        action="store_true",
        help="Skip ComfyUI video generation steps.",
    )
    args = parser.parse_args()

    # Read story from string or file
    story_text = args.story
    if os.path.exists(story_text):
        with open(story_text, "r", encoding="utf-8") as f:
            story_text = f.read()

    output_dir = args.dir
    if not output_dir:
        output_dir = os.path.join(DEFAULT_OUTPUT_BASE_DIR, args.name)

    os.makedirs(output_dir, exist_ok=True)
    log_path = _setup_logging(output_dir)
    print(f"📝 Logging to: {log_path}")
    print(f"Output directory initialized at: {output_dir}")
    print(f"--fresh mode: {bool(args.fresh)}")
    print(f"--stop-before-generation mode: {bool(args.stop_before_generation)}")
    print(f"--stop-after-char-sheets mode: {bool(args.stop_after_char_sheets)}")
    print(f"--only-shots: {args.only_shots}")
    print(f"--only-scenes: {args.only_scenes}")
    print(f"--eager-video: {bool(args.eager_video)}")
    print(f"--skip-video: {bool(args.skip_video)}")

    only_shots_list = None
    if args.only_shots:
        only_shots_list = [s.strip() for s in args.only_shots.split(",") if s.strip()]

    only_scenes_list = None
    if args.only_scenes:
        only_scenes_list = [s.strip() for s in args.only_scenes.split(",") if s.strip()]

    initial_state = {
        "story_text": story_text,
        "output_dir": output_dir,
        "fresh": bool(args.fresh),
        "stop_before_generation": bool(args.stop_before_generation),
        "stop_after_char_sheets": bool(args.stop_after_char_sheets),
        "only_shots": only_shots_list,
        "only_scenes": only_scenes_list,
        "eager_video": bool(args.eager_video),
        "skip_video": bool(args.skip_video),
    }

    pipeline_wf = _build_pipeline(output_dir, args.fresh)

    APP_NAME = "story_to_video_cloud"
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id="director",
        session_id="session_1",
        state=initial_state,
    )

    runner = Runner(
        agent=pipeline_wf,
        app_name=APP_NAME,
        session_service=session_service,
    )

    user_message = types.Content(parts=[types.Part(text=story_text)])

    print(f"\n🚀 Running Graph-Native Cloud Pipeline (Workflow nodes + LLM agents + save nodes)...")
    started_at = datetime.now(timezone.utc)

    # Handle uncaught async exceptions (e.g. dropped tasks in parallel branches)
    def _async_exc_handler(loop, context):
        msg = context.get("exception", context["message"])
        logging.error("Unhandled async exception: %s", msg, exc_info=context.get("exception"))
    asyncio.get_event_loop().set_exception_handler(_async_exc_handler)

    try:
        async for event in runner.run_async(
            user_id="director",
            session_id="session_1",
            new_message=user_message,
        ):
            author = getattr(event, "author", "unknown")
            content_text = ""
            if hasattr(event, "content") and event.content and event.content.parts:
                content_text = "".join(p.text for p in event.content.parts if p.text)[:100]
            if content_text or author not in ("unknown",):
                print(f"[{author}] {event.__class__.__name__}: {content_text}")

        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        print(f"\n✅ Pipeline complete in {elapsed:.1f}s.")

    except Exception:  # noqa: BLE001
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        print(f"\n💥 Pipeline FAILED after {elapsed:.1f}s — full traceback below:")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main_async())
