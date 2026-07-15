"""Validate and reconcile story plan duration against scene budgets."""
from __future__ import annotations

import json

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from .duration_reconcile import (
    reconcile_against_budgets,
    scene_budgets_from_plan_scenes,
)
from ._json_util import clean_json_str


async def duration_budget_validator(ctx: Context) -> None:
    raw = ctx.state.get("story_plan_content")
    if not raw:
        print("⚠️ [duration_budget_validator] story_plan_content missing")
        return

    story = clean_json_str(raw) if isinstance(raw, str) else raw
    meta_backup = story.get("_meta")
    meta = story.get("meta", {})
    target = meta.get("target_duration_seconds") or ctx.state.get("target_duration_seconds")
    tolerance = meta.get(
        "duration_tolerance_percent", ctx.state.get("duration_tolerance_percent", 15)
    )
    min_shot_seconds = int(ctx.state.get("min_shot_seconds", 6))
    max_shot_seconds = int(ctx.state.get("max_shot_seconds", 10))

    # Prefer budgets embedded on the production plan / story scenes.
    plan_raw = ctx.state.get("plan_content")
    budget_source = story
    if plan_raw:
        plan = clean_json_str(plan_raw) if isinstance(plan_raw, str) else plan_raw
        if isinstance(plan, dict) and plan.get("scenes"):
            budget_source = plan
    budgets = scene_budgets_from_plan_scenes(budget_source)
    if budgets:
        story = reconcile_against_budgets(
            story,
            budgets,
            tolerance_percent=tolerance,
            min_shot_seconds=min_shot_seconds,
            max_shot_seconds=max_shot_seconds,
        )
        if meta_backup is not None:
            story["_meta"] = meta_backup
        ctx.state["story_plan_content"] = json.dumps(story, indent=2, ensure_ascii=False)

    if not target:
        print("ℹ️ [duration_budget_validator] No target duration — skipping global check")
        return

    min_panels = int(ctx.state.get("min_panels_per_sheet") or 0)
    pipeline_mode = (ctx.state.get("pipeline_mode") or "").strip().lower()
    if min_panels > 0 and pipeline_mode == "storyboard":
        for scene in story.get("scenes", []):
            shot_count = len(scene.get("shots", []))
            scene_id = scene.get("scene_id", "?")
            if shot_count < min_panels:
                print(
                    f"⚠️ [duration_budget_validator] {scene_id} has {shot_count} shots "
                    f"(minimum {min_panels} per storyboard sheet)"
                )

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
        if pipeline_mode == "storyboard":
            print(
                f"⚠️ [duration_budget_validator] Over budget: {total}s "
                f"(target {target}s ±{tolerance}%, max {high}s) — continuing for storyboard mode"
            )
        else:
            raise ValueError(
                f"Story plan {total}s exceeds target budget {target}s +{tolerance}% (max {high}s)"
            )
    else:
        print(
            f"✅ [duration_budget_validator] {total}s within target "
            f"{target}s ±{tolerance}% ({low}–{high}s)"
        )


duration_budget_validator_node = FunctionNode(
    func=duration_budget_validator, name="duration_budget_validator_node"
)
