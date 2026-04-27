#!/bin/bash
# ---
# name: LTX-2.3 PromptRelay Download Script
# aliases: [ltx-prompt-relay, ltx23-pr, prompt-relay-ltx]
# description: Downloads models for the LTX-2.3 PromptRelay workflow — distilled GGUF unet, fp4 text encoder, text projection, and audio/video VAE
# size: ~29.7GB
# min_vram: 24GB
# ---
set -e

BASE_DIR="/workspace/ComfyUI/models"

echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/{unet,text_encoders,vae}

echo "==> Checking aria2..."
if ! command -v aria2c &> /dev/null; then
    echo "aria2 not found, installing..."
    sudo apt update && sudo apt install -y aria2
else
    echo "aria2 already installed"
fi

echo "==> Starting downloads..."

# Diffusion Model (GGUF — UnetLoaderGGUF, node 608)
aria2c -x 16 -s 16 -k 1M \
  -d "$BASE_DIR/unet" \
  -o "ltx-2.3-22b-distilled-Q5_K_M.gguf" \
  "https://huggingface.co/unsloth/LTX-2.3-GGUF/resolve/main/distilled/ltx-2.3-22b-distilled-Q5_K_M.gguf" &

# Text Encoder — Gemma 3 fp4 (DualCLIPLoader, node 616)
aria2c -x 16 -s 16 -k 1M \
  -d "$BASE_DIR/text_encoders" \
  -o "gemma_3_12B_it_fp4_mixed.safetensors" \
  "https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" &

# Text Projection (DualCLIPLoader, node 616)
aria2c -x 16 -s 16 -k 1M \
  -d "$BASE_DIR/text_encoders" \
  -o "ltx-2.3_text_projection_bf16.safetensors" \
  "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/text_encoders/ltx-2.3_text_projection_bf16.safetensors" &

# Video VAE (VAELoader, node 620)
aria2c -x 16 -s 16 -k 1M \
  -d "$BASE_DIR/vae" \
  -o "LTX23_video_vae_bf16.safetensors" \
  "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/vae/LTX23_video_vae_bf16.safetensors" &

# Audio VAE (VAELoaderKJ, node 619)
aria2c -x 16 -s 16 -k 1M \
  -d "$BASE_DIR/vae" \
  -o "LTX23_audio_vae_bf16.safetensors" \
  "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/vae/LTX23_audio_vae_bf16.safetensors" &

wait
echo "==> All downloads completed!"

echo ""
echo "==> Done!"
echo "    Total:  ~29.7GB across 5 files"
echo "    Models: unet/, text_encoders/, vae/"
echo ""
echo "👉 Restart ComfyUI or click Refresh in the UI."
