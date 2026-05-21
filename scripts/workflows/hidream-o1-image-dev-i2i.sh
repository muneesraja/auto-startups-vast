#!/bin/bash
# ---
# name: HiDream O1 Image Dev I2I
# workflow: image_hidream_o1_dev_fp16_i2i
# aliases: [hidream-o1-dev-i2i, hidream-o1, hidream-o1-image-dev, hidream-i2i]
# description: Downloads the HiDream O1 Image Dev 2604 FP16 merged checkpoint for image-to-image workflows.
# size: ~35GB
# min_vram: 24GB
# ---
set -e

# Platform-aware base directory detection
if [ -d "/workspace/runpod-slim/ComfyUI" ]; then
  BASE_DIR="/workspace/runpod-slim/ComfyUI/models"
  COMFYUI_DIR="/workspace/runpod-slim/ComfyUI"
  echo "  Platform: RunPod (base: $BASE_DIR)"
elif [ -d "/workspace/ComfyUI" ]; then
  BASE_DIR="/workspace/ComfyUI/models"
  COMFYUI_DIR="/workspace/ComfyUI"
  echo "  Platform: Vast.ai (base: $BASE_DIR)"
else
  BASE_DIR="/workspace/ComfyUI/models"
  COMFYUI_DIR="/workspace/ComfyUI"
  echo "  ⚠️  No ComfyUI dir found, defaulting to $BASE_DIR"
fi

echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/{checkpoints}

# =============================================================================
# Install Rebels HiDream custom nodes (if not already present)
# =============================================================================
NODES_DIR="$COMFYUI_DIR/custom_nodes/Rebels_HiDream-01_Image_Dev_NODES"
if [ ! -f "$NODES_DIR/__init__.py" ]; then
  echo "==> Installing Rebels HiDream custom nodes..."
  cd "$COMFYUI_DIR/custom_nodes"
  git clone --depth 1 https://github.com/RealRebelAI/Rebels_HiDream-01_Image_Dev_NODES.git 2>/dev/null || true
  
  # The repo has a nested structure — __init__.py is in a subdirectory
  # Move Python files to repo root so ComfyUI can find __init__.py
  INNER="$NODES_DIR/Rebels_HiDream_01_Image_dev_NODES"
  if [ -d "$INNER" ] && [ ! -f "$NODES_DIR/__init__.py" ]; then
    cp "$INNER"/*.py "$NODES_DIR/" 2>/dev/null || true
    echo "  ✅ Fixed nested directory structure"
  fi
  
  # Install vendored models from upstream HiDream-O1-Image repo
  if [ ! -f "$NODES_DIR/models/pipeline.py" ]; then
    echo "  ==> Cloning upstream HiDream-O1-Image for vendored models..."
    cd /tmp && git clone --depth 1 https://github.com/HiDream-ai/HiDream-O1-Image.git 2>/dev/null
    cp -r /tmp/HiDream-O1-Image/models "$NODES_DIR/"
    rm -rf /tmp/HiDream-O1-Image
    echo "  ✅ Vendored models installed"
  fi
  
  # Install Python requirements
  if [ -f "$NODES_DIR/requirements.txt" ]; then
    /venv/main/bin/pip install -r "$NODES_DIR/requirements.txt" -q 2>/dev/null || true
    echo "  ✅ Requirements installed"
  fi
  
  cd - > /dev/null
  echo "  ✅ Rebels HiDream nodes installed"
else
  echo "  ✅ Rebels HiDream nodes already present"
fi

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
