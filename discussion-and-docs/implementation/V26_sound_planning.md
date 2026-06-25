# V26 — Character Sound and Noise Planning

## Overview

This implementation plans character-specific sounds and noises (non-dialogue acoustic elements) alongside the motion prompt generation stage (Step 6) of the story-to-video-cloud pipeline.

## Target Architecture

1. **Schemas Update**:
   - `schemas/prompts.py` -> `MotionPromptEntry` gets `character_sounds: Optional[dict[str, list[str]]] = None`
   - `schemas/blueprint.py` -> `ShotMotion` gets `character_sounds: Optional[dict[str, list[str]]] = None`

2. **Prompt Planning**:
   - Update `system_prompts/motion_prompter.md` to establish rules and examples for sound/noise selection per character.
   - Update `agents/step6_motion_prompter.py` to prompt the LLM to output `character_sounds` mapped by character ID (e.g. `char_01`) containing the list of planned sounds.

3. **Validation**:
   - Update `scripts/nodes/validate_prompts_node.py` to ensure mapped characters in `character_sounds` are present in the shot.
   - Update schema and validation unit tests.
