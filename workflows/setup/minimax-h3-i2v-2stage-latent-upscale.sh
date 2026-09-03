#!/bin/bash
# ---
# name: MiniMax H3 I2V 2-Stage Latent Upscale
# workflow: minimax-h3-i2v-2stage-latent-upscale
# aliases: [minimax-h3-i2v, h3-i2v-2stage, h3-latent-upscale]
# description: MiniMax H3 image-to-video with 2-stage sampling, sigma split, latent upscaling
# size: ~65GB + taeh3
# min_vram: 24GB
# nodes: [comfyui-kjnodes, comfyui-minimax-h3-audio-T8, Comfyui_Minimax_h3_latent_Upscaler, ComfyUI-VideoHelperSuite]
# ---

set -e

# ── Platform Detection ──
echo "==> Detecting platform..."
if [ -d "/workspace/runpod" ]; then
    PLATFORM="runpod"
    COMFYUI_DIR="/workspace/ComfyUI"
    echo "  ✅ RunPod detected"
elif [ -d "/workspace/ComfyUI" ]; then
    PLATFORM="vast"
    COMFYUI_DIR="/workspace/ComfyUI"
    echo "  ✅ Vast.ai detected"
else
    echo "❌ Unknown platform - ComfyUI directory not found"
    exit 1
fi

BASE_DIR="$COMFYUI_DIR/models"
CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"

# ── Phase 0: Check ComfyUI version (H3 needs v0.30.0+) ──
echo "==> Phase 0: Checking ComfyUI version..."
CURRENT_VERSION=$(python3 -c "import importlib.metadata; print(importlib.metadata.version('comfy'))" 2>/dev/null || echo "unknown")
echo "  Current ComfyUI version: $CURRENT_VERSION"

if [[ "$CURRENT_VERSION" == "unknown" ]] || [[ "$(printf '%s\n' "0.30.0" "$CURRENT_VERSION" | sort -V | head -n1)" != "0.30.0" ]]; then
    echo "  ⚠️  ComfyUI < v0.30.0 detected (or unknown) — upgrading to master..."
    cd "$COMFYUI_DIR"
    git fetch origin master --depth=1 2>/dev/null || git fetch origin main --depth=1 2>/dev/null
    git stash 2>/dev/null || true
    git checkout origin/master -- . 2>/dev/null || git checkout origin/main -- . 2>/dev/null
    echo "  ✅ ComfyUI upgraded to master"
else
    echo "  ✅ ComfyUI $CURRENT_VERSION >= v0.30.0 — no upgrade needed"
fi

# ── Detect ComfyUI Python ──
echo "==> Detecting ComfyUI Python..."
if [ -f "/venv/main/bin/python" ]; then
    COMFY_PYTHON="/venv/main/bin/python"
    COMFY_PIP="/venv/main/bin/pip"
    echo "  ✅ Found /venv/main/bin/python"
elif [ -f "$COMFYUI_DIR/venv/bin/activate" ]; then
    source "$COMFYUI_DIR/venv/bin/activate"
    COMFY_PYTHON="python"
    COMFY_PIP="pip"
    echo "  ✅ Found $COMFYUI_DIR/venv"
elif [ -f "$COMFYUI_DIR/.venv-cu128/bin/activate" ]; then
    source "$COMFYUI_DIR/.venv-cu128/bin/activate"
    COMFY_PYTHON="python"
    COMFY_PIP="pip"
    echo "  ✅ Found $COMFYUI_DIR/.venv-cu128"
else
    COMFY_PYTHON="python3"
    COMFY_PIP="pip3"
    echo "  ⚠️  Using system Python"
fi

# ── Phase 1: Install Custom Nodes ──
echo "==> Phase 1: Installing custom node packs..."
cd "$COMFYUI_DIR"

if command -v comfy >/dev/null 2>&1; then
    echo "  Using comfy-cli..."
    comfy node install https://github.com/kijai/ComfyUI-KJNodes 2>/dev/null || true
    comfy node install https://github.com/T8mars/comfyui-minimax-h3-audio-T8 2>/dev/null || true
    comfy node install https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler 2>/dev/null || true
    comfy node install https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite 2>/dev/null || true
    echo "  ✅ comfy-cli done"
