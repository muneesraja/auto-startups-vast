#!/usr/bin/env python3
"""
V3 Schema Validation Script for cinematic_prompt.json
"""

import sys
import json
import os

def validate_v3_schema(data):
    """
    Validate cinematic_prompt.json v3.0 schema.
    Returns a list of error strings. If empty, the schema is valid.
    """
    errors = []

    # 1. Required top-level fields
    required_toplevel = ["version", "pipeline", "models", "global", "characters", "director_plan"]
    for field in required_toplevel:
        if field not in data:
            errors.append(f"Missing top-level field: '{field}'")
            
    if errors:
        return errors  # Stop early if top-level structure is broken

    # Check version
    if data["version"] != "3.0":
        errors.append(f"Invalid version '{data['version']}', expected '3.0'")
    if data["pipeline"] != "cinematic-v2":
        errors.append(f"Invalid pipeline '{data['pipeline']}', expected 'cinematic-v2'")

    # 2. Characters checks
    characters = data["characters"]
    if not isinstance(characters, list):
        errors.append("'characters' must be an array/list")
        return errors

    char_ids = set()
    for idx, char in enumerate(characters):
        char_id = char.get("id")
        if not char_id:
            errors.append(f"Character at index {idx} is missing 'id'")
            continue
        if char_id in char_ids:
            errors.append(f"Duplicate character ID: '{char_id}'")
        char_ids.add(char_id)

        # 12. All character_sheet_prompt fields non-empty
        sheet_prompt = char.get("character_sheet_prompt")
        if not sheet_prompt or not sheet_prompt.strip():
            errors.append(f"Character '{char_id}' has empty 'character_sheet_prompt'")

    # Flatten all shots and build lookup maps
    director_plan = data["director_plan"]
    if not isinstance(director_plan, dict) or "scenes" not in director_plan:
        errors.append("'director_plan' must be an object with 'scenes'")
        return errors

    scenes = director_plan["scenes"]
    if not isinstance(scenes, list):
        errors.append("'scenes' must be a list")
        return errors

    max_continuous = data["global"].get("max_continuous_shots", 3)

    all_shots_by_prefix = {}
    
    # Pre-populate all shots for mapping lookup
    for s_idx, scene in enumerate(scenes):
        scene_id = scene.get("scene_id")
        if scene_id is None:
            errors.append(f"Scene at index {s_idx} is missing 'scene_id'")
            continue
        
        shots = scene.get("shots", [])
        for sh_idx, shot in enumerate(shots):
            shot_id = shot.get("shot_id")
            if shot_id is None:
                errors.append(f"Shot at index {sh_idx} in Scene {scene_id} is missing 'shot_id'")
                continue
            prefix = f"s{scene_id:02d}_sh{shot_id:02d}"
            all_shots_by_prefix[prefix] = shot

    # Now validate each shot in detail
    for s_idx, scene in enumerate(scenes):
        scene_id = scene.get("scene_id")
        if scene_id is None:
            continue
        
        shots = scene.get("shots", [])
        if not isinstance(shots, list):
            errors.append(f"Scene {scene_id} 'shots' must be a list")
            continue

        current_chain_len = 0

        for sh_idx, shot in enumerate(shots):
            shot_id = shot.get("shot_id")
            if shot_id is None:
                continue

            prefix = f"s{scene_id:02d}_sh{shot_id:02d}"
            
            # 3. characters_present references valid character IDs
            present = shot.get("characters_present", [])
            if not isinstance(present, list):
                errors.append(f"Shot {prefix} 'characters_present' must be a list")
            else:
                for cid in present:
                    if cid not in char_ids:
                        errors.append(f"Shot {prefix} references unregistered character ID: '{cid}'")

            # 4. continues_from references exist as valid shots
            continues_from = shot.get("continues_from")
            if continues_from:
                if continues_from not in all_shots_by_prefix:
                    errors.append(f"Shot {prefix} 'continues_from' refers to non-existent shot: '{continues_from}'")

            # 5. ff_source == "ideogram" requires non-null ff_prompt
            ff_source = shot.get("ff_source")
            ff_prompt = shot.get("ff_prompt")
            if ff_source == "ideogram":
                if not ff_prompt or not ff_prompt.strip():
                    errors.append(f"Shot {prefix} has 'ff_source: ideogram' but empty 'ff_prompt'")
            elif ff_source == "extracted_tail":
                # 6. ff_source == "extracted_tail" requires non-null continues_from
                if not continues_from:
                    errors.append(f"Shot {prefix} has 'ff_source: extracted_tail' but missing 'continues_from'")
            else:
                errors.append(f"Shot {prefix} has invalid 'ff_source': '{ff_source}'")

            # 7. lf_source matches valid enum values
            lf_source = shot.get("lf_source")
            valid_lf_sources = ["ideogram_fresh", "klein_from_ff", "klein_from_extracted_tail"]
            if lf_source not in valid_lf_sources:
                errors.append(f"Shot {prefix} has invalid 'lf_source': '{lf_source}'. Expected one of {valid_lf_sources}")

            # 9. First shot in each scene must be "start" or "##cut"
            continuity = shot.get("continuity", "start")
            if sh_idx == 0:
                if continuity not in ["start", "##cut"]:
                    errors.append(f"First shot {prefix} in Scene {scene_id} must have continuity 'start' or '##cut', got '{continuity}'")

            # 8. No chain longer than max_continuous_shots
            if continuity in ["start", "##cut"]:
                current_chain_len = 1
            elif continuity == "##continue":
                current_chain_len += 1
                if current_chain_len > max_continuous:
                    errors.append(f"Shot {prefix} exceeds max continuous shots limit of {max_continuous} (current chain length: {current_chain_len})")

            # 10. characters_present ordering matches ff_edit_instructions keys (if present)
            ff_edit = shot.get("ff_edit_instructions")
            if isinstance(ff_edit, dict):
                for cid in ff_edit.keys():
                    if cid not in present:
                        errors.append(f"Shot {prefix} has 'ff_edit_instructions' for '{cid}' but they are not in 'characters_present'")
                    if cid not in char_ids:
                        errors.append(f"Shot {prefix} 'ff_edit_instructions' references unregistered character ID: '{cid}'")

            # 11. motion_prompt length < 100 tokens (approx check using space splitting)
            motion_prompt = shot.get("motion_prompt", "")
            if motion_prompt:
                token_count = len(motion_prompt.split())
                if token_count >= 100:
                    errors.append(f"Shot {prefix} 'motion_prompt' has {token_count} words, which exceeds the FFLF 100-token limit: '{motion_prompt[:50]}...'")

    return errors

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 validate_schema.py <path_to_cinematic_prompt.json>")
        sys.exit(1)

    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' does not exist.")
        sys.exit(1)

    try:
        with open(filepath, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON syntax in '{filepath}': {e}")
        sys.exit(1)

    print(f"Validating '{filepath}' against cinematic pipeline V3 schema...")
    errors = validate_v3_schema(data)

    if errors:
        print("❌ Schema validation failed with the following errors:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("✅ Schema is fully valid! No errors found.")
        sys.exit(0)

if __name__ == "__main__":
    main()
