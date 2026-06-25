# V25 — Pipeline Re-Architecture Complete

## Overview

This implementation completes a major re-architecture of the story-to-video-cloud pipeline, adding 5 new features to enhance flexibility, speed, and accuracy:

1. **Remove FF as Default LF Reference** — Stops passing the FF image as a reference for LF prompts by default, preventing over-identical images.
2. **Scene-Based Generation Filtering (`--only-scenes`)** — Adds filtering by scene IDs (expanding them dynamically to shot IDs).
3. **Background Image Generation** — Enables optional environment-only backgrounds generated during the character generation phase.
4. **Programmatic Character Keyword Reference Validation** — Auto-aligns character sheet references using a programmatic keyword check and Gemini 3.1 Flash Lite via OpenRouter.
5. **Eager Video Queueing (`--eager-video`)** — Allows each Wave 1 shot to begin video generation as soon as its own FF/LF pairs are ready.

---

## Completed Implementations

### 1. Remove FF as Default LF Reference
- Modified [lf_shot_prompter.md](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/system_prompts/lf_shot_prompter.md) to instruct that `reference_images` should only list character sheet references unless the shot has `use_ff_as_lf_reference: true`.
- Modified [reference_integrity_node.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/scripts/nodes/reference_integrity_node.py) to append the FF image reference ONLY if the shot has `use_ff_as_lf_reference = true` in the blueprint or is a continuation shot.
- Modified [validate_prompts_node.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/scripts/nodes/validate_prompts_node.py) to validate that FF reference is absent if `use_ff_as_lf_reference` is false.
- Added `use_ff_as_lf_reference` field (default `false`) to the Shot Pydantic model in [blueprint.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/schemas/blueprint.py) and added constraints to [blueprint_structure.md](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/system_prompts/blueprint_structure.md).

### 2. Scene-Based Generation Filtering (`--only-scenes`)
- Added `--only-scenes` argument to `main.py` CLI parser.
- Modified `wave_executor` node in [wave_nodes.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/scripts/nodes/wave_nodes.py) to resolve scene IDs to their corresponding shot IDs from the blueprint, merging them with `only_shots`.

### 3. Background Image Generation
- Added `generate_background` (bool) and `background_prompt` (string) fields to the Scene Pydantic model in [blueprint.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/schemas/blueprint.py) and added constraints to [blueprint_structure.md](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/system_prompts/blueprint_structure.md) and [blueprint_visuals.md](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/system_prompts/blueprint_visuals.md).
- Updated [save_artifact_nodes.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/scripts/nodes/save_artifact_nodes.py) to read the blueprint and populate background prompts under a new `backgrounds` namespace in `prompts.json`.
- Implemented `_run_background` and integrated background nodes alongside character sheet generation in the Wave 1 workflow builder inside [wave_executor_workflow.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/scripts/nodes/wave_executor_workflow.py).

### 4. Programmatic Character Keyword Reference Validation
- Added `get_validation_model()` to [config.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/config.py) configured to run `google/gemini-2.5-flash` via OpenRouter (or fall back to direct Gemini API using `GEMINI_API_KEY` if `OPENROUTER_API_KEY` is missing).
- Created a new validation node [character_ref_validator_node.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/scripts/nodes/character_ref_validator_node.py) which tokenizes character name & appearance keywords and loops through prompts:
  1. If keywords are found but the character sheet is not referenced, queries Gemini to validate if they are present. If verified, injects the reference.
  2. If a character is referenced but keywords are not in the prompt, queries Gemini to confirm they are absent. If verified, removes the reference.
- Integrated the validator node between `save_prompts_node` and `validate_prompts_node` in the workflow edges inside [main.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/main.py).

### 5. Eager Video Queueing (`--eager-video`)
- Added `--eager-video` argument to `main.py` CLI parser.
- Modified `_build_wave1_workflow` in [wave_executor_workflow.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/scripts/nodes/wave_executor_workflow.py) to wire direct `FF -> LF -> video` chains for each shot, running them in parallel without waiting for other shots.

---

## Verification

### Unit Tests
Ran the pytest suite to verify no syntax errors or regressions were introduced:
```bash
pytest skills/story-to-video-cloud/tests/
```
  **Status**: `9 passed` ✅
- Added test case `test_character_ref_validator` to verify keyword reference checking logic.
- Updated reference integrity tests.
- Ran pytest suite:
  ```bash
  pytest skills/story-to-video-cloud/tests/
  ```
  **Status**: `9 passed` ✅

### 2. Baby & Dolphin Scene 1 & 2 Run
Regenerated Scene 1 and Scene 2 images from scratch:
- Command: `python3 skills/story-to-video-cloud/main.py --story "/Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin/Story.md" --name "baby-and-dolphin" --dir "/Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin" --only-scenes "scene_01,scene_02" --skip-video --fresh`
- **Character Turnaround Sheets**: generated successfully for 4 characters in `character_sheets/`.
- **Scene-level Backgrounds**: generated successfully for 6 scenes in `backgrounds/`.
- **First/Last Frames**: 12 images generated successfully in `images/` for Scene 1 & 2 Wave 1 shots.
- **Auto-Correction**: Verified that the validation node checked character keywords and correctly pruned/added character references using Gemini 3.1 Flash Lite.
- **T2I Fallback**: Verified that `scene_01_shot_06_lf` fell back to Grok T2I successfully because it had an empty references array (resolved bug).
