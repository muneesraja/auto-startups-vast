"""Validate prompts as a FunctionNode after assembly and before wave execution.

Defensive layer that catches:
- Char refs present for characters not in `characters_present`
- Missing char refs for characters that are present
- Incorrect prompt types or invalid LF reference templates
- Validates Pydantic schemas on actual artifacts.
"""
import os
import json
import re
from typing import Any

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from ._json_util import clean_json_str


# Regex detecting template references like {{character_sheets.char_01.fal_image_url}}
_REF_PATTERN = re.compile(r"\{\{+([^}]+)\}\}+")


def _check_character_in_prompt(
    prompt_text: str,
    char_id: str,
    char_name: str,
    char_appearance: str,
    spatial_map: dict[str, Any],
    shot_id: str,
) -> tuple[bool, str]:
    """Check if the character is mentioned or described in the prompt text.
    Returns (is_present, reason_or_debug_info).
    """
    if not prompt_text:
        return True, "No prompt text to check"

    prompt_lower = prompt_text.lower()
    char_name_lower = char_name.lower()
    
    # 1. Direct name check
    if char_name_lower in prompt_lower:
        return True, f"Found character name '{char_name}' in prompt"

    # 2. Extract potential nouns from visual_identifier in spatial map
    placements = spatial_map.get(shot_id) or []
    visual_id = ""
    for p in placements:
        if p.get("character_id") == char_id:
            visual_id = p.get("visual_identifier", "")
            break

    desc_to_parse = visual_id if visual_id else char_appearance
    if not desc_to_parse:
        return False, "No name, appearance, or visual identifier found for character"

    # Split by common prepositions/verbs to get the main noun phrase
    desc_lower = desc_to_parse.lower()
    split_words = [" with ", " in ", " at ", " on ", " wearing ", " holding ", " peeking ", " standing ", " sitting ", " lying ", " running ", " walking ", " silhouette ", " profile "]
    main_phrase = desc_lower
    for sw in split_words:
        if sw in desc_lower:
            main_phrase = desc_lower.split(sw)[0]
            break

    # Clean punctuation and tokenize
    words = re.findall(r"\b[a-z]{3,}\b", main_phrase)
    
    # Adjectives/stopwords to filter out
    adjectives_and_stopwords = {
        "a", "an", "the", "and", "or", "but", "chubby", "fluffy", "adorable", "sad", 
        "happy", "little", "big", "small", "young", "old", "cute", "scared", "excited", 
        "playful", "gentle", "whimsical", "soft", "beautiful", "charming", "tiny",
        "giant", "character", "sheet", "style", "render", "animated", "movie", "pixar",
        "disney", "storybook", "feel", "texture", "eyes", "nose", "ears", "mouth", "fur",
        "paw", "paws", "cream", "white", "black", "grey", "gray", "brown", "red", "green",
        "blue", "yellow", "orange", "purple", "color", "colored"
    }
    
    keywords = [w for w in words if w not in adjectives_and_stopwords]
    if not keywords:
        keywords = [w for w in words if w not in {"a", "an", "the", "and", "or", "but", "with", "in", "at", "on"}]

    matched_keywords = []
    for kw in keywords:
        if kw in prompt_lower:
            matched_keywords.append(kw)

    if matched_keywords:
        return True, f"Found matching keyword(s) {matched_keywords} from visual identifier/appearance in prompt"

    return False, f"Character '{char_name}' ({char_id}) not found in prompt text. Searched for name '{char_name}' and keywords {keywords} from description: '{desc_to_parse}'"


