#!/bin/bash
# ---
# name: Flux.2 Dev Turbo
# workflow: fl2dt_001
# aliases: [flux-2-dev-turbo, flux2-dev-turbo, flux-dev-turbo, flux2-turbo]
# description: Downloads Flux.2 Dev Turbo FP8 diffusion model + Mistral 3 Small FP8 text encoder + Flux2 VAE for T2I generation. Auto-updates ComfyUI and restarts after node install.
# size: ~51GB
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
export BASE_DIR
export COMFYUI_DIR

# ─── Detect ComfyUI launch args from running process ───
detect_comfyui_args() {
  local args
  args=$(ps aux | grep '[p]ython.*main.py' | head -1 | sed 's/.*main\.py//')
  if [ -n "$args" ]; then
    echo "$args"
  else
    # Default args if no running process found
    echo "--listen 0.0.0.0 --port 8188 --enable-cors-header"
  fi
}

# ─── Get the Python binary used by ComfyUI ───
detect_comfyui_python() {
  local python_bin
  
  # Method 1: Check the running ComfyUI process (skip unbuffer/tclsh wrappers)
  local comfyui_pid
  comfyui_pid=$(pgrep -af 'main.py' | grep -v 'unbuffer\|tclsh' | awk '{print $1}' | head -1)
  if [ -z "$comfyui_pid" ]; then
    # Fallback: find python3 process whose cmdline contains main.py
    comfyui_pid=$(ps -eo pid,comm,args | awk '$2 ~ /python/ && /main\.py/ {print $1; exit}')
  fi
  if [ -n "$comfyui_pid" ] && [ -f "/proc/$comfyui_pid/exe" ]; then
    python_bin=$(readlink -f "/proc/$comfyui_pid/exe" 2>/dev/null)
    if [ -n "$python_bin" ] && [ -x "$python_bin" ] && [[ "$python_bin" == *python* ]]; then
      echo "$python_bin"
      return
    fi
  fi
  
  # Method 2: Check venv locations (RunPod template)
  if [ -f /venv/main/bin/python3 ]; then
    echo "/venv/main/bin/python3"
    return
  elif [ -f "$COMFYUI_DIR/venv/bin/python3" ]; then
    echo "$COMFYUI_DIR/venv/bin/python3"
    return
  fi
  
  # Method 3: Fall back to system Python
  echo "$(which python3)"
}

COMFYUI_PYTHON=$(detect_comfyui_python)
COMFYUI_ARGS=$(detect_comfyui_args)
echo "  ComfyUI Python: $COMFYUI_PYTHON"
echo "  ComfyUI Args: $COMFYUI_ARGS"

# ─── PHASE 0: Update ComfyUI to latest ───
echo ""
echo "==> [Phase 0] Checking ComfyUI updates..."
cd "$COMFYUI_DIR"
CURRENT_VERSION=$($COMFYUI_PYTHON -c "from comfyui_version import __version__; print(__version__)" 2>/dev/null || echo "unknown")
echo "  Current version: $CURRENT_VERSION"

git fetch origin --quiet 2>/dev/null || true
LATEST_TAG=$(git describe --tags --abbrev=0 origin/master 2>/dev/null || git rev-parse --short origin/master 2>/dev/null || echo "unknown")
echo "  Latest tag: $LATEST_TAG"

if [ "$CURRENT_VERSION" != "$LATEST_TAG" ] && [ "$LATEST_TAG" != "unknown" ]; then
  echo "  🔄 Updating ComfyUI $CURRENT_VERSION → $LATEST_TAG..."
  git stash --quiet 2>/dev/null || true
  if git checkout "$LATEST_TAG" --quiet 2>/dev/null; then
    echo "  ✅ ComfyUI updated to $LATEST_TAG"
    # Update dependencies if requirements changed
    if [ -f requirements.txt ]; then
      echo "  📦 Updating dependencies..."
      $COMFYUI_PYTHON -m pip install -r requirements.txt -q 2>/dev/null || true
    fi
  else
    echo "  ⚠️  Failed to checkout $LATEST_TAG, staying on $CURRENT_VERSION"
    git checkout - --quiet 2>/dev/null || true
  fi
else
  echo "  ✅ ComfyUI already up to date ($CURRENT_VERSION)"
fi

# ─── Create model directories ───
echo ""
echo "==> Creating model directories..."
# Don't pre-create model subdirs here — hf_download uses
# hf_hub_download(local_dir=BASE_DIR/models/<sub>, filename="<sub>/foo") which
# creates the subdir from the filename prefix. Pre-creating the subdir causes
# the double-nesting bug fixed 2026-06-18.
mkdir -p "$BASE_DIR/models"

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

# ─── PHASE 1: Install custom nodes ───
echo ""
echo "==> [Phase 1] Setting up ComfyUI nodes..."
cd "$COMFYUI_DIR"
NODES_DIR="custom_nodes"
NODES_INSTALLED=0

# rgthree-comfy
if [ -d "$NODES_DIR/rgthree-comfy" ]; then
  echo "  ✅ rgthree-comfy already installed"
else
  echo "  📥 Installing rgthree-comfy..."
  git clone https://github.com/rgthree/rgthree-comfy "$NODES_DIR/rgthree-comfy" || true
  if [ -f "$NODES_DIR/rgthree-comfy/requirements.txt" ]; then
    $COMFYUI_PYTHON -m pip install -r "$NODES_DIR/rgthree-comfy/requirements.txt" -q 2>/dev/null || true
  fi
  NODES_INSTALLED=$((NODES_INSTALLED + 1))
