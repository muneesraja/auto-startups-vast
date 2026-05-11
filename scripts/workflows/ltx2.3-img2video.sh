#!/bin/bash
# ---
# name: LTX 2.3 Image to Video
# aliases: [ltx2.3-img2video, ltx-img2video, image2video, ltx2.3 i2v]
# description: Downloads all models required for the LTX 2.3 Image to Video workflow.
# size: ~40GB
# min_vram: 24GB
# ---
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

echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/{checkpoints,loras,latent_upscale_models,text_encoders}

# Load shared HF download helper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for f in "$SCRIPT_DIR/hf_download.sh" "/workspace/hf_download.sh"; do
  [ -f "$f" ] && source "$f" && break
done

echo "==> Starting downloads..."

# Checkpoint
echo "[1/5] Checkpoint (FP8)..."
hf_download "Lightricks/LTX-2.3-fp8" "ltx-2.3-22b-dev-fp8.safetensors" "$BASE_DIR/checkpoints"

# LoRA (distilled)
echo "[2/5] LoRA (distilled)..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-22b-distilled-lora-384.safetensors" "$BASE_DIR/loras"

# LoRA (abliterated)
echo "[3/5] LoRA (abliterated Gemma)..."
hf_download "Comfy-Org/ltx-2" "split_files/loras/gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors" "$BASE_DIR/loras"

# Spatial Upscaler
echo "[4/5] Spatial Upscaler..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "$BASE_DIR/latent_upscale_models"

# Text Encoder (Gemma FP4)
echo "[5/5] Text Encoder (Gemma FP4)..."
hf_download "Comfy-Org/ltx-2" "split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" "$BASE_DIR/text_encoders"

echo "==> All downloads completed!"
echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
