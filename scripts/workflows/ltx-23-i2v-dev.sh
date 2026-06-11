#!/bin/bash
# ---
# name: LTX Dev ComfyUI Workflow 2.3 I2V
# workflow: ltx-23-i2v-dev
# aliases: [ltx-23-i2v-dev]
# description: Downloads all models for the dev LTX 2.3 Image-to-Video workflow (Lightricks FP8 checkpoint + distilled LoRA + Gemma text encoder + spatial upscaler).
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

# Load shared HF download helper (auto-fetch if not present — Vast instances don't bundle it)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_HF_HELPER=""
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh" "/tmp/_hf_download.sh"; do
  [ -f "$f" ] && _HF_HELPER="$f" && break
done
if [ -z "$_HF_HELPER" ]; then
  echo "  Fetching _hf_download.sh from GitHub..."
  GITHUB_BASE="https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/workflows"
  _HF_HELPER="/tmp/_hf_download.sh"
  if ! curl -sSL --fail "$GITHUB_BASE/_hf_download.sh" -o "$_HF_HELPER" 2>/dev/null; then
    # raw.githubusercontent.com fallback
    curl -sSL --fail "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/workflows/_hf_download.sh" -o "$_HF_HELPER" \
      || { echo "❌ FATAL: could not download _hf_download.sh"; exit 1; }
  fi
  chmod +x "$_HF_HELPER"
fi
source "$_HF_HELPER"
unset _HF_HELPER

echo "==> Starting downloads..."

# 1. Checkpoint (Lightricks official FP8 — 29.1GB)
echo "[1/4] Transformer checkpoint (FP8)... "
hf_download "Lightricks/LTX-2.3-fp8" "ltx-2.3-22b-dev-fp8.safetensors" "$BASE_DIR/checkpoints"

# 2. Distilled LoRA (dynamic rank 111, ~6GB)
echo "[2/4] Distilled LoRA..."
hf_download "Comfy-Org/ltx-2.3" "split_files/loras/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors" "$BASE_DIR/loras"

# 3. Text Encoder — Gemma 3 12B FP4 Mixed (9.4GB)
echo "[3/4] Text encoder (Gemma FP4)..."
hf_download "Comfy-Org/ltx-2" "split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" "$BASE_DIR/text_encoders"

# 4. Spatial Upscale Model (~1GB)
echo "[4/4] Spatial upscaler..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "$BASE_DIR/latent_upscale_models"

echo "==> All downloads completed!"
echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
