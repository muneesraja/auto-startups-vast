#!/bin/bash
# ---
# name: LTX 2.3 Director (Subgraphs)
# workflow: ltx-23-director-subgraphs
# aliases: [ltx director, ltx 2.3 director, ltx23 director, whatdreamscost, ltx-director-subgraphs]
# description: Downloads all models for the LTX 2.3 Director workflow with subgraphs (2-stage with spatial upscaler v1.1) — by WhatDreamsCost. Uses LTXVGemmaCLIPModelLoader, tiny VAE, audio + video VAEs, distilled LoRA, and FP8 transformer. Installs required custom nodes and restarts ComfyUI.
# size: ~46.2GB
# min_vram: 24GB
# nodes: [ComfyUI-KJNodes, ComfyUI-LTXVideo, WhatDreamsCost-ComfyUI]
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
CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"

echo "==> Setting up ComfyUI nodes..."
cd "$COMFYUI_DIR"

# Detect the Python that ComfyUI actually runs with (Vast.ai images use /venv/main/)
COMFY_PYTHON=""
COMFY_PIP=""
if [ -f /venv/main/bin/python3 ]; then
    COMFY_PYTHON="/venv/main/bin/python3"
    COMFY_PIP="/venv/main/bin/pip"
elif [ -f venv/bin/activate ]; then
    source venv/bin/activate
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$(which pip)"
elif [ -f .venv-cu128/bin/activate ]; then
    source .venv-cu128/bin/activate
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$(which pip)"
else
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$(which pip)"
fi
echo "  Using ComfyUI Python: $COMFY_PYTHON"

# Install custom nodes required by this workflow:
#   - ComfyUI-KJNodes        (LTX2SamplingPreviewOverride, VAELoaderKJ)
#   - ComfyUI-LTXVideo       (core LTX nodes)
#   - WhatDreamsCost-ComfyUI (LTXDirector, LTXDirectorGuide)
if command -v comfy &> /dev/null; then
    echo "  Using comfy-cli to install nodes..."
    comfy node install https://github.com/kijai/ComfyUI-KJNodes
    comfy node install https://github.com/Lightricks/ComfyUI-LTXVideo
    comfy node install https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI
else
    echo "  comfy-cli not found, cloning node repositories manually..."
    mkdir -p "$CUSTOM_NODES_DIR"
    cd "$CUSTOM_NODES_DIR"
    [ -d ComfyUI-KJNodes ]              || git clone https://github.com/kijai/ComfyUI-KJNodes              || true
    [ -d ComfyUI-LTXVideo ]             || git clone https://github.com/Lightricks/ComfyUI-LTXVideo      || true
    [ -d WhatDreamsCost-ComfyUI ]       || git clone https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI || true
    cd "$COMFYUI_DIR"
fi

# Install pip dependencies into ComfyUI's Python (not system Python)
echo "==> Installing node dependencies..."
for repo in ComfyUI-KJNodes ComfyUI-LTXVideo WhatDreamsCost-ComfyUI; do
    REQ="$CUSTOM_NODES_DIR/$repo/requirements.txt"
    if [ -f "$REQ" ]; then
        echo "  Installing $repo deps..."
        $COMFY_PIP install -q -r "$REQ" 2>&1 | tail -3 || true
    fi
done

echo "==> Creating directories..."
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

# 1. Transformer checkpoint (Lightricks FP8 — 29.1GB)
echo "[1/8] Transformer checkpoint (FP8)... "
hf_download "Lightricks/LTX-2.3-fp8" "ltx-2.3-22b-dev-fp8.safetensors" "$BASE_DIR/models/checkpoints"

# 2. Distilled LoRA (Kijai dynamic fro9 rank 105 — ~2.6GB)
echo "[2/8] Distilled LoRA (Kijai dynamic fro9 rank 105)..."
# Comfy-Org / Kijai repo stores this file under loras/ (HF repo
# browse-tree convention). If we pass local_dir=$BASE_DIR/models/loras
# with the full blob path, the file lands at
# $BASE_DIR/models/loras/loras/<file> (double-nested).
# Workaround: download with local_dir=$BASE_DIR (helper creates
# $BASE_DIR/loras/<file>), then move to the final home.
BLOB_PATH="$BASE_DIR/loras/ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors"
FINAL_PATH="$BASE_DIR/models/loras/ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors"
mkdir -p "$BASE_DIR/models/loras"
hf_download "Kijai/LTX2.3_comfy" "loras/ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  rmdir "$BASE_DIR/loras" 2>/dev/null || true
  echo "  ✅ Moved to $FINAL_PATH"
fi

