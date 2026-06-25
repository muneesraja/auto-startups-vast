# V36 — Disable Prompt Enhancer & Resubmit Video Generation

Progress summary of disabling the prompt enhancer in LTX-2.3 video generation.

## Context & Objectives
To improve composition accuracy and respect the generated motion prompt descriptions precisely, we disabled the "ENABLE PROMPT ENHANCER" option in the ComfyUI LTX-2.3 FFLF workflow. The prompt enhancer (TextGenerateLTX2Prompt node in the workflow) was rewriting the detailed prompter prompts, which sometimes led to less distinct changes between frames or composition mismatches.

Objectives:
1. Turn off prompt enhancement in ComfyUI workflow files.
2. Clean up previously generated video files and reset their generation status.
3. Resume execution directly from the video generation nodes without restarting earlier steps.

## Implementation Details

### 1. Workflow Template Modification
- Modified both workflow JSON templates:
  - `workflows/comfyui/ltx-23-flf2v.json`
  - `workflows/comfyui/ltx-2.3-flf2v.json`
- Set `ENABLE PROMPT ENHANCER` (PrimitiveBoolean node `2082`) `"value"` to `false`.

### 2. Video Cleanup and Reset
- Deleted all partially generated `.mp4` video files under the output `videos/` folder.
- Modified `prompts.json` on disk to reset the status of `scene_01_shot_01` and `scene_01_shot_02` under `"motion_prompts"` to `"status": "pending"` and `"output_path": null` to trigger their re-generation.

### 3. Pipeline Execution
- Interrupted active ComfyUI server executions and cleared the pending queue to avoid conflicts.
- Started the pipeline without the `--fresh` flag:
  `PYTHONPATH=skills/story-to-video-cloud python3 skills/story-to-video-cloud/main.py ... --only-scenes "scene_01,scene_02"`
- Resumed directly at `wave_executor_node` and initiated `scene_01_shot_01_video` rendering.
