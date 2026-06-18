#!/bin/bash
# ---
# name: Ideogram 4 T2I
# workflow: image_ideogram4_t2i
# aliases: [ideogram-4-t2i, ideogram4-t2i, ideogram v4, ideogram v4 t2i, image ideogram4, ideogram4 unet]
# description: Upgrades ComfyUI to >= v0.24.0 (required for Ideogram4Scheduler/DualModelGuider/CFGOverride core nodes), then downloads all models for the ComfyUI official Ideogram 4 text-to-image workflow — conditional + unconditional FP8 diffusion transformers, Qwen3-VL 8B FP8 text encoder, and Flux.2 VAE. Uses only core ComfyUI nodes — no custom node packs required.
# size: ~29.6GB
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
detect_comfyui_python() {
  # Prefer the running ComfyUI process's actual binary (skips tclsh/unbuffer wrappers)
  local pid
  pid=$(ps -eo pid,comm,args | awk '$2 ~ /python/ && /main\.py/ && !/tcl/ {print $1; exit}')
  if [ -n "$pid" ] && [ -f /proc/$pid/exe ]; then
    readlink -f /proc/$pid/exe 2>/dev/null && return
  fi
  # Fall back to known venv locations
  for p in /venv/main/bin/python3 "$COMFYUI_DIR/venv/bin/python3"; do
    [ -x "$p" ] && echo "$p" && return
  done
  which python3
}
COMFY_PYTHON=$(detect_comfyui_python)
COMFY_PIP="$COMFY_PYTHON -m pip"
echo "  Using ComfyUI Python: $COMFY_PYTHON"

# Counter incremented by Phase 0 (ComfyUI upgrade) and Phase 1 (node installs)
# when changes require a Phase 3 ComfyUI restart.
NODES_INSTALLED=0

# No custom node packs to install — this workflow uses only core ComfyUI nodes
# (Ideogram4Scheduler, DualModelGuider, CFGOverride, EmptyFlux2LatentImage, etc.,
# added to ComfyUI core in v0.24.0+). The base ComfyUI image does NOT include them.
# Phase 0 below upgrades ComfyUI if it's running < v0.24.0.

# ─── PHASE 0: Upgrade ComfyUI to >= v0.24.0 (required for Ideogram4 nodes) ───
echo ""
echo "==> [Phase 0] Checking ComfyUI version (>= v0.24.0 required for Ideogram4 nodes)..."
cd "$COMFYUI_DIR"
CURRENT_VERSION=$($COMFY_PYTHON -c "from comfyui_version import __version__; print(__version__)" 2>/dev/null || echo "unknown")
echo "  Current version: $CURRENT_VERSION"

# Use `git describe` to get the latest tag on the remote; fall back to short SHA
git fetch origin --quiet 2>/dev/null || true
LATEST_TAG=$(git describe --tags --abbrev=0 origin/master 2>/dev/null || git rev-parse --short origin/master 2>/dev/null || echo "unknown")
echo "  Latest tag: $LATEST_TAG"

# Compare versions (semver-ish). We only need a major.minor.patch tuple.
ver_ge() {
  # returns 0 (true) if $1 >= $2
  [ "$(printf '%s\n' "$1" "$2" | sort -V | tail -1)" = "$1" ]
}

NEEDS_UPGRADE=false
if [ "$CURRENT_VERSION" = "unknown" ] || ! ver_ge "$CURRENT_VERSION" "v0.24.0"; then
  NEEDS_UPGRADE=true
fi

if [ "$NEEDS_UPGRADE" = "true" ] && [ "$LATEST_TAG" != "unknown" ]; then
  echo "  🔄 Upgrading ComfyUI $CURRENT_VERSION → $LATEST_TAG..."
  git stash --quiet 2>/dev/null || true
  if git checkout "$LATEST_TAG" --quiet 2>/dev/null; then
    echo "  ✅ ComfyUI checked out to $LATEST_TAG"
    if [ -f requirements.txt ]; then
      echo "  📦 Updating dependencies..."
      $COMFY_PYTHON -m pip install -r requirements.txt -q 2>/dev/null || true
    fi
    NODES_INSTALLED=$((NODES_INSTALLED + 1))  # triggers Phase 3 restart
  else
    echo "  ⚠️  Failed to checkout $LATEST_TAG, staying on $CURRENT_VERSION"
    git checkout - --quiet 2>/dev/null || true
  fi
else
  echo "  ✅ ComfyUI $CURRENT_VERSION already >= v0.24.0"
fi

# (Re-)export for the hf_download helper which reads $COMFYUI_DIR
cd "$COMFYUI_DIR"

echo "==> Creating directories..."
# NOTE: do NOT pre-create subdirs here — hf_download uses hf_hub_download(local_dir)
# which preserves the filename's directory prefix. If we pre-create e.g. $BASE_DIR/models/vae/
# and pass filename="vae/flux2-vae.safetensors", the file lands in $BASE_DIR/models/vae/vae/.
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

# 1. Ideogram 4 conditional diffusion model — FP8 scaled (~9.3GB)
# Used as the primary UNet in the workflow's DualModelGuider.
# local_dir = $BASE_DIR (not $BASE_DIR/diffusion_models) — the helper creates the subdir
# from the filename prefix, preventing double-nested $BASE_DIR/models/diffusion_models/diffusion_models/.
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

# ─── PHASE 3: Restart ComfyUI if any upgrade or node install happened ───
echo ""
if [ "$NODES_INSTALLED" -gt 0 ]; then
  echo "==> [Phase 3] Restarting ComfyUI to pick up upgrades/new nodes..."
  if command -v supervisorctl &> /dev/null && supervisorctl status comfyui &> /dev/null; then
    supervisorctl restart comfyui 2>&1
    # Wait for ComfyUI to be ready (extract port from running process)
    PORT=$(ps -eo pid,comm,args | awk '$2 ~ /python/ && /main\.py/ && !/tcl/ {for(i=1;i<=NF;i++) if($i=="--port"){print $(i+1); exit}}')
    [ -z "$PORT" ] && PORT=8188
    echo "  ⏳ Waiting for ComfyUI on port $PORT..."
    for i in $(seq 1 40); do
      if curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/system_stats 2>/dev/null | grep -q 200; then
        echo "  ✅ ComfyUI ready after ${i}s"; break
      fi
      sleep 2
    done
  else
    echo "  ⚠️  supervisorctl not available — restart ComfyUI manually:"
    echo "    cd $COMFYUI_DIR && $COMFY_PYTHON main.py --listen 0.0.0.0 --port 8188 --enable-cors-header &"
  fi
else
  echo "==> [Phase 3] No upgrades needed — ComfyUI already current"
  echo "  💡 Click Refresh in the ComfyUI UI to load new models"
fi

echo ""
echo "==> All tasks completed!"
echo "📊 Summary:"
echo "  • ComfyUI version: $($COMFY_PYTHON -c 'from comfyui_version import __version__; print(__version__)' 2>/dev/null || echo 'unknown')"
echo "  • Upgrades/installs this run: $NODES_INSTALLED"
echo "  • Models: 4 downloaded to $BASE_DIR/models"
echo "👉 Refresh the ComfyUI UI to load the Ideogram 4 workflow."
