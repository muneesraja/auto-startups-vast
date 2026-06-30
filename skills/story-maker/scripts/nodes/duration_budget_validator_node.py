"""Validate story plan total duration against target budget."""
import json

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from ._json_util import clean_json_str


async def duration_budget_validator(ctx: Context) -> None:
    raw = ctx.state.get("story_plan_content")
    if not raw:
        print("⚠️ [duration_budget_validator] story_plan_content missing")
        return

    story = clean_json_str(raw) if isinstance(raw, str) else raw
    meta = story.get("meta", {})
    target = meta.get("target_duration_seconds") or ctx.state.get("target_duration_seconds")
    if not target:
        print("ℹ️ [duration_budget_validator] No target duration — skipping")
        return

    tolerance = meta.get("duration_tolerance_percent", 15)
    total = meta.get("total_duration_seconds", 0)
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
        path = f"{output_dir}/story_plan.json"
        with open(path, encoding="utf-8") as f:
            on_disk = json.load(f)
        on_disk.setdefault("meta", {})["target_duration_seconds"] = target
        on_disk["meta"]["duration_tolerance_percent"] = tolerance
        with open(path, "w", encoding="utf-8") as f:
            json.dump(on_disk, f, indent=2, ensure_ascii=False)


duration_budget_validator_node = FunctionNode(
    func=duration_budget_validator, name="duration_budget_validator_node"
)
