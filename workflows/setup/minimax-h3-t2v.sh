#!/bin/bash
# ---
# name: MiniMax H3 T2V (text/image to video with native audio)
# workflow: video_minimax_h3_t2v
# aliases: [minimax-h3-t2v, minimax-h3, minimax_h3, h3-t2v, h3, MiniMax-H3, MiniMax H3]
# description: Upgrades ComfyUI to >= v0.30.0 (required for MiniMaxH3ImageToVideo core node, merged 2026-08-03), then downloads the 4 MiniMax-H3 models from Comfy-Org/MiniMax-H3 — fl2va pruned int8 convrot diffusion transformer (~20GB), Qwen3-VL 32B MiniMax H3 NVFP4 AWQ text encoder (~15GB), MiniMax H3 video VAE FP16 (~5GB), and MiniMax H3 audio VAE FP32 (~0.6GB). H3 is a single packed-DiT that jointly models text/image/video/audio in one forward pass — output is video with native stereo audio (voice, SFX, music), not video+audio layered on. Uses only core ComfyUI nodes — no custom node packs required. (Filename: video_minimax_h3_t2v.json)
# size: ~40.5GB
# min_vram: 24GB
# ---
# Platform-aware base directory detection.
# IMPORTANT: BASE_DIR must be the ComfyUI root (NOT .../models) so that
# hf_hub_download(local_dir=BASE_DIR/models/<sub>, filename="<sub>/foo.safetensors")
# lands files at $BASE_DIR/models/<sub>/foo.safetensors. Setting BASE_DIR to
# .../models and then pre-creating $BASE_DIR/<sub>/ caused nested paths like
# models/<sub>/<sub>/foo.safetensors (fixed 2026-06-18).
set -e

if [ -d "/workspace/runpod-slim/ComfyUI" ]; then
  COMFYUI_DIR="/workspace/runpod-slim/ComfyUI"
  BASE_DIR="/workspace/runpod-slim/ComfyUI"
  echo "  Platform: RunPod (base: $BASE_DIR)"
elif [ -d "/workspace/ComfyUI" ]; then
  COMFYUI_DIR="/workspace/ComfyUI"
  BASE_DIR="/workspace/ComfyUI"
  echo "  Platform: Vast.ai (base: $BASE_DIR)"
else
  COMFYUI_DIR="/workspace/ComfyUI"
  BASE_DIR="/workspace/ComfyUI"
  echo "  ⚠️  No ComfyUI dir found, defaulting to $BASE_DIR"
fi

# Detect the Python that ComfyUI actually runs with (Vast.ai images use /venv/main/)
detect_comfyui_python() {
  # Prefer the running ComfyUI process's actual binary (skips tclsh/unbuffer wrappers)
  local pid
  pid=$(ps -eo pid,comm,args | awk '$2 ~ /python/ && /main\.py/ && !/tcl/ {print $1; exit}')
  if [ -n "$pid" ] && [ -f /proc/$pid/exe ]; then
    readlink -f /proc/$pid/exe 2>/dev/null && return
  fi
  # Fall back to known venv locations
  for p in /venv/main/bin/python3 "$COMFYUI_DIR/venv/bin/python3" "$COMFYUI_DIR/.venv-cu128/bin/python3"; do
    [ -x "$p" ] && echo "$p" && return
  done
  which python3
}
COMFY_PYTHON=$(detect_comfyui_python)
COMFY_PIP="$COMFY_PYTHON -m pip"
echo "  Using ComfyUI Python: $COMFY_PYTHON"

# Counter incremented by Phase 0 (ComfyUI upgrade) when changes require a Phase 3 restart.
NODES_INSTALLED=0

# No custom node packs to install — this workflow uses only core ComfyUI nodes.
# MiniMaxH3ImageToVideo (and EmptyMiniMaxH3LatentAV, MiniMaxH3SigmaShift, etc.) live in
# comfy_extras/nodes_minimax_h3.py, added to ComfyUI core on 2026-08-03 (PR #15224, first
# released tag v0.30.0). The base Vast/RunPod ComfyUI image ships v0.23.0 — these nodes
# are missing. Phase 0 below upgrades ComfyUI to >= v0.30.0.

# ─── PHASE 0: Upgrade ComfyUI to >= v0.30.0 (required for MiniMax H3 nodes) ───
echo ""
echo "==> [Phase 0] Checking ComfyUI version (>= v0.30.0 required for MiniMax H3 nodes)..."
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
if [ "$CURRENT_VERSION" = "unknown" ] || ! ver_ge "$CURRENT_VERSION" "v0.30.0"; then
  NEEDS_UPGRADE=true
fi

if [ "$NEEDS_UPGRADE" = "true" ] && [ "$LATEST_TAG" != "unknown" ]; then
  echo "  🔄 Upgrading ComfyUI $CURRENT_VERSION → $LATEST_TAG..."
  # Plain `git stash` (no --include-untracked) — the .venv-cu128/ dir is untracked
  # and stash --include-untracked would silently delete it (Bug 9, 2026-07-23).
  git stash --quiet 2>/dev/null || true
  if git checkout "$LATEST_TAG" --quiet 2>/dev/null; then
    echo "  ✅ ComfyUI checked out to $LATEST_TAG"
    if [ -f requirements.txt ]; then
      echo "  📦 Updating dependencies..."
      $COMFY_PIP install -r requirements.txt -q 2>/dev/null || true
    fi
    NODES_INSTALLED=$((NODES_INSTALLED + 1))  # triggers Phase 3 restart
  else
    echo "  ⚠️  Failed to checkout $LATEST_TAG, staying on $CURRENT_VERSION"
    git checkout - --quiet 2>/dev/null || true
  fi
