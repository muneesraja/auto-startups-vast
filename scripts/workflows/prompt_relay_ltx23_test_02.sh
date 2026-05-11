#!/bin/bash
# ---
# name: LTX 2.3 Prompt Relay (prompt_relay_ltx23_test_02)
# workflow: prltx23_002
# aliases: [prompt-relay-ltx23-test-02, prompt_relay_ltx23_test_02, ltx23-prompt-relay, ltx23-oldman-redpanda]
# description: Download LTX 2.3 models for prompt_relay_ltx23_test_02 workflow — old man & red panda, 4 segments (123+122+122+122 frames), PromptRelayEncodeTimeline
# size: ~61.4GB
# min_vram: 24GB
# ---
# =============================================================================
# LTX 2.3 Prompt Relay — Model Download (HF CLI, authenticated)
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

# Install required custom nodes
COMFYUI_DIR="$(dirname "$BASE_DIR")"
CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"

echo "==> Installing custom nodes..."

# ComfyUI-PromptRelay (required for PromptRelayEncodeTimeline node)
if [ ! -d "$CUSTOM_NODES_DIR/ComfyUI-PromptRelay" ]; then
  echo "  Installing ComfyUI-PromptRelay..."
  git clone https://github.com/kijai/ComfyUI-PromptRelay.git "$CUSTOM_NODES_DIR/ComfyUI-PromptRelay" 2>&1
  if [ -f "$CUSTOM_NODES_DIR/ComfyUI-PromptRelay/requirements.txt" ]; then
    pip install -r "$CUSTOM_NODES_DIR/ComfyUI-PromptRelay/requirements.txt" 2>&1 | tail -3
  fi
  echo "  ✅ ComfyUI-PromptRelay installed"
else
  echo "  ✅ ComfyUI-PromptRelay already installed"
fi

echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/{diffusion_models,vae,text_encoders,loras}

# Load shared HF download helper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/hf_download.sh" ]; then
  source "$SCRIPT_DIR/hf_download.sh"
elif [ -f "/workspace/hf_download.sh" ]; then
  source "/workspace/hf_download.sh"
else
  echo "❌ hf_download.sh not found — falling back to aria2c"
  # Fallback: install aria2 and use it
  command -v aria2c &>/dev/null || apt-get update && apt-get install -y aria2
  hf_download() {
    local url="https://huggingface.co/$1/resolve/main/$2"
    aria2c -x 16 -s 16 -k 1M -d "$3" -o "$(basename "$2")" "$url"
  }
fi

echo "==> Starting downloads..."

# UNET (LTX 2.3 Transformer, fp8 scaled) — ~24GB
echo "[1/6] Transformer (fp8 scaled)..."
hf_download "Kijai/LTX2.3_comfy" "diffusion_models/ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors" "$BASE_DIR/diffusion_models"

# Video VAE (bf16)
echo "[2/6] Video VAE..."
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_video_vae_bf16.safetensors" "$BASE_DIR/vae"

# Audio VAE (bf16)
echo "[3/6] Audio VAE..."
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_audio_vae_bf16.safetensors" "$BASE_DIR/vae"

# Text Projection (bf16)
echo "[4/6] Text Projection..."
hf_download "Kijai/LTX2.3_comfy" "text_encoders/ltx-2.3_text_projection_bf16.safetensors" "$BASE_DIR/text_encoders"

# Gemma 3 CLIP (12B text encoder)
echo "[5/6] Gemma 3 12B text encoder..."
hf_download "Comfy-Org/ltx-2" "split_files/text_encoders/gemma_3_12B_it.safetensors" "$BASE_DIR/text_encoders"

# LoRA (384-1.1)
echo "[6/6] LoRA (384-1.1)..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-22b-distilled-lora-384-1.1.safetensors" "$BASE_DIR/loras"

echo ""
echo "==> All downloads completed!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
