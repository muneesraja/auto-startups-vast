"""Validate prompts as a FunctionNode after assembly and before wave execution.

Flux-only architecture: validates that
- FF shots use `flux_klein_t2i` prompt_type, with char-sheet refs matching
  `characters_present` (B2-exclusion + B2-coverage, repurposed from
  consistency-patch checks).
- LF shots use `flux_klein_t2i` prompt_type, with the FF ref + char sheets
  in `reference_images`.
- Character spatial map covers all on-screen characters.
- Pydantic schemas on actual artifacts (ISSUE-012).

Validation logs issues but does NOT raise — execution proceeds to wave
executor, which surfaces still-unresolved prompts naturally.
"""
import os
import json
import re
from typing import Any

from google.adk import Context, Event
from google.adk.workflow import node

from ._json_util import clean_json_str, get_namespace_dict


# Regex detecting template references like {{character_sheets.char_01.output_path}}
_REF_PATTERN = re.compile(r"\{\{+([^}]+)\}\}+")


def _is_template_ref_to(ref: str, namespace: str) -> bool:
    """Check if a {{...}} template ref points into the given namespace (e.g. 'character_sheets')."""
    match = _REF_PATTERN.search(ref)
    if not match:
        return False
    parts = match.group(1).strip().split(".")
    return len(parts) == 3 and parts[0] == namespace


def _validate_ff_shots(
    ff_shots: dict[str, Any], blueprint: dict[str, Any], errors: list[str]
) -> None:
    """For each generated FF shot (prompt_type == 'flux_klein_t2i'), ensure:
    - prompt is a non-empty string
    - reference_images contains one ref per character in `characters_present`
    - no ref points to a character NOT in `characters_present` (B2-exclusion)
    - all chars in `characters_present` are referenced (B2-coverage)
    """
    char_to_shots = _build_shot_lookup(blueprint)
    for shot_id, entry in ff_shots.items():
        if entry.get("prompt_type") == "extracted_frame":
            continue  # Wave-2 continuation; refs not generated.
        shot = char_to_shots.get(shot_id)
        if not shot:
            continue
        characters_present = set(shot.get("characters_present") or [])
        prompt = entry.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            errors.append(
                f"[FF] {shot_id}: ff_shots.prompt must be a non-empty string "
                f"(got {type(prompt).__name__})"
            )
            continue
        refs = entry.get("reference_images") or []
        # B2: every char-sheet ref must point to a character actually in `characters_present`.
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
                f"[B2-excl/FF] {shot_id}: ff_shots.reference_images contain refs to absent "
                f"characters: {bad_refs}. Expected only: {sorted(characters_present)}"
            )
        # B2-coverage: every char in characters_present must have a matching ref.
        missing_refs = sorted(characters_present - referenced_char_ids)
        if missing_refs:
            errors.append(
                f"[B2-cov/FF] {shot_id}: characters_present has {sorted(characters_present)} but "
                f"reference_images only cover {sorted(referenced_char_ids)}. Missing char-sheet "
                f"refs for: {missing_refs}. Flux Klein will not have identity grounding for "
                f"those characters — likely identity drift."
            )


def _validate_lf_shots(
    lf_shots: dict[str, Any], blueprint: dict[str, Any], errors: list[str]
) -> None:
    """For each LF shot, ensure:
    - prompt_type == 'flux_klein_t2i'
    - prompt is a non-empty string
    - reference_images contains char sheets (one per chars_present) + the FF ref
    - the FF ref points to {{ff_shots.<this_shot>.output_path}}
    """
    char_to_shots = _build_shot_lookup(blueprint)
    for shot_id, entry in lf_shots.items():
        prompt_type = entry.get("prompt_type")
        if prompt_type != "flux_klein_t2i":
            errors.append(
                f"[LF-type] {shot_id}: lf_shots.prompt_type must be 'flux_klein_t2i' "
                f"(got {prompt_type!r})"
            )
            continue
        prompt = entry.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            errors.append(
                f"[LF-prompt] {shot_id}: lf_shots.prompt must be a non-empty string "
                f"(got {type(prompt).__name__})"
            )
            continue
        shot = char_to_shots.get(shot_id)
        if not shot:
            continue
        characters_present = set(shot.get("characters_present") or [])
        refs = entry.get("reference_images") or []

        # Must have at least one char-sheet ref per char in characters_present.
        referenced_char_ids: set[str] = set()
        for ref in refs:
            match = _REF_PATTERN.search(ref)
            if not match:
                continue
            parts = match.group(1).strip().split(".")
            if len(parts) == 3 and parts[0] == "character_sheets":
                referenced_char_ids.add(parts[1])
        missing = sorted(characters_present - referenced_char_ids)
        if missing:
            errors.append(
                f"[LF-ref-cov] {shot_id}: lf_shots.reference_images missing char-sheet refs "
                f"for: {missing}. characters_present={sorted(characters_present)}, "
                f"covered={sorted(referenced_char_ids)}."
            )
        # Must include the FF ref for this shot.
        expected_ff_ref = f"{{{{ff_shots.{shot_id}.output_path}}}}"
        has_ff_ref = any(
            isinstance(r, str) and r.strip() == expected_ff_ref for r in refs
        )
        if not has_ff_ref:
            errors.append(
                f"[LF-ff-ref] {shot_id}: lf_shots.reference_images must include "
                f"{expected_ff_ref} as the LAST entry."
            )


def _validate_spatial_map(
    spatial_map: dict[str, Any], blueprint: dict[str, Any], errors: list[str]
) -> None:
    """For each shot in character_spatial_map: every characters_present char must be
    represented, with unique 1-based reference_index."""
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
            if not isinstance(ri, int) or ri < 1:
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


def _validate_schemas(
    char_sheets: dict, ff_shots: dict, lf_shots: dict, motion: dict,
    spatial_map: dict = None,
    errors: list[str] = None,
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
            except Exception as e:  # noqa: BLE001
                errors.append(f"[SCHEMA] {model.__name__}/{key}: {e}")

    # character_spatial_map entries are lists of placements — validate each placement dict.
    try:
        from schemas.prompts import CharacterSpatialEntry
    except ImportError:
        return
    for shot_id, placements in (spatial_map or {}).items():
        if not isinstance(placements, list):
            errors.append(f"[SCHEMA] character_spatial_map/{shot_id}: value must be a list.")
            continue
        for i, placement in enumerate(placements):
            try:
                CharacterSpatialEntry(**placement)
            except Exception as e:  # noqa: BLE001
                errors.append(f"[SCHEMA] character_spatial_map/{shot_id}[{i}]: {e}")


@node
async def validate_prompts_node(ctx: Context) -> None:
    """Cross-check reference_images vs characters_present; verify prompt_type + format;
    validate Pydantic schemas. Logs issues but does NOT raise."""
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

    _validate_ff_shots(prompts.get("ff_shots", {}), blueprint, errors)
    _validate_lf_shots(prompts.get("lf_shots", {}), blueprint, errors)
    _validate_spatial_map(prompts.get("character_spatial_map", {}), blueprint, errors)
    _validate_schemas(
        prompts.get("character_sheets", {}),
        prompts.get("ff_shots", {}),
        prompts.get("lf_shots", {}),
        prompts.get("motion_prompts", {}),
        spatial_map=prompts.get("character_spatial_map", {}),
        errors=errors,
    )

    if errors:
        print(f"⚠️ [validate_prompts_node] {len(errors)} validation issue(s):")
        for e in errors:
            print(f"   - {e}")
    else:
        print(f"✅ [validate_prompts_node] All cross-checks passed (FF, LF, spatial map, schema).")