# 3. Tiny VAE for previews (taeltx2_3 — 23.5MB)
echo "[3/8] Tiny VAE for previews (taeltx2_3)..."
# Comfy-Org / Kijai repo stores this file under vae/ (HF repo
# browse-tree convention). If we pass local_dir=$BASE_DIR/models/vae
# with the full blob path, the file lands at
# $BASE_DIR/models/vae/vae/<file> (double-nested).
# Workaround: download with local_dir=$BASE_DIR (helper creates
# $BASE_DIR/vae/<file>), then move to the final home.
BLOB_PATH="$BASE_DIR/vae/taeltx2_3.safetensors"
FINAL_PATH="$BASE_DIR/models/vae/taeltx2_3.safetensors"
mkdir -p "$BASE_DIR/models/vae"
hf_download "Kijai/LTX2.3_comfy" "vae/taeltx2_3.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  rmdir "$BASE_DIR/vae" 2>/dev/null || true
  echo "  ✅ Moved to $FINAL_PATH"
fi

# 4. Audio VAE (~365MB)
echo "[4/8] Audio VAE (LTX23_audio_vae_bf16)..."
# Comfy-Org / Kijai repo stores this file under vae/ (HF repo
# browse-tree convention). If we pass local_dir=$BASE_DIR/models/vae
# with the full blob path, the file lands at
# $BASE_DIR/models/vae/vae/<file> (double-nested).
# Workaround: download with local_dir=$BASE_DIR (helper creates
# $BASE_DIR/vae/<file>), then move to the final home.
BLOB_PATH="$BASE_DIR/vae/LTX23_audio_vae_bf16.safetensors"
FINAL_PATH="$BASE_DIR/models/vae/LTX23_audio_vae_bf16.safetensors"
mkdir -p "$BASE_DIR/models/vae"
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_audio_vae_bf16.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  rmdir "$BASE_DIR/vae" 2>/dev/null || true
  echo "  ✅ Moved to $FINAL_PATH"
fi

# 5. Video VAE (~1.5GB)
echo "[5/8] Video VAE (LTX23_video_vae_bf16)..."
# Comfy-Org / Kijai repo stores this file under vae/ (HF repo
# browse-tree convention). If we pass local_dir=$BASE_DIR/models/vae
# with the full blob path, the file lands at
# $BASE_DIR/models/vae/vae/<file> (double-nested).
# Workaround: download with local_dir=$BASE_DIR (helper creates
# $BASE_DIR/vae/<file>), then move to the final home.
BLOB_PATH="$BASE_DIR/vae/LTX23_video_vae_bf16.safetensors"
FINAL_PATH="$BASE_DIR/models/vae/LTX23_video_vae_bf16.safetensors"
mkdir -p "$BASE_DIR/models/vae"
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_video_vae_bf16.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  rmdir "$BASE_DIR/vae" 2>/dev/null || true
  echo "  ✅ Moved to $FINAL_PATH"
fi

# 6. Text encoder: Gemma 3 12B FP4 mixed (~9.4GB)
echo "[6/8] Text encoder (Gemma 3 12B FP4 mixed)..."
hf_download "Comfy-Org/ltx-2" "split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" "$BASE_DIR/models/text_encoders"

# 7. LTX text projection (~2.3GB) — loaded as clip_name2 in DualCLIPLoader
echo "[7/8] LTX text projection (clip_name2)..."
# Comfy-Org / Kijai repo stores this file under text_encoders/ (HF repo
# browse-tree convention). If we pass local_dir=$BASE_DIR/models/text_encoders
# with the full blob path, the file lands at
# $BASE_DIR/models/text_encoders/text_encoders/<file> (double-nested).
# Workaround: download with local_dir=$BASE_DIR (helper creates
# $BASE_DIR/text_encoders/<file>), then move to the final home.
BLOB_PATH="$BASE_DIR/text_encoders/ltx-2.3_text_projection_bf16.safetensors"
FINAL_PATH="$BASE_DIR/models/text_encoders/ltx-2.3_text_projection_bf16.safetensors"
mkdir -p "$BASE_DIR/models/text_encoders"
hf_download "Kijai/LTX2.3_comfy" "text_encoders/ltx-2.3_text_projection_bf16.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  rmdir "$BASE_DIR/text_encoders" 2>/dev/null || true
  echo "  ✅ Moved to $FINAL_PATH"
fi

# 8. Spatial upscaler v1.1 (~996MB)
echo "[8/8] Spatial upscaler (v1.1)..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "$BASE_DIR/models/latent_upscale_models"

echo "==> All downloads completed!"

# Restart ComfyUI so it picks up the newly installed custom nodes + model files
echo "==> Restarting ComfyUI..."
if command -v supervisorctl &> /dev/null; then
    supervisorctl restart comfyui 2>/dev/null \
        && echo "✅ ComfyUI restarted via supervisorctl" \
        || echo "⚠️  supervisorctl failed — restart ComfyUI manually"
elif [ -f /etc/supervisor/supervisord.conf ]; then
    supervisord -c /etc/supervisor/supervisord.conf 2>/dev/null \
        && echo "✅ ComfyUI supervisor started" \
        || echo "⚠️  supervisord failed — restart ComfyUI manually"
else
    echo "⚠️  No supervisor found — restart ComfyUI manually"
    echo "    Run: cd $COMFYUI_DIR && $COMFY_PYTHON main.py --listen 0.0.0.0 --port 8188 &"
fi

echo "==> Done!"
echo "👉 ComfyUI should now be loading the new nodes and models."
