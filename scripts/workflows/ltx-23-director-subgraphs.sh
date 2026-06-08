#!/bin/bash
# ---
# name: LTX 2.3 Director (Subgraphs)
# workflow: ltx-23-director-subgraphs
# aliases: [ltx director, ltx 2.3 director, ltx23 director, whatdreamscost, ltx-director-subgraphs]
# description: Downloads all models for the LTX 2.3 Director workflow with subgraphs (2-stage with spatial upscaler v1.1) — by WhatDreamsCost. Uses LTXVGemmaCLIPModelLoader, tiny VAE, audio + video VAEs, distilled LoRA, and FP8 transformer.
# size: ~46.2GB
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
mkdir -p "$BASE_DIR"/{checkpoints,loras,text_encoders,vae,latent_upscale_models}

# Load shared HF download helper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh"; do
  [ -f "$f" ] && source "$f" && break
done

echo "==> Starting downloads..."

# 1. Transformer checkpoint (Lightricks FP8 — 29.1GB)
echo "[1/8] Transformer checkpoint (FP8)... "
hf_download "Lightricks/LTX-2.3-fp8" "ltx-2.3-22b-dev-fp8.safetensors" "$BASE_DIR/checkpoints"

# 2. Distilled LoRA (Kijai dynamic fro9 rank 105 — ~2.6GB)
echo "[2/8] Distilled LoRA (Kijai dynamic fro9 rank 105)..."
hf_download "Kijai/LTX2.3_comfy" "loras/ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors" "$BASE_DIR/loras"

# 3. Tiny VAE for previews (taeltx2_3 — 23.5MB)
echo "[3/8] Tiny VAE for previews (taeltx2_3)..."
hf_download "Kijai/LTX2.3_comfy" "vae/taeltx2_3.safetensors" "$BASE_DIR/vae"

# 4. Audio VAE (~365MB)
echo "[4/8] Audio VAE (LTX23_audio_vae_bf16)..."
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_audio_vae_bf16.safetensors" "$BASE_DIR/vae"

# 5. Video VAE (~1.5GB)
echo "[5/8] Video VAE (LTX23_video_vae_bf16)..."
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_video_vae_bf16.safetensors" "$BASE_DIR/vae"

# 6. Text encoder: Gemma 3 12B FP4 mixed (~9.4GB)
echo "[6/8] Text encoder (Gemma 3 12B FP4 mixed)..."
hf_download "Comfy-Org/ltx-2" "split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" "$BASE_DIR/text_encoders"

# 7. LTX text projection (~2.3GB) — loaded as clip_name2 in DualCLIPLoader
echo "[7/8] LTX text projection (clip_name2)..."
hf_download "Kijai/LTX2.3_comfy" "text_encoders/ltx-2.3_text_projection_bf16.safetensors" "$BASE_DIR/text_encoders"

# 8. Spatial upscaler v1.1 (~996MB)
echo "[8/8] Spatial upscaler (v1.1)..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "$BASE_DIR/latent_upscale_models"

echo "==> All downloads completed!"
echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
