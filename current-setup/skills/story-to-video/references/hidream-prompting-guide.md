# HiDream O1 Image Dev — Prompting Guide

> For use with `hidream-o1-dev-i2i` workflow template and `hidream_o1_image_dev_fp8_scaled.safetensors` checkpoint.

## Model Overview

HiDream O1 is a pixel-native generative model built on a **Pixel-level Unified Transformer (UiT)** architecture. Unlike traditional diffusion models, it treats raw pixels, text, and task conditions in a single shared token space — no separate VAE or disjoint text encoders. This means it handles identity preservation, image editing, and multi-reference composition natively.

**Key specs (Dev variant):**

| Parameter | Value |
|---|---|
| Checkpoint | `hidream_o1_image_dev_fp8_scaled.safetensors` |
| Sampler | LCM |
| Scheduler | normal |
| Steps | 28 |
| CFG | 1.0 |
| Noise Scale | 7.6 |
| Noise Clip Std | 2.5 |
| Reference Slots | 4 (via `HiDreamO1ReferenceImages` node) |
| Negative Prompt | **Empty** (Dev model only) |

---

## Resolution for 16:9

The model is trained on specific native resolutions. For 16:9 output:

| Width | Height | Aspect Ratio | Megapixels | Recommended |
|---|---|---|---|---|
| 2560 | 1440 | 16:9 ✅ | 3.69 MP | **✅ Primary** |
| 2304 | 1296 | 16:9 (approx) | 2.99 MP | ⚠️ Not native |

**Use 2560×1440** — it is the exact native 16:9 resolution. On RTX 3090 (24GB) with FP8, VRAM usage is ~12-14 GB, well within limits.

### All Supported Native Resolutions

| Width | Height | Category |
|---|---|---|
| 2048 | 2048 | Square |
| 2304 | 1728 | Landscape |
| 2304 | 1792 | Landscape |
| 2496 | 1664 | Landscape |
| **2560** | **1440** | **Landscape (16:9)** |
| 3104 | 1312 | Landscape (ultra-wide) |
| 1728 | 2304 | Portrait |
| 1792 | 2304 | Portrait |
| 1664 | 2496 | Portrait |
| 1440 | 2560 | Portrait (9:16) |
| 1312 | 3104 | Portrait (ultra-tall) |

---

## Prompt Structure: SCALIST Framework

HiDream O1 works best with structured, descriptive English paragraphs (not keyword lists). Use the **SCALIST** framework:

| Component | What to Include | Priority |
|---|---|---|
| **S – Subject** | Character identity, appearance, colors, material, texture, expressions, clothing | 🔴 Critical |
| **C – Composition** | Shot type, viewpoint, subject placement, foreground/mid/background layers, focal point | 🟡 Important |
| **A – Action** | What's happening, posture, direction of motion, character interactions | 🟡 Important |
| **L – Location** | Setting, indoor/outdoor, time of day, weather, environment details | 🟡 Important |
| **I – Image Style** | Art style: photorealistic, cinematic, 3D render, watercolor, anime, etc. | 🟢 Include |
| **S – Specs** | Lens type, depth of field, lighting setup, texture quality | 🟢 Include |

### Prompt Template for Story Scenes

```text
Characters in this scene must match the provided reference images exactly:
- {Name}: {identity_spec}. Expression: {mouth description}, {eye description}, {brow description}.

{Action description — what characters are doing, interactions, poses}.

Setting: {detailed environment description with spatial anchoring}.
Mood: {emotional atmosphere}.
Camera: {shot type, angle, lens characteristics}.
Style: {art style}, {lighting}, {rendering quality descriptors}.
```

---

## Critical Rules for Dev Model

### 1. NO Negative Prompts
The Dev model is distilled to work with CFG 1.0. Using negative prompts can cause:
- Washed-out colors
- Over-filtered/plastic textures
- Odd artifacts

