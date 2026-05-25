# Qwen Image Edit 2511 Prompting Guide

This guide covers proven prompting strategies for **Qwen Image Edit 2511 fp8** running on our ComfyUI instance (4-step Lightning workflow on RTX 3090).

**Read this reference before planning any shot prompts.**

## Model Overview

- **Model**: Qwen Image Edit 2511 (based on Qwen2.5-VL architecture)
- **Workflow**: 4-step Lightning (fast generation, ~20-30 sec/scene on RTX 3090)
- **ComfyUI nodes**: 3 LoadImage slots for reference sheets → ImageResizeKJv2 → VAEEncode → ReferenceLatent chain
- **Max reference images**: 3 per generation (use pick_images() from API patterns)

## Core Prompting Principles

### 1. The Anchor Phrase 🔒

**ALWAYS** start character sections with:

```
Characters in this scene must match the provided reference images exactly:
```

This is the single most important prompt element. Without it, the model drifts away from character likeness aggressively. With it, character consistency improves dramatically.

### 2. Visual Descriptors > Abstract Labels

Qwen Image Edit responds much better to **concrete visual descriptions** than abstract emotion words.

| ❌ Bad (Abstract) | ✅ Good (Visual) |
|---|---|
| "sad" | "downcast eyes looking at ground, slight downturned mouth, heavy brow" |
| "angry" | "deep scowl, brows drawn together, mouth tight thin line, eyes narrowed" |
| "happy" | "beaming smile, eyes crinkled at corners, cheeks raised high" |
| "surprised" | "suddenly wide eyes, brows shot up, mouth rounded in surprise" |

**Rule**: Every facial expression must describe at minimum **mouth + eyes + brow/forehead**. Single-word emotions produce inconsistent results.

### 3. Three-Region Face Rule

For each character in a shot prompt, describe at least three facial regions:

1. **Eyes** — "wide eyes", "narrowed eyes", "eyes half-lidded", "darting eyes"
2. **Mouth** — "slight frown", "tight-lipped", "grin", "mouth agape"
3. **Brow/Forehead** — "furrowed brow", "raised eyebrows", "smooth brow", "brows drawn together"

This gives the model concrete pixels to target rather than a vague concept.

### 4. Expression Follows Action

The facial expression must be consistent with the described action. If the action is "Hare sprints ahead confidently", the expression must match:

```
❌ Action: "Hare sprints ahead confidently"
   Expression: "nervous wide eyes, forced smile"  ← contradicts action

✅ Action: "Hare sprints ahead confidently"
   Expression: "confident grin, eyes determined, brows raised high"  ← reinforces action
```

However, **deliberate dissonance** (character hiding true feelings) works if explicitly stated:

```
✅ Action: "Hare crosses the finish line, trying to look happy"
   Expression: "forced tight smile, eyes glistening with unshed tears,
                jaw clenched — trying to look happy but clearly struggling"
```

## Scene Prompt Template (v2)

Each shot uses this template:

```text
Characters in this scene must match the provided reference images exactly:
- {name}: {identity_spec}. Expression: {facial_expression}

Scene setting: {setting}.
Action: {shot.description}.
Mood: {scene.mood}.
Camera: {shot.camera_override or scene.camera}.
Style: {style}.
```

### Abbreviated Prompt (3+ characters)

When 3+ characters are present, shorten identity specs but **keep full expressions**:

```text
Characters in this scene must match the provided reference images exactly:
- Hare: brown fur, long ears, athletic build. Expression: confident grin, eyes determined, brows raised high
- Tortoise: green shell, wrinkled face, short legs. Expression: serene focus, eyes forward, slight determined smile
- Fox: reddish fur, bushy tail, sly face. Expression: knowing smirk, one brow arched, eyes narrowed in amusement

Scene setting: A dusty forest path through dappled sunlight.
Action: Hare bursts forward from the starting line while Fox watches from the shadows.
Mood: Excited, energetic.
Camera: Wide shot.
Style: Colorful children's book illustration, soft watercolor textures.
```

