# V17 — Story to Video Deterministic Skill Progress & Verification (Leo Story)

**Date:** 2026-06-18  
**Status:** In Progress (Wave 1 Execution Active - Resumed)

---

## 1. Milestones Reached
- **Queue Validation Error Resolution:** Diagnosed the `prompt_outputs_failed_validation` error. Found that the `ResolutionSelector` node on the ComfyUI server requires a `multiple` input parameter (which defaults to 8) that was missing from our local workflow templates. Patched the templates.
- **Dynamic Character Prompts Generation:** Discovered that secondary characters `char_02` (Mom), `char_03` (Bumblebee), and `char_04` (Blue Toy Spaceship) were referenced in the shot prompts but their character sheets were missing in `prompts.json`. Created a direct script `generate_missing_characters.py` using MiniMax to generate them and update `prompts.json` on disk.
- **Workflow Builder Resilience Fallback:** Handled cases where zero character reference images are provided (like `scene_01_shot_01` last frame) by adding a fallback inside `workflow_builder.py`. It dynamically falls back to the scene image as a placeholder for the character load node to prevent ComfyUI validation crashes.
- **Wave 1 Execution In-Progress (Resumed):** 
  - All four character sheets (`char_01_sheet.png`, `char_02_sheet.png`, `char_03_sheet.png`, `char_04_sheet.png`) successfully generated and saved.
  - First frames successfully generated and saved for all 26 Wave 1 shots.
  - Consistency Patches successfully generated and saved for all Wave 1 shots (including the patched `scene_03_shot_04` and `scene_04_shot_03` patches).
  - Last frames successfully generated and saved for `scene_01_shot_01` (utilizing the zero-character fallback) and most other shots.
  - Continuation shots (e.g. `scene_03_shot_02`, `scene_03_shot_03`, `scene_05_shot_02`, `scene_05_shot_03`) were successfully skipped in this step as expected.

## 2. In-Progress Action
We are running the deterministic generation pipeline for the **"Leo"** story:
```bash
python3 -u main.py --story "/Users/muneesraja/Documents/growthlabs-vault/story-to-video-cinematic/Leo/Story.md" --name "leo_adventure"
```

## 3. Next Steps
1. Monitor Wave 1 (Ideogram Character Sheets, First Frames, Flux Consistency Patches, Last Frames, and LTX Video Generation).
2. Execute Wave 2 (Continuation keyframing from video last frames).
3. Verify output assets inside `/Users/muneesraja/Documents/growthlabs-vault/story-to-video-deterministic/leo_adventure/`.