fi

# KJNodes
# Use PascalCase (ComfyUI-KJNodes) to match the canonical GitHub repo name
# and stay consistent with the LTX 2.3 FFLF + cinematic-pipeline scripts.
if [ -d "$NODES_DIR/ComfyUI-KJNodes" ] || [ -d "$NODES_DIR/comfyui-kjnodes" ]; then
  echo "  ✅ KJNodes already installed"
else
  echo "  📥 Installing KJNodes..."
  git clone https://github.com/kijai/ComfyUI-KJNodes "$NODES_DIR/ComfyUI-KJNodes" || true
  if [ -f "$NODES_DIR/ComfyUI-KJNodes/requirements.txt" ]; then
    $COMFYUI_PYTHON -m pip install -r "$NODES_DIR/ComfyUI-KJNodes/requirements.txt" -q 2>/dev/null || true
  fi
  NODES_INSTALLED=$((NODES_INSTALLED + 1))
fi

# ─── PHASE 2: Download models ───
echo ""
echo "==> [Phase 2] Starting model downloads..."

# 1. Flux.2 Dev Turbo FP8 diffusion model (~32.2GB)
echo "[1/3] Flux.2 Dev Turbo FP8 diffusion model..."
hf_download "silveroxides/FLUX.2-dev-fp8_scaled" "flux2-dev-turbo-fp8mixed.safetensors" "$BASE_DIR/models/diffusion_models"

# 2. Mistral 3 Small FP8 text encoder (~18.5GB)
echo "[2/3] Mistral 3 Small FP8 text encoder..."
hf_download "silveroxides/FLUX.2-dev-fp8_scaled" "mistral_3_small_flux2_fp8mixed.safetensors" "$BASE_DIR/models/text_encoders"

# 3. Flux2 VAE (~336.2MB) — Comfy-Org/flux2-dev stores it under split_files/vae/.
# If we pass local_dir=$BASE_DIR/models/vae with the full blob path, the file
# lands at $BASE_DIR/models/vae/split_files/vae/foo (double-nested). Workaround:
# download with local_dir=$BASE_DIR (helper creates $BASE_DIR/split_files/vae/foo)
# then move the file to its final home.
echo "[3/3] Flux2 VAE..."
VAE_BLOB="split_files/vae/flux2-vae.safetensors"
VAE_FINAL="$BASE_DIR/models/vae/flux2-vae.safetensors"
hf_download "Comfy-Org/flux2-dev" "$VAE_BLOB" "$BASE_DIR"
if [ -f "$BASE_DIR/$VAE_BLOB" ] && [ "$BASE_DIR/$VAE_BLOB" != "$VAE_FINAL" ]; then
  mv "$BASE_DIR/$VAE_BLOB" "$VAE_FINAL"
  rmdir "$BASE_DIR/split_files/vae" 2>/dev/null || true
  rmdir "$BASE_DIR/split_files" 2>/dev/null || true
  echo "  ✅ Moved VAE to $VAE_FINAL"
fi

# ─── PHASE 3: Restart ComfyUI if nodes were installed ───
echo ""
if [ "$NODES_INSTALLED" -gt 0 ]; then
  echo "==> [Phase 3] Restarting ComfyUI to load new nodes..."
  
  # Find and kill existing ComfyUI process
  COMFYUI_PID=$(pgrep -f 'python.*main.py' | head -1)
  if [ -n "$COMFYUI_PID" ]; then
    echo "  🛑 Stopping ComfyUI (PID: $COMFYUI_PID)..."
    kill "$COMFYUI_PID" 2>/dev/null || true
    # Wait for process to exit (max 10s)
    for i in $(seq 1 10); do
      if ! kill -0 "$COMFYUI_PID" 2>/dev/null; then
        break
      fi
      sleep 1
    done
    # Force kill if still running
    if kill -0 "$COMFYUI_PID" 2>/dev/null; then
      echo "  ⚠️  Force killing ComfyUI..."
      kill -9 "$COMFYUI_PID" 2>/dev/null || true
    fi
  fi
  
  # Relaunch ComfyUI
  cd "$COMFYUI_DIR"
  echo "  🚀 Starting ComfyUI..."
  nohup $COMFYUI_PYTHON main.py $COMFYUI_ARGS > /workspace/comfyui.log 2>&1 &
  NEW_PID=$!
  echo "  ✅ ComfyUI started (PID: $NEW_PID)"
  
  # Wait for ComfyUI to be ready (check port)
  echo "  ⏳ Waiting for ComfyUI to be ready..."
  for i in $(seq 1 30); do
    if curl -s http://localhost:8188/system_stats > /dev/null 2>&1; then
      echo "  ✅ ComfyUI is ready!"
      break
    fi
    sleep 2
  done
else
  echo "==> [Phase 3] No new nodes installed — restart skipped"
  echo "  💡 To load models, click Refresh in the ComfyUI UI"
fi

echo ""
echo "==> All tasks completed!"
echo "📊 Summary:"
echo "  • ComfyUI version: $(cd "$COMFYUI_DIR" && $COMFYUI_PYTHON -c 'from comfyui_version import __version__; print(__version__)' 2>/dev/null || echo 'unknown')"
echo "  • Custom nodes installed this run: $NODES_INSTALLED"
echo "  • Models: 3 downloaded to $BASE_DIR/models"