## Facial Expression Prompting Patterns

### Pattern 1: Direct Expression (most reliable)

State exactly what the face looks like:

```
Expression: warm smile crinkling eyes, relaxed brow, cheeks raised
```

### Pattern 2: Expression with Contrast (for complex emotions)

Describe the expression AND the context that creates it:

```
Expression: bitter tight smile, eyes glistening with unshed tears,
            jaw clenched — trying to appear composed but clearly emotional underneath
```

The contrast phrase after the em-dash helps the model understand *why* the face looks that way.

### Pattern 3: Transition Expression (for motion between emotions)

For I2V motion prompts only (not still generation), describe the shift:

```
Expression shifts from confident grin to worried frown, eyes widening
with realization, brows drawing together
```

### Pattern 4: Suppressed/Hidden Emotion (advanced)

For characters masking their true feelings:

```
Expression: plastered-on smile, but eyes are distant and hollow,
            mouth slightly too wide — overcompensating
```

## Reference Image Best Practices

### Character Sheet Requirements

Reference sheets must show the character with:
- **Neutral/resting expression** — the base face the model learns
- **Clear, front-facing portrait** — at least one view showing full face
- **Consistent style** — same art style as scene prompts
- **Minimal background noise** — character should dominate the image

### Reference Image Slot Strategy

| Characters in Scene | Slot Assignment | Rationale |
|---|---|---|
| 1 character | [char_ref, char_ref, char_ref] | Triple exposure reinforces likeness |
| 2 characters | [char1_ref, char2_ref, char1_ref] | Most important character gets 2 slots |
| 3 characters | [char1_ref, char2_ref, char3_ref] | Perfect 1:1 mapping |
| 4+ characters | [char1_ref, char2_ref, char3_ref] | Pick top 3 by visual importance |

**Important**: Only characters with reference images available on the ComfyUI instance can be included. Missing characters fall back to the closest available reference (see `FALLBACKS` in API patterns).

### Style Consistency Between References and Scenes

The `style` field in the manifest must match across:
1. **Reference sheet generation prompt** (Phase 0B via Gemini nanobanana)
2. **Scene generation prompts** (Phase 2 via Qwen Image Edit)
3. **Motion prompts** (Phase 3, future roadmap)

If reference sheets were generated with a different style string, note it — mismatch causes character drift.

## Expression Pitfalls & Solutions

### Pitfall 1: "Smiling" Without Specificity

```
❌ Expression: smiling
✅ Expression: warm genuine smile, eyes crinkled at corners, dimples showing
```

The model interprets "smiling" as a weak suggestion. With 3 facial features described, it becomes a concrete target.

### Pitfall 2: Multiple Characters, Same Expression

When all characters in a scene have similar emotions, each still needs differentiated descriptions:

```
❌ Expression for Hare: happy
   Expression for Tortoise: happy
   Expression for Fox: happy

✅ Expression for Hare: beaming grin, eyes bright and wide, brows raised in triumph
   Expression for Tortoise: gentle pleased smile, eyes warm and soft, brow relaxed
   Expression for Fox: satisfied smirk, eyes narrowed to slits, one brow arched
```

### Pitfall 3: Negative Descriptions Confuse the Model

Qwen Image Edit does **not** reliably handle negative descriptions:

```
❌ Expression: not smiling, not angry — just neutral
✅ Expression: smooth relaxed brow, mouth at rest, eyes open and calm, no strong emotion
```

**Describe what IS there, not what isn't.**

### Pitfall 4: Over-Loading the Prompt

Keep expression descriptions to 2-3 features per character. Overly long prompts dilute the model's focus:

