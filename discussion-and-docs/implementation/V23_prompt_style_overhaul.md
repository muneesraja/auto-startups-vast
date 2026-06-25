# V23 — Prompt Style Overhaul (Tested-Prompt Alignment)

**Date:** 2026-06-24  
**Status:** Completed

## Overview

Overhauled all 5 prompt-generating system prompts to align with user-tested prompt styles that produce significantly better results with Grok Imagine and LTX 2.3. The key shift: from camera-jargon-heavy templates to natural descriptive prose with few-shot examples from real tested prompts.

Resolution stays at `1k` (1280x720 at 16:9). No changes to `fal_tools.py`.

## Implementation Details

### 1. Director Script Agent — [director_script.md](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/system_prompts/director_script.md)
- Added `## Prompt-Aware Scene Direction` section with 4 rules:
  1. Use concrete physical actions, not abstract cinematic language.
  2. Describe characters by key visual identifiers.
  3. Clearly separate start-state and end-state descriptions.
  4. Keep environment descriptions grounded and visual.
- Added a full example showing how a well-directed scene translates into FF, LF, and motion prompts.

### 2. Character Sheet Prompter — [character_sheet_prompter.md](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/system_prompts/character_sheet_prompter.md)
- Replaced generic template with tested turnaround-sheet structure: "Character turnaround sheet, [desc], [features], full body reference sheet. Show front view, 3/4 front view, side view, 3/4 back view, and back view..."
- Added the user's monkey example as a few-shot prompt.
- Removed rigid 30-80 word limit; replaced with "Aim for completeness over brevity."
- Removed "No keyword stuffing" rule — effective descriptive tags encouraged.

### 3. FF Shot Prompter — [ff_shot_prompter.md](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/system_prompts/ff_shot_prompter.md)
- Replaced `[CAMERA_FRAMING] of [CHARACTER]...` template with natural prose structure.
- Removed "The character must match the reference image exactly" suffix.
- Added 3 few-shot examples: 2 single-character (Scene 1, Scene 3 from Tested-prompts.md) + 1 multi-character (from Tested-prompts-multi-char.md).

### 4. LF Shot Prompter — [lf_shot_prompter.md](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/system_prompts/lf_shot_prompter.md)
- Replaced camera-jargon delta template with natural end-state prose structure.
- Removed camera movement jargon ("Camera panned slightly / zoomed in").
- Added 3 few-shot examples: 2 single-character (Scene 1 LF, Scene 2 LF) + 1 multi-character LF.
- Kept delta-type magnitude guidance, reframed as observable changes.

### 5. Motion Prompter — [motion_prompter.md](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/system_prompts/motion_prompter.md)
- Rewrote core rules: characters identified by name, full action arc as narrative prose, no re-describing static appearance.
- Replaced "KEEP PROMPTS BRIEF" with "Write 4-7 sentences covering the full action arc."
- Added 3 few-shot examples: vine swing (3s), discovery (4s), multi-character walking (4s).

## Verification

### Automated Tests
- `pytest skills/story-to-video-cloud/tests/test_reference_integrity.py` — **6/6 passed** ✅

### Manual Test Runs

#### Test Run 1 (Prompt Styling & Setup)
- **Command**: `python3 skills/story-to-video-cloud/main.py --story "Bamboo the panda and Momo the monkey are friends. They meet in the forest." --name "prompt_style_test" --dir "temp/prompt_style_test" --only-shots scene_01_shot_01 --skip-video --fresh`
- **Result**: Completed successfully in 572.6 seconds.
- **Verification Details**:
  - **Prompts Quality**: Character sheet prompts followed the turnaround layout, and FF/LF prompts used natural prose without camera jargon. Motion prompts are full narrative sequences (4-7 sentences) rather than short tags.
  - **Resolution/Aspect Ratio**: Kept at 1k (1280x720) at 16:9.

#### Test Run 2 (Video Generation & Continuation Shot 1.2)
- **Command**: `python3 skills/story-to-video-cloud/main.py --story "Bamboo the panda and Momo the monkey are friends. They meet in the forest." --name "prompt_style_test" --dir "temp/prompt_style_test" --only-shots scene_01_shot_01,scene_01_shot_02`
- **Setup & Bugfixes**:
  - Pointed the pipeline to a cloud ComfyUI server at `https://b35ggljr188b5o-8188.proxy.runpod.net` via `.env`.
  - Discovered that the template `ltx-23-flf2v.json` was in frontend format instead of API format, and the API format file `ltx-2.3-flf2v.json` had corrupted nodes (missing `class_type` for VideoCombine #43, Power Lora Loader #2107, and Display Any #2070:486). Corrected these node definitions, replaced the backslash model path separators for `unet_name` and `vae_name` to match the Unix server environment, and copied it over `ltx-23-flf2v.json`.
  - **Prompt Enhancer Disabled**: Set `"ENABLE PROMPT ENHANCER"` (node `2082`) value to `false` in the workflow template to ensure LTX 2.3 uses our clean, natural motion prompts without pre-baked prompt expansions interfering.
- **Result**: Completed successfully in 363.2 seconds.
- **Outputs Generated**:
  - Shot 1.1 Video: [scene_01_shot_01.mp4](file:///Users/pandismart/Documents/projects/auto-startups-vast/temp/prompt_style_test/videos/scene_01_shot_01.mp4) (1280x704, LTX multiple-of-32 constraint)
  - Shot 1.2 First Frame (Extracted): [scene_01_shot_02_ff.png](file:///Users/pandismart/Documents/projects/auto-startups-vast/temp/prompt_style_test/images/scene_01_shot_02_ff.png) (1280x704; extracted from last frame of Shot 1.1 video and uploaded to fal.ai CDN)
  - Shot 1.2 Last Frame (Generated): [scene_01_shot_02_lf.png](file:///Users/pandismart/Documents/projects/auto-startups-vast/temp/prompt_style_test/images/scene_01_shot_02_lf.png) (1280x720)
  - Shot 1.2 Video: [scene_01_shot_02.mp4](file:///Users/pandismart/Documents/projects/auto-startups-vast/temp/prompt_style_test/videos/scene_01_shot_02.mp4) (1280x704)
