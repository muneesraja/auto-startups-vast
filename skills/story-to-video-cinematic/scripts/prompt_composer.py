#!/usr/bin/env python3
"""
Prompt Composer: I/O-free utility functions to compose prompts for character sheets,
first frame character edits, and last frame scene derivations.
"""

def compose_multi_character_edit_prompt(characters_present, char_lookup, global_style):
    """
    Auto-compose a Klein edit prompt for N characters.
    
    Reference image numbering:
      "reference image 1" = first character in characters_present
      "reference image 2" = second character
      etc.
    """
    if not characters_present:
        return f"Keep the background, lighting, composition, and overall scene identical. Maintain the {global_style} art style throughout."

    parts = []
    for i, char_id in enumerate(characters_present, start=1):
        char = char_lookup.get(char_id)
        if not char:
            continue
        desc = char.get("edit_prompt_descriptor", f"the {char_id}")
        parts.append(
            f"Make {desc} match the character from reference image {i} "
            f"exactly — same face, body, clothing, and proportions."
        )
    
    preservation = (
        "Keep the background, lighting, composition, and overall scene identical. "
        f"Maintain the {global_style} art style throughout."
    )
    
    return " ".join(parts) + " " + preservation


def build_ff_edit_prompt(shot, char_lookup, global_style):
    """Build concatenated FF edit instructions for characters present.
    
    Uses ff_edit_instructions overrides if present in shot JSON,
    otherwise auto-composes using compose_multi_character_edit_prompt-like wording.
    """
    instructions = []
    characters_present = shot.get("characters_present", [])
    ff_edit_instructions = shot.get("ff_edit_instructions") or {}

    for i, cid in enumerate(characters_present, start=1):
        if cid in ff_edit_instructions:
            instructions.append(ff_edit_instructions[cid])
        else:
            char = char_lookup.get(cid)
            if char:
                desc = char.get("edit_prompt_descriptor", cid)
                instructions.append(
                    f"Replace the {desc} in the scene with the character from reference image {i} exactly — "
                    f"same face, body, clothing, and proportions."
                )
    
    preservation = (
        "Keep the background, lighting, composition, and overall scene identical. "
        f"Maintain the {global_style} art style throughout."
    )
    return " ".join(instructions) + " " + preservation


def build_lf_derivation_prompt(shot, global_style):
    """Build LF edit prompt from shot's lf_edit_instruction + preservation suffix.
    
    Extracts the pattern from wave_2 and wave_n logic:
    shot["lf_edit_instruction"] + " Keep character identity and background identical. 
    Maintain the {global_style} art style throughout."
    """
    instruction = shot.get("lf_edit_instruction", "")
    preservation = (
        f"Keep character identity and background identical. "
        f"Maintain the {global_style} art style throughout."
    )
    if instruction:
        return f"{instruction.strip()} {preservation}"
    return preservation