**Always leave the negative prompt empty.**

### 2. Natural Language, Not Keywords
```
❌ BAD:  "tiger cub, jungle, butterflies, sad, Pixar, 3D, 4K"
✅ GOOD: "A young tiger cub with bright orange fur and no stripes stands alone in a sunlit jungle clearing. His expression is puzzled — eyes downcast, brow lightly creased with confusion. Blue and yellow butterflies flutter around him. The scene is rendered in high-quality Pixar-style 3D animation with soft ambient lighting."
```

### 3. Prompt Length: 50–150 Tokens Ideal
- Too short (<30 tokens): model fills in details unpredictably
- Too long (>200 tokens): diminishing returns, risk of concept confusion
- Sweet spot: **80–120 tokens** for scene descriptions

### 4. Let Reference Images Do the Heavy Lifting
When reference images are provided, **don't over-describe** what's already visible in the reference. Focus the prompt on:
- What's **different** from the reference (new pose, expression, setting)
- Spatial relationships between characters
- Scene context not visible in reference sheets

---

## Multi-Character Scenes

### Identity Preservation Rules

1. **Define characters FIRST** in the prompt, before describing the scene
2. **Use explicit spatial anchoring**: "standing on the left", "sitting in the foreground"
3. **Limit 2-3 characters** per image for best identity consistency (4 max with 4 ref slots)
4. **One reference per character** — don't mix character refs in the same slot
5. **Order refs by visual importance** — slot 1 is the primary character

### Preventing Identity Bleed

Identity bleed = characters swapping features (colors, expressions, proportions).

**Prevention strategies:**
- Separate character descriptions with clear delimiters (dashes, newlines)
- Use contrasting descriptors: "The tiger cub has bright ORANGE fur" vs "The older tiger has BLACK stripes over orange fur"
- Specify unique visual anchors: clothing, accessories, size differences
- Include spatial separation: "on the left" / "on the right" / "in the background"

### Reference Slot Assignment

| Characters | Slot 1 | Slot 2 | Slot 3 | Slot 4 |
|---|---|---|---|---|
| 1 char | char_ref | char_ref (dup) | char_ref (dup) | char_ref (dup) |
| 2 chars | main_char | secondary_char | main_char (dup) | secondary_char (dup) |
| 3 chars | char_1 | char_2 | char_3 | char_1 (dup) |
| 4 chars | char_1 | char_2 | char_3 | char_4 |

---

## Facial Expressions

HiDream O1 handles expressions well, but requires **explicit 3-region descriptors**:

### Expression Format
```text
Expression: {mouth state}, {eye state}, {brow/forehead state}.
```

### Examples
| Emotion | Descriptor |
|---|---|
| Happy | "wide beaming smile with teeth showing, eyes crinkled and sparkling, brows raised high in delight" |
| Sad | "mouth downturned slightly, eyes glistening with soft tears, brow creased with gentle sadness" |
| Surprised | "mouth open in a round O shape, eyes wide and unblinking, brows shot up high" |
| Determined | "jaw set firmly, eyes narrowed with intensity, brows drawn together in focused concentration" |
| Worried | "lower lip slightly bitten, eyes darting with anxiety, brow furrowed with concern" |

### Expression Placement in Prompt
Put expressions **immediately after** the character identity description, **before** the action:
```text
- Toby: young tiger cub with orange fur, no stripes. Expression: puzzled slight frown, eyes downcast, brow lightly creased.

Action: Toby stands alone looking at his stripe-less chest.
```

---

## Image Edit Mode (I2I)

The workflow uses **image edit mode** (`Switch to Image Edit = true`). In this mode:

1. Reference images are passed to `HiDreamO1ReferenceImages` node
2. Latent dimensions are auto-derived from the **first reference image** (floor(dim/32)*32)
3. The model uses in-context learning to understand character identity from references
4. Output maintains visual consistency with reference images

