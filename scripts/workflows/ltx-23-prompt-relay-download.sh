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

# Load shared HF download helper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for f in "$SCRIPT_DIR/hf_download.sh" "/workspace/hf_download.sh"; do
  [ -f "$f" ] && source "$f" && break
done

echo "==> Starting downloads..."

# Diffusion Model (GGUF — UnetLoaderGGUF, node 608)
echo "[1/5] UNet (GGUF Q5_K_M)..."
hf_download "unsloth/LTX-2.3-GGUF" "distilled/ltx-2.3-22b-distilled-Q5_K_M.gguf" "$BASE_DIR/unet"

# Text Encoder — Gemma 3 fp4 (DualCLIPLoader, node 616)
echo "[2/5] Text Encoder (Gemma FP4)..."
hf_download "Comfy-Org/ltx-2" "split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" "$BASE_DIR/text_encoders"

# Text Projection (DualCLIPLoader, node 616)
echo "[3/5] Text Projection..."
hf_download "Kijai/LTX2.3_comfy" "text_encoders/ltx-2.3_text_projection_bf16.safetensors" "$BASE_DIR/text_encoders"

# Video VAE (VAELoader, node 620)
echo "[4/5] Video VAE..."
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_video_vae_bf16.safetensors" "$BASE_DIR/vae"

# Audio VAE (VAELoaderKJ, node 619)
echo "[5/5] Audio VAE..."
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_audio_vae_bf16.safetensors" "$BASE_DIR/vae"

echo "==> All downloads completed!"
echo ""
echo "==> Done!"
echo "    Total:  ~29.7GB across 5 files"
echo "    Models: unet/, text_encoders/, vae/"
echo ""
echo "👉 Restart ComfyUI or click Refresh in the UI."
