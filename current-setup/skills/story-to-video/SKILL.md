---
name: story-to-video
version: 5.0.0
description: "Turn story manifests into scene images using agent-composed prompts (prompt.json) and config-driven workflow templates. Supports model swapping (Qwen, HiDream, etc.) without code changes. Covers character sheet generation (Gemini or ComfyUI T2I fallback), prompt composition, batch scene generation, and vision-based evaluation (OpenRouter Gemini 3.1 Flash Lite with thinking tokens, or Gemini API fallback)."
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
Phase 0: Expand story → manifest + generate character ref sheets
         ├─ Gemini 2.5 Flash Image (default, best quality)
         └─ ComfyUI T2I fallback (when Gemini credits unavailable)
            → Flux 2 Dev Turbo in T2I mode (0 references)
            → 1×4 layout: front, 3/4, side, back (single row)
            → I2I anchoring: use existing sheet as reference for consistency
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
Phase 2: Bulk queue all shots → poll for completion → download results
         (generate_scene.py OR bulk queue + poll script)
        ↓
                            Scene still images (1344×768)
        ↓
Phase 2.5: Evaluate & refine (OpenRouter Gemini 3.1 Flash Lite + thinking, or Gemini API fallback)
        ↓
Phase 3: Animate (LTX 2.3 Director - Keyframe I2V)
        ↓
                            Scene video clips → Final video
