#!/usr/bin/env bash
# ---
# name: Minimax H3 R2V - Final
# workflow: Minimax H3 R2V - Final
# aliases: [minimax-h3-r2v-final, minimax h3 r2v]
# description: Prepares ComfyUI for the Minimax H3 reference-to-video workflow, installs required nodes, and downloads the four MiniMax H3 model files. No LTX models are downloaded.
# size: ~41GB
# min_vram: 24GB minimum; 48GB recommended
# ---
set -euo pipefail

# ─── Platform-aware paths ────────────────────────────────────────────────────
if [ -d "/workspace/runpod-slim/ComfyUI" ]; then
  COMFYUI_DIR="/workspace/runpod-slim/ComfyUI"
  echo "  Platform: RunPod (base: $COMFYUI_DIR)"
elif [ -d "/workspace/ComfyUI" ]; then
  COMFYUI_DIR="/workspace/ComfyUI"
  echo "  Platform: Vast.ai (base: $COMFYUI_DIR)"
else
  COMFYUI_DIR="/workspace/ComfyUI"
  echo "  ⚠️  ComfyUI directory not found; defaulting to $COMFYUI_DIR"
fi
BASE_DIR="$COMFYUI_DIR"
CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"
export COMFYUI_DIR BASE_DIR

# ─── Detect the Python used by the running ComfyUI ────────────────────────────
detect_comfyui_python() {
  local pid
  pid=$(ps -eo pid,comm,args | awk '$2 ~ /python/ && /main\.py/ && !/tcl/ {print $1; exit}')
  if [ -n "$pid" ] && [ -f "/proc/$pid/exe" ]; then
    readlink -f "/proc/$pid/exe" 2>/dev/null
    return
  fi
  for p in \
    /venv/main/bin/python3 \
    "$COMFYUI_DIR/.venv-cu128/bin/python3" \
    "$COMFYUI_DIR/venv/bin/python3"; do
    [ -x "$p" ] && { echo "$p"; return; }
  done
  command -v python3
}
COMFY_PYTHON="$(detect_comfyui_python)"
COMFY_PIP=("$COMFY_PYTHON" -m pip)
echo "  Using ComfyUI Python: $COMFY_PYTHON"

# Preserve the original launch arguments for a manual fallback restart.
COMFYUI_ARGS="$(ps aux | grep '[p]ython.*main.py' | head -1 | sed 's/.*main\.py//')"
[ -n "$COMFYUI_ARGS" ] || COMFYUI_ARGS="--listen 0.0.0.0 --port 8188 --enable-cors-header"
COMFYUI_PORT="$(printf '%s\n' "$COMFYUI_ARGS" | grep -oE -- '--port [0-9]+' | awk '{print $2}' | head -1 || true)"
[ -n "$COMFYUI_PORT" ] || COMFYUI_PORT=8188

NODES_INSTALLED=0

# ─── Phase 0: ComfyUI version floor ───────────────────────────────────────────
echo ""
echo "==> [Phase 0] Checking ComfyUI version (>= v0.30.0 required)..."
cd "$COMFYUI_DIR"
CURRENT_VERSION="$($COMFY_PYTHON -c 'from comfyui_version import __version__; print(__version__)' 2>/dev/null || echo unknown)"
echo "  Current version: $CURRENT_VERSION"
git fetch origin --quiet 2>/dev/null || true
LATEST_TAG="$(git describe --tags --abbrev=0 origin/master 2>/dev/null || git rev-parse --short origin/master 2>/dev/null || echo unknown)"
echo "  Latest available: $LATEST_TAG"

ver_ge() {
  [ "$(printf '%s\n' "$1" "$2" | sort -V | tail -1)" = "$1" ]
}

if [ "$CURRENT_VERSION" = unknown ] || ! ver_ge "$CURRENT_VERSION" "v0.30.0"; then
  if [ "$LATEST_TAG" != unknown ]; then
    echo "  🔄 Upgrading ComfyUI to $LATEST_TAG..."
    # Do NOT use --include-untracked: it can delete the untracked ComfyUI venv.
    git stash --quiet 2>/dev/null || true
    if git checkout "$LATEST_TAG" --quiet 2>/dev/null; then
      [ -f requirements.txt ] && "${COMFY_PIP[@]}" install -r requirements.txt -q || true
      NODES_INSTALLED=$((NODES_INSTALLED + 1))
      echo "  ✅ ComfyUI upgraded"
    else
      echo "  ⚠️  Could not check out $LATEST_TAG; continuing"
    fi
  else
    echo "  ⚠️  Could not determine a ComfyUI tag; continuing"
  fi
else
  echo "  ✅ ComfyUI already satisfies the version floor"
fi

# ─── Phase 1: Required custom nodes ──────────────────────────────────────────
echo ""
echo "==> [Phase 1] Installing required custom node packs..."
mkdir -p "$CUSTOM_NODES_DIR"

