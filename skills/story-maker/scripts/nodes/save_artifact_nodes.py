"""Save artifact nodes — write planning and generation specs to disk."""
import json
import os

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

import config
from ._json_util import clean_json_str


def _output_dir(ctx: Context) -> str:
    out = ctx.state.get("output_dir")
    if not out:
        raise ValueError("output_dir not set in state")
    os.makedirs(out, exist_ok=True)
    return out


def _stamp_planning_meta(data: dict, **model_fields: str) -> dict:
    if not isinstance(data, dict):
        return data
    meta = data.get("_meta")
    if not isinstance(meta, dict):
        meta = {}
    meta.update(model_fields)
    data["_meta"] = meta
    return data


async def save_narrative_outline(ctx: Context) -> None:
    raw = ctx.state.get("narrative_outline_content")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    parsed = _stamp_planning_meta(
        parsed,
        narrative_model=config.get_narrative_expander_model_id(),
    )
    path = os.path.join(_output_dir(ctx), "narrative_outline.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_narrative_outline] Wrote {path}")


async def save_story_plan(ctx: Context) -> None:
    raw = ctx.state.get("story_plan_content")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    parsed = _stamp_planning_meta(
        parsed,
        narrative_model=config.get_narrative_expander_model_id(),
        story_plan_model=config.get_story_plan_model_id(),
    )
    path = os.path.join(_output_dir(ctx), "story_plan.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_story_plan] Wrote {path}")


async def save_audio_plan(ctx: Context) -> None:
    raw = ctx.state.get("audio_plan_content")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    path = os.path.join(_output_dir(ctx), "audio_plan.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_audio_plan] Wrote {path}")


async def save_scene_assets(ctx: Context) -> None:
    raw = ctx.state.get("scene_assets_content")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    for scene in parsed.get("scenes", []):
        if not scene.get("background_reference_mode"):
            scene["background_reference_mode"] = "style_anchor"
    path = os.path.join(_output_dir(ctx), "scene_assets.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_scene_assets] Wrote {path}")


async def merge_generation_specs(ctx: Context) -> None:
    """Fan-in: merge parallel prompter outputs into generation_specs.json."""
    char_raw = clean_json_str(ctx.state.get("character_sheet_prompts_content") or "{}")
    shot_raw = clean_json_str(ctx.state.get("shot_image_specs_content") or "{}")
    scene_assets_raw = clean_json_str(ctx.state.get("scene_assets_content") or "{}")

    character_sheets = {}
    for cid, entry in char_raw.items():
        if not isinstance(entry, dict):
            continue
        character_sheets[cid] = {
            "character_id": cid,
            "sheet_prompt": entry.get("sheet_prompt") or entry.get("prompt", ""),
            "output_path": None,
            "fal_image_url": None,
            "status": "pending",
        }

    shot_images = {}
    for sid, entry in shot_raw.items():
        if isinstance(entry, dict):
            entry = dict(entry)
            entry.setdefault("shot_id", sid)
            entry.setdefault("reference_images", [])
            entry.setdefault("status", "pending")
            shot_images[sid] = entry

    motion = {}
    story_raw = ctx.state.get("story_plan_content")
    story_shots = {}
    if story_raw:
        story = clean_json_str(story_raw) if isinstance(story_raw, str) else story_raw
        for scene in story.get("scenes", []):
            for shot in scene.get("shots", []):
                story_shots[shot["shot_id"]] = shot

    for sid, plan_shot in story_shots.items():
        motion[sid] = {
            "shot_id": sid,
            "motion_prompt": "",
            "duration_seconds": plan_shot.get("duration_seconds", 8),
            "scene_time_offset_seconds": plan_shot.get("scene_time_offset_seconds", 0),
            "pace": plan_shot.get("pace", "medium"),
            "motion_intent": plan_shot.get("motion_intent", ""),
            "camera_intent": plan_shot.get("camera_intent", ""),
            "audio_intent": plan_shot.get("audio_intent", ""),
            "vision_confirmed": False,
            "vision_source_image": None,
            "output_path": None,
            "status": "pending",
        }

    backgrounds = {}
    for scene in scene_assets_raw.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        if scene.get("generate_background") and scene.get("background_prompt"):
            sid = scene["scene_id"]
            backgrounds[sid] = {
                "scene_id": sid,
                "background_prompt": scene["background_prompt"],
                "output_path": None,
                "fal_image_url": None,
                "status": "pending",
            }

    specs = {
        "character_sheets": character_sheets,
        "backgrounds": backgrounds,
        "shot_images": shot_images,
        "motion": motion,
    }
    ctx.state["generation_specs_content"] = json.dumps(specs, indent=2, ensure_ascii=False)
    path = os.path.join(_output_dir(ctx), "generation_specs.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(specs, f, indent=2, ensure_ascii=False)
    print(f"📁 [merge_generation_specs] Wrote {path}")


save_narrative_outline_node = FunctionNode(
    func=save_narrative_outline, name="save_narrative_outline_node"
)
save_story_plan_node = FunctionNode(func=save_story_plan, name="save_story_plan_node")
save_audio_plan_node = FunctionNode(func=save_audio_plan, name="save_audio_plan_node")
save_scene_assets_node = FunctionNode(func=save_scene_assets, name="save_scene_assets_node")
merge_generation_specs_node = FunctionNode(
    func=merge_generation_specs, name="merge_generation_specs_node"
)
