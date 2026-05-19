---
name: story-to-video
version: 3.0.0
description: "Turn story manifests into scene images and video clips using ComfyUI (Qwen Image Edit) + LTX 2.3 I2V. Covers multi-reference image selection, batch scene generation, prompt composition from story manifests, and animation with image-to-video models."
triggers:
  - story to video
  - generate scene images
  - story manifest
  - batch comfyui generation
  - story illustration
  - animate story
  - character reference sheets
---

# Story-to-Video Pipeline

Turn story manifests into illustrated scene images (ComfyUI Qwen Image Edit) and animated video clips (LTX 2.3 I2V).

## Trigger

- User has a `story_manifest.json` with characters and scenes
- User wants to illustrate a story or generate scene-by-scene images
- User wants to go from text → still images → animated video
- Working with the Qwen Image Edit 2511 4-step workflow for character-consistent generation

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
Phase 2: Generate scene images (ComfyUI Qwen Image Edit 2511)
                          (+ smart per-scene character refs)
                                        ↓
                            Scene still images (1024×1024)
                                        ↓
Phase 2.5: Evaluate & refine (Gemini 2.5 Flash vision, optional)
                                        ↓
Phase 3: Animate (LTX 2.3 I2V motion prompts)
                                        ↓
                            Scene video clips → Final video
```

## Prerequisites

- ComfyUI instance running with Qwen Image Edit 2511 workflow + Cloudflare tunnel
- `google-genai` and `Pillow` Python packages (for Phase 0 character sheet generation): `pip install google-genai Pillow`
- Gemini API key in `.env` file (next to skill dir) — use paid tier for image generation (free tier `gemini-2.5-flash-image` quota is extremely limited: **daily limit can be 0 on free plan**)
- `.env.example` committed to git; `.env` gitignored with actual key
- **Character reference sheets** uploaded to the ComfyUI instance's input directory
- **Story manifest** (JSON) defining characters and scenes
- **cURL** for API calls (Python urllib is blocked by Cloudflare — see pitfall #8)

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

## Prerequisites for Phase 0

- **Gemini API key** — Must be in `.env` file (next to skill dir). Free tier `gemini-2.5-flash-image` (a.k.a. "nanobanana") quota is severely limited (daily limit can be 0). Use a paid tier key. See `.env.example` for format.
- **Python packages**: `pip install google-genai Pillow` — required by `generate_story_assets.py`. **No venv needed** — these work system-wide. The vast-ai skill tried venv but reverted due to "local environment incompatibilities" (commit `bbc53f6`). System-wide install is simpler and reliable for single-purpose scripts.
- **API key loading priority**: `.env` file → `GEMINI_API_KEY` env var → `--token` JSON path (subprocess doesn't load `.bashrc`)

| Package | Install | Used by |
|---|---|---|
| `google-genai` | `pip install google-genai` | `generate_story_assets.py` (Gemini image gen) |
| `Pillow` | `pip install Pillow` | `generate_story_assets.py` (image processing) |

**⚠️ GEMINI_API_KEY in subprocess:**
`.bashrc` exports are NOT sourced by non-interactive shells. If running scripts from a terminal subprocess, explicitly extract and export the key:
```bash
export GEMINI_API_KEY=$(grep GEMINI_API_KEY ~/.bashrc | head -1 | sed 's/.*="\([^"]*\)".*/\1/')
```
Otherwise the script silently gets an empty key → `API_KEY_INVALID` errors on all 3 retry attempts.

**⚠️ gemini-2.5-flash-preview-image daily quota:**
This model has a **separate** (and much stricter) free tier quota than `gemini-2.5-flash` (text/vision). The image generation free tier can hit daily limit = 0 even when text/vision works fine. If you see `429 RESOURCE_EXHAUSTED` with `limit: 0` for `gemini-2.5-flash-preview-image`, the daily quota is exhausted — wait for reset (midnight Pacific) or switch to a paid plan. More details in `references/gemini-image-gen-quotas.md`.

## Phase 0: Story Expansion & Character Sheet Generation

This phase takes a high-level user story and turns it into the assets needed for all subsequent phases.

### Step A — Research & Story → Manifest (v2)

**Before planning prompts, review the Qwen Image Edit community research:**
- `references/qwen-image-edit-prompting-guide.md` — includes Reddit community research (8 threads, 600+ comments: offset fixes, LoRA tradeoffs, multi-ref strategies, inpaint masking, max-quality workflow, 2509-vs-2511, face dataset tips, Chinese prompting)
- `references/reddit-scraping-patterns.md` — how to re-scrape Reddit if fresh research is needed (JSON API patterns, what works vs what doesn't)
- If the guide is stale (>30 days old), re-run Reddit research using the patterns in `references/reddit-scraping-patterns.md` and update the prompting guide

Then take the user's high-level story prompt and expand it into a full `story_manifest.json` (v2 schema) with:

- Characters (id, name, identity_spec, personality_traits)
- Scenes with **shots array** — each shot has description, facial_expression (per character), and optional camera_override
- `total_shots_budget` (default 50 for ~5 min story) and `total_duration_seconds` (default 300)
- Style directive (e.g., "children's book watercolor illustration")
- **Read `references/story-manifest-format.md` for the full v2 schema**
- **Read `references/facial-expression-vocabulary.md` for expression descriptors**
- **Read `references/qwen-image-edit-prompting-guide.md` for Qwen prompting best practices BEFORE writing prompts**

### Step B — Manifest → Character Reference Sheets

Automatically generate 7-view character reference sheets using **Gemini 2.5 Flash Image** (`gemini-2.5-flash-image`):

```bash
# Generate character sheets only
python3 generate_story_assets.py --manifest story_manifest.json --phase characters