def _validate_prompt_text_coverage(
    shot_id: str,
    entry: dict[str, Any],
    blueprint: dict[str, Any],
    spatial_map: dict[str, Any],
    errors: list[str]
) -> None:
    """Validate that all characters_present are described/mentioned in the prompt text."""
    shot_lookup = _build_shot_lookup(blueprint)
    shot = shot_lookup.get(shot_id)
    if not shot:
        return

    prompt_type = entry.get("prompt_type")
    if prompt_type == "extracted_frame":
        return

    prompt_text = entry.get("prompt")
    if not prompt_text:
        return

    characters_present = shot.get("characters_present") or []
    if not characters_present:
        return

    char_lookup = {c["id"]: c for c in blueprint.get("characters", []) or []}

    for char_id in characters_present:
        char = char_lookup.get(char_id)
        if not char:
            errors.append(f"[Prompt-Text] {shot_id}: character '{char_id}' is present but not defined in blueprint characters.")
            continue

        is_present, reason = _check_character_in_prompt(
            prompt_text,
            char_id,
            char.get("name", ""),
            char.get("appearance", ""),
            spatial_map,
            shot_id
        )
        if not is_present:
            errors.append(f"[Prompt-Text-cov] {shot_id}: {reason}")


def _validate_ff_shots(
    ff_shots: dict[str, Any], blueprint: dict[str, Any], spatial_map: dict[str, Any], errors: list[str]
) -> None:
    """Validate FF shot prompts:
    - prompt_type is grok_edit or extracted_frame
    - coverage and exclusion checks for present/absent characters
    - reference_images length <= 7
    """
    shot_lookup = _build_shot_lookup(blueprint)
    for shot_id, entry in ff_shots.items():
        shot = shot_lookup.get(shot_id)
        if not shot:
            continue
        
        prompt_type = entry.get("prompt_type")
        if shot.get("continuation_from_previous", False):
            if prompt_type != "extracted_frame":
                errors.append(f"[FF-continuation] {shot_id}: continuation shot must have prompt_type='extracted_frame' (got {prompt_type!r})")
            continue
            
        if prompt_type != "grok_edit":
            errors.append(f"[FF-type] {shot_id}: non-continuation shot must have prompt_type='grok_edit' (got {prompt_type!r})")

        characters_present = set(shot.get("characters_present") or [])
        refs = entry.get("reference_images") or []

        if len(refs) > 7:
            errors.append(f"[FF-limit] {shot_id}: reference_images count exceeds 7 limit (got {len(refs)})")

        referenced_char_ids: set[str] = set()
        bad_refs = []
        for ref in refs:
            match = _REF_PATTERN.search(ref)
            if not match:
                continue
            parts = match.group(1).strip().split(".")
            if len(parts) != 3 or parts[0] != "character_sheets":
                continue
            char_id = parts[1]
            referenced_char_ids.add(char_id)
            if char_id not in characters_present:
                bad_refs.append(ref)
                
        if bad_refs:
            errors.append(
                f"[FF-excl] {shot_id}: reference_images contain refs to absent characters: {bad_refs}. "
                f"Expected only: {sorted(characters_present)}"
            )
            
        missing_refs = sorted(characters_present - referenced_char_ids)
        # Note: only error if within limit, if truncated we logged warning during repair
        if missing_refs and len(refs) < 7:
            errors.append(
                f"[FF-cov] {shot_id}: characters_present has {sorted(characters_present)} but "
                f"reference_images only cover {sorted(referenced_char_ids)}. Missing: {missing_refs}"
            )

        # Validate prompt text coverage
        _validate_prompt_text_coverage(shot_id, entry, blueprint, spatial_map, errors)


