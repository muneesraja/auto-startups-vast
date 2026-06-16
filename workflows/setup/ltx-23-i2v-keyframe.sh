#!/bin/bash
# ---
# name: LTX 2.3 I2V Keyframe
# aliases: [ltx-23-i2v-keyframe, ltx-keyframe, ltx2.3-keyframing]
# description: Downloads all models for the LTX 2.3 first/last-frame keyframing workflow and applies requisite patch.
# size: ~60GB
# min_vram: 24GB
# ---
set -e

# Platform-aware base directory detection
if [ -d "/workspace/runpod-slim/ComfyUI" ]; then
  BASE_DIR="/workspace/runpod-slim/ComfyUI/models"
  echo "  Platform: RunPod (base: $BASE_DIR)"
elif [ -d "/workspace/ComfyUI" ]; then
  BASE_DIR="/workspace/ComfyUI/models"
  echo "  Platform: Vast.ai (base: $BASE_DIR)"
else
  BASE_DIR="/workspace/ComfyUI/models"
  echo "  ⚠️  No ComfyUI dir found, defaulting to $BASE_DIR"
fi

echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/{loras/ltx2,unet,text_encoders,vae,latent_upscale_models,checkpoints}

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

echo "==> Setting up ComfyUI nodes..."
cd /workspace/ComfyUI
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
fi
if command -v comfy &> /dev/null; then
    comfy node install https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI
else
    echo "comfy-cli not found, cloning node repository manually..."
    cd custom_nodes
    git clone https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI || true
    cd ..
fi

echo "==> Starting downloads..."

# UNet (NVFP4)
echo "[1/11] UNet (NVFP4)..."
hf_download "Lightricks/LTX-2.3-nvfp4" "ltx-2.3-22b-dev-nvfp4.safetensors" "$BASE_DIR/unet"

# UNet (FP8)
echo "[2/11] UNet (FP8)..."
hf_download "Lightricks/LTX-2.3-fp8" "ltx-2.3-22b-dev-fp8.safetensors" "$BASE_DIR/unet"

# Text Encoder (Gemma FP4)
echo "[3/11] Text Encoder (Gemma FP4)..."
hf_download "Comfy-Org/ltx-2" "split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" "$BASE_DIR/text_encoders"

# LoRA (distilled)
echo "[4/11] LoRA (distilled)..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-22b-distilled-lora-384.safetensors" "$BASE_DIR/loras"

# LoRA (abliterated)
echo "[5/11] LoRA (abliterated Gemma)..."
hf_download "Comfy-Org/ltx-2" "split_files/loras/gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors" "$BASE_DIR/loras"

# Video VAE
echo "[6/11] Video VAE..."
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_video_vae_bf16.safetensors" "$BASE_DIR/vae"

# Audio VAE
echo "[7/11] Audio VAE..."
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_audio_vae_bf16.safetensors" "$BASE_DIR/vae"

# Spatial Upscaler x1.5
echo "[8/11] Spatial Upscaler x1.5..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-spatial-upscaler-x1.5-1.0.safetensors" "$BASE_DIR/latent_upscale_models"

# Spatial Upscaler x2
echo "[9/11] Spatial Upscaler x2..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "$BASE_DIR/latent_upscale_models"

# Temporal Upscaler x2
echo "[10/11] Temporal Upscaler x2..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-temporal-upscaler-x2-1.0.safetensors" "$BASE_DIR/latent_upscale_models"

# TAE
echo "[11/11] TAE..."
hf_download "Kijai/LTX2.3_comfy" "vae/taeltx2_3.safetensors" "$BASE_DIR/vae"

echo "==> All downloads completed!"

echo "==> Creating symlinks and copies..."
ln -sf ../unet/ltx-2.3-22b-dev-fp8.safetensors "$BASE_DIR/checkpoints/ltx-2.3-22b-dev-fp8.safetensors"
ln -sf ../unet/ltx-2.3-22b-dev-nvfp4.safetensors "$BASE_DIR/checkpoints/ltx-2.3-22b-dev-nvfp4.safetensors"
cp "$BASE_DIR/loras/ltx-2.3-22b-distilled-lora-384.safetensors" "$BASE_DIR/loras/ltx2/ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors"

echo "==> Applying patch..."
PATCH_FILE="/workspace/ComfyUI/comfy/ldm/lightricks/symmetric_patchifier.py"
if [ -f "$PATCH_FILE" ]; then
    if ! grep -q "audio_latents.dim()" "$PATCH_FILE"; then
      sed -i "/b, _, t, _ = audio_latents.shape/i\\        if audio_latents.dim() == 5:\\n            audio_latents = audio_latents.squeeze(1)" "$PATCH_FILE"
    fi
else
    echo "Patch file not found, skipping patch."
fi

echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
