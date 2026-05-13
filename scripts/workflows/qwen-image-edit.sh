#!/bin/bash
# ---
# name: Qwen Image Edit
# aliases: [qwen-image-edit, qwen, qwen-image]
# description: Downloads all models needed for Qwen image editing workflow in ComfyUI (VAE, Text Encoder, Diffusion, LoRA).
# size: ~15-20GB
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
mkdir -p "$BASE_DIR"/{vae,text_encoders,diffusion_models,loras}

# Load shared HF download helper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh"; do
  [ -f "$f" ] && source "$f" && break
done

echo "==> Starting downloads..."

# VAE
echo "[1/4] VAE..."
hf_download "Comfy-Org/Qwen-Image_ComfyUI" "split_files/vae/qwen_image_vae.safetensors" "$BASE_DIR/vae"

# Text Encoder
echo "[2/4] Text Encoder..."
hf_download "Comfy-Org/Qwen-Image_ComfyUI" "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" "$BASE_DIR/text_encoders"

# Diffusion Model
echo "[3/4] Diffusion Model..."
hf_download "Comfy-Org/Qwen-Image-Edit_ComfyUI" "split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors" "$BASE_DIR/diffusion_models"

# LoRA
echo "[4/4] LoRA..."
hf_download "lightx2v/Qwen-Image-Lightning" "Qwen-Image-Lightning/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors" "$BASE_DIR/loras"

echo "==> All downloads completed!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