else
  echo "  ✅ ComfyUI $CURRENT_VERSION already >= v0.30.0"
fi

# (Re-)export for the hf_download helper which reads $COMFYUI_DIR
cd "$COMFYUI_DIR"

echo "==> Creating directories..."
# NOTE: do NOT pre-create subdirs here — hf_download uses hf_hub_download(local_dir)
# which preserves the filename's directory prefix. If we pre-create e.g. $BASE_DIR/models/vae/
# and pass filename="vae/foo.safetensors", the file lands in $BASE_DIR/models/vae/vae/.
# Passing $BASE_DIR/models/<sub> as the local_dir and letting the helper create subdirs
# from the filename prefix is the safe pattern (verified 2026-08-03, matches pitfall 8).
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

# 1. MiniMax H3 fl2va pruned int8 convrot — the main packed-DiT (~20GB)
# Jointly models text/image/video/audio in one forward pass. Used by MiniMaxH3ImageToVideo.
# Repo: Comfy-Org/MiniMax-H3, file lives under diffusion_models/.
echo "[1/4] MiniMax H3 fl2va packed-DiT (pruned int8 convrot)..."
hf_download "Comfy-Org/MiniMax-H3" "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors" "$BASE_DIR/models/diffusion_models"

# 2. Qwen3-VL 32B MiniMax H3 NVFP4 AWQ text encoder (~15GB)
# Used as the CLIP loader (type=minimax) for prompt encoding. AWQ-quantized to fit
# 24GB alongside the 20GB diffusion model.
echo "[2/4] Qwen3-VL 32B text encoder (NVFP4 AWQ)..."
hf_download "Comfy-Org/MiniMax-H3" "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors" "$BASE_DIR/models/text_encoders"

# 3. MiniMax H3 video VAE FP16 (~5GB)
# Decodes the sampled video latents to frames. Bundled in the same Comfy-Org/MiniMax-H3
# repo so all 4 files are single-source downloads.
echo "[3/4] MiniMax H3 video VAE (FP16)..."
hf_download "Comfy-Org/MiniMax-H3" "vae/minimax_h3_video_vae_fp16.safetensors" "$BASE_DIR/models/vae"

# 4. MiniMax H3 audio VAE FP32 (~0.6GB)
# Decodes the sampled audio latents to stereo audio. Required for H3's native-audio
# output — without this, CreateVideo will get a silent stream.
echo "[4/4] MiniMax H3 audio VAE (FP32)..."
hf_download "Comfy-Org/MiniMax-H3" "vae/minimax_h3_audio_vae_fp32.safetensors" "$BASE_DIR/models/vae"

echo "==> All downloads completed!"

# ─── PHASE 3: Restart ComfyUI if any upgrade happened ───
echo ""
if [ "$NODES_INSTALLED" -gt 0 ]; then
  echo "==> [Phase 3] Restarting ComfyUI to pick up the v0.30.0 upgrade..."
  if command -v supervisorctl &> /dev/null && supervisorctl status comfyui &> /dev/null; then
    supervisorctl restart comfyui 2>&1
    # Wait for ComfyUI to be ready (extract port from running process)
    PORT=$(ps -eo pid,comm,args | awk '$2 ~ /python/ && /main\.py/ && !/tcl/ {for(i=1;i<=NF;i++) if($i=="--port"){print $(i+1); exit}}')
    [ -z "$PORT" ] && PORT=8188
    echo "  ⏳ Waiting for ComfyUI on port $PORT..."
    for i in $(seq 1 60); do
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
  echo "==> [Phase 3] No upgrade needed — ComfyUI already current"
  echo "  💡 Click Refresh in the ComfyUI UI to load new models"
fi

echo ""
echo "==> All tasks completed!"
echo "📊 Summary:"
echo "  • ComfyUI version: $($COMFY_PYTHON -c 'from comfyui_version import __version__; print(__version__)' 2>/dev/null || echo 'unknown')"
echo "  • Upgrades/installs this run: $NODES_INSTALLED"
echo "  • Models: 4 downloaded to $BASE_DIR/models (total ~40.5GB)"
echo "👉 Refresh the ComfyUI UI to load the MiniMax H3 workflow (video_minimax_h3_t2v.json)."
echo ""
echo "💡 Tips for the H3 workflow:"
echo "  • ResolutionSelector = 0.4 megapixels → 864x480; for 0.98 (1344x768) you need ~24GB VRAM"
echo "  • Duration (seconds) snaps to H3's 17-frame-per-block grid (max ~15s output)"
echo "  • The workflow's first_frame / last_frame inputs are OPTIONAL (shape=7) — pure T2V works"
echo "  • The workflow's hardcoded Vaporwave prompt in the subgraph is the template; replace it"
echo "    with your own shot-by-shot storyboard text in the parent MiniMaxH3ImageToVideo node"
