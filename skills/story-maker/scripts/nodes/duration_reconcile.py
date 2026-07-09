"""Per-scene duration reconciliation against narrative outline budgets."""
from __future__ import annotations

from tools.workflow_builder import snap_duration_seconds


def scene_budgets(outline: dict) -> dict[str, int]:
    budgets: dict[str, int] = {}
    for act in outline.get("acts", []):
        for scene in act.get("scenes", []):
            sid = scene.get("scene_id")
            if sid:
                budgets[sid] = int(scene.get("duration_budget_seconds", 0))
    return budgets


def recompute_meta(story: dict) -> None:
    total = 0
    shots = 0
    for scene in story.get("scenes", []):
        for shot in scene.get("shots", []):
            shots += 1
            total += int(shot.get("duration_seconds", 0))
    meta = story.setdefault("meta", {})
    meta["total_shots"] = shots
    meta["total_scenes"] = len(story.get("scenes", []))
    meta["total_duration_seconds"] = total


def reconcile_scene_durations(
    story: dict,
    outline: dict,
    *,
    tolerance_percent: int = 15,
    min_shot_seconds: int = 4,
    max_shot_seconds: int = 16,
) -> dict:
    """Rebalance shot durations within each scene toward outline scene budgets."""
    budgets = scene_budgets(outline)
    if not budgets:
        return story

    for scene in story.get("scenes", []):
        sid = scene.get("scene_id")
        budget = budgets.get(sid)
        if not budget:
            continue
        shots = scene.get("shots", [])
        if not shots:
            continue

        for shot in shots:
            snapped = snap_duration_seconds(shot.get("duration_seconds", 8))
            shot["duration_seconds"] = max(min_shot_seconds, min(max_shot_seconds, snapped))

        total = sum(s["duration_seconds"] for s in shots)
        low = int(budget * (1 - tolerance_percent / 100))
        high = int(budget * (1 + tolerance_percent / 100))

        guard = 0
        while total > high and guard < 500:
            guard += 1
            longest = max(shots, key=lambda s: s["duration_seconds"])
            if longest["duration_seconds"] <= min_shot_seconds:
                break
            longest["duration_seconds"] = snap_duration_seconds(longest["duration_seconds"] - 1)
            total = sum(s["duration_seconds"] for s in shots)

        guard = 0
        while total < low and guard < 500:
            guard += 1
            shortest = min(shots, key=lambda s: s["duration_seconds"])
            if shortest["duration_seconds"] >= max_shot_seconds:
                break
            shortest["duration_seconds"] = snap_duration_seconds(shortest["duration_seconds"] + 1)
            total = sum(s["duration_seconds"] for s in shots)

        offset = 0
        for i, shot in enumerate(shots):
            shot["scene_time_offset_seconds"] = offset
            shot["continuity_from_previous"] = i > 0
            offset += shot["duration_seconds"]

    recompute_meta(story)
    return story
