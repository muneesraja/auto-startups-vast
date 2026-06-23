"""Single-writer save nodes — each node writes ONE artifact to disk.

Replaces the legacy `write_intermediate_files` callback that rewrote
ALL accumulated artifacts on every state delta (ISSUE-001).

Each node reads its assigned state key, optionally parses it, and writes
the corresponding file. Nodes are idempotent: re-running with the same
state produces no change.

ADK 2.0 modernization notes:
- Uses the modern `@node` decorator instead of `FunctionNode(func=...)`.
- Returns `Event(state={...})` for state writes mid-node (none here), and
  returns `None` (no-op) for pure save nodes (the state has not changed
  — only disk has).
- Imports `Context` and `Event` from top-level `google.adk`.
"""
import os
import json
from datetime import datetime, timezone

from google.adk import Context, Event
from google.adk.workflow import node

from ._json_util import clean_json_str, get_namespace_dict


def _output_dir(ctx: Context) -> str:
    """Resolve the output directory from session state (set by resume_router)."""
    out = ctx.state.get("output_dir")
    if not out:
        raise ValueError("output_dir not set in state. resume_router_node must run first.")
    os.makedirs(out, exist_ok=True)
    return out


@node
async def save_director_script_node(ctx: Context) -> None:
    """Write Director_script.md from state['director_script_content']."""
    content = ctx.state.get("director_script_content")
    if not content:
        return
    path = os.path.join(_output_dir(ctx), "Director_script.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"📁 [save_director_script_node] Wrote {path}")


@node
async def save_blueprint_structure_node(ctx: Context) -> None:
    """Write director_visual_blueprint_structure.json from state['blueprint_structure_json']."""
    raw = ctx.state.get("blueprint_structure_json")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    path = os.path.join(_output_dir(ctx), "director_visual_blueprint_structure.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_blueprint_structure_node] Wrote {path}")


@node
async def save_blueprint_node(ctx: Context) -> None:
    """Write director_visual_blueprint.json from state['blueprint_json_content']."""
    raw = ctx.state.get("blueprint_json_content")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    path = os.path.join(_output_dir(ctx), "director_visual_blueprint.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_blueprint_node] Wrote {path}")


@node
async def save_lf_delta_plan_node(ctx: Context) -> None:
    """Write lf_delta_plan.json from state['lf_delta_plan_content']."""
    raw = ctx.state.get("lf_delta_plan_content")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    path = os.path.join(_output_dir(ctx), "lf_delta_plan.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_lf_delta_plan_node] Wrote {path}")


@node
async def save_character_spatial_map_node(ctx: Context) -> None:
    """Write character_spatial_map.json from state['character_spatial_map_content']."""
    raw = ctx.state.get("character_spatial_map_content")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    path = os.path.join(_output_dir(ctx), "character_spatial_map.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_character_spatial_map_node] Wrote {path}")


@node
async def save_prompts_node(ctx: Context) -> None:
    """Assemble prompts.json from all `*_content` state keys and write to disk.

    Flux-only architecture: drops consistency_patches / lf_consistency_patches
    namespaces and ff/lf_vision_reviews (vision_review_nodes removed).
    """
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

    prompts_data = {
        "meta": {
            "blueprint_version": 1,
            "last_updated_by": "graph_native_pipeline",
            "last_updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        "character_sheets": get_namespace_dict(char_sheets_raw, "character_sheets"),
        "ff_shots": get_namespace_dict(ff_shots_raw, "ff_shots"),
        "lf_shots": get_namespace_dict(lf_shots_raw, "lf_shots"),
        "lf_delta_plan": lf_delta_raw if isinstance(lf_delta_raw, dict) else {},
        "character_spatial_map": spatial_map_raw if isinstance(spatial_map_raw, dict) else {},
        "motion_prompts": get_namespace_dict(motion_raw, "motion_prompts"),
    }
    path = os.path.join(_output_dir(ctx), "prompts.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prompts_data, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_prompts_node] Wrote {path}")
