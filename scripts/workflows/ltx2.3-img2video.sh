#!/bin/bash
# ---
# name: LTX 2.3 Image to Video
# aliases: [ltx2.3-img2video, ltx-img2video, image2video, ltx2.3 i2v]
# description: Downloads all models required for the LTX 2.3 Image to Video workflow.
# size: ~40GB
# min_vram: 24GB
# ---
set -e

BASE_DIR="/workspace/ComfyUI/models"

echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/{checkpoints,loras,latent_upscale_models}

echo "==> Checking aria2..."
if ! command -v aria2c &> /dev/null; then
    echo "aria2 not found, installing..."
    sudo apt update && sudo apt install -y aria2
else
    echo "aria2 already installed"
fi

echo "==> Starting downloads..."

# Checkpoints
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/checkpoints" -o "ltx-2.3-22b-dev-fp8.safetensors" "https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-dev-fp8.safetensors" &

# Loras
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/loras" -o "ltx-2.3-22b-distilled-lora-384.safetensors" "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-22b-distilled-lora-384.safetensors" &
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/loras" -o "gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors" "https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/loras/gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors" &

# Latent Upscale Models
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/latent_upscale_models" -o "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-spatial-upscaler-x2-1.1.safetensors" &

wait
echo "==> All downloads completed!"

echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
