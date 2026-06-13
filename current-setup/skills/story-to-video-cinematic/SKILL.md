---
name: story-to-video-cinematic
version: 3.0.0
description: "Turn story manifests into highly consistent cinematic videos using a 3-stage model chain: Ideogram 4 (T2I) for scene still generation and character sheets, Flux Klein 9B (I2I) for character consistency editing (edit pass), and LTX 2.3 FFLF Seed Hunter for video generation. Utilizes the batch-wave model to minimize GPU swaps."
triggers:
  - cinematic
  - cinematic pipeline
  - story-to-video-cinematic
  - ideogram-flux-klein-ltx
---

# v3.0.0 — Batch-Wave Cinematic Pipeline Release (2026-06-13)

This skill implements the **Batch-Wave Execution Model** which groups ComfyUI prompts to minimize model swaps (max 7 swaps regardless of story length) and introduces **Dynamic Multi-Character Flux Klein Editing** (1-4 character references per shot) along with the **V3 cinematic prompt schema**.

## Core Pipeline Architecture

```mermaid
graph TD
    A[Story Manifest] --> B["Phase 1: Agent composes cinematic_prompt.json v3"]
    B --> C["Wave 0: Ideogram 4 Character Sheets"]
    C --> D["Wave 1: Ideogram 4 Scene First Frames (FFs)"]
    D --> E["Wave 2: Flux Klein 9B EDIT (consistency + LF derivations)"]
    E --> F["Wave 3: LTX 2.3 FFLF Video Gen (Batch 1 - chain starts)"]
    F --> G["Waves 4 & 5: Klein edit + LTX FFLF (Continuation depth 1)"]
    G --> H["Waves 6 & 7: Klein edit + LTX FFLF (Continuation depth 2)"]
    H --> I["Stitch & Export Final Video"]
    
    style E fill:#ff9900,stroke:#333,color:#000
    style F fill:#00aa00,stroke:#333,color:#fff
```

---

## Batch-Wave Execution Model (7 GPU Swaps)

Instead of swapping models per shot (which causes `N * 3` swaps), the pipeline runs in waves:
* **Wave 0**: Generates all character sheets.
* **Wave 1**: Generates all chain_start/`##cut` First Frames (FFs) via Ideogram T2I.
* **Wave 2**: Performs character consistency edits on FFs + derives all Last Frames (LFs) from FFs via Flux Klein.
* **Wave 3**: Generates first batch of LTX FFLF videos (chain starts) + extracts tail frames.
* **Wave 4 & 5 (Continuation Depth 1)**: Derives LFs from tail frames (Klein) and renders continuation videos (LTX).
* **Wave 6 & 7 (Continuation Depth 2)**: Derives LFs and renders further continuation videos.

---

## Trigger

* User has a `story_manifest.json` and wants to produce a coherent animated film.
* User wants to use the V3 cinematic pipeline for superior character consistency and prompt alignment.

## Quick Start (Working CLI Invocation)

Always pass `--url` and `--auth` explicitly to the current ComfyUI instance.

```bash
cd <story_dir>
python3 current-setup/skills/story-to-video-cinematic/scripts/cinematic_orchestrator.py \
    --prompts cinematic_prompt.json \
    --url "https://<your-comfyui>.trycloudflare.com" \
    --auth "vastai:$(grep ^COMFYUI_AUTH /root/.hermes/.env | cut -d= -f2)" \
    --skip-existing 2>&1 | tee _orchestrator_run.log
```

---

## Worked Examples

We provide a comprehensive set of worked examples for every stage of the pipeline:

* **[01-director-decisions.md](file:///Users/muneesraja/projects/brainstorm/aurora/current-setup/skills/story-to-video-cinematic/examples/01-director-decisions.md)**: How the agent decides about `##cut` vs `##continue` and visual continuity.
* **[02-character-sheet-prompts.md](file:///Users/muneesraja/projects/brainstorm/aurora/current-setup/skills/story-to-video-cinematic/examples/02-character-sheet-prompts.md)**: Ideogram T2I character sheet prompt best practices.
* **[03-scene-ff-prompts.md](file:///Users/muneesraja/projects/brainstorm/aurora/current-setup/skills/story-to-video-cinematic/examples/03-scene-ff-prompts.md)**: Ideogram T2I scene still prompt formula.
* **[04-klein-edit-patterns.md](file:///Users/muneesraja/projects/brainstorm/aurora/current-setup/skills/story-to-video-cinematic/examples/04-klein-edit-patterns.md)**: Flux Klein edit patterns for single, multi-character, and LF derivation edits.
* **[05-motion-prompts.md](file:///Users/muneesraja/projects/brainstorm/aurora/current-setup/skills/story-to-video-cinematic/examples/05-motion-prompts.md)**: FFLF motion prompts and anti-jump-cut guidelines.
* **[06-full-story-dryrun-prompt.json](file:///Users/muneesraja/projects/brainstorm/aurora/current-setup/skills/story-to-video-cinematic/examples/06-full-story-dryrun-prompt.json)**: Fully valid V3 schema cinematic prompt file.
* **[06-full-story-dryrun.md](file:///Users/muneesraja/projects/brainstorm/aurora/current-setup/skills/story-to-video-cinematic/examples/06-full-story-dryrun.md)**: Detailed wave-by-wave execution walkthrough.
* **[07-continuity-chain-walkthrough.md](file:///Users/muneesraja/projects/brainstorm/aurora/current-setup/skills/story-to-video-cinematic/examples/07-continuity-chain-walkthrough.md)**: Step-by-step tail frame extraction logic.
* **[08-multi-character-scene.md](file:///Users/muneesraja/projects/brainstorm/aurora/current-setup/skills/story-to-video-cinematic/examples/08-multi-character-scene.md)**: Handling multi-character scenes and reference slot mapping.

---

## Reference Documentation

* **[Cinematic Prompt Schema v3.0](file:///Users/muneesraja/projects/brainstorm/aurora/current-setup/skills/story-to-video-cinematic/references/cinematic-prompt-schema.md)**: Schema documentation.
* **[Flux Klein Edit Cookbook](file:///Users/muneesraja/projects/brainstorm/aurora/current-setup/skills/story-to-video-cinematic/references/flux-klein-edit-prompt-cookbook.md)**: Multi-character prompts patterns.
* **[Pipeline Architecture v2](file:///Users/muneesraja/projects/brainstorm/aurora/current-setup/skills/story-to-video-cinematic/references/pipeline-architecture.md)**: Core wave architecture.
