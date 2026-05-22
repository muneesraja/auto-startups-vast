#!/bin/bash
# ---
# name: LTX Official ComfyUI Workflow 2.3 I2V
# workflow: video_ltx2_3_i2v
# aliases: [ltx-23-i2v-official, ltx-official, ltx23-official, ltx-i2v-official]
# description: Downloads all models for the official LTX 2.3 Image-to-Video workflow (Lightricks FP8 checkpoint + distilled LoRA + Gemma text encoder + spatial upscaler).
# size: ~47GB
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
mkdir -p "$BASE_DIR"/{checkpoints,loras,text_encoders,latent_upscale_models}

# Load shared HF download helper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh"; do
  [ -f "$f" ] && source "$f" && break
done

echo "==> Starting downloads..."

# 1. Checkpoint (Lightricks official FP8 — 29.1GB)
echo "[1/4] Transformer checkpoint (FP8)... "
hf_download "Lightricks/LTX-2.3-fp8" "ltx-2.3-22b-dev-fp8.safetensors" "$BASE_DIR/checkpoints"

# 2. Distilled LoRA (7.6GB)
echo "[2/4] Distilled LoRA..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-22b-distilled-lora-384.safetensors" "$BASE_DIR/loras"

# 3. Text Encoder — Gemma 3 12B FP4 Mixed (9.4GB)
echo "[3/4] Text encoder (Gemma FP4)..."
hf_download "Comfy-Org/ltx-2" "split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" "$BASE_DIR/text_encoders"

# 4. Spatial Upscale Model (~1GB)
echo "[4/4] Spatial upscaler..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "$BASE_DIR/latent_upscale_models"

echo "==> All downloads completed!"
echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
