# FLUX.2 [klein] 9B FP8 Developer Reference Guide: I2I, Prompting, and Character Consistency Best Practices

This document compiles comprehensive research and best practices for leveraging Black Forest Labs' **FLUX.2 [klein] 9B FP8** model for image-to-image (I2I), image editing, and character-sheet-guided consistent scene generation. 

---

## 1. Model Architecture & Core Configurations

**FLUX.2 [klein] 9B** is a compact, high-performance rectified flow transformer model paired with a Qwen3 8B text embedder (for 9B variants). The FP8 quantized version is designed to run efficiently on consumer GPUs (e.g., RTX 3090/4090) while keeping visual quality comparable to the full BF16 model.

### Key Generation Parameters
To maintain quality and avoid noise artifacts, adhere strictly to the following parameters:

| Parameter | Recommended Value | Behavior & Guidance |
| :--- | :--- | :--- |
| **Sampling Steps** | `4` | It is a step-distilled flow-matching model. Higher steps (e.g., 20–30) yield no quality improvement and only increase latency. |
| **CFG (Guidance)** | `1.0` | Must be exactly 1.0. Higher CFG values cause severe color burning, saturation shifts, and noise artifacts. |
| **Sampler / Scheduler** | `euler` / `simple` (or `normal`) | Standard flow-matching settings. Do not use standard SD samplers like Euler a, DPM++, or UniPC. |
| **Native Resolution** | `1344×768` (16:9) or `1024×1024` (1:1) | Optimized at ~1 megapixel. Fixed aspect ratios prevent composition distortion. |
| **VRAM Consumption** | ~13GB - 29GB | Standard 9B FP8 requires ~29GB VRAM in full mode. In ComfyUI with lowvram, it runs comfortably in ~12-16GB. |

---

## 2. Image-to-Image (I2I) and Editing Best Practices

FLUX.2 Klein unifies image generation and editing in a single architecture. In ComfyUI, this is achieved using **Reference Latents** instead of standard noise blending.

### The Denoise Paradigm
* **ReferenceLatent Attention Editing**: Unlike traditional SD where you encode an image and add noise (denoise < 0.8), Flux Klein feeds reference image latents directly into the model's cross-attention layers. 
* **Sweet Spot**: 
  - To generate a new scene based on references, set denoise to **1.0** (using an `EmptyLatentImage` for structural canvas and feeding references through the conditioning stream).
  - If you need a traditional image edit (e.g. changing clothes or backgrounds on a base image), feed the base image through `VAEEncode` (instead of empty latent) and set denoise to **0.5 – 0.85**. 
  - If denoise is set below `0.85` on an empty latent, severe structural distortion will occur. Always use a VAE-encoded image if you want lower denoise values.

### Color Matching & Bias Correction
FLUX.2 Klein has a known **red-saturation bias** that can make skin tones or scenes appear excessively warm or sunburned.
* **Prompting fix**: Append color grading terms to the end of the prompt, such as: `"balanced white balance, color graded, natural skin tones, daylight temperature"`.
* **Workflow fix**: Use the `ColorMatchV2` node (MKL algorithm) to extract and re-apply color distributions from the original character sheet or base image to the generated output.

---

## 3. Prompting Guidance & Syntax

Because FLUX.2 uses a Qwen text/image transformer, it responds to natural, grammatically correct English instead of keyword tag salads.

### The Prompt Structure Formula
Organize prompts hierarchically to ensure the Qwen embedder prioritizes elements correctly (tokens at the start carry the highest weight):

1. **Subject Description**: Specify the characters, their key identities, and features.
2. **Action & Pose**: Detailed description of movements, postures, and spatial relations.
3. **Style & Medium**: E.g., `"3D Pixar-style animation, rich tactile textures"` or `"photorealistic cinematic still"`.
4. **Environment/Context**: Scene setting, background details, time of day, atmosphere.
5. **Lighting**: E.g., `"warm golden hour rim light, soft shadows, dappled sunlight"`.
6. **Camera & Framing**: E.g., `"medium-wide shot, eye-level camera, shallow depth of field"`.

### Crucial Rules:
* **No Traditional Negative Prompts**: Distilled flow models do not support traditional negative prompts. Describing what *not* to generate (e.g., "no stripes") in a positive prompt will actually cause the model to generate that element. Instead, describe what *is* present (e.g., "completely plain orange fur").
* **Negative-Aware Guidance (NAG)**: For advanced negative conditioning, use specialized ComfyUI NAG nodes (scale set to `5.0` to `7.0`) to subtract unwanted details.
* **Exact Color Control**: Use CSS color names or exact HEX codes (e.g., `#FF6B35`) to specify clothes or product colors.
* **Typography/Text Rendering**: Place text in single or double quotes, e.g., `The text "OPEN" in clean white sans-serif font centered on the glass door`.

