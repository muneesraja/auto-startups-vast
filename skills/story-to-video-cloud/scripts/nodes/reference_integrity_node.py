import json
from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode
from ._json_util import clean_json_str


async def run_reference_integrity(ctx: Context) -> None:
    """Deterministic Reference Integrity Node.
    
    Verifies that for every shot, the character reference arrays strictly match
    the characters present in the blueprint. Automatically handles coverage gaps,
    removes excess references, deduplicates, and truncates to the 7 reference image limit
    for Grok Edit using spatial prominence maps.
    """
    # 1. Load blueprint to check characters_present
    blueprint_str = ctx.state.get("blueprint_json_content")
    if not blueprint_str:
        print("⚠️ [ReferenceIntegrity] blueprint_json_content not found in state. Skipping validation.")
        return
    
    blueprint = clean_json_str(blueprint_str) if isinstance(blueprint_str, str) else blueprint_str
    
    shot_chars = {}
    shot_continuations = {}
    shot_use_ff_ref = {}
    for scene in blueprint.get("scenes", []):
        for shot in scene.get("shots", []):
            shot_id = shot.get("shot_id")
            shot_chars[shot_id] = shot.get("characters_present", [])
            shot_continuations[shot_id] = shot.get("continuation_from_previous", False)
            shot_use_ff_ref[shot_id] = shot.get("use_ff_as_lf_reference", False)
            
    # 2. Load character spatial map to establish priority
    spatial_map_str = ctx.state.get("character_spatial_map_content")
    spatial_map = {}
    if spatial_map_str:
        parsed_sm = clean_json_str(spatial_map_str) if isinstance(spatial_map_str, str) else spatial_map_str
        if isinstance(parsed_sm, dict):
            spatial_map = parsed_sm.get("character_spatial_map", parsed_sm)
            
    def get_prioritized_chars(shot_id: str, present_chars: list[str]) -> list[str]:
        placements = spatial_map.get(shot_id, [])
        if not isinstance(placements, list):
            return present_chars
        valid_placements = [p for p in placements if isinstance(p, dict) and p.get("character_id") in present_chars]
        valid_placements.sort(key=lambda x: x.get("reference_index", 999))
        sorted_chars = [p["character_id"] for p in valid_placements]
        for c in present_chars:
            if c not in sorted_chars:
                sorted_chars.append(c)
        return sorted_chars

    # 3. Process First Frame (FF) prompts
    ff_prompts_raw = ctx.state.get("ff_prompts_content")
    if ff_prompts_raw:
        ff_data = clean_json_str(ff_prompts_raw) if isinstance(ff_prompts_raw, str) else ff_prompts_raw
        if isinstance(ff_data, dict):
            ff_shots = ff_data.get("ff_shots", ff_data)
            repaired = False
            for shot_id, entry in ff_shots.items():
                if not isinstance(entry, dict):
                    continue
                continuation = shot_continuations.get(shot_id, False)
                if continuation:
                    if entry.get("prompt_type") != "extracted_frame" or entry.get("prompt") is not None or entry.get("reference_images"):
                        entry["prompt_type"] = "extracted_frame"
                        entry["prompt"] = None
                        entry["reference_images"] = []
                        entry["status"] = "pending_wave_1"
                        repaired = True
                    continue
                    
                present_chars = shot_chars.get(shot_id, [])
                refs = entry.get("reference_images", [])
                if not isinstance(refs, list):
                    refs = []
                
                # Filter references down to character sheets of present characters
                valid_refs = []
                for ref in refs:
                    if not isinstance(ref, str):
                        continue
                    if ref.startswith("{{character_sheets.") and ref.endswith(".fal_image_url}}"):
                        char_id = ref.split(".")[1]
                        if char_id in present_chars and ref not in valid_refs:
                            valid_refs.append(ref)
                
                # Auto-inject missing character sheet references
                for cid in present_chars:
                    expected_ref = f"{{{{character_sheets.{cid}.fal_image_url}}}}"
                    if expected_ref not in valid_refs:
                        valid_refs.append(expected_ref)
                        repaired = True
                
                # Check for excess or duplicate removals
                if len(valid_refs) != len(refs):
                    repaired = True
                
                # Truncate to Grok's 7 reference limit (using spatial priority)
                if len(valid_refs) > 7:
                    sorted_chars = get_prioritized_chars(shot_id, present_chars)
                    valid_refs = [f"{{{{character_sheets.{cid}.fal_image_url}}}}" for cid in sorted_chars[:7]]
                    print(f"⚠️ [ReferenceIntegrity] FF shot {shot_id} exceeds 7 characters. Truncating reference list to top 7 by spatial prominence.")
                    repaired = True
                
                entry["reference_images"] = valid_refs
                entry["prompt_type"] = "grok_edit"
                
            if repaired or isinstance(ff_prompts_raw, str):
                ctx.state["ff_prompts_content"] = json.dumps(ff_data, indent=2, ensure_ascii=False)

    # 4. Process Last Frame (LF) prompts
    lf_prompts_raw = ctx.state.get("lf_prompts_content")
    if lf_prompts_raw:
        lf_data = clean_json_str(lf_prompts_raw) if isinstance(lf_prompts_raw, str) else lf_prompts_raw
        if isinstance(lf_data, dict):
            lf_shots = lf_data.get("lf_shots", lf_data)
            repaired = False
            for shot_id, entry in lf_shots.items():
                if not isinstance(entry, dict):
                    continue
                
                present_chars = shot_chars.get(shot_id, [])
                use_ff = True
                refs = entry.get("reference_images", [])
                if not isinstance(refs, list):
                    refs = []
                
                valid_refs = []
                ff_ref = f"{{{{ff_shots.{shot_id}.fal_image_url}}}}"
                if use_ff:
                    valid_refs.append(ff_ref)
                
                # Filter references down to character sheets of present characters
                for ref in refs:
                    if not isinstance(ref, str):
                        continue
                    if ref == ff_ref:
                        continue
                    if ref.startswith("{{character_sheets.") and ref.endswith(".fal_image_url}}"):
                        char_id = ref.split(".")[1]
                        if char_id in present_chars and ref not in valid_refs:
                            valid_refs.append(ref)
                
                # Auto-inject missing character sheet references
                for cid in present_chars:
                    expected_ref = f"{{{{character_sheets.{cid}.fal_image_url}}}}"
                    if expected_ref not in valid_refs:
                        valid_refs.append(expected_ref)
                        repaired = True
                
                # Check for duplicate/excess removals or re-ordering
                if len(valid_refs) != len(refs) or valid_refs != refs:
                    repaired = True
                
                # Truncate to 7 total reference limit (if FF reference is present, it takes slot 1)
                limit = 7
                if len(valid_refs) > limit:
                    sorted_chars = get_prioritized_chars(shot_id, present_chars)
                    valid_refs = [ff_ref] + [f"{{{{character_sheets.{cid}.fal_image_url}}}}" for cid in sorted_chars[:6]]
                    print(f"⚠️ [ReferenceIntegrity] LF shot {shot_id} exceeds {limit} references. Truncating reference list by spatial prominence.")
                    repaired = True
                
                entry["reference_images"] = valid_refs
                entry["prompt_type"] = "grok_edit"
                
            if repaired or isinstance(lf_prompts_raw, str):
                ctx.state["lf_prompts_content"] = json.dumps(lf_data, indent=2, ensure_ascii=False)


# ADK node definitions
reference_integrity_ff_node = FunctionNode(func=run_reference_integrity, name="reference_integrity_ff_node")
reference_integrity_lf_node = FunctionNode(func=run_reference_integrity, name="reference_integrity_lf_node")
