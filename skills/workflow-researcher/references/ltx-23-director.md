# Worked Example: `LTX_Director_2_Workflow_Hotfix.json`

> **Note:** This example originally walked through `ltx-23-director-subgraphs.json` (the 2-stage subgraph variant using a 29.1GB dev-FP8 transformer + 2.6GB distilled LoRA combo). The subgraph variant was deprecated in July 2026 in favour of the **hotfix** workflow, which uses a single 25.2GB distilled-1.1 FP8 transformer-only checkpoint (~6.5GB savings, ~15min faster to download).

A canonical end-to-end walkthrough of the full `workflow-researcher` + this patch skill in action. Use this as the reference pattern for any future ComfyUI workflow that:

- Uses subgraphs (definitions/subgraphs) instead of a flat `nodes[]` — **OR** a flat `nodes[]` with many custom nodes (the hotfix variant is flat — same difficulty level)
- Requires **multiple** custom node packs (not just one)
- Includes an LTX 2.3 Director-style 2-stage video workflow with WhatDreamsCost nodes

The resulting script (`workflows/setup/ltx-23-director-hotfix.sh` in the auto-startups-vast repo) is the current standard in the repo and the script this skill's policy section is written against.

## Source workflow

- File: `workflows/comfyui/LTX_Director_2_Workflow_Hotfix.json` (preserved filename from WhatDreamsCost)
- Author: WhatDreamsCost
- Workflow type: 2-stage LTX 2.3 video gen (Stage #1 base → Stage #2 spatial upscaler v1.1)
- Top-level `nodes[]` has 7 entries: 1 `LTXDirector` (timeline editor), 1 `SaveVideo`, 4 subgraph instances, 1 `MarkdownNote` (FAQ)
- `extra.prompt` is absent (subgraph workflows don't have it)
- All real loaders live in `definitions.subgraphs[].nodes[]`

## Subgraph inventory

## Extracted model manifest (7 unique files, ~39.7GB)

The hotfix workflow is **flat** (no subgraphs) — 33 top-level nodes including `LTXDirector`, `LTXDirectorCropGuides`, `LTXVConcatAVLatent`, etc. Loaders are direct `nodes[]` entries:

| Filename | Size | Loader | Subdir | Source repo |
|---|---|---|---|---|
| `ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors` | 25.2G | `UNETLoader` | `diffusion_models/` | `Kijai/LTX2.3_comfy` (`diffusion_models/`) |
| `taeltx2_3.safetensors` | 23.5M | `VAELoaderKJ` | `vae/` | `Kijai/LTX2.3_comfy` (`vae/`) |
| `LTX23_audio_vae_bf16.safetensors` | 365M | `VAELoader` | `vae/` | `Kijai/LTX2.3_comfy` (`vae/`) |
| `LTX23_video_vae_bf16.safetensors` | 1.5G | `VAELoader` | `vae/` | `Kijai/LTX2.3_comfy` (`vae/`) |
| `gemma_3_12B_it_fp4_mixed.safetensors` | 9.4G | `DualCLIPLoader.clip_name1` | `text_encoders/` | `Comfy-Org/ltx-2` (`split_files/text_encoders/`) |
| `ltx-2.3_text_projection_bf16.safetensors` | 2.3G | `DualCLIPLoader.clip_name2` | `text_encoders/` | `Kijai/LTX2.3_comfy` (`text_encoders/`) |
| `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` | 996M | `LatentUpscaleModelLoader` | `latent_upscale_models/` | `Lightricks/LTX-2.3` |

### Subgraph-stage notes (deprecated)

> The original 2-stage subgraph workflow used `CheckpointLoaderSimple` + `LoraLoaderModelOnly` combo (29.1GB FP8 dev checkpoint + 2.6GB Kijai dynamic-fro9 LoRA). The hotfix collapses that pair into a single 25.2GB distilled-1.1 transformer-only checkpoint and uses `UNETLoader` instead of `CheckpointLoaderSimple` → no LoRA needed. Same VAEs, same gemma, same projection, same upscaler.

## Custom node packs required (3)

Discovered by reading `properties.cnr_id` on every node:

1. **`kijai/ComfyUI-KJNodes`** — provides `VAELoaderKJ`
2. **`Lightricks/ComfyUI-LTXVideo`** — provides core LTX 2.3 nodes (`LTXVConcatAVLatent`, `BasicScheduler`)
3. **`WhatDreamsCost/WhatDreamsCost-ComfyUI`** — provides `LTXDirector`, `LTXDirectorCropGuides`

## URL research notes

- **`Lightricks/LTX-2.3-fp8` does NOT contain the distilled-1.1 transformer-only** — the Kijai repo (`Kijai/LTX2.3_comfy`) does. Path is `diffusion_models/ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors` (25.2GB). Verified with `hf download Kijai/LTX2.3_comfy <path> --dry-run` and `curl -sI`.
- `gemma_3_12B_it_fp4_mixed.safetensors` lives in `Comfy-Org/ltx-2` (v2 repo, not v2.3). The path is `split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors` — note the `split_files/` prefix.
- The Kijai repo stores files in subdirectories by loadable type: `diffusion_models/`, `loras/`, `vae/`, `text_encoders/`. When passed to `hf_hub_download(local_dir=...)` with the prefixed filename, the helper creates a double-nested path like `models/vae/vae/<file>`. The script uses the `local_dir=$BASE_DIR` + `mv` workaround (see workflow-researcher SKILL.md §8 cheat sheet) for **every** Kijai download to avoid the double-nest.

## Frontmatter (matches repo standard from `qwen-image-edit-2511-4steps.sh`)

```bash
# ---
# name: LTX 2.3 Director 2 (Workflow Hotfix)
# workflow: LTX_Director_2_Workflow_Hotfix
# aliases: [ltx director hotfix, ltx 2.3 director hotfix, ltx23 director hotfix, whatdreamscost hotfix, ltx-director-2-hotfix]
# description: ...
# size: ~62.3GB     (includes double-counted VAEs across hotfix + scenecraft — actual on-disk is ~39.7GB)
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
5. **Models download** — 7 `hf_download` calls, with `[N/7]` progress echoes; double-nest workaround for Kijai-prefixed blobs
6. **ComfyUI restart** — `supervisorctl restart comfyui`, with manual-launch fallback

## Pitfalls encountered (all addressed in this skill's SKILL.md)

| Pitfall | Resolution |
|---|---|
| Top-level `nodes[]` looked thin (33 flat nodes vs old 7 UUIDs) | Walk flat `nodes[]` directly — hotfix is NOT subgraph-based |
| Filename `ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors` 404 on `Lightricks/LTX-2.3-fp8` | Kijai repo is the canonical home for transformer-only distilled-1.1 FP8; `--dry-run` against `Kijai/LTX2.3_comfy` confirms existence |
| Kijai blobs nest at `models/<subdir>/<subdir>/<file>` | Download to `local_dir=$BASE_DIR`, then `mv $BASE_DIR/<subdir>/<file> $BASE_DIR/models/<subdir>/<file>` for every Kijai download — applies to diffusion_models/, vae/, text_encoders/ alike |
| `cnr_id` was the discovery mechanism for node packs | Always check `properties.cnr_id` — `whatdreamscost-comfyui`, `comfyui-kjnodes` etc. map to specific GitHub repos |
| Older scripts only installed one pack + no restart | New policy: download script is fully self-contained; installs all required packs and restarts ComfyUI |
