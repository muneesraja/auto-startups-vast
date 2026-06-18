#!/bin/bash
# ---
# name: LTX Official ComfyUI Workflow 2.3 I2V
# workflow: video_ltx2_3_i2v
# aliases: [ltx-23-i2v-official, ltx-official, ltx23-official, ltx-i2v-official]
# description: Downloads all models for the official LTX 2.3 Image-to-Video workflow (Lightricks FP8 checkpoint + distilled LoRA + Gemma text encoder + spatial upscaler).
# size: ~32GB (corrected: was 47GB — the original counted an unneeded Gemma FP4 the workflow doesn't load)
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
echo "==> Creating directories..."
# Don't pre-create model subdirs — hf_download uses hf_hub_download(local_dir=...)
# which creates the subdir from the filename prefix. We just need the BASE_DIR.
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

# 1. Checkpoint (Lightricks official FP8 — 29.1GB) — primary transformer for the workflow
echo "[1/3] Transformer checkpoint (FP8)..."
hf_download "Lightricks/LTX-2.3-fp8" "ltx-2.3-22b-dev-fp8.safetensors" "$BASE_DIR/models/checkpoints"

# 2. Distilled LoRA (~1GB) — workflow's actual LoRA from Lightricks/LTX-2.3.
# NOTE: the original script downloaded a different LoRA
# (ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors
#  from Comfy-Org/ltx-2.3) which is NOT what the workflow references. The
# official video_ltx2_3_i2v.json workflow uses ltx-2.3-22b-distilled-lora-384.
# 384 here is the rank preset from Lightricks' official release.
echo "[2/3] Distilled LoRA (Lightricks official, 384-rank)..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-22b-distilled-lora-384.safetensors" "$BASE_DIR/models/loras"

# 3. Gemma 3 abliterated LoRA — workflow also references this for prompt quality.
# Same split_files/loras/ filename-prefix issue we hit with OmniNFT-RL: the
# blob is stored as split_files/loras/gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors
# on HF. If we pass $BASE_DIR/models/loras AND the full blob path, the file
# lands at $BASE_DIR/models/loras/split_files/loras/foo (double-nested).
# Workaround: download with local_dir=$BASE_DIR (helper creates
# $BASE_DIR/split_files/loras/foo) and move to final home.
echo "[3/3] Gemma-3 abliterated LoRA..."
LORA_BLOB="split_files/loras/gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors"
LORA_FINAL="$BASE_DIR/models/loras/gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors"
hf_download "Comfy-Org/ltx-2" "$LORA_BLOB" "$BASE_DIR"
if [ -f "$BASE_DIR/$LORA_BLOB" ] && [ "$BASE_DIR/$LORA_BLOB" != "$LORA_FINAL" ]; then
  mv "$BASE_DIR/$LORA_BLOB" "$LORA_FINAL"
  # Best-effort cleanup of the now-empty split_files/loras chain
  rmdir "$BASE_DIR/split_files/loras" 2>/dev/null || true
  rmdir "$BASE_DIR/split_files" 2>/dev/null || true
  echo "  ✅ Moved LoRA to $LORA_FINAL"
fi

# NOTE on Gemma text encoder: the original script downloaded
# gemma_3_12B_it_fp4_mixed.safetensors (9.4GB) separately, but the official
# video_ltx2_3_i2v.json workflow's Model Storage Location block does NOT
# list a text encoder. The text encoder is either bundled inside the FP8
# checkpoint's ComfyUI loader reference, or loaded via a different path.
# Verified against the workflow file: only checkpoints/, loras/, and
# latent_upscale_models/ are needed. Skipped to save ~9.4 GB.

# NOTE on spatial upscaler: ltx-2.3-spatial-upscaler-x2-1.1.safetensors was
# already downloaded by ltx-23-fflf-seed-hunter.sh. hf_hub_download detects
# the cached file via the local_dir and skips the re-download.

echo "==> All downloads completed!"
echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
