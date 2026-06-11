---
name: story-to-video-filmmaking
version: 1.1.0
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
Phase 1.5: Agent composes filmmaking_prompt.json  ← HEART OF THE PIPELINE
           ├── Per-shot: first_frame_prompt + last_frame_prompt + motion_prompt
           ├── lf_references: smart per-shot reasoning (new characters only)
           ├── lf_reference_note: required agent reasoning note per shot
           ├── Continuation chain metadata (auto-chain within scenes)
           └── Resolution preset + per-shot duration overrides
        ↓
filmmaking_orchestrator.py  ← PRIMARY ENTRY POINT
   For each continuation chain (recursive loop):
     ┌─ Phase 2 (image): Generate FF (char refs) + Generate LF (FF/tail anchor + lf_refs)
     ├─ Phase 3 (video): FFLF Seed Hunt → Stage 2 upscale → Stage 3 1080p render
     ├─ Phase 4 (extract): ffmpeg tail frame extraction
     └─ Repeat with tail frame as next shot's FF anchor
        ↓
Phase 5: Post-Production Assembly
         └── Generate ffmpeg concat or DaVinci Resolve stitching instructions
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

The pipeline is orchestrated by **`filmmaking_orchestrator.py`** which processes each continuation chain recursively (image gen → video gen → tail extract → repeat).

1. **[Phase 0 & 1: Expansion, Reference Sheets & Upload](references/phases/phase-0-story-expansion.md)**
   - Expand story to manifest schema.
   - Generate neutral character reference sheets.
   - Handle Phase 0B approval gate and upload to ComfyUI.

2. **[Phase 1.5: Filmmaking Prompt Composition](references/phases/phase-1-prompt-composition.md)**
   - Compose target-model optimized prompts per shot into `filmmaking_prompt.json`.
   - Decide `lf_references` per shot (agent reasoning: new characters only).
   - Write `lf_reference_note` per shot (required).
   - Setup continuation chains and shot-type flags.

3. **[Phase 2: Smart Frame Generation & Coherence Check](references/phases/phase-2-frame-generation.md)**
   - Called by orchestrator per-shot within each chain.
   - Generates FF (with character refs), then LF (with structural anchor + lf_refs).
   - Anchor = this shot's FF for chain_start/independent; tail frame for continuation/bridge.
   - Optional FF↔LF coherence evaluation.

4. **[Phase 3: FFLF Seed Hunter Video Generation](references/phases/phase-3-fflf-generation.md)**
   - Called by orchestrator immediately after Phase 2 for each shot.
   - Execute the 3-stage FFLF workflow.
   - Run multi-roll Stage 1 low-res previews.
   - Perform automated or interactive seed selection.
   - Render the selected seed at final resolution.

   > ⚠️ **Before running Phase 3, apply the template patches documented in [references/fflf-production-learnings.md](references/fflf-production-learnings.md).** The shipped `ltx-23-fflf-seed-hunter.json` template has 5 validation bugs (bare model paths, missing audio VAE, missing CFGGuider model, 0-indexed ImpactSwitch, wrong video output file) that will fail every queue until patched.

5. **[Phase 4: Shot Continuation](references/phases/phase-4-continuation.md)**
   - Called by orchestrator immediately after Phase 3 for each shot.
   - Extract tail frames from preceding video clips.
   - Feed tail frames as structural anchors to the next shot's LF generation.

6. **[Phase 5: Post-Production Assembly](references/phases/phase-5-assembly.md)**
   - Stitch segments together using generated ffmpeg or DaVinci Resolve templates.

---

## Reference Documentation

- **[Filmmaking Prompt Schema](references/filmmaking-prompt-schema.md)** - Schema for `filmmaking_prompt.json`.
- **[LTX FFLF Prompting Guide](references/models/ltx-fflf-prompting-guide.md)** - Motion-focused prompting and Goldilocks guide.
- **[FFLF Custom Nodes Requirements](references/comfyui/fflf-custom-nodes.md)** - Custom node requirements for ComfyUI.
- **[FFLF Production Run Learnings (2026-06-11)](references/fflf-production-learnings.md)** - ⚠️ **Required reading** — template patches for the shipped FFLF workflow, Vast.ai timing data, and download-pitfall notes.
- **[Facial Expression Vocabulary](references/facial-expression-vocabulary.md)** - Visual region descriptors.
- **[ComfyUI API Pitfalls](references/comfyui/api-pitfalls.md)** - API execution tips.
- **[Story Manifest Format (v2)](references/story-manifest-format.md)** - Story JSON description.
