#!/bin/bash
# ---
# name: MiniMax H3 I2V Fast Cinematic Action 2-Stage Latent Upscale
# workflow: MiniMaxH3I2VFastCinematicAction2-StageSigma-SplitlatentUpscale.json
# aliases: [minimax-h3-i2v-2stage, minimax-h3-latent-upscale, h3-i2v-action, h3-2stage-lupscale]
# description: MiniMax H3 image-to-video with 2-stage sampling, sigma split, and 3D latent upscaling. Uses dual-clock T8 sampler, lightx2v 4-step turbo LoRA, and hybrid fl2va+ref2va int8 UNET.
# size: ~65GB
# min_vram: 24GB
# nodes: [comfyui-kjnodes, comfyui-minimax-h3-audio-T8, Comfyui_Minimax_h3_latent_Upscaler]
# ---
set -e

# ─── Phase 0: ComfyUI master upgrade (H3 requires v0.30.0+) ───
echo "==> Phase 0: Checking ComfyUI version..."
COMFYUI_DIR=""
if [ -d "/workspace/runpod-slim/ComfyUI" ]; then
  COMFYUI_DIR="/workspace/runpod-slim/ComfyUI"
  echo "  Platform: RunPod"
elif [ -d "/workspace/ComfyUI" ]; then
  COMFYUI_DIR="/workspace/ComfyUI"
  echo "  Platform: Vast.ai"
else
  echo "  ⚠️  No ComfyUI dir found, defaulting to /workspace/ComfyUI"
  COMFYUI_DIR="/workspace/ComfyUI"
fi
BASE_DIR="$COMFYUI_DIR/models"
CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"

