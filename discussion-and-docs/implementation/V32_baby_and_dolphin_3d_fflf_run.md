# V32 — 3D Character Sheets & FFLF Default References Run

## Status: Completed (Wave 1 Images Generated with 3D Pixar Style & FFLF Default References)

This document tracks the execution and verification of the updated `story-to-video-cloud` pipeline on the story **"The Baby, the Sea, and the Kind Dolphin"** (Scenes 1 & 2) located at `/Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin`.

---

## 1. Goal
Modify and execute the cloud orchestration pipeline to:
1. Update character sheet prompts to generate a **3D computer-animated CGI Pixar-style** model turnaround sheet instead of 2D concept sheets.
2. Update last frame (LF) prompts to default to a **First-Frame, Last-Frame (FFLF)** edit style prompt template, with the corresponding First Frame (FF) image reference injected at index 0 of the references list.
3. Execute Wave 1 image generation (first/last frames + character sheets) while skipping videos.

---

## 2. Changes Implemented
- **Prompters**:
  - `skills/story-to-video-cloud/system_prompts/character_sheet_prompter.md`: Set default styling to 3D CGI Pixar style asset sheets.
  - `skills/story-to-video-cloud/system_prompts/lf_shot_prompter.md`: Formatted prompt template to use FFLF keyframe editing instructions.
- **Pipeline Nodes**:
  - `skills/story-to-video-cloud/scripts/nodes/reference_integrity_node.py`: Automatically injects the corresponding FF shot fal_image_url placeholder `{{ff_shots.<shot_id>.fal_image_url}}` at index 0 of reference images for all LF shots.
  - `skills/story-to-video-cloud/scripts/nodes/validate_prompts_node.py`: Added checks ensuring that for all LF shots, the FF image reference is present at index 0.

---

## 3. Command Run
The pipeline was resumed using the existing script artifacts on disk:
```bash
python3 skills/story-to-video-cloud/main.py \
  --story "/Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin/Story.md" \
  --name "baby-and-dolphin" \
  --dir "/Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin" \
  --only-scenes "scene_01,scene_02" \
  --skip-video
```

---

## 4. Verification & Results

### prompts.json Structure
- **Character Sheets**:
  - Prompt structure specifies: *"3D character model turnaround sheet, 3D computer-animated CGI... 3D CGI Pixar-style character model render..."*
- **LF Shot Prompts**:
  - Prompt prefix: *"I've attached the first frame as the reference image. Generate the last frame for an image-to-video FFLF (First frame, last frame) keyframe workflow..."*
  - Reference image lists: The FF reference `{{ff_shots.<shot_id>.fal_image_url}}` is at index 0.

### Generated Assets
- **Character Sheets** (regenerated with 3D Pixar styling):
  - `character_sheets/char_01_sheet.png`
  - `character_sheets/char_02_sheet.png`
- **First Frame (FF) & Last Frame (LF) Images** (newly generated for Wave 1 shots):
  - `images/scene_01_shot_01_ff.png`, `lf.png`
  - `images/scene_01_shot_04_ff.png`, `lf.png`
  - `images/scene_02_shot_01_ff.png`, `lf.png`
  - `images/scene_02_shot_04_ff.png`, `lf.png`
  - `images/scene_02_shot_07_ff.png`, `lf.png`
