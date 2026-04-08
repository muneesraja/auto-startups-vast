#!/bin/bash
# ---
# name: Qwen Image Edit
# aliases: [qwen, qwen image, qwen image edit, qwen-image]
# description: Downloads all models needed for Qwen image editing workflow in ComfyUI (VAE, Text Encoder, Diffusion, LoRA).
# size: ~15-20GB
# min_vram: 24GB
# ---
set -e

BASE_DIR="/workspace/ComfyUI/models"

echo "==> Creating directories..."
mkdir -p $BASE_DIR/{vae,text_encoders,diffusion_models,loras}

echo "==> Checking aria2..."
if ! command -v aria2c &> /dev/null; then
    echo "aria2 not found, installing..."
    sudo apt update && sudo apt install -y aria2
else
    echo "aria2 already installed"
fi

echo "==> Starting downloads..."

# VAE
echo "==> Downloading VAE..."
aria2c -x 16 -s 16 -k 1M \
  -d "$BASE_DIR/vae" \
  -o qwen_image_vae.safetensors \
  "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors"

# Text Encoder
echo "==> Downloading Text Encoder..."
aria2c -x 16 -s 16 -k 1M \
  -d "$BASE_DIR/text_encoders" \
  -o qwen_2.5_vl_7b_fp8_scaled.safetensors \
  "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"

# Diffusion Model
echo "==> Downloading Diffusion Model..."
aria2c -x 16 -s 16 -k 1M \
  -d "$BASE_DIR/diffusion_models" \
  -o qwen_image_edit_2509_fp8_e4m3fn.safetensors \
  "https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors"

# LoRA
echo "==> Downloading LoRA..."
aria2c -x 16 -s 16 -k 1M \
  -d "$BASE_DIR/loras" \
  -o Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors \
  "https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Lightning/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors"

echo "==> All downloads completed!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