def _validate_lf_shots(
    lf_shots: dict[str, Any], blueprint: dict[str, Any], spatial_map: dict[str, Any], errors: list[str]
) -> None:
    """Validate LF shot prompts:
    - prompt_type is grok_edit
    - first reference is the FF image only if use_ff_as_lf_reference or continuation
    - coverage and exclusion checks for present/absent characters
    - reference_images length <= 7
    """
    shot_lookup = _build_shot_lookup(blueprint)
    for shot_id, entry in lf_shots.items():
        shot = shot_lookup.get(shot_id)
        if not shot:
            continue
            
        prompt_type = entry.get("prompt_type")
        if prompt_type != "grok_edit":
            errors.append(f"[LF-type] {shot_id}: LF shot must have prompt_type='grok_edit' (got {prompt_type!r})")

        characters_present = set(shot.get("characters_present") or [])
        refs = entry.get("reference_images") or []

        if len(refs) > 7:
            errors.append(f"[LF-limit] {shot_id}: reference_images count exceeds 7 limit (got {len(refs)})")

        use_ff = True
        ff_ref = f"{{{{ff_shots.{shot_id}.fal_image_url}}}}"

        char_refs = refs
        if use_ff:
            if not refs or refs[0] != ff_ref:
                errors.append(
                    f"[LF-ref1] {shot_id}: first reference image must point to ff_shots.{shot_id}.fal_image_url (got {refs[0] if refs else None})"
                )
            char_refs = refs[1:]

        referenced_char_ids: set[str] = set()
        bad_refs = []
        for ref in char_refs:
            match = _REF_PATTERN.search(ref)
            if not match:
                continue
            parts = match.group(1).strip().split(".")
            if len(parts) != 3 or parts[0] != "character_sheets":
                continue
            char_id = parts[1]
            referenced_char_ids.add(char_id)
            if char_id not in characters_present:
                bad_refs.append(ref)
                
        if bad_refs:
            errors.append(
                f"[LF-excl] {shot_id}: reference_images contain refs to absent characters: {bad_refs}. "
                f"Expected only: {sorted(characters_present)}"
            )
            
        missing_refs = sorted(characters_present - referenced_char_ids)
        # Note: only error if within limit, if truncated we logged warning during repair
        if missing_refs and len(refs) < 7:
            errors.append(
                f"[LF-cov] {shot_id}: characters_present has {sorted(characters_present)} but "
                f"reference_images only cover {sorted(referenced_char_ids)}. Missing: {missing_refs}"
            )

        # Validate prompt text coverage
        _validate_prompt_text_coverage(shot_id, entry, blueprint, spatial_map, errors)


def _validate_spatial_map(
    spatial_map: dict[str, Any], blueprint: dict[str, Any], errors: list[str]
) -> None:
    """For each shot in character_spatial_map: every characters_present char must be
    represented, with unique 0-based reference_index."""
    char_to_shots = _build_shot_lookup(blueprint)
    for shot_id, placements in spatial_map.items():
        if not isinstance(placements, list):
            errors.append(f"[SM] {shot_id}: character_spatial_map entry must be a list of placements.")
            continue
        shot = char_to_shots.get(shot_id)
        if not shot:
            continue
        characters_present = set(shot.get("characters_present") or [])

        mapped_char_ids: set[str] = set()
        ref_indices: set[int] = set()
        for p in placements:
            cid = p.get("character_id")
            if not cid:
                errors.append(f"[SM] {shot_id}: placement missing character_id: {p!r}")
                continue
            mapped_char_ids.add(cid)
            if cid not in characters_present:
                errors.append(
                    f"[SM-excl] {shot_id}: character_spatial_map references {cid} but it's "
                    f"not in characters_present ({sorted(characters_present)})."
                )
            ri = p.get("reference_index")
            if not isinstance(ri, int) or ri < 0:
                errors.append(f"[SM] {shot_id}: placement for {cid} has invalid reference_index: {ri!r}")
            elif ri in ref_indices:
                errors.append(f"[SM] {shot_id}: duplicate reference_index {ri} (chars: {cid}).")
            else:
                ref_indices.add(ri)
            for required_field in ("screen_position", "visual_identifier", "action"):
                if not p.get(required_field):
                    errors.append(f"[SM] {shot_id}: placement for {cid} missing '{required_field}'.")
        missing_chars = sorted(characters_present - mapped_char_ids)
        if missing_chars:
            errors.append(
                f"[SM-cov] {shot_id}: character_spatial_map omitted {missing_chars} (chars_present="
                f"{sorted(characters_present)}, mapped={sorted(mapped_char_ids)})."
            )


