#!/bin/bash
# ---
# name: HiDream O1 Dev + Gemma 4 + LoRA
# workflow: hidream_001
# aliases: [hidream-o1, hidream-o1-dev, hidream-gemma4, hidream-o1-gemma4, hidream-o1-lora, image-hidream-o1-dev-1]
# description: Downloads HiDream O1 Image Dev FP8 checkpoint + Gemma 4 E4B text encoder + rank 224 LoRA for image generation.
# size: ~18.5GB
# min_vram: 24GB
# ---
set -e

# Platform-aware base directory detection.
# IMPORTANT: BASE_DIR must be the ComfyUI root (NOT .../models) so that
# hf_hub_download(local_dir=BASE_DIR/models/<sub>, filename="<sub>/foo.safetensors")
# lands files at $BASE_DIR/models/<sub>/foo.safetensors. Setting BASE_DIR to
# .../models and then pre-creating $BASE_DIR/<sub>/ caused nested paths like
# models/<sub>/<sub>/foo.safetensors (fixed 2026-06-18).
if [ -d "/workspace/runpod-slim/ComfyUI" ]; then
  BASE_DIR="/workspace/runpod-slim/ComfyUI"
  echo "  Platform: RunPod (base: $BASE_DIR)"
elif [ -d "/workspace/ComfyUI" ]; then
  BASE_DIR="/workspace/ComfyUI"
  echo "  Platform: Vast.ai (base: $BASE_DIR)"
else
  BASE_DIR="/workspace/ComfyUI"
  echo "  ⚠️  No ComfyUI dir found, defaulting to $BASE_DIR"
fi
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
# Don't pre-create model subdirs here — hf_download uses
# hf_hub_download(local_dir=BASE_DIR/models/<sub>, filename="<sub>/foo")
# which creates the subdir from the filename prefix. Pre-creating the subdir
# causes the double-nesting bug fixed 2026-06-18.
mkdir -p "$BASE_DIR"

# Load shared HF download helper (auto-fetch if not present — Vast instances don't bundle it)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_HF_HELPER=""
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh" "/tmp/_hf_download.sh"; do
  [ -f "$f" ] && _HF_HELPER="$f" && break
done
if [ -z "$_HF_HELPER" ]; then
  echo "  Fetching _hf_download.sh from GitHub..."
  GITHUB_BASE="https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/workflows/setup"
  _HF_HELPER="/tmp/_hf_download.sh"
  if ! curl -sSL --fail "$GITHUB_BASE/_hf_download.sh" -o "$_HF_HELPER" 2>/dev/null; then
    # raw.githubusercontent.com fallback
    curl -sSL --fail "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/workflows/setup/_hf_download.sh" -o "$_HF_HELPER" \
      || { echo "❌ FATAL: could not download _hf_download.sh"; exit 1; }
  fi
  chmod +x "$_HF_HELPER"
fi
source "$_HF_HELPER"
unset _HF_HELPER

echo "==> Starting downloads..."

# NOTE: hf_download(repo, filename, local_dir) places file at local_dir/filename.
# Since HF repos use subdirs (e.g. "checkpoints/file.safetensors"), pass $BASE_DIR
# as local_dir so the repo structure is preserved correctly (avoids double nesting).

# 1. HiDream O1 Image Dev FP8 checkpoint (~8.1GB)
echo "[1/2] HiDream O1 Image Dev FP8 checkpoint..."
hf_download "Comfy-Org/HiDream-O1-Image" "checkpoints/hidream_o1_image_dev_fp8_scaled.safetensors" "$BASE_DIR"

# 2. Gemma 4 E4B FP8 text encoder (~9.1GB)
echo "[2/3] Gemma 4 E4B FP8 text encoder..."
hf_download "Comfy-Org/gemma-4" "text_encoders/gemma4_e4b_it_fp8_scaled.safetensors" "$BASE_DIR"

# 3. HiDream O1 Dev LoRA rank 224 BF16 (~1.3GB)
echo "[3/3] HiDream O1 Dev LoRA rank 224 BF16..."
hf_download "Kijai/hidream-O1-image_comfy" "loras/hidream_o1_image_dev_2604_lora_avg_rankg_224_bf16.safetensors" "$BASE_DIR"

echo "==> All downloads completed!"
echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
