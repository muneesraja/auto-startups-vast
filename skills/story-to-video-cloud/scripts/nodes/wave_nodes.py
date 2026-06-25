"""Wave organizer + wave executor as graph nodes.

- wave_organizer_node: thin FunctionNode wrapper around the existing
  scripts.wave_organizer.organize_waves (no change to organizer logic).
- wave_executor_node: FunctionNode that triggers the wave pipeline (Wave 1 then Wave 2),
  unless state['stop_before_generation'] is true. Execution itself runs through
  the nested Workflow in wave_executor_workflow.py for parallel processing with
  RetryConfig.
"""
import os
import json
import asyncio

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from .wave_executor_workflow import run_wave_executor


async def wave_organizer(ctx: Context) -> None:
    """Read prompts.json + blueprint from disk, write generator_wave_1.json and _2.json."""
    # Import lazily; avoids a sys.path edge case for tests.
    import sys
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if here not in sys.path:
        sys.path.insert(0, here)

    from scripts.wave_organizer import organize_waves  # type: ignore

    output_dir = ctx.state.get("output_dir")
    if not output_dir:
        raise ValueError("output_dir not set in state")
    organize_waves(output_dir)
    print(f"📋 [wave_organizer_node] Wrote generator_wave_1.json and generator_wave_2.json to {output_dir}")


async def wave_executor(ctx: Context) -> None:
    """Run Wave 1 then Wave 2 via the nested Workflow with bounded parallelism + RetryConfig."""
    output_dir = ctx.state.get("output_dir")
    if not output_dir:
        raise ValueError("output_dir not set in state")
    if bool(ctx.state.get("stop_before_generation", False)):
        print(
            "⏸️ [wave_executor_node] --stop-before-generation set; "
            "skipping ComfyUI image/video generation."
        )
        return
    stop_after_char_sheets = bool(ctx.state.get("stop_after_char_sheets", False))
    only_shots = ctx.state.get("only_shots")
    only_scenes = ctx.state.get("only_scenes")
    
    if only_scenes:
        blueprint_path = os.path.join(output_dir, "director_visual_blueprint.json")
        if os.path.exists(blueprint_path):
            with open(blueprint_path, "r", encoding="utf-8") as f:
                blueprint = json.load(f)
            expanded_shots = []
            for scene in blueprint.get("scenes", []):
                if scene.get("scene_id") in only_scenes:
                    for shot in scene.get("shots", []):
                        if shot.get("shot_id"):
                            expanded_shots.append(shot["shot_id"])
            
            if only_shots:
                only_shots = list(set(only_shots) | set(expanded_shots))
            else:
                only_shots = expanded_shots
            print(f"🎬 Expanded --only-scenes {only_scenes} into shots: {expanded_shots}")
            # Update state with the merged list
            ctx.state["only_shots"] = only_shots

    skip_video = bool(ctx.state.get("skip_video", False))
    eager_video = bool(ctx.state.get("eager_video", False))
    await run_wave_executor(
        output_dir,
        stop_after_char_sheets=stop_after_char_sheets,
        only_shots=only_shots,
        skip_video=skip_video,
        eager_video=eager_video,
    )


# ADK node definitions


wave_organizer_node = FunctionNode(func=wave_organizer, name="wave_organizer_node")
wave_executor_node = FunctionNode(func=wave_executor, name="wave_executor_node")
