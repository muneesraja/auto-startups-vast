---
name: story-to-video
version: 4.0.0
description: "Turn story manifests into scene images using agent-composed prompts (prompt.json) and config-driven workflow templates. Supports model swapping (Qwen, HiDream, etc.) without code changes. Covers character sheet generation, prompt composition, batch scene generation, and Gemini vision evaluation."
triggers:
  - story to video
  - generate scene images
  - story manifest
  - batch comfyui generation
  - story illustration
  - animate story
  - character reference sheets
  - prompt composition
---

# Story-to-Video Pipeline

Turn story manifests into illustrated scene images using agent-composed prompts and config-driven ComfyUI workflow templates.

## Trigger

- User has a `story_manifest.json` with characters and scenes
- User wants to illustrate a story or generate scene-by-scene images
- User wants to compose optimized prompts for a specific model
- User wants to swap image generation models without code changes

## Architecture

```
User story (high-level text)
        ↓
Phase 0: Expand story → manifest + generate character ref sheets (Gemini 2.5 Flash Image)
        ↓
Phase 0B: User approval gate — review character sheets, approve/reject per character
        ↓
story_manifest.json + approved character reference sheets
        ↓
Phase 1: Upload refs to ComfyUI + verify
        ↓
Phase 1.5: Agent composes prompt.json ← (reads manifest + prompting guide)
        ↓
prompt.json (agent-composed, model-optimized prompts per shot)
        ↓
Phase 2: generate_scene.py reads prompt.json → loads workflow template → ComfyUI
        ↓
                            Scene still images (1280×720)
        ↓
Phase 2.5: Evaluate & refine (Gemini 2.5 Flash vision, optional)
        ↓
Phase 3: Animate (LTX 2.3 I2V — FUTURE, in testing)
        ↓
                            Scene video clips → Final video
```

## Prerequisites

- ComfyUI instance running with Qwen Image Edit 2511 workflow + Cloudflare tunnel
- `google-genai` and `Pillow` Python packages (for Phase 0 character sheet generation): `pip install google-genai Pillow`
- Gemini API key in `.env` file (next to skill dir) — use paid tier for image generation (free tier `gemini-2.5-flash-image` quota is extremely limited)
- `.env.example` committed to git; `.env` gitignored with actual key
- **Character reference sheets** uploaded to the ComfyUI instance's input directory
- **Story manifest** (JSON) defining characters and scenes
- **cURL** for API calls (Python urllib is blocked by Cloudflare)

## Work Folder

**VPS work directory**: `/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video/`

This is the Syncthing-synced Obsidian vault directory on the GrowthLabs VPS. All generated assets, feedback JSONs, and story manifests live here — synced across devices via Syncthing.

## Output Paths

Default output directory: `/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video/`

Structure per story:
```
story-to-video/
├── {story-slug}/
│   ├── characters/       # Reference sheets (downloaded from ComfyUI)
│   ├── scenes/           # Generated scene images
│   ├── feedback/         # Evaluation JSON per iteration
│   ├── videos/           # Animated clips (Phase 3)
│   └── story_manifest.json
```

Override with `--output-dir` flag on `generate_scene.py`.

---

## Pipeline Phases & Instructions

The pipeline is split into distinct logical phases:

1. **[Phase 0 & 1: Expansion, Reference Sheets & Upload](references/phases/phase-0-story-expansion.md)**
   - Expand story to v2 manifest schema.
   - Generate neutral character reference sheets using Gemini.
   - Handle Phase 0B approval gate & neutrality checks.
   - Upload sheets to ComfyUI input directory.

2. **[Phase 1.5: Prompt Composition](references/phases/phase-1-prompt-composition.md)**
   - Compose target-model optimized prompts per shot.
   - Manage multi-reference limitations (e.g. max 4 characters for Flux).
   - Write `prompt.json` intermediate generation config.

3. **[Phase 2: Scene Generation & Phase 2.5: Evaluation Loop](references/phases/phase-2-generation.md)**
   - Use `generate_scene.py` to queue ComfyUI workflows.
   - Run the automated vision-based evaluate & refine loop.
   - Handle edge cases, parse errors, and score logging.

4. **[Phase 3: Animation](references/phases/phase-3-animation.md)**
   - Convert scene stills to videos using I2V models (LTX 2.3) in the future.
   - Write physical motion prompts.

---

## Reference Documentation

- **[Story Manifest Format (v2)](references/story-manifest-format.md)** - Full JSON schema for stories.
- **[prompt.json Schema](references/prompt-json-schema.md)** - Full JSON schema for prompt.json files.
- **[Facial Expression Vocabulary](references/facial-expression-vocabulary.md)** - Visual visual region descriptors.
- **Model Prompting Guides:**
  - **[Qwen Image Edit Prompting Guide](references/models/qwen-image-edit-prompting-guide.md)**
  - **[HiDream Prompting Guide](references/models/hidream-prompting-guide.md)**
  - **[Flux 2 Klein Prompting Guide](references/models/flux-2-klein-prompting-guide.md)**
  - **[LTX-I2V Prompting Guide](references/models/ltx-i2v-prompting-guide.md)**
- **[ComfyUI API Pitfalls](references/comfyui/api-pitfalls.md)** - Pitfalls & solutions for API execution.
- **[Improvements Roadmap](references/roadmap.md)** - Development checklist & tracking.

---

## Model Reference & Capabilities

### Multi-Reference Image Selection

| Model | Max References | Notes |
|---|---|---|
| Qwen Image Edit 2511 | 3 | Legacy template with static slot counts (pads to 3 by duplicating) |
| HiDream O1 Dev | 12 | Dynamic template (prunes unused slots when <4, spawns slots when >4 up to 12) |
| Flux 2 Klein 9B | 4 | Dynamic ReferenceLatent chain template (prunes when <2, spawns when >2 up to 4) |

### Available Workflow Templates

| Template | Model | Steps | Slots | Status |
|---|---|---|---|---|
| `qwen-image-edit-2511` | Qwen Image Edit 2511 + Lightning LoRA | 4 | 3 refs | ✅ Active |
| `hidream-o1-dev-i2i` | HiDream O1 Dev FP8 | 28 | 4 refs | ✅ Active |
| `flux-2-klein-image-edit` | Flux 2 Klein 9B FP8 | 4 | 2 refs | ✅ Active |

---

## Repository Symlink

**Single source of truth:** The repo path `~/repos/auto-startups-vast/current-setup/skills/story-to-video` is a **symlink** → `~/.hermes/skills/creative/story-to-video/`. All edits happen in the Hermes skill dir; the repo sees them via symlink. Never copy files back into the repo path — it's the same directory.
