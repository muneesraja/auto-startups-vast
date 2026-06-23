"""Story-to-Video deterministic pipeline entrypoint — Flux-only architecture.

Pipeline graph (linear):
    START -> resume_router_node
    resume_router_node -> {
        'director_script' / 'blueprint_structure' / 'blueprint' / 'prompts':
            <entry-point LlmAgent in the linear chain>,
        'wave_payloads': wave_organizer_node,
        'all_complete': wave_executor_node,
    }
    <linear chain>:
        director_script_agent -> save_director_script_node
        -> blueprint_structure_agent -> parse_blueprint_structure_node -> save_blueprint_structure_node
        -> blueprint_visuals_agent -> parse_blueprint_node -> save_blueprint_node
        -> character_sheet_prompter -> char_spatial_mapper_agent
        -> parse_character_spatial_map_node -> save_character_spatial_map_node
        -> ff_shot_prompter
        -> lf_delta_planner_agent -> parse_lf_delta_plan_node -> save_lf_delta_plan_node
        -> lf_prompter_loop (dynamic @node workflow: Generator + Critic, max 3 cycles)
        -> motion_prompter_loop (dynamic @node workflow: Generator + Critic, max 3 cycles)
        -> save_prompts_node -> validate_prompts_node -> wave_organizer_node -> wave_executor_node

Wave 1 (nested workflow):
    cs (Flux Klein T2I char sheets) -> ff (Flux Klein with char refs)
    -> lf (Flux Klein with char sheets + FF as refs)
    -> video (LTX-2.3 FLF2V with FF + LF + motion prompt)

Wave 2 (ordered continuation chain):
    extract_FF (from prev video) -> lf (Flux Klein with char sheets + extracted FF) -> video
"""
import os
import sys
import argparse
import asyncio
from datetime import datetime, timezone

# Make the skill package root importable so `from agents.step1...` and
# `from scripts.nodes...` resolve correctly inside the bundled agent modules.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google.adk import Workflow
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import START
from google.genai import types

from config import DEFAULT_OUTPUT_BASE_DIR
from agents.step1_director_script import director_script_agent
from agents.step2a_blueprint_structure import blueprint_structure_agent
from agents.step2b_blueprint_visuals import blueprint_visuals_agent
from agents.step3_character_prompter import character_sheet_prompter
from agents.step4_5_char_spatial_mapper import char_spatial_mapper_agent
from agents.step4_ff_prompter import ff_shot_prompter
from agents.step6_5_lf_delta_planner import lf_delta_planner_agent
from agents.step6_lf_prompter import lf_prompter_loop
from agents.step7_motion_prompter import motion_prompter_loop

from scripts.nodes.resume_router import resume_router_node
from scripts.nodes.parse_json_node import (
    parse_blueprint_structure_node,
    parse_blueprint_node,
    parse_lf_delta_plan_node,
    parse_character_spatial_map_node,
)
from scripts.nodes.save_artifact_nodes import (
    save_director_script_node,
    save_blueprint_structure_node,
    save_blueprint_node,
    save_lf_delta_plan_node,
    save_character_spatial_map_node,
    save_prompts_node,
)
from scripts.nodes.validate_prompts_node import validate_prompts_node
from scripts.nodes.wave_nodes import wave_organizer_node, wave_executor_node


def _build_pipeline(output_dir: str, fresh: bool) -> Workflow:
    """Assemble the full prompt-generation + wave pipeline as a single Workflow.

    Flux-only architecture: removes the FF/LF consistency prompter nodes;
    the new LF and motion prompters are ADK 2.0 dynamic `@node` workflows
    (Generator + Critic, max 3 cycles, exits on the OK phrase).
    """
    edges = [
        # 0. Resume entry point
        (START, resume_router_node),

        # Resume router emits a route that jumps directly to the entry-point node.
        (resume_router_node, {
            "director_script": director_script_agent,
            "blueprint_structure": blueprint_structure_agent,
            "blueprint": blueprint_visuals_agent,
            "prompts": character_sheet_prompter,
            "wave_payloads": wave_organizer_node,
            "all_complete": wave_executor_node,
        }),
    ]

    # Linear chain LLM agents + save/parse nodes
    edges += [
        (director_script_agent, save_director_script_node),
        (save_director_script_node, blueprint_structure_agent),

        (blueprint_structure_agent, parse_blueprint_structure_node),
        (parse_blueprint_structure_node, save_blueprint_structure_node),
        (save_blueprint_structure_node, blueprint_visuals_agent),

        (blueprint_visuals_agent, parse_blueprint_node),
        (parse_blueprint_node, save_blueprint_node),
        (save_blueprint_node, character_sheet_prompter),

        # Spatial mapper: generates per-shot character placement map -> consumed by
        # the FF and LF prompters for multi-character anchor language (image N refs).
        (character_sheet_prompter, char_spatial_mapper_agent),
        (char_spatial_mapper_agent, parse_character_spatial_map_node),
        (parse_character_spatial_map_node, save_character_spatial_map_node),
        (save_character_spatial_map_node, ff_shot_prompter),

        (ff_shot_prompter, lf_delta_planner_agent),
        (lf_delta_planner_agent, parse_lf_delta_plan_node),
        (parse_lf_delta_plan_node, save_lf_delta_plan_node),
        (save_lf_delta_plan_node, lf_prompter_loop),

        # LF prompter is an ADK 2.0 dynamic @node workflow: Generator + Critic,
        # max 3 cycles, exits when the critic returns LF_PROMPTS_OK.
        (lf_prompter_loop, motion_prompter_loop),

        # Motion prompter is also a dynamic @node workflow with the same structure.
        (motion_prompter_loop, save_prompts_node),
        (save_prompts_node, validate_prompts_node),
        (validate_prompts_node, wave_organizer_node),
        (wave_organizer_node, wave_executor_node),
    ]

    return Workflow(name="StoryToVideoDynamicAgentSetupPipeline", edges=edges)


async def main_async():
    parser = argparse.ArgumentParser(description="Story-to-Video Dynamic Agent Setup Pipeline")
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
        help="Run prompt generation + wave organizer, then stop before any ComfyUI image/video generation.",
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
    print(f"Output directory initialized at: {output_dir}")
    print(f"--fresh mode: {bool(args.fresh)}")
    print(f"--stop-before-generation mode: {bool(args.stop_before_generation)}")

    initial_state = {
        "story_text": story_text,
        "output_dir": output_dir,
        "fresh": bool(args.fresh),
        "stop_before_generation": bool(args.stop_before_generation),
    }

    pipeline_wf = _build_pipeline(output_dir, args.fresh)

    APP_NAME = "story_to_video_dynamic_agent_setup"
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

    print(f"\n🚀 Running Flux-only Story-to-Video Pipeline...")
    started_at = datetime.now(timezone.utc)

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


if __name__ == "__main__":
    asyncio.run(main_async())