```
❌ Expression: furrowed brow with deep creases between the eyebrows,
   eyes narrowed to thin slits like a cat stalking prey, mouth pressed
   into a tight bloodless line, jaw muscles clenched visibly at the temples,
   nostrils flared wide, cheeks flushed red with barely contained rage,
   every muscle in the face taut with tension

✅ Expression: deep scowl, brows drawn tight, mouth a thin pressed line, eyes narrowed
```

The second version gives the model 4 clear targets. The first is 7+ competing signals that produce muddy results.

## Prompt Length Guidelines

| Component | Recommended Length | Maximum |
|---|---|---|
| Identity spec (full) | 40-80 words | 120 words |
| Identity spec (abbreviated, 3+ chars) | 15-30 words | 50 words |
| Facial expression | 10-20 words | 30 words |
| Scene setting | 20-40 words | 60 words |
| Action | 15-30 words | 50 words |
| Mood | 3-8 words | 15 words |
| Camera | 3-8 words | 15 words |
| Style | 10-20 words | 30 words |
| **Total prompt** | **120-200 words** | **350 words** |

Beyond ~350 words, the model starts ignoring later parts of the prompt. Prioritize: **character identity + expression > action > setting > style > mood > camera**.

## Iteration Strategy

When the first generation doesn't match the expression target:

1. **Tighten the expression** — add one more facial feature (brow, eyes, or mouth)
2. **Simplify the action** — too much action can override the expression; reduce to one verb
3. **Add expression context** — "with a worried expression on her face" reinforces the expression
4. **Check reference image** — if the character sheet shows a strong expression, the model may default to it regardless of prompt

Do **not** increase prompt length beyond 350 words to fix expression issues. Instead, restructure and prioritize.

## Model Limitations to Know

1. **Expression vs. Pose Trade-off**: Heavy action descriptions can override facial expressions. If the action is dramatic ("leaping across a chasm"), the model may default to a generic action face regardless of your expression prompt. Solution: put expression description BEFORE the action in the prompt.

2. **Reference Sheet Expression Leakage**: If the reference sheet shows a character smiling, the model tends to make them smile in every scene, even when the prompt says "frowning". This is why **character sheets must use neutral expressions** (see Task 2).

3. **Multi-Character Expression Averaging**: With 3 characters in a scene, the model may average their expressions toward neutral. Mitigate by making each expression description **more specific and intense** than you think necessary.

4. **Child Style Amplification**: In "children's book illustration" style, expressions tend to be amplified. A "slight smile" becomes a beaming grin. Counter by describing MORE subtle expressions than you want: "hint of a smile" instead of "smile".

5. **FP8 Quantization Artifacts**: The fp8 quantization can produce slight texture issues in fine detail areas (eyes, mouth corners). This is usually invisible at scene scale but may affect extreme close-ups. No mitigation needed for story scenes.

## ComfyUI-Specific Notes

- **4-step Lightning workflow**: Fast (~20-30 sec) but fewer inference steps = less prompt adherence for subtle expressions. Make expressions explicit.
- **Resolution**: Default 1280×720 (16:9). Qwen Image Edit handles this well; the wider aspect ratio is optimized for video output. Expressions are more visible at closer camera angles.
- **Seed**: Set seed for reproducibility. Same seed + same prompt = same output. Useful for debugging expression issues.
- **Batch generation**: Currently sequential (one scene at a time). No batch API exposed yet.

## Reddit & Community Research Findings 🔍

Deep-dive conducted across r/StableDiffusion, r/LocalLLaMA, r/ComfyUI on 2026-05-19. Key findings integrated below. Source threads: 8 high-quality threads totaling 600+ comments analyzed.

### Resolution & Offset Fix (Critical) ⚡