```

## Prerequisites

- ComfyUI instance running with target model workflow + Cloudflare tunnel
- **For Gemini character sheets** (default): `google-genai` and `Pillow` Python packages, Gemini API key in `.env` file (paid tier recommended)
- **For ComfyUI T2I character sheets** (fallback): Only needs a running ComfyUI instance — no Gemini API required
- **For vision evaluation** (Phase 2.5): `OPENROUTER_API_KEY` in environment (preferred, uses Gemini 3.1 Flash Lite with thinking tokens) or `GEMINI_API_KEY` (fallback)
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
   - Expand story to v3 manifest schema (with per-shot `characters_present`).
   - Generate neutral character reference sheets using Gemini.
   - Handle Phase 0B approval gate & neutrality checks.
   - Upload sheets to ComfyUI input directory.

2. **[Phase 1.5: Prompt Composition](references/phases/phase-1-prompt-composition.md)**
   - Compose target-model optimized prompts per shot.
   - Apply the **Mandatory Prompt Checklist** from the model's prompting guide (spatial positioning, body-anchoring, token budget, shot-level refs).
   - Manage multi-reference limitations (e.g. max 4 characters for Flux).
   - Write `prompt.json` intermediate generation config.

3. **[Phase 2: Scene Generation & Phase 2.5: Evaluation Loop](references/phases/phase-2-generation.md)**
   - Use `generate_scene.py` to queue ComfyUI workflows.
   - Run the automated vision-based evaluate & refine loop.
   - Handle edge cases, parse errors, and score logging.

4. **[Phase 3: Animation](references/phases/phase-3-animation.md)**
   - Convert scene stills to videos using the LTX 2.3 Image-to-Video (I2V) model.
   - Write physical motion prompts via `motion_prompt.json`.
   - Run `generate_video.py` to upload input images, build workflows, execute, and download animations.

---

## Reference Documentation

- **[Story Manifest Format (v2)](references/story-manifest-format.md)** - Full JSON schema for stories.
- **[prompt.json Schema](references/prompt-json-schema.md)** - Full JSON schema for prompt.json files.
- **[Facial Expression Vocabulary](references/facial-expression-vocabulary.md)** - Visual visual region descriptors.
- **Model Prompting Guides:**
  - **[Qwen Image Edit Prompting Guide](references/models/qwen-image-edit-prompting-guide.md)**
  - **[HiDream Prompting Guide](references/models/hidream-prompting-guide.md)**
  - **[Flux 2 Klein Prompting Guide](references/models/flux-2-klein-prompting-guide.md)**
  - **[Flux 2 Dev Turbo Prompting Guide](references/models/flux-2-dev-turbo-prompting-guide.md)**
  - **[LTX-I2V Prompting Guide](references/models/ltx-i2v-prompting-guide.md)**
  - **[LTX-Director Prompting Guide](references/models/ltx-director-prompting-guide.md)**
- **[ComfyUI API Pitfalls](references/comfyui/api-pitfalls.md)** - Pitfalls & solutions for API execution.
- **[Evaluation Pitfalls](references/eval-pitfalls.md)** - agy context contamination, Gemini CLI quirks, ComfyUI instance contamination.

---

## Vision Evaluation Providers

The evaluation pipeline supports multiple vision providers, selected via `--provider` flag or auto-detected from environment:

| Priority | Provider | Model | Flag | Env Var | Thinking |
|---|---|---|---|---|---|
| 1 (default) | OpenRouter | Gemini 3.1 Flash Lite | `--provider openrouter` | `OPENROUTER_API_KEY` | Medium (2K-4K tokens) |
| 2 | Gemini API | Gemini 2.5 Flash | `--provider gemini` | `GEMINI_API_KEY` | None |

**Auto-detection order:** `OPENROUTER_API_KEY` > `GEMINI_API_KEY`

### OpenRouter (Recommended)

Uses `google/gemini-3.1-flash-lite` via OpenRouter's OpenAI-compatible API with `reasoning.effort: "medium"` (~2K-4K thinking tokens). The model reasons through the image before scoring, improving evaluation accuracy (MMMU Pro: 76.8% vs 66.7% for Gemini 2.5 Flash).

**Key features:**
- Thinking chain captured in eval JSON (`reasoning` field) for debugging
- Thinking token count logged (`thinking_tokens` field)
- Reasoning output capped at 10K chars to prevent JSON bloat
- Automatic retry with exponential backoff on 429 rate limits

**Cost estimate:** ~$0.12 for 50 shots (input $0.25/M, output $1.50/M including thinking tokens)

### Face Structure Reference Fix

When the model doesn't apply face details from the character reference sheet (e.g., missing cream-colored face plate, wrong eye style), add an explicit `CRITICAL FACE DETAIL:` block in the prompt:

```
CRITICAL FACE DETAIL: [Character] has a [specific face structure description] on the front of their body —
this is a [color/texture] [shape] area where facial features sit.
Within this face plate: [eyes], [nose], [eyebrows], [mouth].
The rest of the body is [description].
```

**Why:** Flux 2 Dev Turbo's ReferenceLatent chain doesn't always extract fine face details. Explicit text forces correct rendering.

**When:** Eval feedback mentions face/feature mismatches but overall character shape and color are correct.

**Proven impact:** scene_005_shot002: 6.85→8.95, scene_007_shot002: 8.3→9.5

### Reference Image Evaluation

The evaluation pipeline now supports sending **reference images** alongside the generated image for visual comparison. This allows the model to verify character appearance against the reference sheets.

**How it works:**
- Generated image + up to 3 reference sheets = max 4 images per eval request
- Reference images are resolved from `prompt.json`'s `references` field
- The eval prompt instructs the model to compare against reference sheets
- Auto-detects `characters/` directory relative to `prompt.json` path

**CLI usage:**
```bash
# Auto-detect references from prompt.json location
python3 generate_scene.py --prompts prompt.json --evaluate-only --provider openrouter

# Explicit references directory
python3 generate_scene.py --prompts prompt.json --evaluate-only --references-dir /path/to/characters/
```

**Reference resolution:**
- `prompt.json` defines `references: ["puffy_reference_sheet_final.png", "jalapeno_reference_sheet_v4.png"]`
- Script resolves these to `{prompt.json_dir}/characters/{filename}`
- Missing references are warned but don't block evaluation

### Landscape/Environment Shots

For shots with no characters (landscape panoramas, environment close-ups):
- `character_accuracy` and `facial_expression` are set to `null` in the eval response
- `compute_weighted_score()` automatically excludes null categories from the weighted average
- This prevents false negatives where landscape shots score 0 for character-related categories

**Example:** `scene_001_shot002` (vanilla milk river close-up) has no characters — character_accuracy and facial_expression are excluded, so only scene_composition, action_depicted, and style_consistency contribute to the score.

### Regeneration Workflow

```bash
# 1. Regenerate failed shots with refined prompts
python3 regenerate_refined.py  # Uses eval JSON refined_prompt field

