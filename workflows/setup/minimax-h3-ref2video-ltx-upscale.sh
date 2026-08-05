#!/usr/bin/env bash
# ---
# name: MiniMax H3 Reference-to-Video + LTX 2.3 Upscale
# workflow: H3_Ref2Video_LTX_Upscale
# aliases: [h3-ref2video-ltx-upscale, minimax-h3-ref2v-ltx, h3-ltx-upscale]
# description: Upgrades ComfyUI to >= v0.30.0, installs ComfyUI-KJNodes and ComfyUI_LayerStyle, then downloads the MiniMax H3 Reference-to-Video model set and the LTX 2.3 AV spatial-upscale model set. The LTX AV and MiniMax H3 nodes are core in ComfyUI v0.30.0+. Requires the workflow's two input images in ComfyUI/input/.
# size: ~82GB
# min_vram: 48GB recommended for the two-stage graph
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

# PathchSageAttentionKJ. The LTX AV nodes are core in ComfyUI v0.30.0+.
install_node "ComfyUI-KJNodes" "https://github.com/kijai/ComfyUI-KJNodes"
# INT8 acceleration nodes for quantized model execution.
install_node "ComfyUI-INT8-Fast" "https://github.com/BobJohnson24/ComfyUI-INT8-Fast"
# LayerUtility: PurgeVRAM V2.
install_node "ComfyUI_LayerStyle" "https://github.com/chflame163/ComfyUI_LayerStyle"

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

# H3 Reference-to-Video model set: all four files are public and ungated.
TOTAL=9
step=0
model_step() { step=$((step + 1)); echo "[$step/$TOTAL] $1"; }

model_step "MiniMax H3 ref2va diffusion model (~20GB)"
hf_download "Comfy-Org/MiniMax-H3" \
  "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors" \
  "$BASE_DIR/models"

model_step "MiniMax H3 Qwen3-VL text encoder (~15GB)"
hf_download "Comfy-Org/MiniMax-H3" \
  "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors" \
  "$BASE_DIR/models"

model_step "MiniMax H3 video VAE (~5GB)"
hf_download "Comfy-Org/MiniMax-H3" \
  "vae/minimax_h3_video_vae_fp16.safetensors" \
  "$BASE_DIR/models"

model_step "MiniMax H3 audio VAE (~0.6GB)"
hf_download "Comfy-Org/MiniMax-H3" \
  "vae/minimax_h3_audio_vae_fp32.safetensors" \
  "$BASE_DIR/models"

# LTX checkpoint is placed under models/checkpoints/LTX2.3 because the workflow
# widget explicitly references LTX2.3/<filename>.
model_step "LTX 2.3 FP8 checkpoint (~27.8GB)"
hf_download "Lightricks/LTX-2.3-fp8" \
  "ltx-2.3-22b-dev-fp8.safetensors" \
  "$BASE_DIR/models/checkpoints/LTX2.3"

model_step "Gemma 3 12B FP4 text encoder (~9GB)"
hf_download "Comfy-Org/ltx-2" \
  "split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" \
  "$BASE_DIR/models"
# The helper preserves the HF prefix; normalize to the ComfyUI text_encoders dir.
if [ -f "$BASE_DIR/models/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" ]; then
  mkdir -p "$BASE_DIR/models/text_encoders"
  mv "$BASE_DIR/models/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" \
    "$BASE_DIR/models/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors"
  rmdir "$BASE_DIR/models/split_files/text_encoders" "$BASE_DIR/models/split_files" 2>/dev/null || true
fi

model_step "LTX 2.3 spatial upscaler (~950MB)"
hf_download "Lightricks/LTX-2.3" \
  "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" \
  "$BASE_DIR/models/latent_upscale_models"

model_step "LTX 2.3 dynamic distilled LoRA (~2.6GB)"
hf_download "Comfy-Org/ltx-2.3" \
  "split_files/loras/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors" \
  "$BASE_DIR/models"
if [ -f "$BASE_DIR/models/split_files/loras/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors" ]; then
  mkdir -p "$BASE_DIR/models/loras/LTX2"
  mv "$BASE_DIR/models/split_files/loras/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors" \
    "$BASE_DIR/models/loras/LTX2/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors"
  rmdir "$BASE_DIR/models/split_files/loras" "$BASE_DIR/models/split_files" 2>/dev/null || true
fi

model_step "LTX 2.3 Crisp Enhance LoRA (~673MB)"
hf_download "vrgamedevgirl84/LTX_2.3_Crisp_Enhance_Style_LoRa" \
  "LTX2.3_Crisp_Enhance.safetensors" \
  "$BASE_DIR/models/loras/LTX2"

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
echo "🎉 MiniMax H3 Ref2Video + LTX 2.3 Upscale setup complete"
echo "  Models installed under: $BASE_DIR/models"
echo "  Required input images: $BASE_DIR/input/001-The_Eviction_Notice.png and $BASE_DIR/input/02.webp"
echo "  Workflow requires ComfyUI >= v0.30.0 and the three custom-node packs above."
