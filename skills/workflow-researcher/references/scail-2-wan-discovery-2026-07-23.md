# SCAIL-2 / Wan2.1 Model Discovery — Lessons from `scail-2-mxfp8-dpo.sh` (2026-07-23)

Concrete patterns learned while building a provisioning script for a SCAIL-2 Wan2.1
character-replacement workflow. Use as a reference when the workflow references
SCAIL-2, Wan2.1 I2V, lightx2v, or any `WanSCAILToVideo` / `SCAIL2ColoredMask` graph.

## ⚠️ ComfyUI secondary-directory marker in `UNETLoader` widget strings

Loader widget values can contain a `\\` (or `/`) prefix that ComfyUI interprets as
"look in this subdirectory under the standard models dir". E.g.:

```json
"widgets_values": ["SCAIL2\\wan2.1_14B_SCAIL_2_mxfp8.safetensors", "default"]
```

means the file MUST land at `models/diffusion_models/SCAIL2/<file>`, NOT flat under
`models/diffusion_models/<file>`. The ComfyUI UI displays it as
`SCAIL2/wan2.1_14B_SCAIL_2_mxfp8.safetensors` for the user but the loader resolves
the prefix as a subdir.

**Trap**: blindly stripping everything before the filename when generating download
paths will break the loader → "model not found" at runtime.

**Detection pattern** in workflow JSON: any loader `widgets_values[0]` that contains
`\\` or has a path component other than the bare filename. Audit before writing
the script.

## ⚠️ Lightx2v rank128 bf16 LoRA is NOT in the obvious lightx2v repo

The repo `lightx2v/Wan2.1-I2V-14B-480P-StepDistill-CfgDistill-Lightx2v` only hosts
the **rank64** variant. The **rank128 bf16** variant
(`lightx2v_I2V_14B_480p_cfg_step_distill_rank128_bf16.safetensors`) lives in
**`Kijai/WanVideo_comfy/Lightx2v/<file>`** (1.4 GB).

**Audit before assuming**: don't trust workflow widget filenames to map 1:1 to
the obvious upstream repo. `hf_hub_download` HEAD-check every URL — a 404 on
the "obvious" repo is a strong signal it's in a mirror.

The same pattern is true for some Wan 2.2 / SVI Pro LoRAs — Kijai's mirror
frequently has files the original authors' repos don't expose.

## ⚠️ `SCAIL2ColoredMask` / `WanSCAILToVideo` / `SAM3_VideoTrack` are master-only

All three nodes are in comfy-core master as of 2026-07-13 but are NOT in the
v0.27.0 release (the version the `runpod/comfyui` image pins). The script's
`Upgrading ComfyUI to master` section is mandatory, not optional — without it
the workflow will fail with `Class WanSCAILToVideo not found` at parse time.

Same goes for `ColorTransfer` and `BatchImagesNode` (added later than v0.27.0).
Audit `properties.cnr_id` for `comfy-core` nodes that the v0.27.0 release doesn't
include; if any are SCAIL-2 / Wan-2.2 era, force the master upgrade.

## ⚠️ DPO LoRA lives in `Comfy-Org/SCAIL-2/loras/`, not in `Kijai/SCAIL-2`

The Kijai mirror for SCAIL-2 is gated (401 on public API queries). The DPO LoRA
is in the Comfy-Org mirror:
`Comfy-Org/SCAIL-2/loras/wan2.1_SCAIL_2_DPO_lora_bf16.safetensors` (1.17 GB).

The repo also has `loras/wan2.1_SCAIL_2_relight_lora_bf16.safetensors` — same shape,
useful for adjacent relighting workflows.

## ⚠️ RMBG-1.4 pre-stage the dir

`easy imageRemBg` writes its RMBG model under `models/rmbg/`. The dir is auto-
created on first use, but pre-staging it with `mkdir -p` avoids a race where
the node fails on first invocation if the filesystem is slow (observed on
RunPod cold-cache).

## Reusable audit recipe for any SCAIL-2 / Wan2.1 workflow

```python
import json
with open('<workflow>.json') as f:
    w = json.load(f)
for n in w['nodes']:
    t = n.get('type', '')
    if 'Loader' in t or t in ('UNETLoader','VAELoader','CLIPLoader','CLIPVisionLoader','LoraLoaderModelOnly','CheckpointLoaderSimple'):
        wv = n.get('widgets_values', [])
        if isinstance(wv, list) and wv:
            first = wv[0]
            # Flag any widget that uses ComfyUI's secondary-dir marker
            marker = '⚠️ SUBDIR' if ('\\' in str(first) or '/' in str(first)) and not str(first).endswith('/') else '  flat   '
            print(f"{marker} [{t}] id={n.get('id'):>3} → {first}")
```

Run this on every workflow before writing the script. Catches the secondary-
directory marker pattern automatically and also confirms you haven't missed
any loader.

## Per-frame color transfer pattern (SCAIL-2 specific)

The workflow uses `GetImageRangeFromBatch` (frames 5..4096 on the denoised
output) → `ColorTransfer` (reinhard_lab, per_frame, 1) → `BatchImagesNode`
(image0 = last frame batch, image1 = color-transferred) → `easy forLoopEnd`
so the next loop iteration's `previous_frames` includes the color-corrected
output. This is the SCAIL-2-specific temporal-consistency trick that keeps
the driving video's color palette stable across the forLoop chunks.

Nothing to download extra for this — the nodes are in comfy-core master + the
existing kjnodes pack. Just call out in the script's `# description:` that
the workflow uses forLoop + color transfer.

## Common HF repo map (SCAIL-2 / Wan2.1 era, 2026-07)

| Loader | Repo | Path |
|---|---|---|
| Diffusion (Wan2.1 SCAIL-2 mxfp8) | `Comfy-Org/SCAIL-2` | `diffusion_models/wan2.1_14B_SCAIL_2_mxfp8.safetensors` (15.98 GB) |
| Diffusion (Wan2.1 SCAIL-2 fp8_scaled) | `Comfy-Org/SCAIL-2` | `diffusion_models/wan2.1_14B_SCAIL_2_fp8_scaled.safetensors` (16.5 GB) |
| LoRA: SCAIL-2 DPO | `Comfy-Org/SCAIL-2` | `loras/wan2.1_SCAIL_2_DPO_lora_bf16.safetensors` (1.17 GB) |
| LoRA: SCAIL-2 relight | `Comfy-Org/SCAIL-2` | `loras/wan2.1_SCAIL_2_relight_lora_bf16.safetensors` |
| LoRA: Lightx2v rank64 | `lightx2v/Wan2.1-I2V-14B-480P-StepDistill-CfgDistill-Lightx2v` | `loras/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors` (705 MB) |
| LoRA: Lightx2v rank128 bf16 | `Kijai/WanVideo_comfy` | `Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank128_bf16.safetensors` (1.4 GB) |
| Text encoder: UMT5-XXL FP8 | `Comfy-Org/Wan_2.1_ComfyUI_repackaged` | `split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors` (6.4 GB) |
| CLIP-Vision: ViT-H | `Comfy-Org/Wan_2.1_ComfyUI_repackaged` | `split_files/clip_vision/clip_vision_h.safetensors` (1.2 GB) |
| VAE: Wan 2.1 | `Comfy-Org/Wan_2.1_ComfyUI_repackaged` | `split_files/vae/wan_2.1_vae.safetensors` (242 MB) |
| Checkpoint: SAM3 | `Comfy-Org/sam3.1` | `checkpoints/sam3.1_multiplex_fp16.safetensors` (1.66 GB) |
