"""Graph-native Story-to-Video deterministic pipeline entrypoint.

Migration targets (Issue log):
- ISSUE-001: Replaces the auto-save callback with single-writer save_artifact_nodes
- ISSUE-005: curl_json raises on empty/non-JSON responses (in tools/comfyui_tools.py)
- ISSUE-006: SequentialAgent removed in favor of Workflow
- ISSUE-007: datetime.utcnow() replaced with timezone-aware datetime.now(timezone.utc)
- ISSUE-010: --fresh CLI flag + resume_router FunctionNode
- ISSUE-012: validate_prompts_node validates Pydantic schemas against actual artifacts
- Issue A1: LF prompts are Ideogram 4 T2I full-scene images
- Issue B2/B3: validate_prompts_node enforces absent-char ref stripping + coverage check; system prompt forbids emitting
- Issue C1: consistency prompter uses 'Preserve' framing, not 'Replace'
- Option B: character spatial mapper + LF consistency patches + audit-mode vision reviewers

Pipeline graph:
    START -> resume_router_node
    resume_router_node -> {
        'fresh' or 'director_script' or 'blueprint_structure' or 'blueprint' or 'prompts':
            <entry-point LlmAgent in the linear chain>,
        'wave_payloads': wave_organizer_node,
        'all_complete': wave_executor_node,
    }
    <linear chain>: director_script_agent -> save_director_script_node
        -> blueprint_structure_agent -> parse_blueprint_structure_node -> save_blueprint_structure_node
        -> blueprint_visuals_agent -> parse_blueprint_node -> save_blueprint_node
        -> character_sheet_prompter -> char_spatial_mapper_agent
        -> parse_character_spatial_map_node -> save_character_spatial_map_node
        -> ff_shot_prompter -> consistency_prompter
        -> lf_delta_planner_agent -> parse_lf_delta_plan_node -> save_lf_delta_plan_node
        -> lf_shot_prompter -> lf_consistency_prompter
        -> motion_prompter -> save_prompts_node
        -> validate_prompts_node -> wave_organizer_node -> wave_executor_node
           (wave_executor_node is a no-op when --stop-before-generation is set)

Wave 1 (nested workflow):
    cs (char sheets) -> ff (Ideogram) -> cp (FF consistency patch via Flux Klein)
    -> lf (Ideogram T2I LF) -> lf_cp (LF consistency patch via Flux Klein)
    -> review (ff_vision_review + lf_vision_review in parallel — audit-mode via MiniMax M3 vision)
    -> video (LTX video using consistency_patches FF + lf_consistency_patches LF)
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
from agents.step5_consistency_prompter import consistency_prompter
from agents.step6_5_lf_delta_planner import lf_delta_planner_agent
from agents.step6_lf_prompter import lf_shot_prompter
from agents.step7_motion_prompter import motion_prompter
from agents.step8_lf_consistency_prompter import lf_consistency_prompter

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
    """Assemble the full prompt-generation + wave pipeline as a single Workflow."""
    edges = [
        # 0. Resume entry point
        (START, resume_router_node),

        # Resume router emits a route that jumps directly to the entry-point node.
        # NOTE: 'fresh' and 'director_script' both route to director_script_agent —
        # the framework deduplicates edges by (from, to), so we collapse them.
        # resume_router_node emits 'director_script' for both fresh-mode and
        # missing-file-on-disk cases.
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
        # consistency_prompter + lf_consistency_prompter for multi-character anchor language.
        (character_sheet_prompter, char_spatial_mapper_agent),
        (char_spatial_mapper_agent, parse_character_spatial_map_node),
        (parse_character_spatial_map_node, save_character_spatial_map_node),
        (save_character_spatial_map_node, ff_shot_prompter),

        (ff_shot_prompter, consistency_prompter),
        (consistency_prompter, lf_delta_planner_agent),

        (lf_delta_planner_agent, parse_lf_delta_plan_node),
        (parse_lf_delta_plan_node, save_lf_delta_plan_node),
        (save_lf_delta_plan_node, lf_shot_prompter),

        # LF consistency patcher: emits Flux Klein edit prompts that redraw
        # character identity on the LF (preserving the LF delta). Motion prompter
        # then references lf_consistency_patches.X.output_path for lf_image
        # when characters_present is non-empty.
        (lf_shot_prompter, lf_consistency_prompter),
        (lf_consistency_prompter, motion_prompter),

        (motion_prompter, save_prompts_node),
        (save_prompts_node, validate_prompts_node),
        (validate_prompts_node, wave_organizer_node),
        (wave_organizer_node, wave_executor_node),
    ]

    return Workflow(name="StoryToVideoDeterministicPipeline", edges=edges)


async def main_async():
    parser = argparse.ArgumentParser(description="Deterministic Story-to-Video Pipeline")
    parser.add_argument("--story", required=True, help="Story text or path to file containing story text")
    parser.add_argument("--name", required=True, help="Name of the story output directory")
    parser.add_argument("--dir", default=None, help="Custom absolute path to output directory")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Wipe pipeline-owned artifacts and run all steps from scratch (fixes ISSUE-010).",
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

    APP_NAME = "story_to_video_deterministic"
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

    print(f"\n🚀 Running Graph-Native Pipeline (Workflow nodes + LLM agents + save nodes)...")
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
