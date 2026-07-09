"""Resume router — route to earliest missing artifact."""
import json
import os

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

_RESUME_STEPS = [
    ("scene_paper", "scene_paper_content", "scene_paper.md", "text", None),
    (
        "story_sheet_scene",
        "story_sheet_scene_content",
        "story_sheet_scene.md",
        "text",
        "storyboard",
    ),
    ("narrative_outline", "narrative_outline_content", "narrative_outline.json", "json", None),
    ("story_plan", "story_plan_content", "story_plan.json", "json", None),
    (
        "video_shot_plan",
        "video_shot_plan_content",
        "video_shot_plan.json",
        "json",
        "storyboard",
    ),
    ("audio_plan", "audio_plan_content", "audio_plan.json", "json", None),
    ("scene_assets", "scene_assets_content", "scene_assets.json", "json", None),
    ("generation_specs", None, "generation_specs.json", "skip_load", None),
]

_FRESH_FILES = [
    "scene_paper.md",
    "story_sheet_scene.md",
    "narrative_outline.json",
    "story_plan.json",
    "video_shot_plan.json",
    "audio_plan.json",
    "scene_assets.json",
    "generation_specs.json",
    "final_film.mp4",
]


async def resume_router(ctx: Context) -> None:
    output_dir = ctx.state.get("output_dir")
    fresh = bool(ctx.state.get("fresh", False))
    if not output_dir:
        raise ValueError("output_dir not set in state")
    os.makedirs(output_dir, exist_ok=True)

    if fresh:
        for fname in _FRESH_FILES:
            p = os.path.join(output_dir, fname)
            if os.path.exists(p):
                try:
                    os.remove(p)
                    print(f"🧹 [resume_router] --fresh: removed {p}")
                except OSError as e:
                    print(f"⚠️ [resume_router] could not remove {p}: {e}")
        ctx.route = "scene_paper"
        return

    story_plan_path = os.path.join(output_dir, "story_plan.json")
    outline_path = os.path.join(output_dir, "narrative_outline.json")
    legacy = os.path.exists(story_plan_path) and not os.path.exists(outline_path)
    pipeline_mode = ctx.state.get("pipeline_mode") or "per_shot"

    for route_name, state_key, filename, parser, only_for_mode in _RESUME_STEPS:
        if legacy and route_name == "narrative_outline":
            continue
        if only_for_mode and pipeline_mode != only_for_mode:
            continue
        disk_path = os.path.join(output_dir, filename)
        if not os.path.exists(disk_path):
            print(f"🔄 [resume_router] {filename} missing → '{route_name}'")
            ctx.route = route_name
            return
        if state_key and parser == "json":
            with open(disk_path, encoding="utf-8") as f:
                data = json.load(f)
            if state_key == "story_plan_content":
                from scripts.nodes.story_plan_normalize import normalize_story_plan

                data = normalize_story_plan(data)
            if state_key == "scene_assets_content":
                for scene in data.get("scenes", []):
                    if not scene.get("background_reference_mode"):
                        scene["background_reference_mode"] = "style_anchor"
            ctx.state[state_key] = json.dumps(data, indent=2, ensure_ascii=False)
            print(f"📂 [resume_router] Loaded {filename}")
        elif state_key and parser == "text":
            with open(disk_path, encoding="utf-8") as f:
                text = f.read()
            ctx.state[state_key] = text
            if route_name == "scene_paper":
                ctx.state["scene_paper_text"] = text
            elif route_name == "story_sheet_scene":
                ctx.state["story_sheet_scene_text"] = text
            print(f"📂 [resume_router] Loaded {filename}")

    final_path = os.path.join(output_dir, "final_film.mp4")
    only_scenes = ctx.state.get("only_scenes")
    if only_scenes:
        partial_path = os.path.join(output_dir, f"{'_'.join(only_scenes)}_film.mp4")
        if os.path.exists(partial_path):
            print(f"✅ [resume_router] {os.path.basename(partial_path)} exists — all complete")
            ctx.route = "all_complete"
            return

    if not os.path.exists(final_path):
        specs_path = os.path.join(output_dir, "generation_specs.json")
        if os.path.exists(specs_path):
            with open(specs_path, encoding="utf-8") as f:
                data = json.load(f)
            ctx.state["generation_specs_content"] = json.dumps(
                data, indent=2, ensure_ascii=False
            )
        print("🔄 [resume_router] final_film.mp4 missing → 'generate'")
        ctx.route = "generate"
        return

    print("✅ [resume_router] All complete")
    ctx.route = "all_complete"


async def resume_prompters_entry(ctx: Context) -> None:
    """Entry point when resuming at generation_specs — fan-out to prompters."""
    print("🔄 [resume_prompters_entry] Fan-out to parallel prompters")


async def story_sheet_scene_router(ctx: Context) -> None:
    """After scene_paper is saved, only storyboard-mode profiles need a sheet map."""
    pipeline_mode = ctx.state.get("pipeline_mode") or "per_shot"
    if pipeline_mode == "storyboard":
        ctx.state.setdefault("story_sheet_scene_text", "")
        ctx.route = "storyboard"
    else:
        ctx.state["story_sheet_scene_text"] = ""
        ctx.route = "per_shot"


async def video_shot_plan_router(ctx: Context) -> None:
    """Storyboard mode uses a grouped video-shot plan before audio planning."""
    pipeline_mode = ctx.state.get("pipeline_mode") or "per_shot"
    if pipeline_mode == "storyboard":
        ctx.state.setdefault("video_shot_plan_content", "")
        ctx.route = "storyboard"
    else:
        ctx.state["video_shot_plan_content"] = ""
        ctx.route = "per_shot"


resume_router_node = FunctionNode(func=resume_router, name="resume_router_node")
resume_prompters_entry_node = FunctionNode(
    func=resume_prompters_entry, name="resume_prompters_entry_node"
)
story_sheet_scene_router_node = FunctionNode(
    func=story_sheet_scene_router, name="story_sheet_scene_router_node"
)
video_shot_plan_router_node = FunctionNode(
    func=video_shot_plan_router, name="video_shot_plan_router_node"
)
