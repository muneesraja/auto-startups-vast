---
name: story-to-video-dynamic-agent-setup
version: 2.0.0
description: "Turn stories into highly consistent cinematic videos using Flux Klein 9B for all image generation and LTX-2.3 FLF2V for video — with reflexion-loop prompt engineering for the LF and motion prompters."
triggers:
  - flux-only
  - story-to-video-flux
  - story-to-video-dynamic-agent-setup
---

# v2.0.0 — Flux-Only Story-to-Video Pipeline (Dynamic Agent Setup)

This skill implements a Flux-only, deterministic story-to-video pipeline. All image generation goes through **Flux Klein 9B** (no Ideogram). Video generation uses **LTX-2.3 First-Last-Frame (FLF2V)**. The LF and motion prompters run as **reflexion loops** (Generator + Critic, max 3 cycles) for self-evaluation.

## Architecture Highlights

- **Single image model**: Flux Klein 9B handles character sheets (pure T2I), FF (with char refs), and LF (with char sheets + FF as refs).
- **No consistency patches**: the previous FF/LF consistency-patch phases (Flux Klein edit-mode) are removed — identity is anchored directly via reference images at FF and LF generation time.
- **No vision reviews**: with patches gone, the audit-mode vision-review phases are removed entirely.
- **Self-feedback loops**: the LF prompter and the motion prompter each run as an **ADK 2.0 dynamic `@node` workflow** (Generator + Critic, max 3 cycles). The critic checks 8 specific quality criteria; the loop exits early when the critic's response contains the `LF_PROMPTS_OK` / `MOTION_PROMPTS_OK` phrase.
- **LTX-2 prompting rules** (4 verbatim rules) are baked into the motion prompter's system prompt and checked against by the critic.
- **FLUX.2 multi-reference guidance** ("image N" anchoring) is baked into the FF and LF prompters.

## Orchestration Flow

1. **Director Script** (MiniMax-M3 via LiteLlm)
2. **Blueprint Structure** (MiniMax-M3)
3. **Blueprint Visuals** (MiniMax-M3)
4. **Character Sheet Prompter** (MiniMax-M2.7-highspeed)
5. **Character Spatial Mapper** (MiniMax-M2.7-highspeed)
6. **FF Shot Prompter** (MiniMax-M2.7-highspeed)
7. **LF Delta Planner** (MiniMax-M3)
8. **LF Prompter Loop** — dynamic `@node` workflow: Generator → Critic, max 3 cycles, exits on `LF_PROMPTS_OK`
9. **Motion Prompter Loop** — dynamic `@node` workflow: Generator → Critic, max 3 cycles, exits on `MOTION_PROMPTS_OK`
10. **Wave Organizer & Executor** (Pure Python, ComfyUI Job Runner)

## Wave 1 (Flux-only, no consistency patches)

```
character_sheets → ff → lf → video
```

Each phase uses Flux Klein 9B (FF/LF with refs) or LTX-2.3 FLF2V (video).

## Wave 2 (continuation chain)

```
extract_FF_from_prev_video → lf → video
```

## Reference Image Limits

- Flux Klein 9B: **max 4 reference images** (per FLUX.2 docs).
- FF refs: `{{character_sheets.X.output_path}}` for each char in `characters_present` (in `character_spatial_map` order).
- LF refs: char sheets (1..N) + `{{ff_shots.SHOT.output_path}}` (last entry).

## Usage

Run the pipeline programmatically or via python CLI by passing the story text:

```bash
python3 main.py --story "Your story content here" --name "story_output_dir_name"
```

### CLI flags

- `--fresh` — wipe pipeline-owned artifacts and re-run from scratch.
- `--stop-before-generation` — run prompt generation + wave organizer, then stop before any ComfyUI call (useful for prompt-only dry runs).
- `--dir <path>` — custom absolute output directory (default: `<DEFAULT_OUTPUT_BASE_DIR>/<name>`).

## Tests

```bash
python -m pytest tests/
```

Currently covers:
- Schema validation (Pydantic).
- LoopAgent construction (max_iterations=3, critic has exit_loop tool, etc.).