"""Unified plan.json load/save with legacy multi-file adapter."""
from __future__ import annotations

import json
import os
from typing import Any

from schemas.plan import ProductionPlan


PLAN_FILENAME = "plan.json"


def plan_path(output_dir: str) -> str:
    return os.path.join(output_dir, PLAN_FILENAME)


def story_plan_view(plan: dict) -> dict:
    """Extract StoryPlan-shaped subset for legacy consumers."""
    scenes = []
    for scene in plan.get("scenes", []):
        scenes.append(
            {
                "scene_id": scene.get("scene_id"),
                "title": scene.get("title"),
                "environment": scene.get("environment"),
                "time_of_day": scene.get("time_of_day"),
                "lighting": scene.get("lighting"),
                "location_id": scene.get("location_id", ""),
                "background_population": scene.get("background_population", ""),
                "staging": scene.get("staging", ""),
                "blocking": scene.get("blocking", []),
                "shots": [
                    {
                        k: v
                        for k, v in shot.items()
                        if k != "audio"
                    }
                    for shot in scene.get("shots", [])
                ],
            }
        )
    out = {
        "meta": plan.get("meta", {}),
        "characters": plan.get("characters", []),
        "locations": plan.get("locations", []),
        "scenes": scenes,
    }
    if "_meta" in plan:
        out["_meta"] = plan["_meta"]
    return out


def audio_plan_view(plan: dict) -> dict:
    scenes = []
    shots: dict[str, dict] = {}
    for scene in plan.get("scenes", []):
        audio_scene = scene.get("audio_scene") or {}
        if isinstance(audio_scene, str):
            audio_scene = {"music_bed": audio_scene, "ending_state": ""}
        elif not isinstance(audio_scene, dict):
            audio_scene = {}
        scenes.append(
            {
                "scene_id": scene.get("scene_id"),
                "music_bed": audio_scene.get("music_bed"),
                "ending_state": audio_scene.get("ending_state"),
            }
        )
        for shot in scene.get("shots", []):
            sid = shot.get("shot_id")
            if not sid:
                continue
            audio = dict(shot.get("audio") or {})
            transition = audio.pop("transition", None)
            shots[sid] = {
                "shot_id": sid,
                "audio": {
                    "dialogue": audio.get("dialogue") or [],
                    "music": audio.get("music"),
                    "sfx": audio.get("sfx") or [],
                    "ambience": audio.get("ambience"),
                },
                "transition": transition,
            }
    return {"scenes": scenes, "shots": shots}


def scene_assets_view(plan: dict) -> dict:
    scenes = []
    for scene in plan.get("scenes", []):
        assets = dict(scene.get("assets") or {})
        scenes.append(
            {
                "scene_id": scene.get("scene_id"),
                "generate_background": bool(assets.get("generate_background", False)),
                "background_prompt": assets.get("background_prompt") or "",
                "background_reference_mode": assets.get("background_reference_mode")
                or "style_anchor",
                "rationale": assets.get("rationale") or "",
            }
        )
    return {"scenes": scenes}


def video_shot_plan_view(plan: dict) -> dict:
    scenes = []
    for scene in plan.get("scenes", []):
        scene_id = scene.get("scene_id")
        vshots = []
        for vs in scene.get("video_shots") or []:
            entry = dict(vs)
            entry.setdefault("scene_id", scene_id)
            vshots.append(entry)
        scenes.append({"scene_id": scene_id, "video_shots": vshots})
    return {"scenes": scenes}


def merge_legacy_files(output_dir: str) -> dict | None:
    """Build a ProductionPlan dict from legacy split artifacts, if present."""
    story_path = os.path.join(output_dir, "story_plan.json")
    if not os.path.isfile(story_path):
        return None
    with open(story_path, encoding="utf-8") as f:
        story = json.load(f)

    audio = {"scenes": [], "shots": {}}
    audio_path = os.path.join(output_dir, "audio_plan.json")
    if os.path.isfile(audio_path):
        with open(audio_path, encoding="utf-8") as f:
            audio = json.load(f)

    assets = {"scenes": []}
    assets_path = os.path.join(output_dir, "scene_assets.json")
    if os.path.isfile(assets_path):
        with open(assets_path, encoding="utf-8") as f:
            assets = json.load(f)

    video = {"scenes": []}
    video_path = os.path.join(output_dir, "video_shot_plan.json")
    if os.path.isfile(video_path):
        with open(video_path, encoding="utf-8") as f:
            video = json.load(f)

    audio_scene_lookup = {
        s.get("scene_id"): s for s in audio.get("scenes", []) if isinstance(s, dict)
    }
    assets_lookup = {
        s.get("scene_id"): s for s in assets.get("scenes", []) if isinstance(s, dict)
    }
    video_lookup = {
        s.get("scene_id"): s for s in video.get("scenes", []) if isinstance(s, dict)
    }
    shot_audio = audio.get("shots") or {}

    scenes: list[dict] = []
    for scene in story.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        scene_id = scene.get("scene_id")
        asset = assets_lookup.get(scene_id) or {}
        audio_scene = audio_scene_lookup.get(scene_id) or {}
        vshots = (video_lookup.get(scene_id) or {}).get("video_shots") or []
        shots = []
        for shot in scene.get("shots", []):
            if not isinstance(shot, dict):
                continue
            sid = shot.get("shot_id")
            sa = shot_audio.get(sid) or {}
            audio_block = dict(sa.get("audio") or {})
            if sa.get("transition") is not None:
                audio_block["transition"] = sa.get("transition")
            shots.append({**shot, "audio": audio_block})
        duration_budget = sum(int(s.get("duration_seconds", 0)) for s in shots) or None
        scenes.append(
            {
                **{k: v for k, v in scene.items() if k != "shots"},
                "duration_budget_seconds": duration_budget,
                "assets": {
                    "generate_background": bool(asset.get("generate_background", False)),
                    "background_prompt": asset.get("background_prompt") or "",
                    "background_reference_mode": asset.get("background_reference_mode")
                    or "style_anchor",
                    "rationale": asset.get("rationale") or "",
                },
                "audio_scene": {
                    "music_bed": audio_scene.get("music_bed"),
                    "ending_state": audio_scene.get("ending_state"),
                },
                "shots": shots,
                "video_shots": vshots,
            }
        )

    plan = {
        "meta": story.get("meta", {}),
        "characters": story.get("characters", []),
        "scenes": scenes,
    }
    if "_meta" in story:
        plan["_meta"] = story["_meta"]
    return plan


