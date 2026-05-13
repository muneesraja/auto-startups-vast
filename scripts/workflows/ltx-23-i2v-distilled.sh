#!/bin/bash
# ---
# name: LTX 2.3 I2V Distilled
# aliases: [ltx-23-i2v-distilled, ltx-distilled, kijai-ltx, ltx2.3-distilled]
# description: Downloads all models for the LTX 2.3 Image-to-Video workflow (Distilled 1.1 FP8 Scaled transformer).
# size: ~35GB
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
mkdir -p "$BASE_DIR"/{checkpoints,vae,loras,latent_upscale_models,text_encoders}

# Load shared HF download helper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh"; do
  [ -f "$f" ] && source "$f" && break
done

echo "==> Starting downloads..."

# 1. THE BRAIN (Distilled 1.1 - FP8 Scaled for your 3090)
echo "[1/6] Transformer (FP8 scaled)..."
hf_download "Kijai/LTX2.3_comfy" "diffusion_models/ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors" "$BASE_DIR/checkpoints"

# 2. THE EYES (Video VAE)
echo "[2/6] Video VAE..."
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_video_vae_bf16.safetensors" "$BASE_DIR/vae"

# 3. THE TEXT BRAIN (Gemma 3 FP4 Mixed)
echo "[3/6] Text Encoder (Gemma FP4)..."
hf_download "Comfy-Org/ltx-2" "split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" "$BASE_DIR/text_encoders"

# 4. THE UNCENSOR (Abliterated LoRA for Gemma)
echo "[4/6] LoRA (abliterated Gemma)..."
hf_download "Comfy-Org/ltx-2" "split_files/loras/gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors" "$BASE_DIR/loras"

# 5. THE PREVIEW (TAE - for fast previews while generating)
echo "[5/6] TAE..."
hf_download "Kijai/LTX2.3_comfy" "vae/taeltx2_3.safetensors" "$BASE_DIR/vae"

# 6. UPSCALER (Standard v1.1 Spatial)
echo "[6/6] Spatial Upscaler..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "$BASE_DIR/latent_upscale_models"

echo "==> All downloads completed!"
echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
