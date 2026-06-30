"""Normalize story plan shot ids and backfill scene metadata."""

_VALID_LTX_SHOT_TYPES = frozenset(
    {"establishing", "action", "reaction", "dialogue", "insert", "transition"}
)


def _infer_time_of_day(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ("night", "moon", "stars", "twilight", "dusk")):
        return "night"
    if any(w in lower for w in ("evening", "sunset", "golden hour")):
        return "evening"
    if any(w in lower for w in ("morning", "dawn", "sunrise")):
        return "morning"
    return "day"


def _infer_lighting(text: str) -> str:
    lower = text.lower()
    if "neon" in lower or "glow" in lower:
        return "Colorful neon glow with soft ambient fill"
    if "sunbeam" in lower or "sunlight" in lower or "golden" in lower:
        return "Warm natural sunlight with soft shadows"
    if "night" in lower or "moon" in lower:
        return "Cool moonlit ambience with gentle rim light"
    return "Soft natural lighting with balanced contrast"


def normalize_story_plan(story: dict) -> dict:
    """Ensure scene_XX_shot_YY ids and required scene-level fields."""
    for scene in story.get("scenes", []):
        scene_id = scene.get("scene_id", "")
        shots = scene.get("shots", [])
        for index, shot in enumerate(shots, start=1):
            shot["shot_id"] = f"{scene_id}_shot_{index:02d}"
            shot["scene_id"] = scene_id
            if shot.get("ltx_shot_type") not in _VALID_LTX_SHOT_TYPES:
                shot["ltx_shot_type"] = "action"

        first = shots[0] if shots else {}
        env_hint = (
            first.get("environment_state")
            or first.get("description")
            or scene.get("title", "")
        )
        scene.setdefault("environment", env_hint or "Unspecified environment")
        scene.setdefault("time_of_day", _infer_time_of_day(env_hint))
        scene.setdefault("lighting", _infer_lighting(env_hint))

    return story