def load_plan(output_dir: str, *, write_if_legacy: bool = False) -> dict | None:
    """Load plan.json, or synthesize from legacy files."""
    path = plan_path(output_dir)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    legacy = merge_legacy_files(output_dir)
    if legacy is None:
        return None
    if write_if_legacy:
        save_plan_dict(output_dir, legacy)
    return legacy


def save_plan_dict(output_dir: str, plan: dict) -> str:
    os.makedirs(output_dir, exist_ok=True)
    path = plan_path(output_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    return path


def validate_plan_dict(plan: dict) -> dict:
    """Validate via ProductionPlan; return dumped dict (preserves unknown _meta)."""
    meta_backup = plan.get("_meta")
    validated = ProductionPlan(**{k: v for k, v in plan.items() if k != "_meta"}).model_dump()
    if meta_backup is not None:
        validated["_meta"] = meta_backup
    return validated


def sync_legacy_state(state: dict[str, Any], plan: dict) -> None:
    """Populate legacy state keys so existing nodes keep working."""
    state["plan_content"] = json.dumps(plan, indent=2, ensure_ascii=False)
    state["story_plan_content"] = json.dumps(story_plan_view(plan), indent=2, ensure_ascii=False)
    state["audio_plan_content"] = json.dumps(audio_plan_view(plan), indent=2, ensure_ascii=False)
    state["scene_assets_content"] = json.dumps(scene_assets_view(plan), indent=2, ensure_ascii=False)
    state["video_shot_plan_content"] = json.dumps(
        video_shot_plan_view(plan), indent=2, ensure_ascii=False
    )


def apply_story_view_to_plan(plan: dict, story_view: dict) -> dict:
    """Merge timeline/duration updates from a story-plan view back into plan.json."""
    shot_lookup: dict[str, dict] = {}
    scene_lookup: dict[str, dict] = {}
    for scene in story_view.get("scenes", []):
        sid = scene.get("scene_id")
        if sid:
            scene_lookup[sid] = scene
        for shot in scene.get("shots", []):
            if shot.get("shot_id"):
                shot_lookup[shot["shot_id"]] = shot

    out = dict(plan)
    out["meta"] = story_view.get("meta", plan.get("meta", {}))
    if "_meta" in story_view:
        out["_meta"] = story_view["_meta"]
    elif "_meta" in plan:
        out["_meta"] = plan["_meta"]

    new_scenes = []
    for scene in plan.get("scenes", []):
        scene_id = scene.get("scene_id")
        updated_scene = dict(scene)
        src = scene_lookup.get(scene_id) or {}
        for key in (
            "title",
            "environment",
            "time_of_day",
            "lighting",
            "location_id",
            "background_population",
            "staging",
            "blocking",
        ):
            if key in src:
                updated_scene[key] = src[key]
        new_shots = []
        for shot in scene.get("shots", []):
            sid = shot.get("shot_id")
            src_shot = shot_lookup.get(sid) or {}
            merged = {**shot, **{k: v for k, v in src_shot.items() if k != "audio"}}
            if "audio" in shot:
                merged["audio"] = shot["audio"]
            new_shots.append(merged)
        updated_scene["shots"] = new_shots
        if updated_scene.get("duration_budget_seconds") is None:
            updated_scene["duration_budget_seconds"] = sum(
                int(s.get("duration_seconds", 0)) for s in new_shots
            )
        new_scenes.append(updated_scene)
    out["scenes"] = new_scenes
    return out


def apply_video_shots_to_plan(plan: dict, video_plan: dict) -> dict:
    lookup = {
        s.get("scene_id"): s.get("video_shots") or []
        for s in video_plan.get("scenes", [])
        if isinstance(s, dict)
    }
    out = dict(plan)
    scenes = []
    for scene in plan.get("scenes", []):
        updated = dict(scene)
        sid = scene.get("scene_id")
        if sid in lookup:
            updated["video_shots"] = lookup[sid]
        scenes.append(updated)
    out["scenes"] = scenes
    return out
