"""Deterministic scene timeline enrichment for story plan shots."""
import json
import os

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from ._json_util import clean_json_str
from .story_plan_normalize import normalize_story_plan


def enrich_story_timeline(story: dict) -> dict:
    """Set scene_time_offset_seconds and continuity_from_previous per shot."""
    shot_count = 0
    duration_sum = 0
    for scene in story.get("scenes", []):
        offset = 0
        for i, shot in enumerate(scene.get("shots", [])):
            shot["scene_time_offset_seconds"] = offset
            shot["continuity_from_previous"] = i > 0
            dur = shot.get("duration_seconds", 0)
            offset += dur
            shot_count += 1
            duration_sum += dur
    meta = story.setdefault("meta", {})
    meta["total_shots"] = shot_count
    meta["total_scenes"] = len(story.get("scenes", []))
    meta["total_duration_seconds"] = duration_sum
    return story


def enrich_story_timeline_with_target(story: dict, target_duration_seconds: int | None) -> dict:
    story = normalize_story_plan(story)
    story = enrich_story_timeline(story)
    if target_duration_seconds is not None:
        story.setdefault("meta", {})["target_duration_seconds"] = target_duration_seconds
    return story


async def timeline_enricher(ctx: Context) -> None:
    raw = ctx.state.get("story_plan_content")
    if not raw:
        print("⚠️ [timeline_enricher] story_plan_content missing, skipping")
        return

    story = clean_json_str(raw) if isinstance(raw, str) else raw
    target = ctx.state.get("target_duration_seconds")
    enriched = enrich_story_timeline_with_target(story, target)
    ctx.state["story_plan_content"] = json.dumps(enriched, indent=2, ensure_ascii=False)

    output_dir = ctx.state.get("output_dir")
    if output_dir:
        path = os.path.join(output_dir, "story_plan.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(enriched, f, indent=2, ensure_ascii=False)
        print(f"📁 [timeline_enricher] Wrote enriched {path}")


timeline_enricher_node = FunctionNode(
    func=timeline_enricher, name="timeline_enricher_node"
)
