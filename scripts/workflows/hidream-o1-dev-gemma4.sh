#!/bin/bash
# ---
# name: HiDream O1 Dev + Gemma 4
# workflow: hidream_001
# aliases: [hidream-o1, hidream-o1-dev, hidream-gemma4, hidream-o1-gemma4, image-hidream-o1-dev-1]
# description: Downloads HiDream O1 Image Dev FP8 checkpoint + Gemma 4 E4B text encoder for image generation.
# size: ~17.2GB
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
mkdir -p "$BASE_DIR"/{checkpoints,text_encoders}

# Load shared HF download helper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh"; do
  [ -f "$f" ] && source "$f" && break
done

echo "==> Starting downloads..."

# 1. HiDream O1 Image Dev FP8 checkpoint (~8.1GB)
echo "[1/2] HiDream O1 Image Dev FP8 checkpoint..."
hf_download "Comfy-Org/HiDream-O1-Image" "checkpoints/hidream_o1_image_dev_fp8_scaled.safetensors" "$BASE_DIR/checkpoints"

# 2. Gemma 4 E4B FP8 text encoder (~9.1GB)
echo "[2/2] Gemma 4 E4B FP8 text encoder..."
hf_download "Comfy-Org/gemma-4" "text_encoders/gemma4_e4b_it_fp8_scaled.safetensors" "$BASE_DIR/text_encoders"

echo "==> All downloads completed!"
echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