else
    echo "  comfy-cli not found, cloning manually..."
    cd "$CUSTOM_NODES_DIR"
    [ -d ComfyUI-KJNodes ] || git clone --depth=1 https://github.com/kijai/ComfyUI-KJNodes || true
    [ -d comfyui-minimax-h3-audio-T8 ] || git clone --depth=1 https://github.com/T8mars/comfyui-minimax-h3-audio-T8 || true
    [ -d Comfyui_Minimax_h3_latent_Upscaler ] || git clone --depth=1 https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler || true
    [ -d ComfyUI-VideoHelperSuite ] || git clone --depth=1 https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite || true
    cd "$COMFYUI_DIR"
fi

# ── Install node dependencies ──
echo "==> Installing node dependencies..."
for repo in ComfyUI-KJNodes comfyui-minimax-h3-audio-T8 Comfyui_Minimax_h3_latent_Upscaler ComfyUI-VideoHelperSuite; do
    REQ="$CUSTOM_NODES_DIR/$repo/requirements.txt"
    if [ -f "$REQ" ]; then
        echo "  Installing $repo deps..."
        $COMFY_PIP install -q -r "$REQ" 2>&1 | tail -5 || true
    fi
done

# ── Create model directories ──
echo "==> Creating model directories..."
mkdir -p "$BASE_DIR"/{vae,vae_approx,text_encoders,diffusion_models,loras,latent_upscale_models}

# ── Load shared HF download helper ──
if [ ! -f "$BASE_DIR/_hf_download.sh" ]; then
    echo "  Fetching _hf_download.sh from GitHub..."
    curl -sSL -o "$BASE_DIR/_hf_download.sh" \
        "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/workflows/setup/_hf_download.sh" || true
fi
source "$BASE_DIR/_hf_download.sh"

# ── Downloads ──
echo "==> Starting model downloads..."

# ── VAE (video) ──
echo "[1/8] minimax_h3_video_vae_fp16.safetensors (VAE - video)..."
hf_download "Comfy-Org/MiniMax-H3" "vae/minimax_h3_video_vae_fp16.safetensors" "$BASE_DIR"

# ── VAE (audio) ──
echo "[2/8] minimax_h3_audio_vae_fp32.safetensors (VAE - audio)..."
hf_download "Comfy-Org/MiniMax-H3" "vae/minimax_h3_audio_vae_fp32.safetensors" "$BASE_DIR"

# ── Text Encoder ──
echo "[3/8] qwen3vl_32b_minimax_h3_int8_convrot.safetensors (Text Encoder)..."
hf_download "Comfy-Org/MiniMax-H3" "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" "$BASE_DIR"

# ── Diffusion Model ──
echo "[4/8] minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors (Diffusion Model)..."
hf_download "smhfacct/Minimax-H3-fl2va-ref2va-hybrid-models" "minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors" "$BASE_DIR/diffusion_models"

# ── LoRA: fl2v lightx2v turbo 4-step ──
echo "[5/8] minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors (LoRA - fl2v turbo 4-step)..."
hf_download "Kijai/MiniMax-H3_comfy" "loras/minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors" "$BASE_DIR"

# ── LoRA: ref2v lightx2v turbo 4-step resized avg rank 20 ──
echo "[6/8] minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors (LoRA - ref2v turbo 4-step rank 20)..."
hf_download "Kijai/MiniMax-H3_comfy" "loras/minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors" "$BASE_DIR"

# ── Latent Upscale Model ──
echo "[7/8] minimax_h3_latent_upscaler_3d_fp16.safetensors (Latent Upscaler 3D)..."
hf_download "LBH-123-AI/Minimax_h3_latent_Upscaler" "minimax_h3_latent_upscaler_3d_fp16.safetensors" "$BASE_DIR/latent_upscale_models"

# ── Tiny VAE for live preview ──
echo "[8/8] taeh3.safetensors (Tiny VAE - live preview)..."
hf_download "Kijai/MiniMax-H3-TAE" "vae_approx/taeh3.safetensors" "$BASE_DIR/vae_approx"

echo "==> All downloads completed!"

# ── Restart ComfyUI ──
echo "==> Restarting ComfyUI..."
supervisorctl restart comfyui || true

echo "✅ Setup complete!"
echo "👉 Open ComfyUI and load the workflow"
echo "👉 Upload an image in the LoadImage node"
