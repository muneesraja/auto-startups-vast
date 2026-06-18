#!/bin/bash
# ---
# name: LTX 2.3 I2V Distilled
# aliases: [ltx-23-i2v-distilled, ltx-distilled, kijai-ltx, ltx2.3-distilled]
# description: Downloads all models for the LTX 2.3 Image-to-Video workflow (Distilled 1.1 FP8 Scaled transformer).
# size: ~35GB
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

# 1. THE BRAIN (Distilled 1.1 - FP8 Scaled for your 3090)
echo "[1/6] Transformer (FP8 scaled)..."
hf_download "Kijai/LTX2.3_comfy" "diffusion_models/ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors" "$BASE_DIR/models/checkpoints"

# 2. THE EYES (Video VAE)
echo "[2/6] Video VAE..."
# Comfy-Org / Kijai repo stores this file under vae/ (HF repo
# browse-tree convention). If we pass local_dir=$BASE_DIR/models/vae
# with the full blob path, the file lands at
# $BASE_DIR/models/vae/vae/<file> (double-nested).
# Workaround: download with local_dir=$BASE_DIR (helper creates
# $BASE_DIR/vae/<file>), then move to the final home.
BLOB_PATH="$BASE_DIR/vae/LTX23_video_vae_bf16.safetensors"
FINAL_PATH="$BASE_DIR/models/vae/LTX23_video_vae_bf16.safetensors"
mkdir -p "$BASE_DIR/models/vae"
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_video_vae_bf16.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  rmdir "$BASE_DIR/vae" 2>/dev/null || true
  echo "  ✅ Moved to $FINAL_PATH"
fi

# 3. THE TEXT BRAIN (Gemma 3 FP4 Mixed)
echo "[3/6] Text Encoder (Gemma FP4)..."
hf_download "Comfy-Org/ltx-2" "split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" "$BASE_DIR/models/text_encoders"

# 4. THE UNCENSOR (Abliterated LoRA for Gemma)
echo "[4/6] LoRA (abliterated Gemma)..."
hf_download "Comfy-Org/ltx-2" "split_files/loras/gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors" "$BASE_DIR/models/loras"

# 5. THE PREVIEW (TAE - for fast previews while generating)
echo "[5/6] TAE..."
# Comfy-Org / Kijai repo stores this file under vae/ (HF repo
# browse-tree convention). If we pass local_dir=$BASE_DIR/models/vae
# with the full blob path, the file lands at
# $BASE_DIR/models/vae/vae/<file> (double-nested).
# Workaround: download with local_dir=$BASE_DIR (helper creates
# $BASE_DIR/vae/<file>), then move to the final home.
BLOB_PATH="$BASE_DIR/vae/taeltx2_3.safetensors"
FINAL_PATH="$BASE_DIR/models/vae/taeltx2_3.safetensors"
mkdir -p "$BASE_DIR/models/vae"
hf_download "Kijai/LTX2.3_comfy" "vae/taeltx2_3.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  rmdir "$BASE_DIR/vae" 2>/dev/null || true
  echo "  ✅ Moved to $FINAL_PATH"
fi

# 6. UPSCALER (Standard v1.1 Spatial)
echo "[6/6] Spatial Upscaler..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "$BASE_DIR/models/latent_upscale_models"

echo "==> All downloads completed!"
echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
