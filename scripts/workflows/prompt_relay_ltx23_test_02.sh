#!/bin/bash
# ---
# name: LTX 2.3 Prompt Relay (prompt_relay_ltx23_test_02)
# aliases: [prompt-relay-ltx23-test-02, prompt_relay_ltx23_test_02, ltx23-prompt-relay, ltx23-oldman-redpanda]
# description: Download LTX 2.3 models for prompt_relay_ltx23_test_02 workflow — old man & red panda, 4 segments (123+122+122+122 frames), PromptRelayEncodeTimeline
# size: ~61.4GB
# min_vram: 24GB
# workflow: prompt_relay_ltx23_test_02.json
# ---
set -e

BASE_DIR="/workspace/ComfyUI/models"

echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/diffusion_models vae text_encoders loras

echo "==> Checking aria2..."
if ! command -v aria2c &> /dev/null; then
    echo "aria2 not found, installing..."
    sudo apt update && sudo apt install -y aria2
else
    echo "aria2 already installed"
fi

echo "==> Starting downloads..."

# UNET (LTX 2.3 Transformer, fp8 scaled)
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/diffusion_models" -o "ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors" "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/diffusion_models/ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors" &

# Video VAE (bf16)
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/vae" -o "LTX23_video_vae_bf16.safetensors" "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/vae/LTX23_video_vae_bf16.safetensors" &

# Audio VAE (bf16)
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/vae" -o "LTX23_audio_vae_bf16.safetensors" "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/vae/LTX23_audio_vae_bf16.safetensors" &

# Text Projection (bf16)
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/text_encoders" -o "LTX23_text_projection_bf16.safetensors" "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/text_encoders/ltx-2.3_text_projection_bf16.safetensors" &

# Gemma 3 CLIP (12B text encoder)
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/text_encoders" -o "gemma_3_12B_it.safetensors" "https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it.safetensors" &

# LoRA (384-1.1)
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/loras" -o "ltx-2.3-22b-distilled-lora-384-1.1.safetensors" "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-22b-distilled-lora-384-1.1.safetensors" &

wait
echo "==> All downloads completed!"

echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