install_node() {
  local dir="$1"
  local url="$2"
  if [ -d "$CUSTOM_NODES_DIR/$dir/.git" ] || [ -d "$CUSTOM_NODES_DIR/$dir" ]; then
    echo "  ✅ $dir already installed"
  else
    echo "  📥 Installing $dir..."
    git clone --depth 1 "$url" "$CUSTOM_NODES_DIR/$dir"
    NODES_INSTALLED=$((NODES_INSTALLED + 1))
  fi
  if [ -f "$CUSTOM_NODES_DIR/$dir/requirements.txt" ]; then
    "${COMFY_PIP[@]}" install -r "$CUSTOM_NODES_DIR/$dir/requirements.txt" -q || true
  fi
}

# MiniMax H3 is core in ComfyUI >= v0.30.0. VHS_LoadVideo is used by this workflow.
install_node "ComfyUI-KJNodes" "https://github.com/kijai/ComfyUI-KJNodes"
install_node "ComfyUI-VideoHelperSuite" "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite"

# ─── Load shared Hugging Face helper ──────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_HF_HELPER=""
for f in "$SCRIPT_DIR/_hf_download.sh" /workspace/_hf_download.sh /tmp/_hf_download.sh; do
  if [ -f "$f" ]; then _HF_HELPER="$f"; break; fi
done
if [ -z "$_HF_HELPER" ]; then
  echo "  Fetching _hf_download.sh..."
  _HF_HELPER=/tmp/_hf_download.sh
  curl -fsSL "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/workflows/setup/_hf_download.sh" -o "$_HF_HELPER"
  chmod +x "$_HF_HELPER"
fi
source "$_HF_HELPER"
unset _HF_HELPER

# ─── Phase 2: Models ──────────────────────────────────────────────────────────
echo ""
echo "==> [Phase 2] Downloading models..."
mkdir -p "$BASE_DIR/models"

# MiniMax H3 Reference-to-Video model set: all four files are public and ungated.
TOTAL=4
step=0
model_step() { step=$((step + 1)); echo "[$step/$TOTAL] $1"; }

model_step "MiniMax H3 ref2va diffusion model (~20GB)"
hf_download "Comfy-Org/MiniMax-H3" \
  "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors" \
  "$BASE_DIR/models"

model_step "MiniMax H3 Qwen3-VL text encoder (~15GB)"
hf_download "Comfy-Org/MiniMax-H3" \
  "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" \
  "$BASE_DIR/models"

model_step "MiniMax H3 video VAE (~5GB)"
hf_download "Comfy-Org/MiniMax-H3" \
  "vae/minimax_h3_video_vae_fp16.safetensors" \
  "$BASE_DIR/models"

model_step "MiniMax H3 audio VAE (~0.6GB)"
hf_download "Comfy-Org/MiniMax-H3" \
  "vae/minimax_h3_audio_vae_fp32.safetensors" \
  "$BASE_DIR/models"

# ─── Phase 3: Restart / liveness recovery ────────────────────────────────────
echo ""
comfyui_alive() {
  curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
    "http://127.0.0.1:$COMFYUI_PORT/system_stats" 2>/dev/null | grep -q '^200$'
}

if [ "$NODES_INSTALLED" -gt 0 ] || ! comfyui_alive; then
  echo "==> [Phase 3] Restarting ComfyUI (changes=$NODES_INSTALLED, alive=$(comfyui_alive && echo yes || echo no))..."
  if command -v supervisorctl >/dev/null 2>&1 && supervisorctl status comfyui >/dev/null 2>&1; then
    supervisorctl restart comfyui
  else
    pid=$(ps -eo pid,comm,args | awk '$2 ~ /python/ && /main\.py/ && !/tcl/ {print $1; exit}')
    [ -n "${pid:-}" ] && kill "$pid" 2>/dev/null || true
    sleep 3
    nohup "$COMFY_PYTHON" "$COMFYUI_DIR/main.py" $COMFYUI_ARGS \
      >"$COMFYUI_DIR/comfyui.log" 2>&1 &
  fi
  echo "  ⏳ Waiting for ComfyUI on port $COMFYUI_PORT..."
  ready=false
  for _ in $(seq 1 60); do
    if comfyui_alive; then ready=true; echo "  ✅ ComfyUI ready"; break; fi
    sleep 2
  done
  [ "$ready" = true ] || echo "  ⚠️  ComfyUI did not answer within 120 seconds"
else
  echo "==> [Phase 3] ComfyUI is already running; model refresh is sufficient"
fi

echo ""
echo "🎉 Minimax H3 R2V - Final setup complete"
echo "  Models installed under: $BASE_DIR/models"
echo "  Required input images: $BASE_DIR/input/001-The_Eviction_Notice.png and $BASE_DIR/input/02.webp"
echo "  Workflow requires ComfyUI >= v0.30.0, ComfyUI-KJNodes, and ComfyUI-VideoHelperSuite."
