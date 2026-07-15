"""Normalize story plan shot ids and backfill scene metadata."""

_VALID_LTX_SHOT_TYPES = frozenset(
    {"establishing", "action", "reaction", "dialogue", "insert", "transition"}
)
_COMPLEXITY_MAP = {
    "low": "simple",
    "simple": "simple",
    "medium": "moderate",
    "moderate": "moderate",
    "high": "complex",
    "complex": "complex",
}
_VALID_FRAME_STRATEGIES = frozenset(
    {"empty_then_enter", "at_rest_then_react", "in_action_continuous"}
)


def _infer_time_of_day(text: str) -> str:
    lower = str(text or "").lower()
    if any(w in lower for w in ("night", "moon", "stars", "twilight", "dusk")):
        return "night"
    if any(w in lower for w in ("evening", "sunset", "golden hour")):
        return "evening"
    if any(w in lower for w in ("morning", "dawn", "sunrise")):
        return "morning"
    return "day"


def _infer_lighting(text: str) -> str:
    lower = str(text or "").lower()
    if "neon" in lower or "glow" in lower:
        return "Colorful neon glow with soft ambient fill"
    if "sunbeam" in lower or "sunlight" in lower or "golden" in lower:
        return "Warm natural sunlight with soft shadows"
    if "night" in lower or "moon" in lower:
        return "Cool moonlit ambience with gentle rim light"
    return "Soft natural lighting with balanced contrast"


def normalize_story_plan(story: dict) -> dict:
    """Ensure scene_XX_shot_YY ids and required scene-level fields."""
    name_to_id: dict[str, str] = {}
    known_character_ids: set[str] = set()
    raw_characters = story.get("characters", [])
    normalized_characters: list[dict] = []
    for idx, ch in enumerate(raw_characters, start=1):
        if isinstance(ch, str):
            label = ch.strip()
            slug = "".join(c for c in label.lower().replace(" ", "_") if c.isalnum() or c == "_")
            normalized_characters.append(
                {
                    "id": slug or f"character_{idx}",
                    "name": label or f"Character {idx}",
                    "appearance": "Not specified",
                    "voice_profile": "Natural conversational tone",
                }
            )
            continue
        if isinstance(ch, dict):
            normalized_characters.append(ch)
    story["characters"] = normalized_characters

    for idx, ch in enumerate(story.get("characters", []), start=1):
        cid = (ch.get("id") or "").strip()
        if not cid:
            fallback = (ch.get("name") or f"character_{idx}").strip().lower().replace(" ", "_")
            cid = "".join(c for c in fallback if c.isalnum() or c == "_").strip("_")
            ch["id"] = cid or f"character_{idx}"
            cid = ch["id"]
        name = (ch.get("name") or "").strip().lower()
        if not ch.get("appearance"):
            ch["appearance"] = (
                ch.get("description")
                or ch.get("role")
                or "Not specified"
            ).strip()
        if not ch.get("voice_profile"):
            ch["voice_profile"] = "Natural conversational tone"
        if cid:
            name_to_id[cid.lower()] = cid
            known_character_ids.add(cid)
        if name and cid:
            name_to_id[name] = cid

    for scene in story.get("scenes", []):
        scene_id = scene.get("scene_id", "")
        if not scene.get("title"):
            scene["title"] = (
                scene.get("scene_title")
                or scene.get("subtitle")
                or scene_id.replace("_", " ").title()
            )
        shots = scene.get("shots", [])
        blocking = scene.get("blocking")
        if isinstance(blocking, dict):
            normalized_blocking = []
            for raw_key, raw_val in blocking.items():
                key = str(raw_key).strip()
                cid = name_to_id.get(key.lower(), key)
                if cid not in known_character_ids:
                    continue
                position = str(raw_val).strip()
                normalized_blocking.append(
                    {
                        "character_id": cid,
                        "position": position,
                        "facing": "",
                    }
                )
            scene["blocking"] = normalized_blocking
        elif isinstance(blocking, list):
            normalized_blocking = []
            for item in blocking:
                if not isinstance(item, dict):
                    continue
                raw_id = (
                    item.get("character_id")
                    or item.get("character")
                    or item.get("id")
                    or ""
                )
                key = str(raw_id).strip()
                if not key:
                    continue
                cid = name_to_id.get(key.lower(), key)
                if cid not in known_character_ids:
                    continue
                normalized_blocking.append(
                    {
                        "character_id": cid,
                        "position": str(item.get("position") or "").strip(),
                        "facing": str(item.get("facing") or "").strip(),
                    }
                )
            scene["blocking"] = normalized_blocking
        else:
            scene["blocking"] = []

        for index, shot in enumerate(shots, start=1):
            shot["shot_id"] = f"{scene_id}_shot_{index:02d}"
            shot["scene_id"] = scene_id
            shot["characters_present"] = [
                name_to_id.get(str(c).strip().lower(), str(c).strip())
                for c in shot.get("characters_present", [])
                if str(c).strip()
            ]
            if shot.get("ltx_shot_type") not in _VALID_LTX_SHOT_TYPES:
                shot["ltx_shot_type"] = "action"
            raw_complexity = str(shot.get("ltx_complexity", "")).strip().lower()
            shot["ltx_complexity"] = _COMPLEXITY_MAP.get(raw_complexity, "moderate")
            if shot.get("frame_strategy") not in _VALID_FRAME_STRATEGIES:
                # Freeform director labels are normalized to the closest safe default.
                shot["frame_strategy"] = "in_action_continuous"

        first = shots[0] if shots else {}
        env_hint = (
            first.get("environment_state")
            or first.get("description")
            or scene.get("title", "")
        )
        scene.setdefault("environment", env_hint or "Unspecified environment")
        scene.setdefault("time_of_day", _infer_time_of_day(env_hint))
        scene.setdefault("lighting", _infer_lighting(env_hint))

    # Ensure every referenced character exists in story.characters so schema validation
    # does not fail on LLM outputs that mention valid participants but omit roster rows.
    referenced_ids: set[str] = set()
    for scene in story.get("scenes", []):
        for item in scene.get("blocking", []) or []:
            if isinstance(item, dict) and str(item.get("character_id", "")).strip():
                referenced_ids.add(str(item["character_id"]).strip())
        for shot in scene.get("shots", []) or []:
            for cid in shot.get("characters_present", []) or []:
                if str(cid).strip():
                    referenced_ids.add(str(cid).strip())

    missing_ids = sorted(referenced_ids - known_character_ids)
    if missing_ids:
        chars = story.setdefault("characters", [])
        for cid in missing_ids:
            chars.append(
                {
                    "id": cid,
                    "name": cid.replace("_", " ").title(),
                    "role": "Supporting character",
                    "appearance": "Not specified",
                    "voice_profile": "Natural conversational tone",
                }
            )
            known_character_ids.add(cid)

    return story