---

## 4. Multi-Reference & Character Sheet Consistency

For character consistency, our goal is to feed a character sheet (or cropped character turnarounds) into ComfyUI so the model draws features directly from them.

### Standard `ReferenceLatent` Chaining
In default ComfyUI configurations, references are chained sequentially:
* **Chaining Logic**: 
  - Positive text conditioning feeds into the first `ReferenceLatent` node, which connects to the latent of reference image 1.
  - The output of the first node feeds as the conditioning input to the second `ReferenceLatent` node (which connects to the latent of reference image 2), and so on.
  - The negative conditioning (generated via `ConditioningZeroOut`) is chained through a parallel set of `ReferenceLatent` nodes for each image.
  - The final outputs of the positive and negative chains connect to the `CFGGuider` or `KSampler`.

---

## 5. Advanced Character Steering: ComfyUI-Flux2Klein-Enhancer

For advanced consistency control, the community-developed custom node suite **ComfyUI-Flux2Klein-Enhancer** (by `capitan01R`) introduces specialized nodes that bypass the limitations of basic chaining.

### A. `IdentityFeatureTransferFinal` Node
This node injects character features into the diffusion model's double and single blocks with fine-grained block-level weight controls.

#### Core Parameters:
* **`preset`**: Defines the stiffness of identity preservation.
  - `HARD_LOCK` (Default): Strict identity preservation (best for face likeness).
  - `MID_LOCK`: Balanced style and feature transfer.
  - `SOFT_LOCK`: Soft styling, allows more pose/environmental flexibility.
  - `custom`: Manually adjust double and single block strings.
* **`similarity_floor`** (`0.040` default): The threshold for cosine similarity. Higher values (e.g., `0.10`) force stricter identity matching but can cause grid artifacts.
* **`softmax_temperature`** (`0.025` default): Controls the sharpness of feature mapping. Lower values make mapping sharper.
* **`double_blocks`** (`"0-7:mid_img=0.55"` default): Specifies which double attention blocks transfer features and at what strength.
* **`single_blocks`** (`"0:mid_img=0.22; 1:mid_img=0.24; 3:mid_img=0.28..."` default): Fine-tunes attention on individual single blocks.
* **`subject_mask_1` to `subject_mask_8`**: Optional mask inputs. **CRITICAL FOR CHARACTER SHEETS**: Pass cropped subject masks here to restrict the model from learning background noise or other sheet details.

### B. `Flux2KleinMultiReferenceLatent` Node
Replaces the complex chained `ReferenceLatent` nodes with a single, clean bank.
* Takes a base `conditioning` input.
* Exposes 8 distinct latent ports (`latent_1` to `latent_8`) to load VAE-encoded crops of character references.
* Outputs unified conditioning directly to the KSampler.

---

## 6. Pipeline Integration for Scene and Shot Generation

When using a character sheet to generate specific shots (e.g. Toby and Taro interacting in a jungle), use the following pipeline strategy:

### Step 1: Pre-Processing the Character Sheet
1. **Crop to Single Subjects**: Crop the multi-character sheet into individual high-resolution images of each character (up to 4, which is the VRAM limit).
2. **Remove Backgrounds**: Apply transparency/background removal or create precise character masks. 
3. **Feed to VAE**: Pass each cropped character image through `VAEEncode` to convert them into latents for the `MultiReferenceLatent` node.
4. **Link Masks**: Connect the corresponding character masks to the `subject_mask_x` inputs of the `IdentityFeatureTransferFinal` node.

### Step 2: Prompt Slot Mapping
Align the order of character description mapping headers with the reference indices.

```text
Characters in this scene must match the provided reference images exactly:
- Toby (first reference / latent_1): A young round orange tiger cub, big blue eyes, stripe-less plain peach-orange fur.
- Taro (second reference / latent_2): An older lean tiger with magnificent black stripes over orange fur, confident golden eyes.

[Scene Action]: Toby stands in the sunlit clearing, looking down at his own stripe-less belly in confusion, while Taro stands beside him with his stripes gleaming. Warm jungle clearing with mottled sunlight streaming through the canopy. 3D Pixar-style animation, cinematic lighting, rich textures, depth of field.
```

### Step 3: Scene Partitioning for Large Casts
* **The 4-Character Limit**: Flux 2 Klein has a creative and memory limit of **4 references**. If a scene contains 5 or more characters, the orchestrator script MUST:
  - Exclude background/unimportant characters from the reference bank and positive prompt mapping header.
  - Or partition the scene into multiple separate close-up shots containing $\le 4$ active characters.
