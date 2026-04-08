#!/bin/bash
# =============================================================================
# Wan 2.2 — Full Model Download Script
# =============================================================================
# Downloads all Wan 2.2 models for multi-keyframe video generation in ComfyUI.
#
# Models:
#   - Text Encoder: umt5_xxl_fp8_e4m3fn_scaled.safetensors
#   - Diffusion Model (High Noise): wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors
#   - Diffusion Model (Low Noise): wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors
#   - LoRA (High Noise): wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors
#   - LoRA (Low Noise): wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors
#   - VAE: wan_2.1_vae.safetensors
#
# Total download size: ~20-30 GB
# =============================================================================
set -e

BASE_DIR="/workspace/ComfyUI/models"

echo "=== Wan 2.2 Download — Starting ==="

# Text Encoder
echo "[1/6] Downloading text encoder..."
aria2c -x 16 -s 16 -d "$BASE_DIR/text_encoders/" -o umt5_xxl_fp8_e4m3fn_scaled.safetensors \
  "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"

# Diffusion Model (High Noise)
echo "[2/6] Downloading diffusion model (high noise)..."
aria2c -x 16 -s 16 -d "$BASE_DIR/diffusion_models/" -o wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors \
  "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"

# Diffusion Model (Low Noise)
echo "[3/6] Downloading diffusion model (low noise)..."
aria2c -x 16 -s 16 -d "$BASE_DIR/diffusion_models/" -o wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors \
  "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"

# LoRA (High Noise)
echo "[4/6] Downloading LoRA (high noise)..."
aria2c -x 16 -s 16 -d "$BASE_DIR/loras/" -o wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors \
  "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors"

# LoRA (Low Noise)
echo "[5/6] Downloading LoRA (low noise)..."
aria2c -x 16 -s 16 -d "$BASE_DIR/loras/" -o wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors \
  "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors"

# VAE
echo "[6/6] Downloading VAE..."
aria2c -x 16 -s 16 -d "$BASE_DIR/vae/" -o wan_2.1_vae.safetensors \
  "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors"

echo "=== Wan 2.2 Download — Complete! ==="
