---
name: story-to-video
version: 2.0.0
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
story_manifest.json → character prompts → scene prompts
                                        ↓
                            ComfyUI Qwen Image Edit 2511
                          (+ character reference sheets)
                                        ↓
                            Scene still images (1024×1024)
                                        ↓
                            LTX 2.3 I2V (motion prompts)
                                        ↓
                            Scene video clips → Final video
```

## Prerequisites

- **ComfyUI instance** running Qwen Image Edit 2511 workflow (provision with `vast-ai` skill)
- **Character reference sheets** uploaded to the ComfyUI instance's input directory
- **Story manifest** (JSON) defining characters and scenes
- **cURL** for API calls (Python urllib is blocked by Cloudflare — see pitfall #8)

## Output Paths

Default output directory: `/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video/`

Structure per story:
```
story-to-video/
├── {story-slug}/
│   ├── characters/       # Reference sheets (downloaded from ComfyUI)
│   ├── scenes/           # Generated scene images
│   ├── videos/           # Animated clips (Phase 3)
│   └── story_manifest.json
```

Override with `--output-dir` flag on `generate_scene.py`.

## Phase 1: Prepare Character Reference Sheets

Each character needs a multi-view reference sheet on the ComfyUI instance.

1. **Generate or obtain reference sheets** — Use Gemini or another image model to create character sheets with 4 body views + 3 face views on a white background
2. **Upload to ComfyUI** — `curl -X POST "$COMFY_URL/upload/image" -F "image=@hare_reference_sheet.png" -F "overwrite=true"`
3. **Verify availability** — Check `/object_info/LoadImage` for the `image` input's enum list of available filenames

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

**Rules:**
1. Use actual character reference sheets if available on the instance
2. If a character's ref is missing, fall back to the closest available character (e.g., fox → tortoise as similar woodland character)
3. Deduplicate — don't pass the same image twice (wastes a slot)
4. If fewer than 3 unique refs, fill remaining slots by duplicating the first ref
5. Never pass more than 3 images — the workflow enforces this

| Characters in Scene | Image Assignment | Rationale |
|---|---|---|
| 1 | [ref, ref, ref] | Duplicate to fill 3 slots |
| 2 | [ref1, ref2, ref1] | Fill 3rd slot with most important char |
| 3 | [ref1, ref2, ref3] | Perfect fit |
| 4+ | [ref1, ref2, ref3] | Pick top 3 by visual importance |

### Scene Prompt Composition

Each scene prompt combines: **Characters + Setting + Action + Emotion + Camera + Style**

```text
Characters in this scene must match the provided reference images exactly:
- {character}: {identity_spec}

Scene setting: {setting}.
Action: {action}.
Mood: {emotion}.
Camera: {camera}.
Style: {style}.
```

**Tips:**
- For scenes with many characters (3+), use abbreviated identity specs (key features only) to keep prompts within limits
- Always include "must match the provided reference images exactly" — this anchors the model to reference consistency
- The style should match the reference sheet style for consistency

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

These are known areas to improve based on our testing session:

### Must-Have
- [ ] **Manifest-driven script**: `generate_scene.py` should load `story_manifest.json` and `story-to-video-prompts.md` automatically instead of hardcoding scenes
- [ ] **Auto image check**: Script should query `/object_info/LoadImage` at start and build `AVAILABLE_ON_INSTANCE` dynamically instead of hardcoding
- [ ] **Auto upload**: If a ref image exists locally but not on instance, upload it automatically before generation
- [ ] **Fox reference sheet**: Generate the missing character ref and upload

### Nice-to-Have
- [ ] **Parallel generation**: Queue multiple scenes at once (ComfyUI handles queuing)
- [ ] **Seed sweep**: Generate multiple seeds per scene for best-pick selection
- [ ] **Image review step**: Auto-send generated images to Discord for review before proceeding
- [ ] **Variation prompts**: Support "variation of scene X with changes Y" for iterating
- [ ] **Custom node mapping**: Allow different ComfyUI setups (not hardcoded node IDs)

### Future
- [ ] **LTX 2.3 I2V integration**: Full pipeline from scenes → video clips in one command
- [ ] **FFmpeg assembly**: Auto-stitch clips with transitions and audio
- [ ] **Voiceover**: TTS narration per scene synced to video length

## Related Skills

- `vast-ai` — Provision GPU instances for ComfyUI
- `ltx23-video-gen` — LTX 2.3 image-to-video on RunPod
- `comfyui-api` (if exists) — Basic ComfyUI REST API patterns

## Reference Files

- `references/story-manifest-format.md` — JSON schema for story manifests and prompt composition rules
- `references/qwen-image-edit-api-patterns.md` — Working API patterns with curl snippets
- `references/comfyui-api-pitfalls.md` — Complete list of all 10 pitfalls with fixes

## Scripts

- `scripts/generate_scene.py` — Full pipeline: load manifest → pick images → build workflow → queue → poll → download

## Assets

- `assets/workflow-api-template.json` — Complete Qwen Image Edit 2511 API-format workflow template