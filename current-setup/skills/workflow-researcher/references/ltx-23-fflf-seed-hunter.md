# Worked Example: LTX 2.3 FFLF Seed Hunter (ltx23FFLFSeedHunter_v10.json)

Companion to `references/ltx-23-director.md`. This workflow exercises three patterns the
director example does NOT cover, so it's worth documenting separately:

1. **All loaders are inside a subgraph** — `nodes[]` has 74 entries but only 1 loader (a stray
   `VAELoader` for the tiny preview VAE). The real "Models" subgraph holds `UNETLoader`,
   `DualCLIPLoader`, `VAELoader`, `VAELoaderKJ`, `LatentUpscaleModelLoader`.
2. **Power Lora Loader (rgthree)** — uses the nested-dict `widgets_values` format, not a
   flat filename list.
3. **Seven custom node packs** — not just KJNodes + LTXVideo + WhatDreamsCost like the
   director workflow. Also: `rgthree-comfy`, `ComfyUI-VideoHelperSuite`, `ComfyUI-Easy-Use`,
   `ComfyUI-Impact-Pack`, `mxSlider`. Many of these would be missed if detection only looked
   for `*KJ` or `*Director*` class types.

## Workflow → Script Mapping

| Source | Destination | Notes |
|---|---|---|
| `current-setup/comfyui-workflows/ltx23FFLFSeedHunter_v10.json` | Preserved exactly (per skill 0.5) | Original filename kept — do NOT rename to kebab-case |
| `scripts/workflows/ltx-23-fflf-seed-hunter.sh` | Generated | Canonical kebab-case name (per skill 0.2) |
| `workflow:` frontmatter ID | `ltx23_FFLFSeedHunter_v10` | Matches the JSON filename |

## Model Manifest (8 files, ~44.5GB)

| Filename | Loader | Source Repo | Subdir | Size |
|---|---|---|---|---|
| `ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors` | `UNETLoader` (subgraph) | `Kijai/LTX2.3_comfy` → `diffusion_models/` | `diffusion_models/` | 25.2G |
| `LTX23_video_vae_bf16.safetensors` | `VAELoader` (subgraph) | `Kijai/LTX2.3_comfy` → `vae/` | `vae/` | 1.5G |
| `LTX23_audio_vae_bf16.safetensors` | `VAELoaderKJ` (subgraph) | `Kijai/LTX2.3_comfy` → `vae/` | `vae/` | 365M |
| `taeltx2_3.safetensors` | `VAELoader` (top-level!) | `Kijai/LTX2.3_comfy` → `vae/` | `vae/` | 23.5M |
| `gemma_3_12B_it_fp8_e4m3fn.safetensors` | `DualCLIPLoader` (subgraph) | `GitMylo/LTX-2-comfy_gemma_fp8_e4m3fn` (root) | `text_encoders/` | 13.2G |
| `ltx-2.3_text_projection_bf16.safetensors` | `DualCLIPLoader` (subgraph) | `Kijai/LTX2.3_comfy` → `text_encoders/` | `text_encoders/` | 2.3G |
| `LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors` | `Power Lora Loader (rgthree)` (top-level) | `Kijai/LTX2.3_comfy` → `loras/` | `loras/` | 617M |
| `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` | `LatentUpscaleModelLoader` (subgraph) | `Lightricks/LTX-2.3` (root) | `latent_upscale_models/` | 996M |

## Why This Workflow Is Tricky

### Pitfall A: The "Models" Subgraph Has All The Real Loaders

Quick scan of top-level `nodes[]` shows:
- 1 `VAELoader` (the tiny `taeltx2_3.safetensors` for `LTX2SamplingPreviewOverride`)
- 1 `Power Lora Loader (rgthree)` (the OmniNFT LoRA)
- 1 `LTXVAudioVAEDecode`, 1 `LTXVAudioVAEEncode` (disabled), 1 `LoadAudioUI`, etc.

If you stop there, you miss 5 critical loaders. You must recurse into
`definitions.subgraphs[].nodes[]` — find the subgraph named "Models" and extract
from there. The subgraph's id is `95bc2c44-bc14-4728-a0f4-f2cb37a09796`, which appears
as a UUID-typed node in the top-level `nodes[]`.

### Pitfall B: `gemma_3_12B_it_fp8_e4m3fn` Is Not In Comfy-Org/ltx-2

The first instinct is to look in `Comfy-Org/ltx-2` (where the official gemma files live).
That repo only ships:
- `gemma_3_12B_it.safetensors` (24.4G, bf16)
- `gemma_3_12B_it_fp8_scaled.safetensors` (13.2G, fp8 scaled)
- `gemma_3_12B_it_fp4_mixed.safetensors` (9.4G, fp4 mixed)

**None of those are `fp8_e4m3fn`.** The workflow's filename specifies that exact
quantization. The community FP8 e4m3fn build lives at
`GitMylo/LTX-2-comfy_gemma_fp8_e4m3fn` — a separate community repo by GitMylo. See
section 2b of the main supplementary skill for details.

Detection tip: if `Kijai/LTX2.3_comfy --dry-run` doesn't show the file under
`text_encoders/`, and `Comfy-Org/ltx-2` only has `fp8_scaled`/`fp4_mixed` variants,
try `hf models ls --search "gemma fp8 e4m3fn"` — GitMylo's repo comes up.

### Pitfall C: Power Lora Loader Widget Format

`Power Lora Loader (rgthree)` uses a nested-dict schema (see section 3b of the main
supplementary skill). The LoRA in this workflow is:

```python
node["widgets_values"] = [
    {},
    {"type": "PowerLoraLoaderHeaderWidget"},
    {"on": True, "lora": "LTX2\\LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors", "strength": 2, "strengthTwo": None},
    {},
    ""
]
```

The actual filename is `LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors` (after stripping the
`LTX2\` secondary-dir prefix). The bare filename is then found in
`Kijai/LTX2.3_comfy` at `loras/LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors` (616.9MB).

### Pitfall D: Seven Custom Node Packs

The workflow uses nodes from across the rgthree, Impact, VHS, and mxSlider ecosystems
in addition to the standard KJNodes + LTXVideo combo. Detection by `*KJ` class_type
suffix would miss most of these. The `properties.cnr_id` scan from section 7 of the
main supplementary skill catches them all.

## Final Script Shape

The generated `ltx-23-fflf-seed-hunter.sh` follows the
`qwen-image-edit-2511-4steps.sh` pattern (per the policy in section 6 of the main
supplementary skill):

- `set -e` for fail-fast
- Platform-aware `BASE_DIR` block (RunPod vs Vast.ai)
- Custom node install section: `comfy-cli` with manual `git clone` fallback
- Pip install of node requirements using the **ComfyUI's own Python** (`/venv/main/bin/python3` or `venv/bin/python3`)
- `mkdir -p` for all subdirs actually used
- Sources `_hf_download.sh` (underscore prefix)
- 8 sequential `hf_download` calls
- `supervisorctl restart comfyui` at the end

`workflow:` field in the frontmatter = `ltx23_FFLFSeedHunter_v10` (matches the
JSON filename, per skill 0.4).
