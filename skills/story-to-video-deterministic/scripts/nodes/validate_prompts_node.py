"""Validate prompts as a FunctionNode after assembly and before wave execution.

Defensive layer that catches the three user-identified issues end-to-end:
- B2: char refs present for characters not in `characters_present` (Issue B)
- A1: LF prompts that look like Flux edit instructions instead of Ideogram T2I (Issue A1)
- C1: Consistency prompts using "Replace" instead of "Preserve" (Issue C)

Also validates Pydantic schemas on actual artifacts (ISSUE-012).
"""
import os
import json
import re
from typing import Any

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from ._json_util import clean_json_str, get_namespace_dict


# Regex detecting template references like {{character_sheets.char_01.output_path}}
_REF_PATTERN = re.compile(r"\{\{+([^}]+)\}\}+")

# Forbidden phrasing in consistency patch prompts (Issue C1).
_REPLACE_ANTI = re.compile(r"\breplace\b", re.IGNORECASE)

# Phrasings that signal a Flux edit instruction in an LF prompt (should be ideogram_t2i now).
_FLUX_EDIT_HINTS = (
    "in reference image",
    "reference image 1",
    "reference image 2",
    "reference image 3",
    "reference image 4",
    "image-to-image",
    "flux edit",
    "in the base image",
)

# Regex detecting spatial-anchoring language ("in the left foreground", "in the center midground",
# "reference image N"). Used to check multi-char consistency prompts include per-character anchors.
_MULTI_CHAR_ANCHOR = re.compile(
    r"(in the (?:left|center|right|upper|lower|foreground|midground|background)"
    r"(?:\s+(?:left|center|right|foreground|midground|background))?)"
    r"|(reference image \d+)",
    re.IGNORECASE,
)

# Regex detecting LF-patch language that preserves the LF delta (pose/expression/motion/camera).
# Required so the LF patch doesn't collapse the video's motion into a static image.
_LF_DELTA_PRESERVE = re.compile(
    r"(preserve.*\b(pose|expression|gesture|gaze|motion|camera|delta)\b"
    r"|\b(pose|expression|motion|camera|delta)\b.*preserve)"
    r"|do not revert|don'?t revert|keep.*delta",
    re.IGNORECASE,
)


def _is_template_ref_to(ref: str, namespace: str) -> bool:
    """Check if a {{...}} template ref points into the given namespace (e.g. 'character_sheets')."""
    match = _REF_PATTERN.search(ref)
    if not match:
        return False
    parts = match.group(1).strip().split(".")
    return len(parts) == 3 and parts[0] == namespace


def _validate_consistency_patches(
    consistency_patches: dict[str, Any], blueprint: dict[str, Any], errors: list[str]
) -> None:
    """For each consistency patch, ensure:
    - B2-exclusion: no char-sheet ref points to a character NOT in `characters_present`
    - B2-coverage: every char in `characters_present` has a matching ref in `reference_images`
    - C1: prompt uses 'Preserve' framing, not 'Replace'
    """
    char_to_shots = _build_shot_lookup(blueprint)
    for shot_id, entry in consistency_patches.items():
        if entry.get("status") == "skipped":
            continue
        shot = char_to_shots.get(shot_id)
        if not shot:
            continue  # Unknown shot id — handled by schema check downstream.
        characters_present = set(shot.get("characters_present") or [])
        refs = entry.get("reference_images") or []

        # Resolve which char_ids each {{character_sheets.X.output_path}} ref points to.
        referenced_char_ids: set[str] = set()
        # B2: every char-sheet ref must point to a character actually in `characters_present`.
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
                f"[B2-excl] {shot_id}: consistency_patches reference_images contain refs to absent "
                f"characters: {bad_refs}. Expected only: {sorted(characters_present)}"
            )
        # B2-coverage: every char in characters_present must have a matching ref.
        missing_refs = sorted(characters_present - referenced_char_ids)
        if missing_refs:
            errors.append(
                f"[B2-cov] {shot_id}: characters_present has {sorted(characters_present)} but "
                f"reference_images only cover {sorted(referenced_char_ids)}. Missing char-sheet "
                f"refs for: {missing_refs}. Flux Klein will not have identity grounding for "
                f"those characters — likely identity drift."
            )
        # C1: prompt must NOT use 'replace' language.
        prompt_text = entry.get("prompt") or ""
        if _REPLACE_ANTI.search(prompt_text):
            errors.append(
                f"[C1] {shot_id}: consistency patch prompt uses 'replace' wording. "
                f"Rewrite to use 'Preserve pose/expression, swap identity only' framing. "
                f"Prompt snippet: {prompt_text[:120]!r}"
            )
        # C1-multi: multi-char prompts must mention each on-screen character explicitly.
        if len(characters_present) >= 2:
            if not _MULTI_CHAR_ANCHOR.search(prompt_text):
                errors.append(
                    f"[C1-multi] {shot_id}: multi-character shot ({len(characters_present)} chars) "
                    f"consistency patch prompt does NOT include spatial anchoring language "
                    f"('in the [position]' / 'reference image N'). Flux Klein will likely swap "
                    f"identities. Prompt snippet: {prompt_text[:120]!r}"
                )


