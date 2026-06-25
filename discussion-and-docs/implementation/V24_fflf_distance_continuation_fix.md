# V24 — Fix FF↔LF Visual Distance + Continuation Frame Quality

## Overview

This implementation resolves two key issues in the story-to-video pipeline:
1. **FF↔LF delta too small for 4-5s shots** — The LTX-2.3 video model was hallucinating visual artifacts because the visual distance between the First Frame (FF) and Last Frame (LF) was too small.
2. **Blurry continuation frames** — The extracted last frame of a video is degraded due to video compression artifacts, which caused subsequent continuation shots (which inherit this frame as their FF) to suffer from poor visual quality and propagation of degradation.

---

## Proposed & Implemented Solutions

### 1. Duration-Tiered Delta Constraints (System Prompts)
We replaced the single-tier delta taxonomy with a **duration-tiered** taxonomy, assigning distinct magnitude scales for different shot durations:
*   **2s shots (micro-delta)**: Subtle facial expression shifts or minor gestures. Camera is near-static.
*   **3s shots (small delta)**: One clear action (e.g., step forward, turn head). Position changes ≤20%.
*   **4-5s shots (large delta)**: Noticeably different pose/position (30-50% position shift), full-body reorientations, lighting/weather progression, or dense particle shifts. FF and LF must depict "two distinct moments in time".

This guidance has been written into:
*   [blueprint_visuals.md](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/system_prompts/blueprint_visuals.md) (L31-37)
*   [lf_delta_planner.md](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/system_prompts/lf_delta_planner.md) (L34-36)
*   [lf_shot_prompter.md](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/system_prompts/lf_shot_prompter.md) (L19-22) — added a 5-second establishing shot example.

### 2. Quality Restoration for Continuation Frames (Code Change)
We updated the Wave 2 sequential continuation chain in [wave_executor_workflow.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/scripts/nodes/wave_executor_workflow.py):
*   The raw frame extracted from the preceding video is now saved as `{shot_id}_ff_raw.png` and uploaded to the fal.ai CDN.
*   We use the preceding shot's LF prompt (from `prompts.json` key `lf_shots[prev_shot_id]["prompt"]`) and characters present in the shot (retrieved via `_get_chars_for_shot`) to gather character sheets.
*   We pass the raw frame (blurry reference) + character sheet URLs as reference images into `generate_grok_edit` with the preceding LF prompt.
*   The regenerated sharp frame is saved as the final `{shot_id}_ff.png` and uploaded.
*   **Fallback**: If the preceding LF prompt is missing or Grok Edit restoration fails for any reason, the pipeline falls back to using the raw extracted frame directly to guarantee execution robustness.

---

## Verification

### Automated Tests
Ran the pytest suite to verify no syntax errors or regressions were introduced:
```bash
pytest skills/story-to-video-cloud/tests/test_reference_integrity.py
```
**Status**: `6 passed` ✅
