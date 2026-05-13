#!/bin/bash
# ---
# name: Wan 2.2 I2V Keyframe
# aliases: [wan-22-i2v-keyframe, wan, wan2.2, wanvideo]
# description: Downloads all Wan 2.2 models for multi-keyframe I2V video generation in ComfyUI.
# size: ~25GB
# min_vram: 24GB
# ---
# =============================================================================
# Wan 2.2 — Full Model Download Script (HF CLI, authenticated)
# =============================================================================
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

echo "=== Wan 2.2 Download — Starting ==="
mkdir -p "$BASE_DIR"/{text_encoders,diffusion_models,loras,vae}

# Load shared HF download helper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh"; do
  [ -f "$f" ] && source "$f" && break
done

echo "==> Starting downloads..."

# Text Encoder
echo "[1/6] Text encoder..."
hf_download "Comfy-Org/Wan_2.1_ComfyUI_repackaged" "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" "$BASE_DIR/text_encoders"

# Diffusion Model (High Noise)
echo "[2/6] Diffusion model (high noise)..."
hf_download "Comfy-Org/Wan_2.2_ComfyUI_Repackaged" "split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" "$BASE_DIR/diffusion_models"

# Diffusion Model (Low Noise)
echo "[3/6] Diffusion model (low noise)..."
hf_download "Comfy-Org/Wan_2.2_ComfyUI_Repackaged" "split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors" "$BASE_DIR/diffusion_models"

# LoRA (High Noise)
echo "[4/6] LoRA (high noise)..."
hf_download "Comfy-Org/Wan_2.2_ComfyUI_Repackaged" "split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors" "$BASE_DIR/loras"

# LoRA (Low Noise)
echo "[5/6] LoRA (low noise)..."
hf_download "Comfy-Org/Wan_2.2_ComfyUI_Repackaged" "split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors" "$BASE_DIR/loras"

# VAE
echo "[6/6] VAE..."
hf_download "Comfy-Org/Wan_2.2_ComfyUI_Repackaged" "split_files/vae/wan_2.1_vae.safetensors" "$BASE_DIR/vae"

echo "=== Wan 2.2 Download — Complete! ==="
