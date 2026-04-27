#!/bin/bash
# ---
# name: Kijai LTX 2.3
# aliases: [kijai-ltx2.3, ltx-kijai, kijai-ltx, ltx2.3-distilled]
# description: Downloads all models required for the Kijai LTX 2.3 workflow (Distilled 1.1 FP8 Scaled).
# size: ~35GB
# min_vram: 24GB
# ---
set -e

BASE_DIR="/workspace/ComfyUI/models"

echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/{checkpoints,vae,loras,latent_upscale_models,text_encoders}

echo "==> Checking aria2..."
if ! command -v aria2c &> /dev/null; then
    echo "aria2 not found, installing..."
    sudo apt update && sudo apt install -y aria2
else
    echo "aria2 already installed"
fi

echo "==> Starting downloads..."

# 1. THE BRAIN (Distilled 1.1 - FP8 Scaled for your 3090)
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/checkpoints" -o "ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors" "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/diffusion_models/ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors" &

# 2. THE EYES (Video VAE)
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/vae" -o "LTX23_video_vae_bf16.safetensors" "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/vae/LTX23_video_vae_bf16.safetensors" &

# 3. THE TEXT BRAIN (Gemma 3 FP4 Mixed)
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/text_encoders" -o "gemma_3_12B_it_fp4_mixed.safetensors" "https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" &

# 4. THE UNCENSOR (Abliterated LoRA for Gemma)
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/loras" -o "gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors" "https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/loras/gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors" &

# 5. THE PREVIEW (TAE - for fast previews while generating)
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/vae" -o "taeltx2_3.safetensors" "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/vae/taeltx2_3.safetensors" &

# 6. UPSCALER (Standard v1.1 Spatial)
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/latent_upscale_models" -o "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-spatial-upscaler-x2-1.1.safetensors" &

wait
echo "==> All downloads completed!"

echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
