"""Cost estimate node for plan-only and resume visibility."""
from __future__ import annotations

import json
import os

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

import config
from ._json_util import clean_json_str
from .generation_nodes import _load_specs, _only_scenes, _scene_in_scope


def _load_video_shot_plan(ctx: Context) -> dict:
    raw = ctx.state.get("video_shot_plan_content")
    if not raw:
        path = os.path.join(ctx.state["output_dir"], "video_shot_plan.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                raw = f.read()
    if not raw:
        return {"scenes": []}
    return clean_json_str(raw) if isinstance(raw, str) else raw


def _pending_count(entries: dict[str, dict]) -> int:
    total = 0
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        out = entry.get("output_path")
        if out and os.path.isfile(out):
            continue
        if entry.get("status") == "completed":
            continue
        total += 1
    return total


async def cost_estimate(ctx: Context) -> None:
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    video_shot_plan = _load_video_shot_plan(ctx)
    only_scenes = _only_scenes(ctx)
    pipeline_mode = ctx.state.get("pipeline_mode") or "per_shot"

    character_calls = _pending_count(specs.get("character_sheets", {}))
    sheet_calls = _pending_count(specs.get("storyboard_sheets", {}))

    if pipeline_mode == "storyboard" and video_shot_plan.get("scenes"):
        anchor_ids: list[str] = []
        ltx_count = 0
        for scene in video_shot_plan.get("scenes", []):
            scene_id = scene.get("scene_id")
            if not _scene_in_scope(scene_id, only_scenes):
                continue
            for vshot in scene.get("video_shots", []):
                anchor = vshot.get("anchor_panel_id")
                if anchor and anchor not in anchor_ids:
                    anchor_ids.append(anchor)
                ltx_count += 1
        panel_regen_calls = 0
        for sid in anchor_ids:
            shot_entry = specs.get("shot_images", {}).get(sid, {})
            out = shot_entry.get("output_path")
            if out and os.path.isfile(out):
                continue
            panel_regen_calls += 1
        vision_calls = ltx_count
    else:
        panel_regen_calls = _pending_count(specs.get("shot_images", {}))
        vision_calls = panel_regen_calls
        ltx_count = _pending_count(specs.get("motion", {}))

    replicate_calls = character_calls + sheet_calls + panel_regen_calls
    estimate = {
        "counts": {
            "character_sheet_images": character_calls,
            "storyboard_sheet_images": sheet_calls,
            "panel_or_shot_images": panel_regen_calls,
            "vision_motion_calls": vision_calls,
            "ltx_video_calls": ltx_count,
            "replicate_image_calls_total": replicate_calls,
        },
        "unit_costs_usd": {
            "replicate_image_call": config.COST_REPLICATE_IMAGE,
            "openrouter_call": config.COST_OPENROUTER_CALL,
            "ltx_video_call": config.COST_LTX_VIDEO,
        },
    }
    estimate["estimated_cost_usd"] = {
        "replicate_images": round(replicate_calls * config.COST_REPLICATE_IMAGE, 4),
        "openrouter_calls": round(vision_calls * config.COST_OPENROUTER_CALL, 4),
        "ltx_videos": round(ltx_count * config.COST_LTX_VIDEO, 4),
    }
    estimate["estimated_cost_usd"]["total"] = round(
        estimate["estimated_cost_usd"]["replicate_images"]
        + estimate["estimated_cost_usd"]["openrouter_calls"]
        + estimate["estimated_cost_usd"]["ltx_videos"],
        4,
    )

    path = os.path.join(output_dir, "cost_estimate.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(estimate, f, indent=2, ensure_ascii=False)

    print(
        "💰 [cost_estimate] "
        f"replicate={replicate_calls}, vision={vision_calls}, ltx={ltx_count}, "
        f"estimated_total_usd={estimate['estimated_cost_usd']['total']}"
    )


cost_estimate_node = FunctionNode(func=cost_estimate, name="cost_estimate_node")
