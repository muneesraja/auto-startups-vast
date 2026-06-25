"""Single-writer save nodes — each node writes ONE artifact to disk.

Each node reads its assigned state key, optionally parses it, and writes
the corresponding file. Nodes are idempotent.
"""
import os
import json
from datetime import datetime, timezone

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from ._json_util import clean_json_str, get_namespace_dict


def _output_dir(ctx: Context) -> str:
    """Resolve the output directory from session state (set by resume_router)."""
    out = ctx.state.get("output_dir")
    if not out:
        raise ValueError("output_dir not set in state. resume_router_node must run first.")
    os.makedirs(out, exist_ok=True)
    return out


async def save_director_script(ctx: Context) -> None:
    """Write Director_script.md from state['director_script_content']."""
    content = ctx.state.get("director_script_content")
    if not content:
        return
    path = os.path.join(_output_dir(ctx), "Director_script.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"📁 [save_director_script_node] Wrote {path}")


async def save_fflf_plan(ctx: Context) -> None:
    """Write fflf_plan.json from state['fflf_plan_content']."""
    raw = ctx.state.get("fflf_plan_content")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    path = os.path.join(_output_dir(ctx), "fflf_plan.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_fflf_plan_node] Wrote {path}")


async def save_blueprint_structure(ctx: Context) -> None:
    """Write director_visual_blueprint_structure.json from state['blueprint_structure_json']."""
    raw = ctx.state.get("blueprint_structure_json")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    path = os.path.join(_output_dir(ctx), "director_visual_blueprint_structure.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_blueprint_structure_node] Wrote {path}")


async def save_blueprint(ctx: Context) -> None:
    """Write director_visual_blueprint.json from state['blueprint_json_content']."""
    raw = ctx.state.get("blueprint_json_content")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    path = os.path.join(_output_dir(ctx), "director_visual_blueprint.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_blueprint_node] Wrote {path}")


async def save_lf_delta_plan(ctx: Context) -> None:
    """Write lf_delta_plan.json from state['lf_delta_plan_content']."""
    raw = ctx.state.get("lf_delta_plan_content")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    path = os.path.join(_output_dir(ctx), "lf_delta_plan.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_lf_delta_plan_node] Wrote {path}")


async def save_character_spatial_map(ctx: Context) -> None:
    """Write character_spatial_map.json from state['character_spatial_map_content']."""
    raw = ctx.state.get("character_spatial_map_content")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    path = os.path.join(_output_dir(ctx), "character_spatial_map.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_character_spatial_map_node] Wrote {path}")


async def save_prompts(ctx: Context) -> None:
    """Assemble prompts.json from all `*_content` state keys and write to disk."""
    # Idempotency: only run if at least one namespace is present.
    raw_keys = (
        "character_prompts_content",
        "ff_prompts_content",
        "lf_prompts_content",
        "motion_prompts_content",
        "lf_delta_plan_content",
        "character_spatial_map_content",
    )
    if not any(ctx.state.get(k) for k in raw_keys):
        return

    char_sheets_raw = clean_json_str(ctx.state.get("character_prompts_content") or "{}")
    ff_shots_raw = clean_json_str(ctx.state.get("ff_prompts_content") or "{}")
    lf_shots_raw = clean_json_str(ctx.state.get("lf_prompts_content") or "{}")
    motion_raw = clean_json_str(ctx.state.get("motion_prompts_content") or "{}")
    lf_delta_raw = clean_json_str(ctx.state.get("lf_delta_plan_content") or "{}")
    spatial_map_raw = clean_json_str(ctx.state.get("character_spatial_map_content") or "{}")

    # Load blueprint if present to extract background generation requests
    backgrounds_data = {}
    blueprint_raw = ctx.state.get("blueprint_json_content")
    if blueprint_raw:
        blueprint = clean_json_str(blueprint_raw) if isinstance(blueprint_raw, str) else blueprint_raw
        if isinstance(blueprint, dict):
            for scene in blueprint.get("scenes", []):
                if scene.get("generate_background") and scene.get("background_prompt"):
                    scene_id = scene["scene_id"]
                    backgrounds_data[scene_id] = {
                        "prompt_type": "grok_t2i",
                        "prompt": scene["background_prompt"],
                        "output_path": None,
                        "fal_image_url": None,
                        "status": "pending",
                        "generated_by": "save_prompts_node"
                    }

    # Load existing prompts on disk to merge fal_image_url/output_path/status for backgrounds
    path = os.path.join(_output_dir(ctx), "prompts.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
                existing_bg = existing.get("backgrounds", {})
                for bg_id, bg_entry in backgrounds_data.items():
                    if bg_id in existing_bg:
                        # Preserving state
                        bg_entry["status"] = existing_bg[bg_id].get("status", "pending")
                        bg_entry["output_path"] = existing_bg[bg_id].get("output_path")
                        bg_entry["fal_image_url"] = existing_bg[bg_id].get("fal_image_url")
        except Exception as e:
            print(f"⚠️ Error merging existing backgrounds: {e}")

    prompts_data = {
        "meta": {
            "blueprint_version": 1,
            "last_updated_by": "graph_native_pipeline",
            "last_updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        "character_sheets": get_namespace_dict(char_sheets_raw, "character_sheets"),
        "backgrounds": backgrounds_data,
        "ff_shots": get_namespace_dict(ff_shots_raw, "ff_shots"),
        "lf_shots": get_namespace_dict(lf_shots_raw, "lf_shots"),
        "lf_delta_plan": lf_delta_raw if isinstance(lf_delta_raw, dict) else {},
        "character_spatial_map": spatial_map_raw if isinstance(spatial_map_raw, dict) else {},
        "motion_prompts": get_namespace_dict(motion_raw, "motion_prompts"),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prompts_data, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_prompts_node] Wrote {path}")


save_director_script_node = FunctionNode(func=save_director_script, name="save_director_script_node")
save_fflf_plan_node = FunctionNode(func=save_fflf_plan, name="save_fflf_plan_node")
save_blueprint_structure_node = FunctionNode(func=save_blueprint_structure, name="save_blueprint_structure_node")
save_blueprint_node = FunctionNode(func=save_blueprint, name="save_blueprint_node")
save_lf_delta_plan_node = FunctionNode(func=save_lf_delta_plan, name="save_lf_delta_plan_node")
save_character_spatial_map_node = FunctionNode(func=save_character_spatial_map, name="save_character_spatial_map_node")
save_prompts_node = FunctionNode(func=save_prompts, name="save_prompts_node")
