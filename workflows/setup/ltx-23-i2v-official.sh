#!/bin/bash
# ---
# name: LTX Official ComfyUI Workflow 2.3 I2V
# workflow: video_ltx2_3_i2v
# aliases: [ltx-23-i2v-official, ltx-official, ltx23-official, ltx-i2v-official]
# description: Downloads all models for the official LTX 2.3 Image-to-Video workflow (Lightricks FP8 checkpoint + Kijai dynamic-rank distilled LoRA + Lightricks 384-rank distilled LoRA + Gemma FP4 text encoder + Gemma abliterated LoRA + spatial upscaler + OmniNFT RL LoRA).
# size: ~49GB
# min_vram: 24GB
# ---
set -e

# Platform-aware base directory detection.
# IMPORTANT: BASE_DIR must be the ComfyUI root (NOT .../models) so that
# hf_hub_download(local_dir=BASE_DIR/models/<sub>, filename="<sub>/foo.safetensors")
# lands files at $BASE_DIR/models/<sub>/foo.safetensors. Setting BASE_DIR to
# .../models and then pre-creating $BASE_DIR/<sub>/ caused nested paths like
# models/<sub>/<sub>/foo.safetensors (fixed 2026-06-18).
if [ -d "/workspace/runpod-slim/ComfyUI" ]; then
  BASE_DIR="/workspace/runpod-slim/ComfyUI"
  echo "  Platform: RunPod (base: $BASE_DIR)"
elif [ -d "/workspace/ComfyUI" ]; then
  BASE_DIR="/workspace/ComfyUI"
  echo "  Platform: Vast.ai (base: $BASE_DIR)"
else
  BASE_DIR="/workspace/ComfyUI"
  echo "  ⚠️  No ComfyUI dir found, defaulting to $BASE_DIR"
fi
echo "==> Creating directories..."
# Don't pre-create model subdirs — hf_download uses hf_hub_download(local_dir=...)
# which creates the subdir from the filename prefix. We just need the BASE_DIR.
mkdir -p "$BASE_DIR"

# Load shared HF download helper (auto-fetch if not present — Vast instances don't bundle it)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_HF_HELPER=""
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh" "/tmp/_hf_download.sh"; do
  [ -f "$f" ] && _HF_HELPER="$f" && break
done
if [ -z "$_HF_HELPER" ]; then
  echo "  Fetching _hf_download.sh from GitHub..."
  GITHUB_BASE="https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/workflows/setup"
  _HF_HELPER="/tmp/_hf_download.sh"
  if ! curl -sSL --fail "$GITHUB_BASE/_hf_download.sh" -o "$_HF_HELPER" 2>/dev/null; then
    # raw.githubusercontent.com fallback
    curl -sSL --fail "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/workflows/setup/_hf_download.sh" -o "$_HF_HELPER" \
      || { echo "❌ FATAL: could not download _hf_download.sh"; exit 1; }
  fi
  chmod +x "$_HF_HELPER"
fi
source "$_HF_HELPER"
unset _HF_HELPER

echo "==> Starting downloads..."

# 1. Checkpoint (Lightricks official FP8 — 29.1GB) — primary transformer for the workflow
echo "[1/7] Transformer checkpoint (FP8)..."
hf_download "Lightricks/LTX-2.3-fp8" "ltx-2.3-22b-dev-fp8.safetensors" "$BASE_DIR/models/checkpoints"

# 2. Distilled LoRA — Kijai dynamic-rank variant (~2.6GB).
# The workflow references this LoRA in its Power Lora Loader nodes. The
# filename's "split_files/loras/" prefix is HF's repo browse-tree convention.
# Workaround for double-nest: download with local_dir=$BASE_DIR (helper
# creates $BASE_DIR/split_files/loras/foo), then move to
# $BASE_DIR/models/loras/.
echo "[2/7] Kijai dynamic-rank distilled LoRA..."
LORA_BLOB="split_files/loras/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors"
LORA_FINAL="$BASE_DIR/models/loras/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors"
mkdir -p "$BASE_DIR/models/loras"
hf_download "Comfy-Org/ltx-2.3" "$LORA_BLOB" "$BASE_DIR"
if [ -f "$BASE_DIR/$LORA_BLOB" ] && [ "$BASE_DIR/$LORA_BLOB" != "$LORA_FINAL" ]; then
  mv "$BASE_DIR/$LORA_BLOB" "$LORA_FINAL"
  rmdir "$BASE_DIR/split_files/loras" 2>/dev/null || true
  rmdir "$BASE_DIR/split_files" 2>/dev/null || true
  echo "  ✅ Moved LoRA to $LORA_FINAL"
