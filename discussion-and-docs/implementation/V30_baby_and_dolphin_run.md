# V30 — Baby and Dolphin Scene 1 & 2 Run

## Status: Completed (Stopped Before Generation)

This document tracks the execution of the `story-to-video-cloud` pipeline on the story **"The Baby, the Sea, and the Kind Dolphin"** located at `/Users/pandismart/Documents/projects/auto-startups-vast/stories/baby-and-dolphin/Story.md`.

---

## 1. Goal
Execute the cloud-integrated story-to-video pipeline with:
- Story file: `/Users/pandismart/Documents/projects/auto-startups-vast/stories/baby-and-dolphin/Story.md`
- Name: `baby-and-dolphin`
- Output base: `/Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin`
- Limits: Scene 1 and Scene 2 only (`--only-scenes "scene_01,scene_02"`)
- Mode: `--stop-before-generation` (stops at wave organizer/prompts generation, before actual image/video API calls)
- Fresh: Resuming (NO `--fresh` flag, allowing `resume_router` to pick up existing blueprints and plans)

---

## 2. Command Run
```bash
python3 skills/story-to-video-cloud/main.py \
  --story "/Users/pandismart/Documents/projects/auto-startups-vast/stories/baby-and-dolphin/Story.md" \
  --name "baby-and-dolphin" \
  --dir "/Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin" \
  --only-scenes "scene_01,scene_02" \
  --stop-before-generation
```

---

## 3. Progress Tracking
- **Director Script**: COMPLETED
- **FF/LF Visual Plan**: COMPLETED
- **Blueprint Structure**: COMPLETED
- **Blueprint Visuals**: COMPLETED
- **Parallel Fan-out Steps**:
  - *Character Prompter*: COMPLETED
  - *Spatial Mapper & FF Shot Prompter*: COMPLETED
  - *LF Delta & LF Shot Prompter*: COMPLETED
  - *Motion Prompter*: COMPLETED
- **Prompts validation and organization**: COMPLETED

---

## 4. Generated Artifacts
All prompt planning and payloads are successfully stored under:
`/Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin/`
- `prompts.json` (Combined prompts payload)
- `character_spatial_map.json` (Character position composition mapping)
- `lf_delta_plan.json` (Movement/delta details)
- `generator_wave_1.json` (Wave 1 scheduling payload)
- `generator_wave_2.json` (Wave 2 scheduling payload)


