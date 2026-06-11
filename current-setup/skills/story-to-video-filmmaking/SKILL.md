---
name: story-to-video-filmmaking
version: 1.0.0
description: "Turn story manifests into cinematic videos using agent-composed prompts (filmmaking_prompt.json) and config-driven workflow templates. Uses the LTX 2.3 FFLF (First Frame Last Frame) Seed Hunter multi-stage workflow, supporting smart frame generation, multi-roll seed hunting, spatial upscaling, motion quality evaluation, and seamless continuation chaining."
triggers:
  - filmmaking
  - FFLF pipeline
  - seed hunting
  - cinematic video
  - story filmmaking
---

# Story-to-Video-Filmmaking Pipeline

Turn story manifests into cinematic, high-fidelity videos using agent-composed prompts, smart frame generation, and the LTX 2.3 FFLF (First Frame Last Frame) Seed Hunter ComfyUI workflow.

## Trigger

- User has a `story_manifest.json` and wants to produce a coherent animated film.
- User wants to use the FFLF multi-stage seed-hunting pipeline for superior motion control and upscaling.
- User wants to establish continuity between consecutive shots in a scene.

## Architecture

```
User story (high-level text)
        ↓
Phase 0: Expand story → manifest + generate character ref sheets
        ↓
Phase 0B: User approval gate — review character sheets
        ↓
story_manifest.json + approved character reference sheets
        ↓
Phase 1: Upload refs to ComfyUI + verify
        ↓
Phase 1.5: Agent composes filmmaking_prompt.json
           ├── Per-shot: first_frame_prompt + last_frame_prompt + motion_prompt
           ├── Continuation chain metadata (auto-chain within scenes)
           └── Resolution preset + per-shot duration overrides
        ↓
Phase 2: Smart Frame Generation (Flux/Qwen via ComfyUI)
         ├── Continuation-aware: only generate images actually needed
         ├── Chain-start shots: generate both FF + LF (2 images)
         ├── Continuation shots: generate only LF (1 image, FF comes from prev video)
         ├── Independent shots: generate both FF + LF (2 images)
         └── Evaluate & refine loop per image + FF↔LF coherence check
        ↓
Phase 3: FFLF Seed Hunter Video Generation (multi-stage)
         ├── Stage 3A: Upload FF+LF images to ComfyUI
         ├── Stage 3B: Run 3× parallel Stage 1 seed hunting (low-res previews)
         ├── Stage 3C: Auto-select best motion quality (or --interactive)
         ├── Stage 3D: Stage 2 spatial upscale (selected seed)
         ├── Stage 3E: Stage 3 full-res render (1080p or 720p based on preset)
         └── Stage 3F: Download final video
        ↓
Phase 4: Shot Continuation & Stitching
         ├── Extract tail frames from completed clips (ffmpeg)
         ├── Feed as first frames for next-in-chain shots
         ├── Repeat Phase 3 for continuation segments
         └── Timeline overlap alignment metadata
        ↓
Phase 5: Post-Production Assembly Metadata
         └── Generate DaVinci Resolve / ffmpeg concat instructions
```

## Prerequisites

- ComfyUI instance running with the LTX 2.3 FFLF Seed Hunter workflow.
- **For Gemini character sheets** (default): `google-genai` and `Pillow` Python packages, Gemini API key in `.env` file.
- **For vision evaluation** (Phase 2.5/Gemini Motion Eval): `OPENROUTER_API_KEY` (Gemini 3.1 Flash Lite) or `GEMINI_API_KEY` in environment.
- **FFmpeg** installed on both the local machine and VPS for frame extraction and stitching.
- `.env` configured with necessary API keys.
- cURL for API communication.

## Work Folder

**VPS work directory**: `/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video-filmmaking/`

## Output Paths

Structure per story:
```
story-to-video-filmmaking/
├── {story-slug}/
│   ├── characters/       # Reference sheets
│   ├── scenes/           # Smart-generated frame images (FF and LF)
│   ├── feedback/         # Frame & coherence evaluation JSONs
│   ├── motion_eval/      # Previews and motion selection evaluations
│   ├── videos/           # Final rendered video segments
│   └── filmmaking_prompt.json
```

---

## Pipeline Phases & Instructions

The pipeline is split into distinct logical phases:

1. **[Phase 0 & 1: Expansion, Reference Sheets & Upload](references/phases/phase-0-story-expansion.md)**
   - Expand story to manifest schema.
   - Generate neutral character reference sheets.
   - Handle Phase 0B approval gate and upload to ComfyUI.

2. **[Phase 1.5: Filmmaking Prompt Composition](references/phases/phase-1-prompt-composition.md)**
   - Compose target-model optimized prompts per shot into `filmmaking_prompt.json`.
   - Setup continuation chains and flags.

3. **[Phase 2: Smart Frame Generation & Coherence Check](references/phases/phase-2-frame-generation.md)**
   - Check shot types (chain start vs continuation).
   - Generate only the required images (saving up to 31% of image gen API calls).
   - Evaluate FF ↔ LF coherence to verify motion compatibility before video generation.

4. **[Phase 3: FFLF Seed Hunter Video Generation](references/phases/phase-3-fflf-generation.md)**
   - Execute the 3-stage FFLF workflow.
   - Run multi-roll Stage 1 low-res previews.
   - Perform automated or interactive seed selection.
   - Render the selected seed at final resolution.

5. **[Phase 4: Shot Continuation](references/phases/phase-4-continuation.md)**
   - Extract tail frames from preceding video clips.
   - Feed tail frames directly as first frames to the next segment.

6. **[Phase 5: Post-Production Assembly](references/phases/phase-5-assembly.md)**
   - Stitch segments together using generated ffmpeg or DaVinci Resolve templates.

---

## Reference Documentation

- **[Filmmaking Prompt Schema](references/filmmaking-prompt-schema.md)** - Schema for `filmmaking_prompt.json`.
- **[LTX FFLF Prompting Guide](references/models/ltx-fflf-prompting-guide.md)** - Motion-focused prompting and Goldilocks guide.
- **[FFLF Custom Nodes Requirements](references/comfyui/fflf-custom-nodes.md)** - Custom node requirements for ComfyUI.
- **[Facial Expression Vocabulary](references/facial-expression-vocabulary.md)** - Visual region descriptors.
- **[ComfyUI API Pitfalls](references/comfyui/api-pitfalls.md)** - API execution tips.
- **[Story Manifest Format (v2)](references/story-manifest-format.md)** - Story JSON description.