def _build_shot_lookup(blueprint: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map shot_id -> shot dict from a parsed blueprint."""
    result: dict[str, dict[str, Any]] = {}
    for scene in blueprint.get("scenes", []) or []:
        for shot in scene.get("shots", []) or []:
            sid = shot.get("shot_id")
            if sid:
                result[sid] = shot
    return result


def _validate_motion_prompts(
    motion_prompts: dict[str, Any], blueprint: dict[str, Any], errors: list[str]
) -> None:
    """Validate motion prompts:
    - If character_sounds is present, verify that keys (character IDs) are present in the shot's characters_present.
    """
    shot_lookup = _build_shot_lookup(blueprint)
    for shot_id, entry in motion_prompts.items():
        shot = shot_lookup.get(shot_id)
        if not shot:
            continue
        
        char_sounds = entry.get("character_sounds")
        if not char_sounds or not isinstance(char_sounds, dict):
            continue
            
        characters_present = set(shot.get("characters_present") or [])
        for char_id in char_sounds.keys():
            if char_id not in characters_present:
                errors.append(
                    f"[Motion-sound] {shot_id}: character '{char_id}' has planned sounds but is not in characters_present ({sorted(characters_present)})."
                )


def _validate_schemas(
    char_sheets: dict, ff_shots: dict, lf_shots: dict, motion: dict,
    spatial_map: dict = None, errors: list[str] = None,
) -> None:
    """Validate each namespace entry against its Pydantic schema (ISSUE-012)."""
    if errors is None:
        return
    try:
        from schemas.prompts import (
            CharacterSheetEntry,
            FFShotEntry,
            LFShotEntry,
            MotionPromptEntry,
            CharacterSpatialEntry,
        )
    except ImportError:
        return

    model_map = [
        (CharacterSheetEntry, char_sheets),
        (FFShotEntry, ff_shots),
        (LFShotEntry, lf_shots),
        (MotionPromptEntry, motion),
    ]
    for model, ns in model_map:
        for key, entry in (ns or {}).items():
            try:
                model(**entry)
            except Exception as e:
                errors.append(f"[SCHEMA] {model.__name__}/{key}: {e}")

    for shot_id, placements in (spatial_map or {}).items():
        if not isinstance(placements, list):
            errors.append(f"[SCHEMA] character_spatial_map/{shot_id}: value must be a list.")
            continue
        for i, placement in enumerate(placements):
            try:
                CharacterSpatialEntry(**placement)
            except Exception as e:
                errors.append(f"[SCHEMA] character_spatial_map/{shot_id}[{i}]: {e}")


async def validate_prompts(ctx: Context) -> None:
    """Cross-check reference_images vs characters_present; verify Grok Edit shapes; validate Pydantic schemas."""
    output_dir = ctx.state.get("output_dir")
    if not output_dir:
        return

    blueprint_path = os.path.join(output_dir, "director_visual_blueprint.json")
    prompts_path = os.path.join(output_dir, "prompts.json")
    if not os.path.exists(blueprint_path) or not os.path.exists(prompts_path):
        print("⚠️ [validate_prompts_node] Blueprint or prompts.json missing on disk; skipping.")
        return

    with open(blueprint_path, "r", encoding="utf-8") as f:
        blueprint = json.load(f)
    with open(prompts_path, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    errors: list[str] = []

    spatial_map = prompts.get("character_spatial_map", {})
    _validate_ff_shots(prompts.get("ff_shots", {}), blueprint, spatial_map, errors)
    _validate_lf_shots(prompts.get("lf_shots", {}), blueprint, spatial_map, errors)
    _validate_spatial_map(spatial_map, blueprint, errors)
    _validate_motion_prompts(prompts.get("motion_prompts", {}), blueprint, errors)
    _validate_schemas(
        prompts.get("character_sheets", {}),
        prompts.get("ff_shots", {}),
        prompts.get("lf_shots", {}),
        prompts.get("motion_prompts", {}),
        spatial_map=spatial_map,
        errors=errors,
    )

    if errors:
        print(f"⚠️ [validate_prompts_node] {len(errors)} validation issue(s):")
        for e in errors:
            print(f"   - {e}")
    else:
        print(f"✅ [validate_prompts_node] All cross-checks passed (Grok consistency, schema).")


validate_prompts_node = FunctionNode(func=validate_prompts, name="validate_prompts_node")
