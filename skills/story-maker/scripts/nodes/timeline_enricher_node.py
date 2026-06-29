"""Deterministic scene timeline enrichment for story plan shots."""
import json
import os

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from ._json_util import clean_json_str


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


async def timeline_enricher(ctx: Context) -> None:
    raw = ctx.state.get("story_plan_content")
    if not raw:
        print("⚠️ [timeline_enricher] story_plan_content missing, skipping")
        return

    story = clean_json_str(raw) if isinstance(raw, str) else raw
    enriched = enrich_story_timeline(story)
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
