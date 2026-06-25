# V28 — Baby and Dolphin Cloud Story Generation

## Status: Paused / Pipeline Debugged

This document tracks the execution of the `story-to-video-cloud` pipeline on the story **"The Baby, the Sea, and the Kind Dolphin"** located at `/Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin`.

---

## 1. Goal
Execute the cloud-integrated story-to-video pipeline which uses:
- Grok Imagine (via fal.ai API) for character sheets, backgrounds, and shot generation.
- LTX-2.3 (via ComfyUI) for First-to-Last Frame video generation.
- The story file: `/Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin/Story.md`.
- Output directory: `/Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin/` (outputs are placed directly alongside the story).

## 2. Completed Steps / Bug Resolution
1. **Identified MiniMax API Hang:**
   - The large visual blueprint prompt size (~150,000 characters) caused `openai/MiniMax-M3` requests to hang indefinitely on step 6 (`motion_prompter`).
2. **Integrated Native Gemini Fallback:**
   - Updated [config.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/config.py) to check for `GEMINI_API_KEY` and fall back to `gemini/gemini-2.5-flash` for reasoning, light, and validation models.
   - Tested Gemini via LiteLLM directly on the motion prompter payload; it successfully completed within **1m 38s** (compared to MiniMax which hung for over 30 minutes).
3. **Execution Interrupted:**
   - A dry run with `--fresh` was started to verify the entire pipeline with Gemini. It successfully generated the [Director_script.md](file:///Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin/Director_script.md) before the background tasks were stopped per the user's "Stop" request and server restart.

## 3. Next Steps
1. Re-run the dry-run pipeline with `run_and_debug.py` to regenerate the remaining prompts and layout JSONs (will be very fast now with Gemini).
2. Proceed with active media generation (character sheets, first/last frame images, and ComfyUI videos).