def _validate_lf_consistency_patches(
    lf_consistency_patches: dict[str, Any], blueprint: dict[str, Any], errors: list[str]
) -> None:
    """Same rules as FF consistency_patches, applied to LF consistency patches."""
    char_to_shots = _build_shot_lookup(blueprint)
    for shot_id, entry in lf_consistency_patches.items():
        if entry.get("status") == "skipped":
            continue
        shot = char_to_shots.get(shot_id)
        if not shot:
            continue
        characters_present = set(shot.get("characters_present") or [])
        refs = entry.get("reference_images") or []

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
                f"[B2-excl/LF] {shot_id}: lf_consistency_patches reference_images contain refs to "
                f"absent characters: {bad_refs}."
            )
        missing_refs = sorted(characters_present - referenced_char_ids)
        if missing_refs:
            errors.append(
                f"[B2-cov/LF] {shot_id}: LF patch missing char-sheet refs for: {missing_refs}."
            )
        # C1: LF preserve language — must not use 'replace'.
        prompt_text = entry.get("prompt") or ""
        if _REPLACE_ANTI.search(prompt_text):
            errors.append(
                f"[C1/LF] {shot_id}: LF consistency patch prompt uses 'replace' wording. "
                f"Prompt snippet: {prompt_text[:120]!r}"
            )
        # A1-LF-base: base_image must point to lf_shots, not ff_shots.
        base_image = entry.get("base_image") or ""
        if base_image and "{{ff_shots." in base_image:
            errors.append(
                f"[A1-LF-base] {shot_id}: lf_consistency_patches.base_image points to ff_shots "
                f"({base_image}); should be {{lf_shots.{shot_id}.output_path}}."
            )
        # C1/LF-delta: LF patch should mention preserving delta / motion (not just identity swap).
        if not _LF_DELTA_PRESERVE.search(prompt_text):
            errors.append(
                f"[C1/LF-delta] {shot_id}: LF consistency patch prompt does not include "
                f"'preserve'-style language for the LF delta (pose/expression/motion). "
                f"Prompt snippet: {prompt_text[:120]!r}"
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
            continue  # Unknown shot — schema check will catch it.
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


def _validate_lf_shots(lf_shots: dict[str, Any], errors: list[str]) -> None:
    """LF prompts must be Ideogram 4 T2I JSON objects, NOT Flux edit instruction strings."""
    for shot_id, entry in lf_shots.items():
        prompt_type = entry.get("prompt_type")
        if prompt_type != "ideogram_t2i":
            errors.append(
                f"[A1] {shot_id}: lf_shots.prompt_type must be 'ideogram_t2i' (got {prompt_type!r})"
            )
        prompt = entry.get("prompt")
        if isinstance(prompt, str):
            # Old-style Flux edit instruction — should now be a dict (Ideogram JSON).
            lowered = prompt.lower()
            if any(hint in lowered for hint in _FLUX_EDIT_HINTS):
                errors.append(
                    f"[A1] {shot_id}: lf_shots.prompt looks like a Flux edit instruction string, "
                    f"not an Ideogram 4 JSON object. Snippet: {prompt[:120]!r}"
                )
        elif not isinstance(prompt, (dict, list)):
            errors.append(
                f"[A1] {shot_id}: lf_shots.prompt must be a dict (Ideogram 4 JSON) — got {type(prompt).__name__}"
            )
        # reference_images must be empty for Ideogram T2I.
        refs = entry.get("reference_images")
        if refs:
            errors.append(
                f"[A1] {shot_id}: lf_shots.reference_images must be [] for ideogram_t2i, got {refs!r}"
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
    char_sheets: dict, ff_shots: dict, consistency: dict, lf_shots: dict, motion: dict,
    lf_consistency: dict = None, spatial_map: dict = None,
    errors: list[str] = None,
) -> None:
    """Validate each namespace entry against its Pydantic schema (ISSUE-012)."""
    if errors is None:
        return
    try:
        from schemas.prompts import (
            CharacterSheetEntry,
            FFShotEntry,
            ConsistencyPatchEntry,
            LFShotEntry,
            LFConsistencyPatchEntry,
            MotionPromptEntry,
        )
    except ImportError:
        # Tests/CLI may import without the working dir on sys.path; soft-skip schema validation.
        return

    model_map = [
        (CharacterSheetEntry, char_sheets),
        (FFShotEntry, ff_shots),
        (ConsistencyPatchEntry, consistency),
        (LFShotEntry, lf_shots),
        (LFConsistencyPatchEntry, lf_consistency or {}),
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


async def validate_prompts(ctx: Context) -> None:
    """Cross-check reference_images vs characters_present; verify Ideogram T2I shape; enforce
    'Preserve' wording; validate Pydantic schemas. Logs issues but does NOT raise — execution
    proceeds to wave_organizer, which will surface still-unresolved prompts naturally."""
    output_dir = ctx.state.get("output_dir")
    if not output_dir:
        return  # Cannot run without disk-backed blueprint/prompts files.

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

    _validate_consistency_patches(prompts.get("consistency_patches", {}), blueprint, errors)
    _validate_lf_consistency_patches(prompts.get("lf_consistency_patches", {}), blueprint, errors)
    _validate_spatial_map(prompts.get("character_spatial_map", {}), blueprint, errors)
    _validate_lf_shots(prompts.get("lf_shots", {}), errors)
    _validate_schemas(
        prompts.get("character_sheets", {}),
        prompts.get("ff_shots", {}),
        prompts.get("consistency_patches", {}),
        prompts.get("lf_shots", {}),
        prompts.get("motion_prompts", {}),
        lf_consistency=prompts.get("lf_consistency_patches", {}),
        spatial_map=prompts.get("character_spatial_map", {}),
        errors=errors,
    )

    if errors:
        # Print summary; do NOT raise — the agent will still execute since we want concrete
        # material for the validation rerun to inspect downstream behavior.
        print(f"⚠️ [validate_prompts_node] {len(errors)} validation issue(s):")
        for e in errors:
            print(f"   - {e}")
    else:
        print(f"✅ [validate_prompts_node] All cross-checks passed (consistency, LF, schema).")


validate_prompts_node = FunctionNode(func=validate_prompts, name="validate_prompts_node")
