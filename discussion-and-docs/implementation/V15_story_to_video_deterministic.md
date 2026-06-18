# V15 — Story to Video Deterministic Skill Progress & Verification

**Date:** 2026-06-17  
**Status:** In Progress / Verifying  

---

## 1. Milestones Reached

We have successfully run and verified the core prompt generation pipeline (Steps 1–8) of the deterministic story-to-video pipeline:
- **Director Script generation (Step 1)** completed successfully.
- **Structural Blueprint (Step 2a)** and **Visual Blueprint (Step 2b)** parsing/enrichment succeeded.
- **Namespaced prompt generation (Steps 3–7)** successfully ran:
  - Character Sheets, First Frames (FF), Consistency Patches, Last Frames (LF), and Motion Prompts are all fully generated.
- **Pydantic Validation passed** on the generated `prompts.json` payload.
- **Wave Organizer (Step 8)** ran successfully, splitting the workload into `generator_wave_1.json` and `generator_wave_2.json`.

---

## 2. Issues Encountered & Resolved

### 2.1 File Writing in Main Script
- **Issue:** `main.py` did not write `Director_script.md`, `director_visual_blueprint_structure.json`, or `director_visual_blueprint.json` to the output folder.
- **Fix:** Added direct file-writing logic to `main.py` to output all generated blueprints from session state.

### 2.2 Motion Prompter JSON Parsing Error
- **Issue:** Step 7 `motion_prompter` using `gemini-2.5-flash` failed to output structured JSON properly (returned an incomplete `{"` string).
- **Fix:** 
  1. Switched `step7_motion_prompter.py` to use `REASONING_MODEL` (`gemini-3.1-pro-preview`) for high-fidelity reasoning.
  2. Modified the system prompt `system_prompts/motion_prompter.md` to remove format conflicts.
  3. Switched return instructions in `system_prompts/consistency_prompter.md` and `system_prompts/lf_shot_prompter.md` to avoid similar structured conflicts.

### 2.3 Silent Hang on Queue Failures
- **Issue:** If ComfyUI fails to queue a prompt, `prompt_id` is returned as `None` and the runner sleeps/hangs for up to 40 minutes.
- **Fix:** Added explicit `None` validation in `wait_for_prompt` inside [comfyui_tools.py](file:///Users/muneesraja/projects/brainstorm/aurora/skills/story-to-video-deterministic/tools/comfyui_tools.py) to raise a `ValueError` instantly.

---

## 3. Current Blockers

- **Stale ComfyUI URL:** The current ComfyUI URL in `.env` (`https://scholars-dominant-places-secret.trycloudflare.com`) is stale and cannot be resolved by DNS (tunnel expired). Localhost connection is also refused.
- **Action Required:** We need the user to provide the active/updated `COMFYUI_URL` to execute the image and video generation waves.

---

## 4. Next Steps
1. Obtain the updated `COMFYUI_URL` from the user.
2. Rerun the pipeline execution to generate character sheets, first frames, last frames, and compile the final LTX clips.
