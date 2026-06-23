"""Resume router FunctionNode — replaces Python disk-checks in legacy main.py.

Fixes ISSUE-010: --fresh flag and resumable execution as a first-class graph node.

Behavior:
- Reads `output_dir`, `fresh` (bool) from state.
- If `fresh` is True: skip all disk scans; route = "fresh" (run all LLM agents).
- Else: scan disk for each expected artifact; load existing ones into state.
  Route to the earliest missing step; route = "all_complete" if everything's present.
"""
import os
import json

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode


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


async def resume_router(ctx: Context) -> None:
    """Set state['output_dir'], load existing artifacts, emit route to next step."""
    output_dir = ctx.state.get("output_dir")
    fresh = bool(ctx.state.get("fresh", False))
    if not output_dir:
        raise ValueError("output_dir not set in state. main.py must populate it.")

    os.makedirs(output_dir, exist_ok=True)

    if fresh:
        # Wipe any pre-existing artifacts so the run is truly fresh.
        # (We don't blindly rm -rf, only remove pipeline-owned filenames.)
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
        # 'fresh' and 'director_script' collapse to the same entry-point agent
        # (director_script_agent); downstream edges in the graph target by node
        # identity, not route value.
        ctx.route = "director_script"
        return

    # Resume mode: try to load each artifact from disk; route to earliest missing.
    for route_name, state_key, filename, parser in _RESUME_STEPS:
        disk_path = os.path.join(output_dir, filename)
        if not os.path.exists(disk_path):
            # The first missing artifact determines the entry-point route.
            print(f"🔄 [resume_router] {filename} missing on disk → routing to '{route_name}'")
            ctx.route = route_name
            return
        if state_key and parser == "text":
            with open(disk_path, "r", encoding="utf-8") as f:
                ctx.state[state_key] = f.read()
            print(f"📂 [resume_router] Loaded {filename} into state[{state_key!r}]")
        elif state_key and parser == "json":
            with open(disk_path, "r", encoding="utf-8") as f:
                ctx.state[state_key] = f.read()  # raw JSON text; downstream parse node handles it
            print(f"📂 [resume_router] Loaded {filename} into state[{state_key!r}]")
        # For prompts/wave_payloads steps we skip pre-loading; downstream nodes read disk.

    # Everything present: jump straight to wave execution.
    print("✅ [resume_router] All artifacts present on disk. Routing to 'all_complete'.")
    ctx.route = "all_complete"


resume_router_node = FunctionNode(func=resume_router, name="resume_router_node")
