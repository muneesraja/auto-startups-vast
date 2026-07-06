"""Validate and reconcile story plan duration against narrative outline budgets."""
from __future__ import annotations

import json
import os

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from .duration_reconcile import reconcile_scene_durations
from ._json_util import clean_json_str


def _load_outline(ctx: Context) -> dict | None:
    raw = ctx.state.get("narrative_outline_content")
    if raw:
        return clean_json_str(raw) if isinstance(raw, str) else raw
    output_dir = ctx.state.get("output_dir")
    if not output_dir:
        return None
    path = os.path.join(output_dir, "narrative_outline.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def duration_budget_validator(ctx: Context) -> None:
    raw = ctx.state.get("story_plan_content")
    if not raw:
        print("⚠️ [duration_budget_validator] story_plan_content missing")
        return

    story = clean_json_str(raw) if isinstance(raw, str) else raw
    meta_backup = story.get("_meta")
    meta = story.get("meta", {})
    target = meta.get("target_duration_seconds") or ctx.state.get("target_duration_seconds")
    tolerance = meta.get("duration_tolerance_percent", ctx.state.get("duration_tolerance_percent", 15))

    outline = _load_outline(ctx)
    if outline:
        story = reconcile_scene_durations(story, outline, tolerance_percent=tolerance)
        if meta_backup is not None:
            story["_meta"] = meta_backup
        ctx.state["story_plan_content"] = json.dumps(story, indent=2, ensure_ascii=False)

    if not target:
        print("ℹ️ [duration_budget_validator] No target duration — skipping global check")
        return

    total = story.get("meta", {}).get("total_duration_seconds", 0)
    if not total:
        total = sum(
            shot.get("duration_seconds", 0)
            for scene in story.get("scenes", [])
            for shot in scene.get("shots", [])
        )

    low = int(target * (1 - tolerance / 100))
    high = int(target * (1 + tolerance / 100))

    if total < low:
        print(
            f"⚠️ [duration_budget_validator] Under budget: {total}s "
            f"(target {target}s ±{tolerance}%, need ≥{low}s)"
        )
    elif total > high:
        raise ValueError(
            f"Story plan {total}s exceeds target budget {target}s +{tolerance}% (max {high}s)"
        )
    else:
        print(
            f"✅ [duration_budget_validator] {total}s within target "
            f"{target}s ±{tolerance}% ({low}–{high}s)"
        )

    output_dir = ctx.state.get("output_dir")
    if output_dir:
        if meta_backup is not None:
            story["_meta"] = meta_backup
        path = os.path.join(output_dir, "story_plan.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(story, f, indent=2, ensure_ascii=False)


duration_budget_validator_node = FunctionNode(
    func=duration_budget_validator, name="duration_budget_validator_node"
)
