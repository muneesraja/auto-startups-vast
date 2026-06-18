# V18 — LTX Workflow Validation Fix & Retries Integration

**Date:** 2026-06-18  
**Status:** Interrupted (ComfyUI Tunnel Disconnected / HTTP 530)

---

## 1. Milestones Reached
- **LTX Workflow Correction:** Fixed static queue validation errors in `workflows/comfyui/ltx-23-fflf-seed-hunter.json`:
  1. Connected node `"model": ["5025:5153", 0]` to node `"5002:4828"` (`CFGGuider` in Stage 1 seed 1).
  2. Added a new `VAELoader` node `"5220"` for loading `LTX23_audio_vae_bf16.safetensors`.
  3. Connected the `"audio_vae"` input of node `"5050"` to the new loader.
- **Robust API & Upload Retries:** Updated [comfyui_tools.py](file:///Users/muneesraja/projects/brainstorm/aurora/skills/story-to-video-deterministic/tools/comfyui_tools.py) to incorporate up to 3 automatic retries with a 3-second delay on JSON parsing errors, empty responses, or connection drops, significantly reducing pipeline vulnerability to minor lags.
- **Verification of Validation:** Created and successfully executed a test script `test_ltx_workflow.py` which uploaded local keyframes, passed validation, and cleared the queue.
- **Resumed Video Generation Run:** Launched the deterministic pipeline for the **Leo** story. It correctly skipped all 100% pre-generated assets (Character Sheets, First Frames, Flux Consistency Patches, and Last Frames) and queued the first video `scene_01_shot_01` to the server.

## 2. Blockage Description
During the execution of the first video, the ComfyUI remote tunnel client disconnected. Requests to `https://trio-temporal-collar-comment.trycloudflare.com/` now fail with an **HTTP 530** (Site Temporary Unavailable / Cloudflare Tunnel Disconnected) error code.
As a result:
- The first video and subsequent uploads/queues could not complete.
- Wave 2 execution could not begin as preceding video files are missing.

## 3. Next Steps
1. Restart the ComfyUI server tunnel on the host system to restore connectivity.
2. Update the `.env` file with the new tunnel URL if the subdomain has changed.
3. Rerun the pipeline:
   ```bash
   bun run python3 -u main.py --story "/Users/muneesraja/Documents/growthlabs-vault/story-to-video-cinematic/Leo/Story.md" --name "leo_adventure"
   ```
   *Note: Because step status caching is preserved in `prompts.json`, the pipeline will immediately resume execution at the first video file without repeating prior stages.*
