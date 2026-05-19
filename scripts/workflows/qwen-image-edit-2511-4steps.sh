#!/bin/bash
# ---
# name: Qwen Image Edit 2511 4-Step Lightning
# workflow: qwen-img-edit-2511-001
# aliases: [qwen-image-edit-2511-4steps, qwen-2511, qwen-image-edit-2511, qwen-image-lightning-4steps]
# description: Downloads all models and custom nodes for Qwen Image Edit 2511 4-step Lightning workflow in ComfyUI.
# size: ~31.4GB
# min_vram: 24GB
# nodes: [rgthree-comfy, ComfyUI-KJNodes, ComfyUI-Easy-Use]
# ---
set -e

BASE_DIR="/workspace/ComfyUI/models"

echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/{vae,text_encoders,diffusion_models,loras}

# Load shared HF download helper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh"; do
  [ -f "$f" ] && source "$f" && break
done

echo "==> Setting up ComfyUI nodes..."
cd /workspace/ComfyUI

# Detect the Python that ComfyUI actually runs with (Vast.ai images use /venv/main/)
COMFY_PYTHON=""
if [ -f /venv/main/bin/python3 ]; then
    COMFY_PYTHON="/venv/main/bin/python3"
    COMFY_PIP="/venv/main/bin/pip"
elif [ -f venv/bin/activate ]; then
    source venv/bin/activate
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$(which pip)"
else
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$(which pip)"
fi

if command -v comfy &> /dev/null; then
    comfy node install https://github.com/rgthree/rgthree-comfy
    comfy node install https://github.com/kijai/ComfyUI-KJNodes
    comfy node install https://github.com/yolain/ComfyUI-Easy-Use
else
    echo "comfy-cli not found, cloning node repositories manually..."
    cd custom_nodes
    git clone https://github.com/rgthree/rgthree-comfy || true
    git clone https://github.com/kijai/ComfyUI-KJNodes || true
    git clone https://github.com/yolain/ComfyUI-Easy-Use || true
    cd ..
fi

# Install pip dependencies into ComfyUI's Python (not system Python)
# ComfyUI-Easy-Use requires opencv-python-headless (cv2)
echo "==> Installing node dependencies into ComfyUI Python ($COMFY_PYTHON)..."
for req in \
    custom_nodes/rgthree-comfy/requirements.txt \
    custom_nodes/ComfyUI-KJNodes/requirements.txt \
    custom_nodes/ComfyUI-Easy-Use/requirements.txt; do
    if [ -f "$req" ]; then
        echo "  Installing $(dirname $req | xargs basename) deps..."
        $COMFY_PIP install -q -r "$req" 2>&1 || true
    fi
done

echo "==> Starting downloads..."

# VAE
# Comfy-Org/Qwen-Image_ComfyUI - shared with base Qwen Image workflows
# Size: ~253.8M
echo "[1/4] VAE..."
hf_download "Comfy-Org/Qwen-Image_ComfyUI" "split_files/vae/qwen_image_vae.safetensors" "$BASE_DIR/vae"

# Text Encoder
# Comfy-Org/Qwen-Image_ComfyUI - shared with base Qwen Image workflows
# Size: ~9.4G
echo "[2/4] Text Encoder..."
hf_download "Comfy-Org/Qwen-Image_ComfyUI" "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" "$BASE_DIR/text_encoders"

# Diffusion Model
# xms991/Qwen-Image-Edit-2511-fp8-e4m3fn - Qwen Image Edit 2511 fp8_e4m3fn variant
# Size: 20.4G
echo "[3/4] Diffusion Model..."
hf_download "xms991/Qwen-Image-Edit-2511-fp8-e4m3fn" "qwen_image_edit_2511_fp8_e4m3fn.safetensors" "$BASE_DIR/diffusion_models"

# LoRA
# lightx2v/Qwen-Image-Lightning - Qwen Image Lightning LoRA v2.0
# Size: 1.7G
echo "[4/4] LoRA..."
hf_download "lightx2v/Qwen-Image-Lightning" "Qwen-Image-Lightning-4steps-V2.0.safetensors" "$BASE_DIR/loras"

echo "==> All downloads completed!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
