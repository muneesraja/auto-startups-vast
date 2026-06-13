#!/bin/bash
# ---
# name: Ideogram 4 T2I
# workflow: image_ideogram4_t2i
# aliases: [ideogram-4-t2i, ideogram4-t2i, ideogram v4, ideogram v4 t2i, image ideogram4, ideogram4 unet]
# description: Downloads all models for the ComfyUI official Ideogram 4 text-to-image workflow — conditional + unconditional FP8 diffusion transformers, Qwen3-VL 8B FP8 text encoder, and Flux.2 VAE. Uses only core ComfyUI nodes (Ideogram4Scheduler, DualModelGuider, CFGOverride, EmptyFlux2LatentImage added in 0.23.0+) — no custom node packs required.
# size: ~29.6GB
# min_vram: 24GB
# ---
set -e

# Platform-aware base directory detection (Vast.ai vs RunPod)
if [ -d "/workspace/runpod-slim/ComfyUI" ]; then
  BASE_DIR="/workspace/runpod-slim/ComfyUI/models"
  COMFYUI_DIR="/workspace/runpod-slim/ComfyUI"
  echo "  Platform: RunPod (base: $BASE_DIR)"
elif [ -d "/workspace/ComfyUI" ]; then
  BASE_DIR="/workspace/ComfyUI/models"
  COMFYUI_DIR="/workspace/ComfyUI"
  echo "  Platform: Vast.ai (base: $BASE_DIR)"
else
  BASE_DIR="/workspace/ComfyUI/models"
  COMFYUI_DIR="/workspace/ComfyUI"
  echo "  ⚠️  No ComfyUI dir found, defaulting to $BASE_DIR"
fi

CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"

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

# No custom node packs to install — this workflow uses only core ComfyUI nodes
# (Ideogram4Scheduler, DualModelGuider, CFGOverride, EmptyFlux2LatentImage, etc.,
# all added to ComfyUI core in v0.23.0+). The base ComfyUI image already includes them.
# If running an older ComfyUI (< 0.23.0), update ComfyUI first:
#   cd $COMFYUI_DIR && git pull
# Docs: https://docs.comfy.org/changelog

echo "==> Creating directories..."
# NOTE: do NOT pre-create subdirs here — hf_download uses hf_hub_download(local_dir)
# which preserves the filename's directory prefix. If we pre-create e.g. $BASE_DIR/vae/
# and pass filename="vae/flux2-vae.safetensors", the file lands in $BASE_DIR/vae/vae/.
# Passing $BASE_DIR as the local_dir and letting the helper create subdirs avoids that.
mkdir -p "$BASE_DIR"

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

# 1. Ideogram 4 conditional diffusion model — FP8 scaled (~9.3GB)
# Used as the primary UNet in the workflow's DualModelGuider.
# local_dir = $BASE_DIR (not $BASE_DIR/diffusion_models) — the helper creates the subdir
# from the filename prefix, preventing double-nested $BASE_DIR/diffusion_models/diffusion_models/.
echo "[1/4] Ideogram 4 diffusion model (FP8 scaled)..."
hf_download "Comfy-Org/Ideogram-4" "diffusion_models/ideogram4_fp8_scaled.safetensors" "$BASE_DIR"

# 2. Ideogram 4 unconditional diffusion model — FP8 scaled (~9.3GB)
# Used as the unconditional UNet in DualModelGuider (asymmetric CFG, drops text tokens)
echo "[2/4] Ideogram 4 unconditional diffusion model (FP8 scaled)..."
hf_download "Comfy-Org/Ideogram-4" "diffusion_models/ideogram4_unconditional_fp8_scaled.safetensors" "$BASE_DIR"

# 3. Qwen3-VL 8B FP8 scaled text encoder (~10.6GB)
# Used as the CLIP loader (type=ideogram) for prompt encoding
echo "[3/4] Qwen3-VL 8B text encoder (FP8 scaled)..."
hf_download "Comfy-Org/Ideogram-4" "text_encoders/qwen3vl_8b_fp8_scaled.safetensors" "$BASE_DIR"

# 4. Flux.2 VAE (~336MB)
# Bundled in the same Comfy-Org/Ideogram-4 repo for convenience (single-source download)
echo "[4/4] Flux.2 VAE..."
hf_download "Comfy-Org/Ideogram-4" "vae/flux2-vae.safetensors" "$BASE_DIR"

echo "==> All downloads completed!"

# Restart ComfyUI so it picks up the new model files
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
echo "👉 ComfyUI should now be loading the new models."
