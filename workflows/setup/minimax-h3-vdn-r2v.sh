#!/usr/bin/env bash
# ---
# name: MiniMax H3 Reference-to-Video + VDN-H3
# workflow: Minimax-H3VDN-R2V_only-VDN
# aliases: [minimax-h3-vdn-r2v, h3-vdn-r2v, minimax-h3-ref2v-vdn]
# description: Upgrades ComfyUI to >= v0.30.0, installs ComfyUI-KJNodes, ComfyUI-VDN-H3, ComfyUI-VideoHelperSuite and rgthree-comfy, then downloads the MiniMax H3 Reference-to-Video model set (int8_convrot) plus the VDN-H3 stage-dmd-step-250 checkpoint. The H3 + VDN-H3 nodes are core in ComfyUI v0.30.0+. VDN weights are the MiniMax H3 Community License — read it before use. Requires the workflow's two reference images at API upload time.
# size: ~69GB
# min_vram: 32GB (VDN runs an extra linear-branch on every transformer block; the README benchmark is 1280x736 on an RTX 5090)
# nodes: [ComfyUI-KJNodes, ComfyUI-VDN-H3, ComfyUI-VideoHelperSuite, rgthree-comfy]
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
MODELS_DIR="$COMFYUI_DIR/models"
CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"
export COMFYUI_DIR BASE_DIR MODELS_DIR

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

# Preserve original launch args for a manual fallback restart.
COMFYUI_ARGS="$(ps aux | grep '[p]ython.*main.py' | head -1 | sed 's/.*main\.py//')"
[ -n "$COMFYUI_ARGS" ] || COMFYUI_ARGS="--listen 0.0.0.0 --port 8188 --enable-cors-header"
COMFYUI_PORT="$(printf '%s\n' "$COMFYUI_ARGS" | grep -oE -- '--port [0-9]+' | awk '{print $2}' | head -1 || true)"
[ -n "$COMFYUI_PORT" ] || COMFYUI_PORT=8188

NODES_INSTALLED=0

# ─── Phase 0: ComfyUI version floor (>= v0.30.0 for H3 + VDN-H3 core nodes) ──
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

# GetNode/SetNode, ImageResizeKJv2, ModelPatchTorchSettings, MiniMaxChunkFeedForward
install_node "ComfyUI-KJNodes" "https://github.com/kijai/ComfyUI-KJNodes"
# ApplyVDNH3Advanced (Video Delta Net for MiniMax-H3). No new pip deps.
install_node "ComfyUI-VDN-H3" "https://github.com/Saganaki22/ComfyUI-VDN-H3"
# VHS_VideoCombine (mp4 output) + VHS_LoadImagePath (reference images)
install_node "ComfyUI-VideoHelperSuite" "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite"
# Label (rgthree) — display only
install_node "rgthree-comfy" "https://github.com/rgthree/rgthree-comfy"

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
mkdir -p "$MODELS_DIR"

# Helper: download repo file (with repo-relative prefix) into MODELS_DIR, then
# move it under <subdir>/minimax-h3/ (the workflow's secondary-dir layout).
fetch_and_place() {
  local repo="$1" prefix="$2" subdir="$3"
  local fname; fname="$(basename "$prefix")"
  echo "  Downloading $prefix ..."
  hf_download "$repo" "$prefix" "$MODELS_DIR"
  local src="$MODELS_DIR/$prefix"
  local dst="$MODELS_DIR/$subdir/minimax-h3"
  if [ -f "$src" ]; then
    mkdir -p "$dst"
    mv "$src" "$dst/"
    # clean empty parents up to MODELS_DIR
    local d; d="$(dirname "$prefix")"
    while [ "$d" != "." ] && [ "$d" != "/" ]; do
      rmdir "$MODELS_DIR/$d" 2>/dev/null || true
      d="$(dirname "$d")"
    done
  fi
}

TOTAL=5
step=0
model_step() { step=$((step + 1)); echo "[$step/$TOTAL] $1"; }

model_step "MiniMax H3 ref2va diffusion model (int8_convrot, ~32.5GB)"
fetch_and_place "Comfy-Org/MiniMax-H3" \
  "diffusion_models/minimax_h3_ref2va_int8_convrot.safetensors" \
  "diffusion_models"

model_step "MiniMax H3 Qwen3-VL text encoder (int8_convrot, ~25.9GB)"
# Upstream file is qwen3vl_32b_minimax_h3_int8_convrot.safetensors; the workflow
# widget references the .comfy suffix. Rename on install to match the loader.
fetch_and_place "Comfy-Org/MiniMax-H3" \
  "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" \
  "text_encoders"

model_step "MiniMax H3 video VAE (~5GB)"
fetch_and_place "Comfy-Org/MiniMax-H3" \
  "vae/minimax_h3_video_vae_fp16.safetensors" \
  "vae"

model_step "MiniMax H3 audio VAE (~0.6GB)"
fetch_and_place "Comfy-Org/MiniMax-H3" \
  "vae/minimax_h3_audio_vae_fp32.safetensors" \
  "vae"

model_step "VDN-H3 stage-dmd-step-250 checkpoint (~5.2GB)"
# Preserve the reply's release layout (model_spec.json, linear_branch/, adapters/)
# under models/vdn/ — the ApplyVDNH3Advanced node re-keys these in memory.
vdn_base="$MODELS_DIR/vdn"
for vf in \
  "stage-dmd-step-250/model_spec.json" \
  "stage-dmd-step-250/metadata.json" \
  "stage-dmd-step-250/linear_branch/config.json" \
  "stage-dmd-step-250/linear_branch/model.safetensors" \
  "stage-dmd-step-250/adapters/default/adapter_config.json" \
  "stage-dmd-step-250/adapters/default/adapter_model.safetensors" \
  "stage-dmd-step-250/adapters/turbo/adapter_config.json" \
  "stage-dmd-step-250/adapters/turbo/adapter_model.safetensors"; do
  hf_download "OpenVDN/vdn-minimax-h3" "$vf" "$vdn_base"
done

# ─── Apply workflow-required filename fixes ───────────────────────────────────
echo ""
echo "==> [Filename fix] Aligning CLIP filename to workflow expectation..."
clip_src="$MODELS_DIR/text_encoders/minimax-h3/qwen3vl_32b_minimax_h3_int8_convrot.safetensors"
clip_dst="$MODELS_DIR/text_encoders/minimax-h3/qwen3vl_32b_minimax_h3_int8_convrot.comfy.safetensors"
if [ -f "$clip_src" ] && [ ! -f "$clip_dst" ]; then
  cp "$clip_src" "$clip_dst"
  echo "  ✅ Created $clip_dst (copy of upstream int8_convrot)"
fi

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
echo "🎉 MiniMax H3 Ref2Video + VDN-H3 setup complete"
echo "  Models under: $MODELS_DIR"
echo "  VDN stage under: $MODELS_DIR/vdn/stage-dmd-step-250"
echo "  ComfyUI requires >= v0.30.0 (Phase 0) and the 4 node packs above."
echo "  ⚠️  VDN weights are the MiniMax H3 Community License — review before commercial use."
echo "  Reminder: supply the workflow's two reference images (VHS_LoadImagePath) via API upload."
