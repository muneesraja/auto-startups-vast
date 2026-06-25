# V22 — Prompt Text Validation & Multi-Character Dry Run

**Date:** 2026-06-23  
**Status:** Completed  

## Overview

Implemented suggestions from the review (V21):
1. **Prompt-text validator**: Checks if all `characters_present` are described/mentioned in the prompt string (not just in `reference_images` array).
2. **Multi-character dry run**: Executed a 3-character end-to-end dry run to validate reference passing and validation checks.
3. **Character-Sheets-Only Mode**: Added support to stop after character sheet generation (Wave 1 `char_sheets` generated, subsequent steps and Wave 2 skipped).
4. **Shot-Filtering Mode**: Added support to run only targeted shots (`--only-shots`) and skip video generation (`--skip-video`).
5. **Grok Edit Fallback to T2I**: Added automatic fallback to Grok Text-to-Image when a first frame shot does not reference any characters, resolving API validation crashes.

## Implementation Details

### 1. Prompt-Text Character Coverage Check
- Implemented `_check_character_in_prompt` and `_validate_prompt_text_coverage` in [validate_prompts_node.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/scripts/nodes/validate_prompts_node.py).
- Performs a case-insensitive check for:
  - Character name (direct search).
  - Keywords from the character's appearance in the blueprint or `visual_identifier` in `character_spatial_map` (adjectives/stopwords filtered).
- Integration test with `capsys` added to [test_reference_integrity.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/tests/test_reference_integrity.py).

### 2. Shot-Filtering and Wave Execution Control
- Modified [main.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/main.py) to parse `--only-shots` and `--skip-video`.
- Modified [wave_nodes.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/scripts/nodes/wave_nodes.py) to forward these state flags to the runner.
- Modified [wave_executor_workflow.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/scripts/nodes/wave_executor_workflow.py) to:
  - Skip non-targeted shots or video nodes if filters are active.
  - Automatically fallback to standard Text-to-Image (`generate_grok_t2i`) when the references array is empty, which resolves the API error on empty edits (e.g. establishing shots with no characters).

## Verification

### Automated Tests
- Ran `pytest skills/story-to-video-cloud/tests/test_reference_integrity.py`.
- **Outcome**: `6 passed` (all tests passed, including `test_prompt_text_validation` and `test_validate_prompts_node_integration`).

### Multi-Character Dry Run
- Executed the dry run (`--stop-before-generation`) with 3 characters. Checked `prompts.json` in `temp/multi_char_test/` and confirmed correct references injected for multi-character shots.

### Character-Sheet-Only Generation Test
- Executed character sheet generation for Bamboo and Momo:
  - **Outcome**: Successfully saved `char_01_sheet.png` and `char_02_sheet.png` to disk. The new prompt-text coverage validator successfully flagged 7 omissions.

### Shot Image Generation Test (Scene 1 Shot 1)
- Executed:
  ```bash
  python3 skills/story-to-video-cloud/main.py --story "Bamboo the panda and Momo the monkey are friends. They meet in the forest." --name "char_sheet_test" --dir "temp/char_sheet_test" --only-shots scene_01_shot_01 --skip-video --fresh
  ```
- **Results**:
  - Successfully generated and downloaded the images for `scene_01_shot_01` (running within `task-428` and completing in 1092s):
    - **Character 1 Sheet**: [char_01_sheet.png](file:///Users/pandismart/Documents/projects/auto-startups-vast/temp/char_sheet_test/character_sheets/char_01_sheet.png) — **1280 x 720** (16:9)
    - **Character 2 Sheet**: [char_02_sheet.png](file:///Users/pandismart/Documents/projects/auto-startups-vast/temp/char_sheet_test/character_sheets/char_02_sheet.png) — **1280 x 720** (16:9)
    - **First Frame (FF)**: Handled by T2I fallback due to empty references.
      - Path: [scene_01_shot_01_ff.png](file:///Users/pandismart/Documents/projects/auto-startups-vast/temp/char_sheet_test/images/scene_01_shot_01_ff.png) — **1280 x 720** (16:9)
    - **Last Frame (LF)**: Generated using Grok Edit referencing the FF image.
      - Path: [scene_01_shot_01_lf.png](file:///Users/pandismart/Documents/projects/auto-startups-vast/temp/char_sheet_test/images/scene_01_shot_01_lf.png) — **1280 x 720** (16:9)
  - All other shots and video generations were successfully skipped, and the aspect ratio/resolution target was fully met.
