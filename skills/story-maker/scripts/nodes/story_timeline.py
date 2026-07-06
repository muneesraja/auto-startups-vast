"""Pure story timeline enrichment (no ADK dependencies)."""
from __future__ import annotations

from tools.workflow_builder import snap_duration_seconds
from .story_plan_normalize import normalize_story_plan


def enrich_story_timeline(story: dict, *, fps: int = 25) -> dict:
    """Snap durations to LTX 8n+1, then set offsets and continuity."""
    shot_count = 0
    duration_sum = 0
    for scene in story.get("scenes", []):
        offset = 0
        for i, shot in enumerate(scene.get("shots", [])):
            raw = shot.get("duration_seconds", 8)
            shot["duration_seconds"] = snap_duration_seconds(raw, fps=fps)
            shot["scene_time_offset_seconds"] = offset
            shot["continuity_from_previous"] = i > 0
            dur = shot["duration_seconds"]
            offset += dur
            shot_count += 1
            duration_sum += dur
    meta = story.setdefault("meta", {})
    meta["total_shots"] = shot_count
    meta["total_scenes"] = len(story.get("scenes", []))
    meta["total_duration_seconds"] = duration_sum
    return story


def enrich_story_timeline_with_target(story: dict, target_duration_seconds: int | None) -> dict:
    meta_backup = story.get("_meta")
    story = normalize_story_plan(story)
    story = enrich_story_timeline(story)
    if target_duration_seconds is not None:
        story.setdefault("meta", {})["target_duration_seconds"] = target_duration_seconds
    if meta_backup is not None:
        story["_meta"] = meta_backup
    return story