### Important: Reference Image Preparation

- **Resolution**: Reference sheets should ideally be the same aspect ratio as output (16:9 = 2560×1440) or square. The workflow scales via `ImageScaleToTotalPixels` (4 MP target)
- **Content**: Use character reference sheets with multiple views/poses on a clean background
- **Format**: PNG preferred (lossless)
- **Naming**: `{character_id}_reference_sheet.png` convention

---

## Comparison with Qwen Image Edit

| Feature | HiDream O1 Dev | Qwen Image Edit 2511 |
|---|---|---|
| Architecture | Pixel-level Unified Transformer | Flow-based transformer |
| Steps | 28 | 4 (Lightning) |
| Speed (3090) | ~60-90s per image | ~20-30s per image |
| Reference Slots | 4 | 3 |
| Negative Prompt | ❌ Not recommended | ✅ Supported |
| CFG | 1.0 | 1.0 |
| Best For | High-quality character consistency | Fast iteration |
| Expression Adherence | Good with 3-region descriptors | Good with 3-region descriptors |
| Prompt Style | Natural language paragraphs | Structured template |
| Native 16:9 | 2560×1440 | Any (via resize node) |

---

## Example Prompts

### Single Character Scene
```text
Characters in this scene must match the provided reference images exactly:
- Toby: A young round tiger cub with bright orange fur, no stripes at all, completely plain orange like a fuzzy peach. Big curious blue eyes, small rounded ears, a stubby tail, and a button nose. Expression: puzzled slight frown, eyes downcast looking at his own fur, brow lightly creased with confusion.

Toby stands alone in a sunlit jungle clearing, looking down at his own stripe-less chest with gentle bewilderment. Blue and yellow butterflies flutter around his plain orange fur. The jungle behind him is softly blurred with dappled golden morning light filtering through the canopy. Wildflowers scatter across the soft green ground.

Camera: medium shot with warm golden lighting and shallow depth of field.
Style: high-quality 3D rendered Pixar-style animation, soft ambient lighting, lush jungle environment, vibrant but naturalistic colors, smooth fur rendering with visible texture.
```

### Two Character Interaction
```text
Characters in this scene must match the provided reference images exactly:
- Taro (left side): An older juvenile tiger with magnificent sharp black stripes across bright orange fur. Athletic lean build, tall pointed ears, confident golden-amber eyes. Expression: warm encouraging smile, eyes bright and open, brows raised enthusiastically.
- Toby (right side, sitting): A young round tiger cub with bright orange fur, no stripes at all. Big curious blue eyes, small rounded ears. Expression: hesitant half-smile, eyes wide and uncertain, one brow slightly raised.

Taro bounds over to Toby with energy and warmth, one paw raised mid-stride in a welcoming gesture. Toby looks up from the ground where he sits, meeting Taro's gaze with a mixture of hope and uncertainty. The brightly lit jungle clearing surrounds them with tall grass, blue and yellow wildflowers, and warm golden morning light.

Camera: medium shot capturing both characters with warm golden backlighting.
Style: high-quality 3D Pixar-style animation, soft ambient lighting, lush vibrant jungle environment, expressive character faces with detailed fur rendering.
```

---

## Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| Plastic/artificial textures | Negative prompt used | Remove negative prompt entirely |
| Grid/tile artifacts at high res | Patch seam issue | Add Patch Seam Smoothing node to workflow |
| Characters swapping features | Identity bleed | Add spatial anchoring ("left"/"right"), use contrasting descriptors |
| Wrong expressions | Vague expression description | Use 3-region format (mouth + eyes + brow) |
| Colors washed out | CFG too high or negative prompt | Set CFG to 1.0, empty negative prompt |
| VRAM OOM | Resolution too high | Use FP8 model, target 2560×1440 max on 24GB |
| Inconsistent character identity | Too many characters or weak refs | Limit to 2-3 chars, use high-quality reference sheets |
