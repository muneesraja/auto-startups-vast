"""Wave organizer + wave executor as graph nodes.

- wave_organizer_node: thin FunctionNode wrapper around the existing
  scripts.wave_organizer.organize_waves (no change to organizer logic).
- wave_executor_node: FunctionNode that triggers the wave pipeline (Wave 1 then Wave 2),
  unless state['stop_before_generation'] is true. Execution itself runs through
  the nested Workflow in wave_executor_workflow.py for parallel processing with
  RetryConfig.

ADK 2.0 modernization notes:
- Uses the modern `@node` decorator instead of `FunctionNode(func=...)`.
- Imports `Context` and `Event` from top-level `google.adk`.
"""
import os
import json
import asyncio

from google.adk import Context, Event
from google.adk.workflow import node

from .wave_executor_workflow import run_wave_executor


@node
async def wave_organizer_node(ctx: Context) -> None:
    """Read prompts.json + blueprint from disk, write generator_wave_1.json and _2.json."""
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


@node
async def wave_executor_node(ctx: Context) -> None:
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
    await run_wave_executor(output_dir)
