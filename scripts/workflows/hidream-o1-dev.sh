#!/bin/bash
# ---
# name: HiDream O1 Dev (image_hidream_o1_dev)
# workflow: hidream_o1_dev
# aliases: [hidream-o1-dev, hidream-o1, hidream-o1-image-dev, hidream-dev, hidream-o1-dev-t2i, hidream-o1-dev-ref]
# description: Downloads the HiDream O1 Image Dev 2604 FP16 merged checkpoint for T2I/I2I reference workflows.
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
mkdir -p "$BASE_DIR"/{checkpoints}

# Load shared HF download helper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh"; do
  [ -f "$f" ] && source "$f" && break
done

echo "==> Starting downloads..."

# 1. Merged checkpoint (Model + CLIP/Gemma + VAE — all-in-one)
echo "[1/1] HiDream O1 Image Dev 2604 FP16 checkpoint..."
hf_download "HodgeMann/HiDream-O1-Image-Dev-2604-FP16-merged" "HiDream-O1-Image-Dev-2604-FP16.safetensors" "$BASE_DIR/checkpoints"

echo "==> All downloads completed!"
echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
