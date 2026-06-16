# Worked Example: `ltx-23-director-subgraphs.json`

A canonical end-to-end walkthrough of the full `workflow-researcher` + this patch skill in action. Use this as the reference pattern for any future ComfyUI workflow that:

- Uses subgraphs (definitions/subgraphs) instead of a flat `nodes[]`
- Requires **multiple** custom node packs (not just one)
- Includes an LTX 2.3 Director-style 2-stage video workflow

The resulting script (`workflows/setup/ltx-23-director-subgraphs.sh` in the auto-startups-vast repo) is the current standard in the repo and the script this skill's policy section is written against.

## Source workflow

- File: `workflows/comfyui/ltx-23-director-subgraphs.json` (renamed from `LTX_Director_Example_Workflow_Subgraphs_v2_workflow.json`)
- Author: WhatDreamsCost
- Workflow type: 2-stage LTX 2.3 video gen (Stage #1 base → Stage #2 spatial upscaler v1.1)
- Top-level `nodes[]` has 7 entries: 1 `LTXDirector` (timeline editor), 1 `SaveVideo`, 4 subgraph instances, 1 `MarkdownNote` (FAQ)
- `extra.prompt` is absent (subgraph workflows don't have it)
- All real loaders live in `definitions.subgraphs[].nodes[]`

## Subgraph inventory

| Subgraph | Nodes | What it does |
|---|---|---|
| `Model Loader` | 7 | Loads checkpoint, applies distilled LoRA, sets LTX2 sampling preview override, loads 3 VAEs + 1 DualCLIPLoader for the gemma+projection pair |
| `Stage #1` | 10 | First sampling pass — scheduler, sampler, KSamplerSelect, latent concat/separation, director guide, CFG, conditioning, RandomNoise |
| `Stage #2` | 11 | Second sampling pass — same structure as Stage #1 + LatentUpscaleModelLoader + LTXVLatentUpsampler + LTXVCropGuides |
| `Decode` | 3 | Final decode: `LTXVAudioVAEDecode` + `VAEDecode` + `CreateVideo` |

## Extracted model manifest (8 unique files, ~46.3GB)

| Filename | Size | Loader | Subdir | Source repo |
|---|---|---|---|---|
| `ltx-2.3-22b-dev-fp8.safetensors` | 29.1G | `CheckpointLoaderSimple` | `checkpoints/` | `Lightricks/LTX-2.3-fp8` |
| `ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors` | 2.6G | `LoraLoaderModelOnly` | `loras/` | `Kijai/LTX2.3_comfy` |
| `taeltx2_3.safetensors` | 23.5M | `VAELoaderKJ` | `vae/` | `Kijai/LTX2.3_comfy` |
| `LTX23_audio_vae_bf16.safetensors` | 365M | `VAELoaderKJ` | `vae/` | `Kijai/LTX2.3_comfy` |
| `LTX23_video_vae_bf16.safetensors` | 1.5G | `VAELoaderKJ` | `vae/` | `Kijai/LTX2.3_comfy` |
| `gemma_3_12B_it_fp4_mixed.safetensors` | 9.4G | `DualCLIPLoader.clip_name1` | `text_encoders/` | `Comfy-Org/ltx-2` (`split_files/text_encoders/`) |
| `ltx-2.3_text_projection_bf16.safetensors` | 2.3G | `DualCLIPLoader.clip_name2` | `text_encoders/` | `Kijai/LTX2.3_comfy` |
| `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` | 996M | `LatentUpscaleModelLoader` | `latent_upscale_models/` | `Lightricks/LTX-2.3` |

## Custom node packs required (3)

Discovered by reading `properties.cnr_id` on every node:

1. **`kijai/ComfyUI-KJNodes`** — provides `LTX2SamplingPreviewOverride`, `VAELoaderKJ`
2. **`Lightricks/ComfyUI-LTXVideo`** — provides core LTX 2.3 nodes used across both stages
3. **`WhatDreamsCost/WhatDreamsCost-ComfyUI`** — provides `LTXDirector`, `LTXDirectorGuide` (used twice in Stage #1 and Stage #2)

## URL research notes

- The `Lightricks/LTX-2.3-fp8` repo is **separate** from `Lightricks/LTX-2.3`. It only contains the 22B dev and distilled FP8 transformers. Always verify with `curl -sI` — a 404 on `Lightricks/LTX-2.3` for the FP8 file doesn't mean the file doesn't exist.
- `gemma_3_12B_it_fp4_mixed.safetensors` lives in `Comfy-Org/ltx-2` (v2 repo, not v2.3). The path is `split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors` — note the `split_files/` prefix.
- The `LoraLoaderModelOnly` widget value `ltx2\ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors` has a `ltx2\` prefix from ComfyUI's "secondary directory" display. Strip it when looking up the file in HF — the actual filename has no prefix.

## Frontmatter (matches repo standard from `qwen-image-edit-2511-4steps.sh`)

```bash
# ---
# name: LTX 2.3 Director (Subgraphs)
# workflow: ltx-23-director-subgraphs
# aliases: [ltx director, ltx 2.3 director, ltx23 director, whatdreamscost, ltx-director-subgraphs]
# description: ...
# size: ~46.2GB
# min_vram: 24GB
# nodes: [ComfyUI-KJNodes, ComfyUI-LTXVideo, WhatDreamsCost-ComfyUI]
# ---
```

The `nodes:` field lists the three custom node packs the script will install.

## Script structure (the current standard)

1. **Platform-aware `BASE_DIR` detection** — `/workspace/runpod-slim/ComfyUI` (RunPod) vs `/workspace/ComfyUI` (Vast.ai)
2. **ComfyUI Python detection** — `/venv/main/bin/python3` (Vast.ai) > `venv/bin/python3` > `.venv-cu128/bin/python3` (RunPod) > system
3. **Custom node install** — `comfy node install` for each pack, with `git clone` fallback to `custom_nodes/` if comfy-cli not present
4. **Pip deps install** — for each pack's `requirements.txt`, into the detected ComfyUI Python
5. **Models download** — 8 `hf_download` calls, with `[N/8]` progress echoes
6. **ComfyUI restart** — `supervisorctl restart comfyui`, with manual-launch fallback

## Pitfalls encountered (all addressed in this skill's SKILL.md)

| Pitfall | Resolution |
|---|---|
| Top-level `nodes[]` looked empty (7 UUID nodes) | Recurse into `definitions.subgraphs[].nodes[]` |
| `LoraLoaderModelOnly` widget value had `ltx2\` prefix | Strip prefix before HF lookup; actual filename has no prefix |
| `Lightricks/LTX-2.3-fp8` 404 on first try | It's a separate repo from `Lightricks/LTX-2.3` — confirmed by `curl -sI` |
| `cnr_id` was the discovery mechanism for node packs | Always check `properties.cnr_id` — `whatdreamscost-comfyui`, `comfyui-kjnodes` etc. map to specific GitHub repos |
| Older scripts only installed one pack + no restart | New policy: download script is fully self-contained; installs all required packs and restarts ComfyUI |
