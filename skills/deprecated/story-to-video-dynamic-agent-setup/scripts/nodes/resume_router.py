"""Resume router FunctionNode — replaces Python disk-checks in legacy main.py.

Fixes ISSUE-010: --fresh flag and resumable execution as a first-class graph node.

Behavior:
- Reads `output_dir`, `fresh` (bool) from state.
- If `fresh` is True: skip all disk scans; route = "director_script" (runs all LLM agents).
- Else: scan disk for each expected artifact; load existing ones into state.
  Route to the earliest missing step; route = "all_complete" if everything's present.

ADK 2.0 modernization notes:
- Uses `return Event(route="...", state={...})` instead of the legacy
  `ctx.route = "..."; ctx.state[k] = v; return None` mutation pattern.
  This is the canonical ADK 2.0 graph-routes pattern: state mutations AND
  routing decision flow through one explicit Event return value, which is
  easier to test and composes cleanly with parent workflows.
- Uses the modern `@node` decorator instead of `FunctionNode(func=...)`.
- Imports `Context` and `Event` from top-level `google.adk`.
"""
import os
import json

from google.adk import Context, Event
from google.adk.workflow import node


# Map: route_key -> (state_key, filename) for each artifact that, if missing,
# requires re-running a specific downstream LLM agent.
_RESUME_STEPS = [
    # (route_name, state_key_to_populate, disk_filename, parser)
    ("director_script", "director_script_content", "Director_script.md", "text"),
    ("blueprint_structure", "blueprint_structure_json", "director_visual_blueprint_structure.json", "json"),
    ("blueprint", "blueprint_json_content", "director_visual_blueprint.json", "json"),
    ("prompts", None, "prompts.json", "skip_load"),  # prompts.json holds multiple namespaces
    ("wave_payloads", None, "generator_wave_1.json", "skip_load"),
]


@node
async def resume_router_node(ctx: Context) -> Event:
    """Set state['output_dir'], load existing artifacts, emit route to next step."""
    output_dir = ctx.state.get("output_dir")
    fresh = bool(ctx.state.get("fresh", False))
    if not output_dir:
        raise ValueError("output_dir not set in state. main.py must populate it.")

    os.makedirs(output_dir, exist_ok=True)

    if fresh:
        # Wipe any pre-existing artifacts so the run is truly fresh.
        filenames_to_clear = [
            "Director_script.md",
            "director_visual_blueprint_structure.json",
            "director_visual_blueprint.json",
            "prompts.json",
            "lf_delta_plan.json",
            "character_spatial_map.json",
            "generator_wave_1.json",
            "generator_wave_2.json",
        ]
        for fname in filenames_to_clear:
            p = os.path.join(output_dir, fname)
            if os.path.exists(p):
                try:
                    os.remove(p)
                    print(f"🧹 [resume_router] --fresh: removed {p}")
                except OSError as e:
                    print(f"⚠️ [resume_router] could not remove {p}: {e}")
        # Wipe the vision-review output directories if present (audit-mode content
        # is regenerated each wave run; stale reviews should not survive --fresh).
        for d in ("ff_vision_reviews", "lf_vision_reviews"):
            dpath = os.path.join(output_dir, d)
            if os.path.isdir(dpath):
                try:
                    import shutil
                    shutil.rmtree(dpath)
                    print(f"🧹 [resume_router] --fresh: removed review dir {dpath}")
                except OSError as e:
                    print(f"⚠️ [resume_router] could not remove dir {dpath}: {e}")
        return Event(route="director_script")

    # Resume mode: try to load each artifact from disk; route to earliest missing.
    loaded_state: dict = {}
    for route_name, state_key, filename, parser in _RESUME_STEPS:
        disk_path = os.path.join(output_dir, filename)
        if not os.path.exists(disk_path):
            print(f"🔄 [resume_router] {filename} missing on disk → routing to '{route_name}'")
            # Persist any artifacts loaded so far (from earlier steps) before routing.
            return Event(state=loaded_state or None, route=route_name)
        if state_key and parser in ("text", "json"):
            with open(disk_path, "r", encoding="utf-8") as f:
                loaded_state[state_key] = f.read()
                print(f"📂 [resume_router] Loaded {filename} into state[{state_key!r}]")
        # For prompts/wave_payloads steps we skip pre-loading; downstream nodes read disk.

    # Everything present: jump straight to wave execution.
    print("✅ [resume_router] All artifacts present on disk. Routing to 'all_complete'.")
    return Event(state=loaded_state or None, route="all_complete")