fi

# 3. Distilled LoRA — Lightricks 384-rank variant (~7.1GB).
# Different from step 2: this is the rank-384 preset from Lightricks' official
# release. Both LoRAs are needed (different rank/training method, applied
# at different strengths in the workflow).
echo "[3/7] Lightricks 384-rank distilled LoRA..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-22b-distilled-lora-384.safetensors" "$BASE_DIR/models/loras"

# 4. Text Encoder — Gemma 3 12B FP4 Mixed (~8.8GB).
# Required by the workflow's DualCLIPLoader as clip_name1.
# The HF blob path includes "split_files/text_encoders/" prefix.
# Workaround for double-nest: download with local_dir=$BASE_DIR (helper
# creates $BASE_DIR/split_files/text_encoders/foo), then move to
# $BASE_DIR/models/text_encoders/.
echo "[4/7] Gemma 3 12B FP4 text encoder..."
TE_BLOB="split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors"
TE_FINAL="$BASE_DIR/models/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors"
mkdir -p "$BASE_DIR/models/text_encoders"
hf_download "Comfy-Org/ltx-2" "$TE_BLOB" "$BASE_DIR"
if [ -f "$BASE_DIR/$TE_BLOB" ] && [ "$BASE_DIR/$TE_BLOB" != "$TE_FINAL" ]; then
  mv "$BASE_DIR/$TE_BLOB" "$TE_FINAL"
  rmdir "$BASE_DIR/split_files/text_encoders" 2>/dev/null || true
  rmdir "$BASE_DIR/split_files" 2>/dev/null || true
  echo "  ✅ Moved text encoder to $TE_FINAL"
fi

# 5. Gemma 3 abliterated LoRA — workflow also references this for prompt quality.
# Same split_files/loras/ filename-prefix double-nest as the Kijai LoRA in step 2.
echo "[5/7] Gemma-3 abliterated LoRA..."
ABLORA_BLOB="split_files/loras/gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors"
ABLORA_FINAL="$BASE_DIR/models/loras/gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors"
hf_download "Comfy-Org/ltx-2" "$ABLORA_BLOB" "$BASE_DIR"
if [ -f "$BASE_DIR/$ABLORA_BLOB" ] && [ "$BASE_DIR/$ABLORA_BLOB" != "$ABLORA_FINAL" ]; then
  mv "$BASE_DIR/$ABLORA_BLOB" "$ABLORA_FINAL"
  rmdir "$BASE_DIR/split_files/loras" 2>/dev/null || true
  rmdir "$BASE_DIR/split_files" 2>/dev/null || true
  echo "  ✅ Moved LoRA to $ABLORA_FINAL"
fi

# 6. Spatial upscaler v1.1 (~996MB) — required by the workflow's LatentUpscaleModelLoader.
# Previously assumed to be cached by ltx-23-fflf-seed-hunter.sh, but on fresh
# instances that assumption is wrong and the workflow silently fails to load.
echo "[6/7] Spatial upscaler (v1.1)..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "$BASE_DIR/models/latent_upscale_models"

# 7. OmniNFT RL LoRA (~588MB) — Kijai's OmniNFT reinforcement learning LoRA.
# The HF filename includes a "loras/" prefix, so passing local_dir=$BASE_DIR/models
# places the file at $BASE_DIR/models/loras/LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors
# directly — no move/rename needed.
echo "[7/7] OmniNFT RL LoRA..."
hf_download "Kijai/LTX2.3_comfy" "loras/LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors" "$BASE_DIR/models"

echo "==> All downloads completed!"
echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
