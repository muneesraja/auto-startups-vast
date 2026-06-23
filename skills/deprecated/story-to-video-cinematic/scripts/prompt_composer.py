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
    """Build a director-style prompt for Last Frame (LF) derivation.
    
    Instructs Flux to introduce camera motion, environmental animations,
    and pose changes to avoid static videos while maintaining character likeness.
    """
    instruction = shot.get("lf_edit_instruction", "")
    motion_prompt = shot.get("motion_prompt", "").lower()
    cinematography = shot.get("cinematography_notes", "").lower()
    narrative = shot.get("narrative", "").lower()
    ff_prompt = shot.get("ff_prompt", "").lower()
    
    # 1. Determine camera movement directions
    camera_move = ""
    if "zoom in" in cinematography or "dolly in" in cinematography or "zoom in" in motion_prompt:
        camera_move = "Dolly in slightly closer to the subjects, changing the framing to be tighter."
    elif "zoom out" in cinematography or "dolly out" in cinematography or "zoom out" in motion_prompt:
        camera_move = "Dolly out further away, revealing more of the surrounding environment."
    elif "tracking" in cinematography or "pan" in cinematography or "chase" in narrative or "sprint" in narrative:
        camera_move = "Subtly pan and track the camera horizontally to follow the direction of motion."
    elif "low camera angle" in cinematography or "looking up" in cinematography:
        camera_move = "Slightly tilt the camera upwards from a low-angle perspective."
    elif "high angle" in cinematography or "looking down" in cinematography:
        camera_move = "Slightly tilt the camera downwards from a high-angle perspective."
    else:
        # Default fallback: subtle cinematic camera drift
        camera_move = "Introduce a subtle cinematic camera drift or slow panning movement."

    # 2. Determine environmental animation directives
    env_animations = []
    
    # Water check
    water_keywords = ["ocean", "sea", "river", "lake", "water", "waves", "cliff overlooking"]
    if any(k in ff_prompt or k in narrative or k in motion_prompt for k in water_keywords):
        env_animations.append("Water dynamics: If water, sea, or ocean is visible, show natural flowing motion, active waves, and gentle water ripples.")
        
    # Wind/Foliage check
    foliage_keywords = ["grass", "trees", "leaves", "meadow", "tall grass"]
    if any(k in ff_prompt or k in narrative or k in motion_prompt for k in foliage_keywords):
        env_animations.append("Foliage dynamics: Grass blades and leaves sway naturally in the wind to show wind direction.")

    # Dust/Particles check
    dust_keywords = ["dust", "skid", "halt", "slide"]
    if any(k in narrative or k in motion_prompt for k in dust_keywords):
        env_animations.append("Particle dynamics: Show a puff of dust kicked up from the ground shifting or dispersing.")

    # Clouds check
    cloud_keywords = ["clouds", "sky", "fog", "mist"]
    if any(k in ff_prompt or k in narrative or k in motion_prompt for k in cloud_keywords):
        env_animations.append("Atmospheric dynamics: Clouds and skies shift slightly in the background.")

    env_section = ""
    if env_animations:
        env_section = " " + " ".join(env_animations)

    # 3. Build the final structured director narration
    preservation = (
        f"Camera move: {camera_move}{env_section} "
        f"Likeness preservation: Keep character identity and core background elements identical, "
        f"but allow changes in poses, positions, and framing to reflect the camera motion. "
        f"Maintain the {global_style} art style throughout."
    )
    
    if instruction:
        return f"{instruction.strip()} {preservation}"
    return preservation