# Force regeneration of existing sheets
python3 generate_story_assets.py --manifest story_manifest.json --phase characters --force
```

Each sheet shows: 4 body views (front, 3/4 left, right profile, back) + 3 face close-ups (front, 3/4 left, right profile) on a white background.

**⚠️ CRITICAL — Neutral Expressions Only:** Character reference sheets MUST show characters with **neutral/resting expressions**. If a reference sheet shows a character smiling, frowning, or showing any emotion, it will bias every downstream scene toward that expression — Qwen Image Edit uses reference sheets as anchors and will reproduce the sheet's expression regardless of the prompt. The evaluation check for `expression_neutrality >= 6` enforces this.

### Step C — Upload to ComfyUI

Upload generated sheets to the ComfyUI instance:

```bash
# Upload all character sheets
for f in characters/*_reference_sheet.png; do
  curl -X POST "$COMFY_URL/upload/image" -F "image=@$f" -F "overwrite=true"
done
```

> Future: add `--upload-url` flag to `generate_story_assets.py` so Step B + C happen in one command.

## Phase 0B: Character Sheet Approval Gate

Before proceeding to scene generation, **every character reference sheet must be approved by the user**. This prevents wasting GPU time on scenes built from bad reference sheets.

### Flow

```
Step B generates character sheets
        ↓
Step C uploads to ComfyUI
        ↓
Phase 0B: Display sheets to user for review
        ↓
User approves ✓ or rejects ✗ per character
        ↓
If rejected: regenerate specific characters, loop back to 0B
        ↓
All approved → proceed to Phase 1
```

### What Gets Reviewed

For each character, send to the user:
1. **The reference sheet image** (inline, so the user sees it immediately)
2. **Identity spec** from the manifest
3. **Evaluation scores** from Gemini (character_likeness, expression_neutrality, style_match, feature_visibility)

### Approval/Rejection

- **Approve per-character**: User says "Hare looks good" → mark Hare as approved
- **Reject per-character**: User says "Fox's eyes are wrong" or "Tortoise is smiling, needs neutral" → regenerate that specific character
- **Regenerate with feedback**: Pass the user's feedback as refinement instructions to the character sheet prompt
- **No proceeding without approval**: Do NOT start scene generation until ALL characters are approved

### Neutrality Check

The Gemini evaluation for character sheets checks `expression_neutrality` (0-10). If a sheet scores < 6, flag it for regeneration rather than asking the user — a non-neutral sheet will cause expression drift in all downstream scenes.

```
Auto-reject criteria (don't even show to user):
- expression_neutrality < 6 → regenerate with "neutral resting face, no emotion"
- character_likeness < 5 → regenerate with stronger identity spec
- style_match < 5 → regenerate with style more prominently in prompt
```

### Implementation

In script form:
```bash
# Evaluate all character sheets
python3 evaluate_scene.py --manifest story_manifest.json --phase characters

# Review results — auto-reject if expression_neutrality < 6
# Only show to user if all auto-reject criteria pass
```

In agent workflow:
1. After Step C (upload), run character sheet evaluation for each image
2. Auto-reject any sheet with expression_neutrality < 6 — regenerate immediately
3. For sheets that pass auto-check, display them to the user with:
   - Image (inline or attached)
   - Character name + identity spec
   - Evaluation scores
4. Ask user to approve or reject per character
5. If rejected, incorporate user feedback and regenerate only that character
6. Loop until all characters approved

## Phase 1: Upload & Verify Character Reference Sheets

If Phase 0 has already generated character sheets, this phase is simply upload + verify.

1. **Upload generated sheets** — Use the curl command from Phase 0 Step C, or upload manually:
   `curl -X POST "$COMFY_URL/upload/image" -F "image=@teddy_bear_reference_sheet.png" -F "overwrite=true"`
2. **Verify availability** — Check `/object_info/LoadImage` for the `image` input's enum list of available filenames
3. **If a ref is missing** — Either run Phase 0 Step B to generate it, or create a character sheet manually and upload

### Reference Sheet Prompt Template

```text
Create a professional character reference sheet for the following character.

Character: {identity_spec}

Layout:
- Top row: four full-body standing views (front, left 3/4 view, right side profile, back view)
- Bottom row: three face close-up portraits (front, left 3/4 angle, right side profile)

Requirements:
- CONSISTENT identity across ALL seven views - same face, same body, same outfit
- Clean white/neutral background
- Even studio lighting
- Style: {style}
- Each view clearly separated with space between them
- Character should be the same scale/proportion in each view
```

### Auto-Verify & Fallback

Always verify reference images exist on the instance before queuing. If a character's ref is missing:

```bash
# Check available images
curl -s "$COMFY_URL/object_info/LoadImage" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for img in data['LoadImage']['input']['required']['image'][0]: print(f'  - {img}')
"
```

Define fallbacks in the script config (e.g., fox missing → tortoise as similar woodland character).

## Phase 2: Generate Scene Images

### Using the Script

```bash
# Generate a single scene from a story manifest
python3 generate_scene.py --manifest story_manifest.json --scene 1 --seed 42

# Generate all scenes
python3 generate_scene.py --manifest story_manifest.json --all

# Override ComfyUI URL and output directory
python3 generate_scene.py --manifest story_manifest.json --all \
  --url https://mandi-qwen.muneesraja.com \
  --output-dir /root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video/hare-and-tortoise
```

### Multi-Reference Image Selection

The Qwen Image Edit workflow takes exactly **3 reference images**. Stories often have 1-5 characters per scene.

**Auto-mapping (convention-based):** The `pick_images()` function auto-derives the character→filename mapping using the `{character_id}_reference_sheet.png` naming convention (matching `generate_story_assets.py` output). This means ANY new story works without editing `DEFAULT_REF_IMAGES`. The `build_ref_mapping()` function checks available images on the instance and matches them to character IDs from the manifest automatically.

**Rules:**
1. Auto-map character IDs to `{character_id}_reference_sheet.png` using `build_ref_mapping()` (works for any story)
2. If auto-map misses (naming mismatch), fall back to hardcoded `DEFAULT_REF_IMAGES` (backward compat for hare-and-tortoise)
3. If a character's ref is still missing from the instance, fall back to the closest available character (e.g., fox → tortoise as similar woodland character) via `DEFAULT_FALLBACKS`
4. If no fallback defined, use `example.png` as last resort
5. Deduplicate — don't pass the same image twice (wastes a slot)
6. If fewer than 3 unique refs, fill remaining slots by duplicating the first ref
7. Never pass more than 3 images — the workflow enforces this

**⚠️ Pitfall:** If all refs fall back to `example.png`, the auto-mapping is failing. This originally happened because `DEFAULT_REF_IMAGES` was hardcoded for hare-and-tortoise only. The `build_ref_mapping()` fix (v2.2) resolved this by deriving mappings from the naming convention dynamically.

| Characters in Scene | Image Assignment | Rationale |
|---|---|---|
| 1 | [ref, ref, ref] | Duplicate to fill 3 slots |
| 2 | [ref1, ref2, ref1] | Fill 3rd slot with most important char |
| 3 | [ref1, ref2, ref3] | Perfect fit |
| 4+ | [ref1, ref2, ref3] | Pick top 3 by visual importance |

### Scene Prompt Composition (v2)

Each **shot** prompt combines: **Characters (with expressions) + Setting + Action + Mood + Camera + Style**

```text
Characters in this scene must match the provided reference images exactly:
- {name}: {identity_spec}. Expression: {facial_expression[character_id]}

Scene setting: {setting}.
Action: {shot.description}.
Mood: {scene.mood}.
Camera: {shot.camera_override or scene.camera}.
Style: {style}.
```

**Key changes from v1:**
- `facial_expression` is now **required per shot** — describe mouth + eyes + brow for each character
- `mood` replaces `emotion` — set at scene level, expressions are per-shot
- `camera_override` allows per-shot camera angles
- See `references/qwen-image-edit-prompting-guide.md` for expression best practices
- See `references/facial-expression-vocabulary.md` for approved expression descriptors

**Tips:**
- For scenes with many characters (3+), use abbreviated identity specs (key features only) to keep prompts within limits
- **Always include expressions** — even abbreviated prompts must have expressions
- Always include "must match the provided reference images exactly" — this anchors the model to reference consistency
- The style should match the reference sheet style for consistency
- Put expression descriptions BEFORE action in the prompt for better adherence

### Generation Timing

- **Per scene**: ~20-30 seconds on RTX 3090 (4-step Lightning)
- **6 scenes**: ~3 minutes total (sequential)
- **Prompt queue**: instant
- **Polling**: 5-second intervals recommended

## Phase 3: Animate Scenes (LTX 2.3 I2V)

> Requires `ltx23-video-gen` skill for RunPod provisioning.

### Motion Prompt Format

Motion prompts describe **movement**, not the still image. They should:
- Start with what the main character does (verb-first)
- Include secondary motions (crowd reactions, environmental movement)
- Note camera motion (dolly, track, hold)
- NOT re-describe the scene appearance (the I2V model sees the input image)

```text
{character_1} {primary_action} while {character_2} {secondary_action}. 
{environmental_motion}. The camera {camera_motion}.
```

Example (from hare-and-tortoise):
```text
Hare jolts upright, ears snapping high as he fumbles for the gold watch on his wrist. 
His eyes widen, his mouth falls open, and he twists toward the finish line with a sharp inhale. 
Long shadows stretch farther across the path as leaves tremble in a cooler breeze. 
The camera pushes in from a medium close-up to a tighter view as panic takes over his face.
```

### Motion Prompt Source

The `story_manifest.json` `action` field describes what happens — convert it to motion-focused text:
1. Remove all visual description (the I2V model sees the input image)
2. Convert actions to present-tense verbs with physical detail
3. Add camera motion that matches the `camera` field from the manifest
4. Keep it concise (~3-4 sentences max)

## ComfyUI API Pitfalls (CRITICAL)

These all caused real failures during testing. Read carefully.

### 1. Model File Paths Need Prefixes
- CLIPLoader: `split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors` (NOT bare filename)
- VAELoader: `split_files/vae/qwen_image_vae.safetensors` (NOT bare filename)
- UNETLoader: `qwen_image_edit_2511_fp8_e4m3fn.safetensors` (no prefix needed)

### 2. ImageResizeKJv2 Input Names Are Non-Obvious
- `upscale_method` (NOT `interpolation`): `nearest-exact, bilinear, area, bicubic, lanczos, nvidia_rtx_vsr`
- `keep_proportion` (NOT `resize_mode`): `stretch, resize, pad, pad_edge, pad_edge_pixel, crop, pillarbox_blur, total_pixels`
- `pad_color` (NOT `fill_color` or `fill_color2`): `"0, 0, 0"` format

### 3. FluxKontextMultiReferenceLatentMethod Key Name
- `reference_latents_method` (NOT `mode`) — options: `offset, index, uxo/uno, index_timestep_zero`
- Using `mode` causes validation error

### 4. SaveImage Required
API returns `prompt_no_outputs` error without at least one SaveImage/PreviewImage node.

### 5. LoadImage `upload` Key Doesn't Exist in API
The UI shows an `upload` widget but it's not an API input — remove it or get validation error.

### 6. Image Output Index 0 vs 1 (CRITICAL!)
ImageResizeKJv2 outputs:
- `[0]` = IMAGE tensor ← USE THIS
- `[1]` = width (INT)
- `[2]` = height (INT)
- `[3]` = mask (MASK)

Using `[1]` passes integer `1024` instead of image → `'int' object has no attribute 'movedim'` error.

### 7. CFGNorm Output Name
Output is `patched_model` (not `MODEL`), but reference by index `[0]` works fine in API format.

### 8. Cloudflare Blocks Python urllib
Always use `curl` via `subprocess.run()` for API calls. Python's `urllib` gets 403 with "error code: 1010" from Cloudflare.

### 9. Workflow JSON ≠ API Format
The `.json` files saved by ComfyUI UI use a different structure (`nodes[]` + `links[]` array). The API format uses `{node_id: {class_type, inputs}}` dict. Must convert — see `scripts/generate_scene.py` for the working API format.

### 10. `Any Switch (rgthree)` Required for Routing
Nodes 184 and 205 are Any Switch nodes that select between reference/latent inputs. They must be included in the API format — omitting them breaks the execution graph.

## Full Workflow Template (30 Nodes)

The complete working API workflow is in `assets/workflow-api-template.json`. Key customizable fields:

| Node IDs | Type | What to customize |
|---|---|---|
| 213, 175, 182 | LoadImage | `image` = reference filename |
| 154, 153 | TextEncodeQwenImageEditPlus | `prompt` = scene prompt |
| 3 | KSampler | `seed`, `steps`, `denoise` |
| 214 | SaveImage | `filename_prefix` |
| 200, 201, 202 | ImageResizeKJv2 | `width`, `height` if not 1024×1024 |

## Improvements Roadmap

### Done ✅
- [x] **Manifest v2 schema**: shots array, facial_expression per shot, mood (renamed from emotion), total_shots_budget, personality_traits per character
- [x] **Facial expression vocabulary**: 20+ emotions mapped to 3-region visual descriptors (mouth + eyes + brow)
- [x] **Qwen Image Edit prompting guide**: Anchor phrase, three-region face rule, expression patterns, pitfalls, length guidelines, **Reddit community research** (8 threads, 600+ comments — offset fixes, LoRA reviews, multi-ref strategies, inpaint masking, max-quality workflow, 2509-vs-2511 comparison, face dataset tips)
- [x] **Phase 0B approval gate**: Character sheet review with inline images, per-character approval, auto-reject for non-neutral expressions
- [x] **Evaluation v2**: 5-category scoring with facial_expression (0.25 weight), character sheet evaluation with expression_neutrality
- [x] **Manifest-driven script**: `generate_scene.py` loads `story_manifest.json` via `--manifest` flag
- [x] **Auto image check**: Script queries `/object_info/LoadImage` dynamically at start
- [x] **ComfyUI API pitfalls**: All 10 documented with fixes in `references/comfyui-api-pitfalls.md`
- [x] **Workflow template**: `assets/workflow-api-template.json` — standalone reusable JSON
- [x] **Auto-mapping ref selection**: `build_ref_mapping()` derives character→filename from naming convention `{character_id}_reference_sheet.png`. No more hardcoded `DEFAULT_REF_IMAGES` — works for any story.
- [x] **End-to-end test (teddy bear story)**: 5 chars, 6 scenes, full Phase 0→1→2 pipeline. Character sheets generated via paid Gemini key, uploaded to ComfyUI, all 6 scenes generated with correct per-scene refs. Character consistency holds in early scenes but drifts in later multi-char scenes (4+ chars).

### In Progress
- [ ] **`--upload-url` flag**: Add to `generate_story_assets.py` so Step B (generate sheets) + Step C (upload to ComfyUI) happen in one command. Replaces the old "auto-upload" concept — upload belongs with generation, not consumption.
- [ ] **Negative prompt node**: Add `TextEncodeQwenImageEditPlus` node for negative prompts to suppress unwanted features (e.g., "gold jewelry on rabbit")
- [ ] **Fox reference sheet**: Generate the missing character ref and upload
- [ ] **Character consistency late scenes**: Multi-character scenes (4+ chars like Scene 6) show character drift — some characters don't match their reference sheets. Likely caused by only 3 ref slots (4th+ character gets no visual anchor). Investigate: stronger identity text in prompt, negative prompts for wrong features, or split multi-char scenes.

### Done (Phase 2.5 — Evaluate & Refine) ✅
- [x] **Evaluate-and-refine loop integration**: `generate_scene.py` now supports `--evaluate`, `--max-iterations`, `--cleanup-iters`, and `--evaluate-only` flags
- [x] **Vision evaluation via Gemini 2.5 Flash**: Direct Google API call (free tier, `responseMimeType: application/json`, `temperature: 0.2`)
- [x] **Raw sub-scores with weighted average**: Vision model returns 4 category scores; script computes weighted average (character_accuracy=0.40, scene_composition=0.25, action_depicted=0.20, style_consistency=0.15)
- [x] **Chain-of-thought evaluation prompt**: "Describe what you see first, then score" for audit trail and reduced hallucination
- [x] **Pass threshold**: score ≥ 7 AND no critical issues (AND, not OR)
- [x] **Prompt refinement**: Refined prompts are JSON-sanitized before ComfyUI injection (escape quotes, newlines, backslashes)
- [x] **Pipeline summary**: Auto-generates `pipeline_summary.json` at story root after full run
- [x] **Cleanup iteration files**: `--cleanup-iters` flag deletes non-best iteration files after scene passes
- [x] **Standalone evaluator**: `evaluate_scene.py` can be run independently for spot-checking images

### Nice-to-Have
- [ ] **Parallel generation**: Queue multiple scenes at once (ComfyUI handles queuing)
- [ ] **Seed sweep**: Generate multiple seeds per scene for best-pick selection
- [ ] **Image review step**: Auto-send generated images to Discord for review before proceeding
- [ ] **Variation prompts**: Support "variation of scene X with changes Y" for iterating
- [ ] **Custom node mapping**: Allow different ComfyUI setups (not hardcoded node IDs)
- [ ] **Negative prompt support**: Second `TextEncodeQwenImageEditPlus` node for suppressing unwanted features (e.g., "gold jewelry", "extra fingers") — especially useful for iteration 2+ refine loops

### Future
- [ ] **LTX 2.3 I2V integration**: Full pipeline from scenes → video clips in one command
- [ ] **FFmpeg assembly**: Auto-stitch clips with transitions and audio
- [ ] **Voiceover**: TTS narration per scene synced to video length

## Vision Evaluation Model: Gemini 2.5 Flash

**Provider:** Google AI Studio (free tier) — `gemini-2.5-flash`
**Why not other options:**
- `qwen3-coder-next:cloud` — does NOT support vision (returns 400 "this model does not support image input")
- `MiniMax MCP vision` — auth broken in our setup, and we're dropping the subscription
- `gemini-3.1-pro` — rate limited (daily quota exhausted quickly)
- `gemini-2.5-flash` — works reliably, free tier, JSON response mode, good at detailed image analysis

**API:** Direct Google Generative Language API via `urllib` (not the Gemini CLI — CLI has broken `ripGrep.js` dependency and needs `--yolo` + JSON flags). The `evaluate_scene.py` script uses `urllib.request` to call the REST API directly.

**Key pitfall:** `GEMINI_API_KEY` is set in `~/.bashrc` but NOT auto-exported in subprocess calls. The script reads it from `os.environ` — must either `source ~/.bashrc` first or pass `--api-key` flag.

**Key pitfall:** When comparing skill dirs across repo vs Hermes, remember they are symlinks (see Repository Symlink section). Files appear in both paths but are the same physical files.

**Response format:** `responseMimeType: "application/json"` forces structured JSON output. The script uses `temperature: 0.2` for consistent scoring.

## Phase 2.5: Evaluate & Refine Loop

After generating a scene, optionally run a vision-based evaluation to check quality. If the image doesn't pass, refine the prompt and regenerate — up to 3 iterations.

### Architecture

```
GENERATE ──▶ EVALUATE ──▶ PASS?
  ▲                        │
  │                    Yes → Save final, next scene
  │                    No  → REFINE prompt, loop (max 3)
  └────────────────────────┘
```

### CLI

```bash
# Full pipeline with evaluation loop
python3 generate_scene.py --manifest story_manifest.json --all --evaluate --max-iterations 3

# Without evaluation (single-shot, current behavior)
python3 generate_scene.py --manifest story_manifest.json --all

# Evaluate only (on existing images)
python3 evaluate_scene.py --manifest story_manifest.json --scene 1 --image scenes/scene_001_iter1.png
```

### v2 Script Notes

- **`generate_scene.py --all` on v2 manifests** iterates all shots across all scenes, not just scenes. Each shot gets its own ComfyUI call with its own prompt.
- **`generate_scene.py --scene X --shot Y`** targets a specific shot. Omit `--shot` to generate the first shot of a v2 scene (or the whole scene for v1).
- **Expression drift detection**: The v2 eval passes `expected` expressions to Gemini so it can compare against `observed` and give a specific `facial_expression` score. If expression drift is detected, the refined prompt strengthens descriptors using the three-region rule (mouth + eyes + brow) or moves expression text earlier in the prompt.
- **v1 backward compat**: If `detect_manifest_version()` returns v1 (no `shots` array, no `total_shots_budget`), the script falls back to 4-category eval and single-prompt-per-scene generation. v1 manifests work without changes.

### Pass Threshold

A scene passes when: **score ≥ 7 AND no critical issues** (missing character, wrong setting). Use AND, not OR — a scene with score 3 but "no critical issues" must NOT pass.

### Vision Evaluation Returns Raw Sub-Scores

The vision model returns category scores; the script computes the weighted average:

**v2 scoring (5 categories):**
```json
{
  "category_scores": {
    "character_accuracy": 6,
    "facial_expression": 4,
    "scene_composition": 8,
    "action_depicted": 7,
    "style_consistency": 9
  },
  "score": 6.5,
  "passed": false,
  "issues": ["Hare's expression is neutral, not the specified confident grin"],
  "strengths": ["Good composition, correct setting"],
  "refined_prompt": "<improved prompt or null if passed>",
  "expression_detail": {
    "hare": {"expected": "confident grin, eyes determined", "observed": "neutral face, no expression"},
    "tortoise": {"expected": "gentle knowing smile", "observed": "gentle knowing smile"}
  }
}
```

**v1 scoring (4 categories, backward compat):**
```json
{
  "category_scores": {
    "character_accuracy": 6,
    "scene_composition": 8,
    "action_depicted": 7,
    "style_consistency": 9
  },
  "score": 7.15,
  "passed": false,
  "issues": ["Fox character is missing"],
  "strengths": ["Good composition, correct aspect ratio"],
  "refined_prompt": "<improved prompt or null if passed>"
}
```

Weights (v2): character_accuracy=0.30, facial_expression=0.25, scene_composition=0.20, action_depicted=0.15, style_consistency=0.10.

**Why facial_expression is 25%**: Expression accuracy differentiates shots within the same scene. A 5-shot scene where every face is neutral defeats the purpose of shot-level planning.

### Chain-of-Thought Evaluation

The evaluation prompt must instruct the vision AI to **describe what it sees first**, then score. This gives an audit trail and reduces hallucination:

```
First, describe every character you see in the image and their approximate position.
Then describe the setting, action, and style.
Then score each category 0-10.
```

### Prompt Refinement Rules

- **Only modify parts related to the issues.** Preserve all other wording exactly.
- **Never add global restatements** like "high quality" or "detailed".
- **Extract negations** — "NOT a dark scene" is weak for diffusion models. Instead, describe what IS wanted: "bright, sun-dappled clearing with warm golden light".
- **JSON-escape refined prompts** before injecting into ComfyUI payload — newlines, quotes, and backslashes from the vision model can break the workflow JSON.

### Edge Cases

See `references/evaluate-loop-design.md` for the full 12-edge-case plan. Key rules:
- **Generation failures don't consume eval iterations.** Only successful generations that fail evaluation count.
- **Vision API failures:** 3s timeout, 2 retries. If all fail, keep the image (don't loop on eval failures).
- **Vision parse errors:** If JSON is unparseable after extraction attempts, treat as pass and log `eval_parse_error`.
- **Regression detection:** Track all iteration scores; pick the highest, not the latest.
- **Idempotency:** Re-running skips completed scenes (checks for existing `scene_XXX.png`).
- **Seed increment:** Iteration N uses `seed + N` to avoid same-output loops.
- **Disk space:** Log available disk before starting; `--cleanup-iterations` flag to delete non-best iter files after scene passes.

### Pipeline Summary

After a full run, generate `pipeline_summary.json` at the story root:

```json
{
  "story_slug": "hare-and-tortoise",
  "completed_at": "...",
  "scenes": [
    {"scene": 1, "best_iteration": 1, "passed": true, "score": 8.5},
    {"scene": 2, "best_iteration": 3, "passed": false, "needs_manual_review": true}
  ]
}
```

### File Structure

```
story-to-video/{story-slug}/
├── characters/           # Reference sheets
├── scenes/
│   ├── scene_001_iter1.png    # iteration 1
│   ├── scene_001_iter2.png    # iteration 2 (if needed)
│   ├── scene_001.png          # final (best iteration)
│   └── ...
├── feedback/
│   ├── scene_001_iter1.json   # evaluation per iteration
│   └── ...
├── pipeline_summary.json
└── story_manifest.json
```

## Repository Symlink

**Single source of truth:** The repo path `~/repos/auto-startups-vast/current-setup/skills/story-to-video` is a **symlink** → `~/.hermes/skills/creative/story-to-video/`. All edits happen in the Hermes skill dir; the repo sees them via symlink. Never copy files back into the repo path — it's the same directory.

To replicate this pattern for other skills:
```bash
rm -rf ~/repos/auto-startups-vast/current-setup/skills/<skill-name>
ln -s ~/.hermes/skills/<category>/<skill-name> ~/repos/auto-startups-vast/current-setup/skills/<skill-name>
```

## File Editing Pitfalls

### write_file Truncates Large Files
The `write_file` tool has a character limit (~25KB). Files above this get silently truncated. **For files >20KB**, use `patch` mode to make targeted edits instead of rewriting the whole file.

### skill_manage(action='write_file') Overwrites Source
⚠️ **CRITICAL**: `skill_manage(action='write_file')` writes the `file_content` you pass to BOTH the skill directory AND the location you copied from. If you `cp` a file then use `write_file` to update the skill copy, it will also overwrite your backup. Always `cp` to `/tmp/` for safe backups before using this action.

## Related Skills

- `vast-ai` — Provision GPU instances for ComfyUI
- `ltx23-video-gen` — LTX 2.3 image-to-video on RunPod
- `comfyui-api` (if exists) — Basic ComfyUI REST API patterns

## Reference Files

- `references/story-manifest-format.md` — JSON schema for story manifests (v2) and prompt composition rules
- `references/facial-expression-vocabulary.md` — Approved expression descriptors: 20+ emotions mapped to visual descriptors for Qwen prompts
- `references/qwen-image-edit-prompting-guide.md` — Prompting strategies for Qwen Image Edit 2511: anchor phrase, three-region face rule, expression patterns, pitfalls, length guidelines, plus **Reddit community research** (r/StableDiffusion, r/LocalLLaMA, r/ComfyUI — 8 threads, 600+ comments: resolution offset fixes, Lightning LoRA quality tradeoffs, consistence/AnyPose/Next Scene LoRAs, multi-reference strategies, inpaint-style masking, max-quality workflow, 2509-vs-2511 comparison, Chinese prompting, face dataset generation, plastic skin mitigation)
- `references/qwen-image-edit-api-patterns.md` — Working API patterns with curl snippets
- `references/comfyui-api-pitfalls.md` — Complete list of all 10 pitfalls with fixes
- `references/evaluate-loop-design.md` — Evaluate-and-refine loop: edge cases, scoring, prompt refinement rules, JSON schema
- `references/gemini-vision-api-patterns.md` — Gemini 2.5 Flash direct REST API pattern for vision evaluation (API key setup, response parsing, retry logic, CLI pitfalls)
- `references/gemini-image-gen-quotas.md` — Gemini 2.5 Flash Image gen quota pitfalls, daily limits, workarounds
- `references/reddit-scraping-patterns.md` — How to scrape Reddit for Qwen/AI research: JSON API patterns, what works vs what doesn't, parsing caveats, relevant subreddits
- `references/env-and-key-management.md` — `.env` / `.env.example` pattern for skill-local API keys, subprocess key loading, why no venv

## Scripts

- `scripts/generate_story_assets.py` — **Phase 0**: Character reference sheets via Gemini `gemini-2.5-flash-image` + scene illustrations with smart per-scene reference selection. **Emits v2 manifest** (shots array, facial_expression per shot, mood, personality_traits, total_shots_budget). Uses `google-genai` Python SDK (requires `pip install google-genai Pillow`). **API key priority**: `.env` file (next to skill dir) → `GEMINI_API_KEY` env var → `--token` JSON file path. The `.env` file is read with stdlib only (no `python-dotenv` needed) — just `Path` + string parsing. See `.env.example` for template. Flags: `--manifest`, `--phase characters|scenes|all`, `--force`, `--max-refs`, `--token`. Future: add `--upload-url` to push sheets to ComfyUI after generation.
- `scripts/generate_scene.py` — **Phase 2** (v2): Full pipeline with per-shot generation and 5-category evaluation. Auto-detects v1 vs v2 manifests. **v2 features**: shot-level prompts with facial_expression per character, `--shot` flag for specific shots, `scene_XXX_shotYYY.png` naming, `build_scene_eval_context()` passes expression targets to Gemini. **v1 backward compat**: falls back to 4-category eval for old manifests. Flags: `--manifest`, `--scene`, `--shot`, `--all`, `--evaluate`, `--evaluate-only`, `--max-iterations`, `--url`, `--output-dir`, `--seed`, `--cleanup-iters`. Auto-maps character IDs to `{character_id}_reference_sheet.png` using convention.
- `scripts/evaluate_scene.py` — **Phase 2.5** (v2): 5-category vision evaluator using **Gemini 2.5 Flash**. Categories: character_accuracy (0.30), facial_expression (0.25), scene_composition (0.20), action_depicted (0.15), style_consistency (0.10). Passes scene context + target expressions to Gemini for accurate expression scoring. Returns `expression_detail` with expected vs observed per character. Supports character sheet evaluation (`--phase characters`) with expression_neutrality check. Requires `GEMINI_API_KEY` env var.

## Assets

- `assets/workflow-api-template.json` — Complete Qwen Image Edit 2511 API-format workflow template