# Version check
CURRENT_VERSION="unknown"
if [ -f "$COMFYUI_DIR/comfy/cli_args.py" ]; then
  CURRENT_VERSION=$(python3 -c "
import importlib.metadata
try: print('v' + importlib.metadata.version('comfy'))
except: print('unknown')
" 2>/dev/null || echo "unknown")
fi
echo "  Current ComfyUI version: $CURRENT_VERSION"

ver_ge() {
  [ "$(printf '%s\n' "$1" "$2" | sort -V | head -n1)" = "$2" ]
}

NEEDS_UPGRADE=false
if [ "$CURRENT_VERSION" = "unknown" ] || ! ver_ge "$CURRENT_VERSION" "v0.30.0"; then
  NEEDS_UPGRADE=true
fi

if [ "$NEEDS_UPGRADE" = true ]; then
  echo "  ComfyUI $CURRENT_VERSION < v0.30.0 — upgrading to master..."
  cd "$COMFYUI_DIR"
  git fetch origin master --depth=1 2>/dev/null || git fetch origin main --depth=1 2>/dev/null || true
  git stash 2>/dev/null || true
  git checkout origin/master -- . 2>/dev/null || git checkout origin/main -- . 2>/dev/null || true
  echo "  ✅ ComfyUI upgraded to master"
else
  echo "  ✅ ComfyUI $CURRENT_VERSION >= v0.30.0 — no upgrade needed"
fi

# ─── ComfyUI Python detection ───
echo "==> Detecting ComfyUI Python..."
COMFY_PYTHON=""
COMFY_PIP=""
if [ -f /venv/main/bin/python3 ]; then
    COMFY_PYTHON="/venv/main/bin/python3"
    COMFY_PIP="/venv/main/bin/pip"
elif [ -f "$COMFYUI_DIR/venv/bin/activate" ]; then
    source "$COMFYUI_DIR/venv/bin/activate"
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$(which pip)"
elif [ -f "$COMFYUI_DIR/.venv-cu128/bin/activate" ]; then
    source "$COMFYUI_DIR/.venv-cu128/bin/activate"
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$(which pip)"
else
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$(which pip)"
fi
echo "  Using ComfyUI Python: $COMFY_PYTHON"

# ─── Phase 1: Custom node install ───
echo "==> Phase 1: Installing custom node packs..."
cd "$COMFYUI_DIR"

if command -v comfy &> /dev/null; then
    echo "  Using comfy-cli..."
    comfy node install https://github.com/kijai/ComfyUI-KJNodes 2>/dev/null || true
    comfy node install https://github.com/T8mars/comfyui-minimax-h3-audio-T8 2>/dev/null || true
    comfy node install https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler 2>/dev/null || true
else
    echo "  comfy-cli not found, cloning manually..."
    mkdir -p "$CUSTOM_NODES_DIR"
    cd "$CUSTOM_NODES_DIR"
    [ -d ComfyUI-KJNodes ] || git clone --depth=1 https://github.com/kijai/ComfyUI-KJNodes || true
    [ -d comfyui-minimax-h3-audio-T8 ] || git clone --depth=1 https://github.com/T8mars/comfyui-minimax-h3-audio-T8 || true
    [ -d Comfyui_Minimax_h3_latent_Upscaler ] || git clone --depth=1 https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler || true
    cd "$COMFYUI_DIR"
fi

# ─── Pip deps for each pack ───
echo "==> Installing node dependencies..."
for repo in ComfyUI-KJNodes comfyui-minimax-h3-audio-T8 Comfyui_Minimax_h3_latent_Upscaler; do
    REQ="$CUSTOM_NODES_DIR/$repo/requirements.txt"
    if [ -f "$REQ" ]; then
        echo "  Installing $repo deps..."
        $COMFY_PIP install -q -r "$REQ" 2>&1 | tail -3 || true
    fi
done

# ─── Model directory creation ───
echo "==> Creating model directories..."
mkdir -p "$BASE_DIR"/{vae,text_encoders,diffusion_models,loras,latent_upscale_models}

# ─── Load shared HF download helper ───
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_HF_HELPER=""
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh" "/tmp/_hf_download.sh"; do
  [ -f "$f" ] && _HF_HELPER="$f" && break
done
if [ -z "$_HF_HELPER" ]; then
  echo "  Fetching _hf_download.sh from GitHub..."
  GITHUB_BASE="https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/workflows/setup"
  _HF_HELPER="/tmp/_hf_download.sh"
  curl -sSL --fail "$GITHUB_BASE/_hf_download.sh" -o "$_HF_HELPER" \
    || { echo "❌ FATAL: could not download _hf_download.sh"; exit 1; }
  chmod +x "$_HF_HELPER"
fi
source "$_HF_HELPER"
unset _HF_HELPER

# ─── Downloads ───
echo "==> Starting model downloads..."

# ── VAE (video) ──
echo "[1/7] minimax_h3_video_vae_fp16.safetensors (VAE - video)..."
hf_download "Comfy-Org/MiniMax-H3" "vae/minimax_h3_video_vae_fp16.safetensors" "$BASE_DIR"

# ── VAE (audio) ──
echo "[2/7] minimax_h3_audio_vae_fp32.safetensors (VAE - audio)..."
hf_download "Comfy-Org/MiniMax-H3" "vae/minimax_h3_audio_vae_fp32.safetensors" "$BASE_DIR"

# ── Text Encoder (CLIP) ──
echo "[3/7] qwen3vl_32b_minimax_h3_int8_convrot.safetensors (Text Encoder)..."
hf_download "Comfy-Org/MiniMax-H3" "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" "$BASE_DIR"

# ── Diffusion Model (UNET) ──
echo "[4/7] minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors (Diffusion Model)..."
hf_download "smhfacct/Minimax-H3-fl2va-ref2va-hybrid-models" "minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors" "$BASE_DIR/diffusion_models"

# ── LoRA: fl2v lightx2v turbo 4-step (workflow) ──
echo "[5/7] minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors (LoRA - fl2v turbo 4-step)..."
hf_download "Kijai/MiniMax-H3_comfy" "loras/minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors" "$BASE_DIR"

# ── LoRA: ref2v lightx2v turbo 4-step resized avg rank 20 ──
echo "[6/7] minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors (LoRA - ref2v turbo 4-step rank 20)..."
hf_download "Kijai/MiniMax-H3_comfy" "loras/minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors" "$BASE_DIR"

# ── Latent Upscale Model ──
echo "[7/7] minimax_h3_latent_upscaler_3d_fp16.safetensors (Latent Upscaler 3D)..."
hf_download "LBH-123-AI/Minimax_h3_latent_Upscaler" "minimax_h3_latent_upscaler_3d_fp16.safetensors" "$BASE_DIR/latent_upscale_models"

echo "==> All downloads completed!"

# ─── Restart ComfyUI ───
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