# 2. Re-evaluate the v2 images
python3 evaluate_scene.py --manifest story_manifest.json --scene X --shot Y --image scene_X_shotY_v2.png --provider openrouter
```

### Regeneration Best Practices (Critical)

**Rule: Use character reference sheets ONLY. Never send the previous failed generation as a ComfyUI reference.**

When a shot fails evaluation and needs regeneration, the temptation is to send the previous generated image back to ComfyUI so the model "improves" it. **This backfires.**

**What happens when you send the previous failed shot:**
- The model treats it as the "primary" composition to modify
- It replicates the same errors (missing characters, wrong composition, bad action)
- Character reference sheets get deprioritized — the scene image dominates the reference chain
- Score drops instead of improving

**Proven approach (scene_004_shot004: 6.93 → 9.60):**
1. Send **character reference sheets only** (from `prompt.json` `references` field)
2. Write a **stronger, more detailed prompt** that explicitly fixes the identified issues
3. Use **body-anchoring** to describe character positions and actions
4. Describe the **specific action/composition** the eval feedback said was missing

**Example — fixing missing action character:**
```
❌ Wrong: Send previous shot + character refs as ComfyUI refs
   → Score: 3.8 (previous shot's wrong composition dominates)

✅ Right: Character refs only + explicit prompt fix
   "Puffy (small round red bun, cream face plate, dot eyes) is the CENTRAL character
    bouncing through a formation of green chili soldiers, sending them flying..."
   → Score: 9.60
```

**When to use this approach:**
- Character is missing from the scene (reference contamination)
- Action/composition is wrong (model replicates the failed layout)
- Multiple characters but only one renders (previous shot had the wrong one)

**When the previous shot MIGHT work as reference:**
- Only for minor color/lighting tweaks where composition is correct
- Never when character presence or action is the issue

### CLI Usage

```bash
# Auto-detect provider (OpenRouter preferred)
python3 evaluate_scene.py --manifest story_manifest.json --all --scenes-dir ./scenes

# Force OpenRouter
python3 evaluate_scene.py --manifest story_manifest.json --all --provider openrouter

# Force Gemini API
python3 evaluate_scene.py --manifest story_manifest.json --all --provider gemini

# Single shot evaluation
python3 evaluate_scene.py --manifest story_manifest.json --scene 1 --shot 2 --image scene_001_shot002.png
```
- **[Improvements Roadmap](references/roadmap.md)** - Development checklist & tracking.

---

## Model Reference & Capabilities

### Multi-Reference Image Selection

| Model | Max References | Notes |
|---|---|---|
| Qwen Image Edit 2511 | 3 | Legacy template with static slot counts (pads to 3 by duplicating) |
| HiDream O1 Dev | 12 | Dynamic template (prunes unused slots when <4, spawns slots when >4 up to 12) |
| Flux 2 Klein 9B | 4 | Dynamic ReferenceLatent chain template (prunes when <2, spawns when >2 up to 4) |
| Flux 2 Dev Turbo | 4 | Dynamic single-chain ReferenceLatent (bypasses when 0, spawns when >1 up to 4) |

### Available Workflow Templates

| Template | Model | Steps | Slots | Status |
|---|---|---|---|---|
| `qwen-image-edit-2511` | Qwen Image Edit 2511 + Lightning LoRA | 4 | 3 refs | ✅ Active |
| `hidream-o1-dev-i2i` | HiDream O1 Dev FP8 | 28 | 4 refs | ✅ Active |
| `flux-2-klein-image-edit` | Flux 2 Klein 9B FP8 | 4 | 2 refs | ✅ Active |
| `flux-2-klein-t2i` | Flux 2 Klein 9B FP8 | 4 | 0 refs | ✅ Active |
| `flux-2-dev-turbo` | Flux 2 Dev Turbo FP8 | 8 | 1 ref (dynamic) | ✅ Active |
| `ltx-23-director` | LTX 2.3 Director | 8+4 (2-stage) | Keyframe I2V | ✅ Active (Primary) |
| `ltx-23-i2v-dev` | LTX 2.3 I2V FP8 | 11 | 1 ref (I2V) | ✅ Active (Legacy) |

---

## Repository Symlink

**Single source of truth:** The repo path `~/repos/auto-startups-vast/current-setup/skills/story-to-video` is a **symlink** → `~/.hermes/skills/creative/story-to-video/`. All edits happen in the Hermes skill dir; the repo sees them via symlink. Never copy files back into the repo path — it's the same directory.