**Problem**: Qwen Image Edit 2509/2511 crops/offsets the output even when input is a multiple of 112.
**Root cause**: The `TextEncodeQwenImageEditPlus` node forces image resize to 1MP internally, causing misalignment.
**Community fix** (from r/comfyui top-quality post, score 283):
- Use a custom or patched `TextEncodeQwenImageEditPlus` that accepts manual width/height input
- Match reference image dimensions exactly with the empty latent size
- The **ScaleImageToPixels** node is NOT the problem — it's the text encoder
- When reference width/height matches output latent, offset/crop artifacts disappear

**For our pipeline**: Ensure reference images are scaled to match our target output resolution exactly. Don't rely on Qwen's internal resizing.

### Lightning LoRAs — Quality vs Speed ⚡

**Community verdict** (consistent across multiple threads):
- Lightning LoRAs (4-step) reduce generation time 4-5x but produce **noticeably worse quality**
- They reduce prompt adherence, especially for subtle expressions and fine details
- Color intensity tends to increase with each generation (drift)
- They carry over fewer fine details like lip texture, hair strands
- **Our 4-step Lightning workflow trades expression quality for speed — make expressions MORE explicit in prompts to compensate**

### Consistence/Identity LoRA (Optional) 🔗

Community LoRA: `qwenedit-consistence-lora` (Civitai #1939453)
- **Pros**: Carries over fine lip texture, tiny face details slightly better
- **Cons**: Carries over unintended features too (logos, background elements); reduces creative variation; can degrade quality of other image areas (leg shapes, etc.)
- **Verdict**: Useful for character consistency in sequential shots. Trade-off with creativity. **Not recommended for first generation — use for consistency iterations only.**

### Next Scene LoRA 🎬

Community LoRA: `next-scene-qwen-image-lora-2509` (HuggingFace)
- Use prompt prefix "Next scene:" followed by description
- Maintains character, lighting, environment continuity between scenes
- **Highly relevant for our story pipeline** — enables scene-to-scene character continuity
- Limitation: works best with 2509, not yet verified on 2511

### AnyPose LoRA 🎭

Community LoRA: `lilylilith/AnyPose` (HuggingFace)
- ControlNet-free arbitrary posing from a reference image
- Built for Qwen Edit 2511
- **Relevant for our pipeline**: Can be used to generate specific poses from character reference sheets
- Works with and without reference latent nodes

### Multi-Reference Image Strategy 🖼️

Community best practices for reference images:
1. **Slot priority matters**: Main image gets rightmost slot. Add references right-to-left
2. **Reference images don't need exact 1MP scaling** — they can be bigger or smaller. Bigger = slower, smaller = faster
3. **2-image and 3-image workflows**: Each additional reference adds ~1x time multiplier. 3-image = ~5x slower
4. **Without reference latent nodes**: Multi-image is faster (2x/3x) but output is **blurry**
5. **With reference latent nodes**: Multi-image is slower (3x/5x) but quality is **maximal**

**For our pipeline**: Use reference latent nodes for quality. Accept the speed hit for story scenes requiring multiple characters.

### Masking for Inpaint-Style Edits 🎯

For scene changes that should only affect part of the image (e.g., expression changes, adding objects):
- Use **Inpaint Crop and Stitch** technique (ComfyUI-Inpaint-CropAndStitch node)
- Mask only the area that needs changing (face, background element)
- Stitch result back onto original — preserves untouched areas perfectly
- **Does NOT fix Qwen's inherent blurriness in the masked area**
- **Best for expression-only edits**: mask just the face region, preserve the rest of the scene

### Model Comparison: 2509 vs 2511 vs 2512 📊

Community consensus (r/comfyui, r/LocalLLaMA):
| Feature | 2509 | 2511 | 2512 |
|---|---|---|---|
| Identity consistency | Good | **Better (reduced drift)** | N/A (not Edit model) |
| Multi-person consistency | Fair | **Strong (built-in community LoRAs)** | N/A |
| Prompt obedience | Good | Better, prompting "still a pain" | N/A |
| Built-in LoRAs | None | **Popular community LoRAs fused** | N/A |
| Geometric reasoning | Fair | **Better (construction lines, structural)** | N/A |
| Image offset/crop bug | Present | Present (same root cause) | N/A |
| 4-step Lightning | Available | Available | N/A |

**Key note from community**: "2511 is pretty good, but prompting is still a pain in the ass. However, it has more consistency." — r/comfyui user (score 17)

### Character/Face Dataset Generation 👤

Community technique for generating face datasets from a single reference:
1. Start with an **upper body headshot** of the character
2. Use 20+ prompts generating different angles (profile, ¾, front, etc.)
3. Generate with Qwen Edit 2509 fp8 + Lightning LoRA for speed
4. **Minimal captioning works**: 1-word character name captions are sufficient for LoRA training
5. **Verbose captioning is NOT necessary** for likeness — "over the dozens of loras I've trained on FLUX, QWEN and WAN, it seems that you can train loras with a minimal 1 word caption"
6. **Alternative**: Google AI Studio (Gemini) can also generate face datasets with good consistency

**For our pipeline character sheets**: Use diverse angle prompts. Single-word character name in captions is sufficient for training, though for Qwen Edit prompting we still need full visual descriptors.

### Realism Limitation — Plastic Skin 🎨

Community concern (consistent across threads):
- Qwen Image Edit results tend to look "slightly plasticy and airbrushed"
- Teeth and eyes don't look natural in non-portrait shots
- **Mitigation**: Run Qwen Edit output through a second-stage refiner model (Z-Image Turbo, Flux.2 Klein, SUPIR)
- **Not applicable for our pipeline yet** (would add latency), but noted for future quality pass

### Community Workflow Pattern for Max Quality ✅

From the highest-quality Reddit post (r/comfyui, score 283, 111 comments):

1. **Scale main image to ~1MP** (multiple of 112)
2. **Use reference latent nodes** for all reference images (not just conditioning)
3. **Patch the TextEncodeQwenImageEditPlus** to accept custom dimensions
4. **20 steps without Lightning LoRA** for max quality
5. **Negative conditioning**: Use the conditioning from the text encoder but zero it out and pipe into the negative — this is the "secret" to the best quality
6. **"I really mean it when I said I can't fully explain why this works so well"** — the zeroed negative conditioning trick produces notably better results than no negative

**Key community quotes**:
> "I was really unimpressed with qwen edit until I tried the official qwen chat version and was like 'wtf this is so much higher quality than my crappy workflow'. Then 10 hours of googling + trial-and-error later I got lucky"

> "Prompt adherence is already really good in English for 2509/2511. May be worth trying translated Chinese terms when it's having difficulty with a specific concept though."

### Facial Expression Tips from Community 💬

| Issue | Community Solution |
|---|---|
| Expression changes not taking effect | Use inpaint masking on just the face area |
| Character identity drifts between shots | Use reference latent nodes; consider consistence LoRA |
| Plastic/synthetic skin appearance | Add "natural skin texture, visible pores, slight imperfections" to prompt |
| Teef/eyes look unnatural | Describe them specifically: "teeth slightly visible", "eyes with visible iris detail" |
| All characters get same face | Each character needs their own reference image slot |
| Reference expression leaks into scenes | Use neutral expression reference sheets (matches our Phase 0B requirement) |

### Prompting in Chinese 🇨🇳

Community testing (r/comfyui): "Just tried it out and haven't noticed any difference. Prompt adherence is already really good in English." 
**Verdict**: No measurable improvement from Chinese prompts for 2511. Useful as a fallback if a specific concept is difficult to express in English.

---

*Updated 2026-05-19 with Reddit community research from r/StableDiffusion, r/LocalLLaMA, r/ComfyUI.*
*Sources: 8 threads with 600+ comments analyzed, including the definitive quality guide (score 283), face dataset workflow (score 984), AnyPose LoRA (score 846), Next Scene LoRA (score 725), and mask editing technique (score 497).*