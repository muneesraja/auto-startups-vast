# V31 — Baby and Dolphin Wave 1 Image Generation Run

## Status: Completed (Wave 1 Images Generated)

This document tracks the execution of the image generation phase of the `story-to-video-cloud` pipeline on the story **"The Baby, the Sea, and the Kind Dolphin"** (Scenes 1 & 2) located at `/Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin`.

---

## 1. Goal
Execute the image generation phase:
- Target: Character turnaround sheets, first-frame (FF) images, and last-frame (LF) images for Wave 1.
- Flag: `--skip-video` to generate only the images (Grok T2I and Grok Edit via fal.ai API) and skip ComfyUI video generation.

---

## 2. Command Run
```bash
python3 skills/story-to-video-cloud/main.py \
  --story "/Users/pandismart/Documents/projects/auto-startups-vast/stories/baby-and-dolphin/Story.md" \
  --name "baby-and-dolphin" \
  --dir "/Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin" \
  --only-scenes "scene_01,scene_02" \
  --skip-video
```

---

## 3. Progress Tracking
- **Character Sheets Generation (Grok T2I)**: COMPLETED
- **First Frame (FF) Images Generation (Grok Edit/T2I)**: COMPLETED
- **Last Frame (LF) Images Generation (Grok Edit)**: COMPLETED
- **Video Generation (LTX-2.3)**: SKIPPED (as requested)

---

## 4. Generated Artifacts
All generated assets are stored under `/Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin/`:
- **Character Sheets**:
  - `character_sheets/char_01_sheet.png` (Baby Boy turnaround reference sheet)
  - `character_sheets/char_02_sheet.png` (Friendly Dolphin turnaround reference sheet)
- **Scene 1 Shot Images (FF / LF)**:
  - `images/scene_01_shot_01_ff.png`, `lf.png`
  - `images/scene_01_shot_04_ff.png`, `lf.png`
  - `images/scene_01_shot_05_ff.png`, `lf.png`
- **Scene 2 Shot Images (FF / LF)**:
  - `images/scene_02_shot_01_ff.png`, `lf.png`
  - `images/scene_02_shot_03_ff.png`, `lf.png`
  - `images/scene_02_shot_04_ff.png`, `lf.png`
  - `images/scene_02_shot_05_ff.png`, `lf.png`
  - `images/scene_02_shot_06_ff.png`, `lf.png`

