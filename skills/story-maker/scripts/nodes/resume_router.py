"""Resume router — route to earliest missing durable artifact."""
import json
import os

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from .plan_io import load_plan, sync_legacy_state
from .story_plan_normalize import normalize_story_plan

_FRESH_FILES = [
    "developed_story.md",
    "scene_paper.md",
    "plan.json",
    "generation_specs.json",
    "cost_estimate.json",
    "final_film.mp4",
    # Legacy artifacts cleaned on --fresh so old runs don't confuse resume.
    "story_sheet_scene.md",
    "narrative_outline.json",
    "story_plan.json",
    "video_shot_plan.json",
    "audio_plan.json",
    "scene_assets.json",
]


def write_through_developed_story(ctx: Context) -> str:
    """Copy raw story_text into developed_story.md (skip-LLM path)."""
    output_dir = ctx.state.get("output_dir")
    if not output_dir:
        raise ValueError("output_dir not set in state")
    os.makedirs(output_dir, exist_ok=True)
    content = (ctx.state.get("story_text") or "").strip()
    path = os.path.join(output_dir, "developed_story.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
        if content and not content.endswith("\n"):
            f.write("\n")
    ctx.state["developed_story_text"] = content
    ctx.state["developed_story_content"] = content
    print(f"📁 [resume_router] skip-story-developer: wrote {path}")
    return content


def _load_developed_story(ctx: Context, output_dir: str) -> str:
    path = os.path.join(output_dir, "developed_story.md")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    ctx.state["developed_story_content"] = text
    ctx.state["developed_story_text"] = text
    print("📂 [resume_router] Loaded developed_story.md")
    return text


async def resume_router(ctx: Context) -> None:
    output_dir = ctx.state.get("output_dir")
    fresh = bool(ctx.state.get("fresh", False))
    skip_developer = bool(ctx.state.get("skip_story_developer", False))
    if not output_dir:
        raise ValueError("output_dir not set in state")
    os.makedirs(output_dir, exist_ok=True)

    if fresh:
        # Wipe only part-level planning files under output_dir — never shared
        # asset_root dirs (characters / locations / backgrounds).
        for fname in _FRESH_FILES:
            p = os.path.join(output_dir, fname)
            if os.path.exists(p):
                try:
                    os.remove(p)
                    print(f"🧹 [resume_router] --fresh: removed {p}")
                except OSError as e:
                    print(f"⚠️ [resume_router] could not remove {p}: {e}")
        if skip_developer:
            write_through_developed_story(ctx)
            ctx.route = "scene_paper"
        else:
            ctx.route = "developed_story"
        return

    developed_path = os.path.join(output_dir, "developed_story.md")
    if not os.path.exists(developed_path):
        if skip_developer:
            write_through_developed_story(ctx)
        else:
            print("🔄 [resume_router] developed_story.md missing → 'developed_story'")
            ctx.route = "developed_story"
            return
    else:
        _load_developed_story(ctx, output_dir)

    scene_paper_path = os.path.join(output_dir, "scene_paper.md")
    if not os.path.exists(scene_paper_path):
        print("🔄 [resume_router] scene_paper.md missing → 'scene_paper'")
        ctx.route = "scene_paper"
        return
    with open(scene_paper_path, encoding="utf-8") as f:
        text = f.read()
    ctx.state["scene_paper_content"] = text
    ctx.state["scene_paper_text"] = text
    print("📂 [resume_router] Loaded scene_paper.md")

    plan = load_plan(output_dir, write_if_legacy=True)
    if plan is None:
        print("🔄 [resume_router] plan.json missing → 'plan'")
        ctx.route = "plan"
        return

    sync_legacy_state(ctx.state, plan)
    from ._json_util import clean_json_str
    from .plan_io import apply_story_view_to_plan, save_plan_dict

    story = clean_json_str(ctx.state["story_plan_content"])
    story = normalize_story_plan(story)
    plan = apply_story_view_to_plan(plan, story)
    save_plan_dict(output_dir, plan)
    sync_legacy_state(ctx.state, plan)
    print("📂 [resume_router] Loaded plan.json")

    specs_path = os.path.join(output_dir, "generation_specs.json")
    if not os.path.exists(specs_path):
        print("🔄 [resume_router] generation_specs.json missing → 'generation_specs'")
        ctx.route = "generation_specs"
        return
    with open(specs_path, encoding="utf-8") as f:
        data = json.load(f)
    ctx.state["generation_specs_content"] = json.dumps(data, indent=2, ensure_ascii=False)
    print("📂 [resume_router] Loaded generation_specs.json")

    final_path = os.path.join(output_dir, "final_film.mp4")
    only_scenes = ctx.state.get("only_scenes")
    if only_scenes:
        partial_path = os.path.join(output_dir, f"{'_'.join(only_scenes)}_film.mp4")
        if os.path.exists(partial_path):
            print(f"✅ [resume_router] {os.path.basename(partial_path)} exists — all complete")
            ctx.route = "all_complete"
            return

    if not os.path.exists(final_path):
        print("🔄 [resume_router] final_film.mp4 missing → 'generate'")
        ctx.route = "generate"
        return

    print("✅ [resume_router] All complete")
    ctx.route = "all_complete"


async def resume_prompters_entry(ctx: Context) -> None:
    """Entry point when resuming at generation_specs — fan-out to per-shot prompters."""
    print("🔄 [resume_prompters_entry] Fan-out to parallel prompters")


resume_router_node = FunctionNode(func=resume_router, name="resume_router_node")
resume_prompters_entry_node = FunctionNode(
    func=resume_prompters_entry, name="resume_prompters_entry_node"
)
