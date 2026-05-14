# Story-to-Video: Cost Optimization & Open Model Research

Date: 2026-05-14 (Updated)

---

## 1. Context & Problem Statement

The current story-to-video pipeline uses **Gemini 2.5 Flash Image (Nano Banana)** for both character reference sheets and scene images. At ~50 images per story, the API cost adds up:

| Scenario | Standard ($0.039/img) | Batch/Flex ($0.0195/img) |
|---|---:|---:|
| 1 story (50 images) | $1.95 | $0.975 |
| 10 stories/month | $19.50 | $9.75 |
| 30 stories/month | $58.50 | $29.25 |

> [!IMPORTANT]
> Input-token costs for reference images are extra. With 1-5 character sheets per scene call, the real per-story cost could be **$3-5** at standard pricing.

### The Hybrid Strategy

- **Keep Nano Banana for character reference sheets only** (2-10 per story → ~$0.08-$0.39 per story)
- **Use a self-hosted open-source model on rented RTX 3090 for scene rendering** (~40-48 scene images per story)
- **Keep LTX 2.3 video prompt phase unchanged**

This shifts ~90% of image generation to local GPU, where the only cost is rental time.

### Resolved Decisions

| Question | Answer |
|---|---|
| **Commercial use?** | Yes — the generated images will be used commercially (the model weights themselves won't be redistributed). This means we need Apache 2.0, MIT, or a license that permits commercial use of *outputs*. |
| **Target resolution?** | **Landscape 1280×720** (16:9) — the recommended LTX 2.3 I2V input resolution for landscape video. Scene images should be generated at this resolution. All LTX dimensions must be divisible by 32. |
| **Self-hosted vs API?** | **Self-hosted** on Vast.ai / RunPod. RTX 3090 (24 GB VRAM) is the target GPU. |

---

## 2. LTX 2.3 I2V — Preferred Input Resolutions

Since the scene images feed directly into LTX 2.3 for video generation, the scene model must output at these resolutions:

| Aspect Ratio | Resolution | Use Case |
|---|---|---|
| **16:9 Landscape** | **1280 × 720** | ⭐ Primary — standard HD, lower VRAM, fast |
| 16:9 Landscape | 1920 × 1080 | Full HD — higher quality, more VRAM |
| 9:16 Portrait | 720 × 1280 | Vertical/mobile content |
| 1:1 Square | 1024 × 1024 | Fallback only |

> [!IMPORTANT]
> All dimensions must be divisible by 32. Input images should match the target video aspect ratio exactly — do not generate square and crop to landscape.

---

## 3. Requirements For Scene Model

| Requirement | Priority | Notes |
|---|---|---|
| Multi-reference identity preservation | **Critical** | Feed 1-5 character sheets, get consistent characters in new scene |
| Cartoon/Pixar style fidelity | **Critical** | Default art style is "Pixar-style 3D animation" |
| Run on RTX 3090 (24GB VRAM) | **Critical** | Our target rental GPU |
| Output 1280×720 landscape | **Critical** | Must match LTX 2.3 I2V input |
| ComfyUI integration | **High** | Our existing workflow platform |
| Image-to-image / reference conditioning | **High** | Not just text-to-image |
| Commercial output license | **High** | Generated images used commercially |
| Fast inference (<30s per image) | **Medium** | 50 images × 30s = 25 min per story is acceptable |

---

## 4. Candidate Model Deep Dive

### 4.1 FLUX.2 [klein] 4B

| Spec | Value |
|---|---|
| Parameters | 4B |
| VRAM | ~13 GB |
| License | **Apache 2.0** ✅ commercial outputs OK |
| Multi-ref support | Up to 4 reference images (native) |
| Inference speed | Sub-second with distilled (4-step) variant |
| ComfyUI support | Mature, first-party and community nodes |

**Strengths:**
- Native multi-reference editing — upload reference images and assign roles (face, clothing, style)
- Apache 2.0 = zero licensing risk for commercial outputs
- 13 GB VRAM leaves 11 GB headroom for ControlNets, LoRAs, upscalers
- "Lock" presets (Hard Lock, Soft Lock, Median Lock) for identity adherence control
- Sub-second inference with distilled variant → 50 scenes in under 2 minutes

**Concerns:**
- 4B params may struggle with complex multi-character compositions
- Max 4 refs (our design wants 5) — text-only fallback for 5th character
- Cartoon/Pixar style adherence needs testing

---

### 4.2 FLUX.2 [klein] 9B

| Spec | Value |
|---|---|
| Parameters | 9B |
| VRAM | ~29 GB native / **~19-20 GB FP8 quantized** |
| License | **FLUX Non-Commercial License** ⚠️ |
| Multi-ref support | Up to 4 reference images (native) |
| Inference speed | Fast (distilled 4-step variant available) |
| ComfyUI support | Mature |

**Strengths:**
- Significant quality jump over 4B — better nuance, detail retention, complex compositions
- FP8 quantized fits on RTX 3090 at ~19-20 GB
- Same architecture as 4B, so same Lock presets and multi-ref workflow
- Distilled variant still fast

**Concerns:**
- **Non-Commercial License** — the license restricts use of the model weights to non-commercial purposes. However, since we're using outputs commercially (not redistributing weights), this needs careful license review. BFL may consider generated outputs as commercial use.
- 19-20 GB FP8 leaves only ~4 GB headroom — tight for LoRAs/ControlNets
- Still max 4 refs like klein 4B

> [!WARNING]
> The FLUX Non-Commercial License likely restricts commercial use of outputs. Need to verify BFL's exact terms before relying on this for production.

---

### 4.3 FLUX.2 [dev] 32B — Quality Benchmark Only

| Spec | Value |
|---|---|
| Parameters | 32B |
| VRAM | ~54-90 GB full; needs weight streaming on RTX 3090 |
| License | **FLUX Non-Commercial License** ⚠️ |
| Multi-ref support | Up to 10 reference images (native) |
| Inference speed | Slow on RTX 3090 (offloading penalty) |
| ComfyUI support | Mature |

**Role:** Quality ceiling benchmark only. Same licensing concern as klein 9B, plus too heavy for single RTX 3090.

---

### 4.4 Qwen-Image-Edit-2509 (Superseded)

| Spec | Value |
|---|---|
| Parameters | ~20B (MMDiT) |
| VRAM | ~22.5 GB FP8 / 12-16 GB GGUF |
| License | Qwen license |
| Multi-ref support | Up to 3 input images |
| Inference speed | Moderate; Lightning LoRA (8-step) available |
| ComfyUI support | Good, dedicated nodes |

**Status:** Superseded by 2511. Included for reference only — test 2511 instead.

---

### 4.5 Qwen-Image-Edit-2511 (Plus) ⭐ NEW

| Spec | Value |
|---|---|
| Parameters | 20B (MMDiT, upgraded from 2509) |
| VRAM | **~6 GB+ with FP8/optimized loaders** / 12-16 GB GGUF / 35 GB+ full BF16 |
| License | **Apache 2.0** ✅ commercial outputs OK |
| Multi-ref support | Up to 3 (standard) / **up to 5 in advanced ComfyUI configs** |
| Inference speed | Moderate; Lightning LoRA compatible |
| ComfyUI support | Good, updated nodes required (`zero_cond_t` config) |

**Strengths:**
- **Apache 2.0** — fully commercial, replaces the older Qwen license
- Massive VRAM improvement: runs from ~6 GB+ with FP8 optimized loaders (vs 22.5 GB for 2509)
- **Up to 5 input images** in advanced ComfyUI testing — matches our 5-ref design!
- Improved multi-person consistency over 2509 — fewer identity swaps in group scenes
- Enhanced geometric reasoning and reduced image drift across editing passes
- Integrated LoRA support for style variations
- Better non-square aspect ratio support — **1216×832 landscape reported to produce cleaner results** than square
- Already in our ecosystem (we have `qwen-image-edit.json` — would need workflow update)
- Identity-preserving editing is the core design purpose

**Concerns:**
- Still fundamentally an "editing" model — scene composition may need creative prompting
- Community is still migrating from 2509; some ComfyUI nodes may need updates
- 5-image support is "advanced testing" — standard is still 3

**Verdict:** Major upgrade over 2509. Apache 2.0 + potential 5 refs + tiny VRAM footprint makes this a strong contender.

---

### 4.6 HiDream-O1-Image ⭐

| Spec | Value |
|---|---|
| Parameters | 8B |
| VRAM | ~10 GB FP8 / ~17-20 GB full precision |
| License | **MIT** ✅ commercial outputs OK |
| Multi-ref support | Up to 12 reference images in ComfyUI |
| Inference speed | 28 steps (Dev), 50 steps (Full) |
| ComfyUI support | Community nodes (`HiDream_O1-ComfyUI`), new but functional |

**Strengths:**
- **12 reference images** — far beyond our 5-ref need
- MIT license — most commercially permissive possible
- 10 GB FP8 leaves 14 GB headroom on RTX 3090
- Native storyboard generation — explicitly designed for sequential scene consistency
- Subject-driven personalization is a first-class feature
- Built-in reasoning agent resolves layout and spatial relationships before generation
- No VAE dependency — architecturally simpler

**Concerns:**
- Very new (May 2026) — ecosystem maturity uncertain
- Grid artifacts reported with Full variant; **Dev variant recommended**
- Pixel-level architecture is computationally intensive per pixel
- Needs FlashAttention/SageAttention for practical speed
- Limited real-world examples of Pixar-style character consistency

> [!NOTE]
> HiDream-O1 **Pro** (200B+, closed-source, API-only) exists but is irrelevant for self-hosted RTX 3090 use. We are evaluating the open-source 8B model only.

---

### 4.7 HunyuanImage 3.0 Instruct — Deprioritized

| Spec | Value |
|---|---|
| Parameters | 80B MoE (13B active per token) |
| VRAM | 8× 80GB recommended |
| License | Tencent custom license |
| Multi-ref support | Up to 3 images |
| fal.ai cost | $0.09 per megapixel |

**Verdict:** Skip. Cannot self-host on RTX 3090. API cost higher than Gemini. Defeats the goal.

---

## 5. Full Comparison Matrix

| Feature | FLUX.2 klein 4B | FLUX.2 klein 9B | Qwen-Edit-2511 | HiDream-O1 | FLUX.2 dev 32B | Hunyuan 3.0 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **VRAM (RTX 3090)** | ✅ 13 GB | ⚠️ 19-20 GB FP8 | ✅ 6-16 GB | ✅ 10 GB FP8 | ❌ Offload | ❌ Impossible |
| **Max refs** | 4 | 4 | 3-5 | 12 | 10 | 3 |
| **License** | Apache 2.0 ✅ | Non-Commercial ⚠️ | Apache 2.0 ✅ | MIT ✅ | Non-Commercial ⚠️ | Custom ⚠️ |
| **Speed** | ⚡ Sub-second | ⚡ Fast | 🔄 Moderate | 🔄 28 steps | 🐌 Slow | N/A |
| **ComfyUI** | ✅ Mature | ✅ Mature | ✅ Good | ⚠️ New | ✅ Mature | ⚠️ Heavy |
| **Identity lock** | Hard/Soft Lock | Hard/Soft Lock | ControlNet | Subject-driven | Hard/Soft Lock | Fusion |
| **Our 5-ref design** | ⚠️ Max 4 | ⚠️ Max 4 | ⚠️ 3 std / 5 adv | ✅ Max 12 | ✅ Max 10 | ❌ Max 3 |
| **Commercial outputs** | ✅ Yes | ⚠️ Check BFL | ✅ Yes | ✅ Yes | ⚠️ Check BFL | ⚠️ Check |
| **Landscape 1280×720** | ✅ | ✅ | ✅ Better non-square | ✅ Up to 2048² | ✅ | N/A |

---

## 5A. Competition Table: Qwen-Edit-2511 vs HiDream-O1 vs FLUX.2 klein 9B

Scope: scene generation for our story-to-video pipeline using Nano Banana character sheets as references.

Scoring: 10 = best fit for our use case. The final score is not a generic image-model leaderboard; it weights our needs: reference-character consistency, multi-character scene composition, RTX 3090 self-hosting, commercial safety, ComfyUI maturity, speed, and benchmark/review confidence.

| Model | Official Positioning | Benchmarks / Reviews Found | Strengths For Us | Risks For Us | License | RTX 3090 Fit | Score |
|---|---|---|---|---|---|---|---:|
| **Qwen-Image-Edit-2511** | 20B image-to-image editing model; improved image drift, character consistency, multi-person consistency, LoRA support, geometric reasoning | Lumenfall editing tests show competitive ELO bands around 1177-1269 depending on task. ComfyUI docs highlight improved character and multi-person consistency. Reddit reports are mixed: some users call it a major upgrade, others report over-smoothing or weak second-reference recognition in certain workflows. | Best match for identity-preserving edits; Apache 2.0; mature enough in ComfyUI; directly supports multi-image prompts; strong for characters and group shots. | More edit-oriented than pure scene generation; standard workflows often cite 2-3 input images, while 5-image support is workflow-dependent; quality depends heavily on correct ComfyUI setup. | Apache 2.0 | Good with optimized/quantized loaders | **8.6 / 10** |
| **FLUX.2 klein 9B** | 9B unified text-to-image + image-to-image model with multi-reference editing; BFL calls it the quality/latency frontier of the Klein family | Replicate and BFL describe native multi-reference editing. Aigazine reports Artificial Analysis open-weight editing ELO: FLUX.2 klein 9B 1158, Qwen-Edit-2511 1151, FLUX.2 dev Turbo 1149. Reddit users praise speed and quality, but some report poor reference merging unless workflow/prompting is tuned. | Best independent editing benchmark signal; fast 4-step distilled model; strong visual quality; unified generation/editing; mature Diffusers/ComfyUI support. | First-party BFL/Hugging Face says FLUX Non-Commercial License; native VRAM around 29GB, though quantized/offload can fit; reference blending can merge identities if not carefully conditioned. | FLUX Non-Commercial | Marginal native; likely okay quantized/offload | **7.8 / 10** if non-commercial; **5.8 / 10** for commercial production |
| **HiDream-O1-Image** | 8B pixel-level unified transformer supporting text-to-image, editing, subject-driven personalization, and storyboard generation up to 2048x2048 | Official paper/model card claims parity or better than much larger models and #8 in Artificial Analysis Text-to-Image Arena. User-review evidence is still thin because release was May 2026; early Reddit discussion mostly repeats official claims rather than production tests. | Very promising for our exact long-term goal: subject-driven personalization and storyboard generation; MIT license; good theoretical fit for sequential story scenes. | Newest and least proven; ComfyUI/workflow maturity uncertain; editing tasks recommend full model; practical speed/VRAM and character-sheet consistency need hands-on testing. | MIT | Likely good in optimized Dev/FP8 paths; verify | **7.4 / 10** now; high upside after testing |

### Ranking For Our Pipeline

1. **Qwen-Image-Edit-2511** — best first production test because it combines commercial-safe licensing, character consistency focus, and working ComfyUI support.
2. **HiDream-O1-Image** — best research/upside candidate because storyboard and subject-driven personalization map directly to story-to-video, but it needs validation.
3. **FLUX.2 klein 9B** — likely strongest quality/benchmark competitor, but the non-commercial license makes it risky for our commercial pipeline unless BFL confirms acceptable terms or we buy commercial access.

### Benchmark Confidence

| Model | Benchmark Confidence | Why |
|---|---:|---|
| FLUX.2 klein 9B | High | Independent preference benchmark reporting exists, plus first-party and hosted-provider support. |
| Qwen-Image-Edit-2511 | Medium-High | Independent editing test pages and many community tests exist, but workflow variance is large. |
| HiDream-O1-Image | Low-Medium | Strong technical report and model-card claims, but too new for broad independent review evidence. |

### Source Notes

- BFL official sources list FLUX.2 klein 9B under the FLUX Non-Commercial License, even though some third-party articles describe Klein broadly as Apache 2.0. Use the first-party BFL/Hugging Face license for decisions.
- Qwen-Image-Edit-2511's Hugging Face page lists Apache 2.0 and explicitly calls out reduced drift, improved character consistency, and multi-person consistency.
- HiDream-O1's Hugging Face page lists MIT and describes text-to-image, editing, subject-driven personalization, and storyboard generation in one model.

Sources:

- https://huggingface.co/Qwen/Qwen-Image-Edit-2511
- https://docs.comfy.org/tutorials/image/qwen/qwen-image-edit-2511
- https://lumenfall.ai/models/alibaba/qwen-image-edit-2511/benchmarks
- https://huggingface.co/black-forest-labs/FLUX.2-klein-9B
- https://github.com/black-forest-labs/flux2
- https://bfl.ai/models/flux-2-klein
- https://replicate.com/black-forest-labs/flux-2-klein-9b-base
- https://huggingface.co/HiDream-ai/HiDream-O1-Image
- https://arxiv.org/abs/2605.11061

---

## 6. GPU Rental Cost Analysis

### RTX 3090 on Vast.ai

| Metric | Value |
|---|---|
| Typical price | $0.13 – $0.22/hr |
| Low end (spot) | $0.05/hr |
| VRAM | 24 GB |

### Cost Per Story (50 scene images at 1280×720)

| Model | Est. time for 50 imgs | GPU cost per story |
|---|---|---|
| FLUX.2 klein 4B (sub-second) | ~2-5 min | **$0.01 – $0.02** |
| Qwen-Edit-2511 + Lightning | ~10-20 min | **$0.02 – $0.07** |
| HiDream-O1 FP8 (28 steps) | ~15-25 min | **$0.03 – $0.09** |
| FLUX.2 klein 9B FP8 | ~5-10 min | **$0.01 – $0.04** |

### Monthly Projection (30 stories/month)

| Cost item | Gemini (current) | Hybrid (proposed) |
|---|---:|---:|
| Character sheets (Nano Banana) | included | ~$3-12 |
| Scene images | $58.50 standard | **$0.30 – $2.70** (GPU rental) |
| **Total** | **~$58.50** | **~$3 – $15** |

> [!TIP]
> The hybrid approach cuts monthly image generation costs by **75-95%**.

---

## 7. Updated Recommendation: Testing Order

### Tier 1 — Test First (Commercial-Safe, RTX 3090 Friendly)

1. **Qwen-Image-Edit-2511** — Apache 2.0, tiny VRAM (6-16 GB), up to 5 refs in advanced mode, best non-square support, already in our ecosystem. Start here.
2. **HiDream-O1-Image (Dev)** — MIT, 10 GB FP8, 12 refs, native storyboard mode. Most feature-rich but newest/least proven.
3. **FLUX.2 [klein] 4B** — Apache 2.0, 13 GB, sub-second speed, mature ComfyUI. Fastest option but max 4 refs.

### Tier 2 — Test If Tier 1 Quality Disappoints

4. **FLUX.2 [klein] 9B FP8** — Better quality than 4B but Non-Commercial license is a risk. Only if BFL confirms commercial output use is permitted.

### Benchmark Only

5. **FLUX.2 [dev] 32B** — Quality ceiling reference, not production viable.

### Skip

6. **HunyuanImage 3.0** — Cannot self-host, API cost higher than Gemini.
7. **Qwen-Image-Edit-2509** — Superseded by 2511.

---

## 8. Proposed Test Protocol

For each Tier 1 model, run the same standardized test:

1. **Input:** 2-3 Nano Banana character reference sheets (from our existing pipeline)
2. **Output resolution:** 1280×720 landscape (matching LTX 2.3 I2V input)
3. **Test scenes:**
   - Scene A: 1 character, close-up, simple background
   - Scene B: 2 characters interacting, medium shot
   - Scene C: 3+ characters, wide shot, complex setting
4. **Style:** "Pixar-style 3D animation, rich lighting, expressive characters"
5. **Evaluate on:**
   - Character identity consistency (does it look like the reference?)
   - Art style adherence (does it maintain Pixar look?)
   - Multi-character composition (do 2-3 characters coexist well?)
   - Landscape aspect ratio quality (no stretched/cropped artifacts)
   - Speed (time per image)
   - VRAM usage (headroom for LoRAs/ControlNets?)

---

## 9. Next Steps

- [ ] Provision RTX 3090 on Vast.ai
- [ ] Install ComfyUI with required custom nodes for test models
- [ ] Generate 2-3 character reference sheets using Nano Banana
- [ ] Run test protocol on Qwen-Edit-2511 → HiDream-O1 → FLUX.2 klein 4B
- [ ] Compare results and select production model
- [ ] Update `generate_story_assets.py` to support the chosen model

---

## 10. Sources

- [FLUX.2 GitHub](https://github.com/black-forest-labs/flux2)
- [FLUX.2 dev on HuggingFace](https://huggingface.co/black-forest-labs/FLUX.2-dev)
- [Qwen-Image-Edit-2509 on HuggingFace](https://huggingface.co/Qwen/Qwen-Image-Edit-2509)
- [Qwen-Image-Edit-2511 (community reports and model card)]
- [HiDream-O1-Image on HuggingFace](https://huggingface.co/HiDream-ai/HiDream-O1-Image)
- [HunyuanImage 3.0 GitHub](https://github.com/Tencent-Hunyuan/HunyuanImage-3.0)
- [Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [LTX Video Documentation](https://ltx.video)
- [Vast.ai GPU Marketplace](https://vast.ai)
