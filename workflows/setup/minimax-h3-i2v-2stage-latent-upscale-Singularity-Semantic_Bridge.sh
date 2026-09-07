#!/bin/bash
# ---
# name: MiniMax H3 I2V 2-Stage Latent Upscale (Singularity + Semantic Bridge)
# workflow: minimax-h3-i2v-2stage-latent-upscale-Singularity-Semantic_Bridge
# aliases: [minimax-h3-i2v, h3-i2v-2stage, h3-latent-upscale, minimax-h3-i2v-singularity, minimax-h3-i2v-singularity-semantic-bridge]
# description: MiniMax H3 image-to-video with 2-stage sampling, sigma split, latent upscaling; Singularity ref2va pruned base + Semantic Bridge (FL2VA/text-conditioning adapter)
# size: ~69GB + taeh3
# min_vram: 24GB
# nodes: [comfyui-kjnodes, comfyui-minimax-h3-audio-T8, Comfyui_Minimax_h3_latent_Upscaler, ComfyUI-VideoHelperSuite, MiniMax_H3_Semantic_Bridge]
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

# ── Phase 1b: MiniMax_H3_Semantic_Bridge custom node (zip node, no pip deps) ──
echo "==> Installing MiniMax_H3_Semantic_Bridge custom node..."
mkdir -p "$CUSTOM_NODES_DIR"
cd "$CUSTOM_NODES_DIR"
if [ -d MiniMax_H3_Semantic_Bridge ]; then
    echo "  ✅ MiniMax_H3_Semantic_Bridge already installed"
else
    echo "  📥 Downloading + extracting MiniMax_H3_Semantic_Bridge (zip node)..."
    curl -fsSL --max-time 120 -o /tmp/semantic_bridge.zip         "https://huggingface.co/speach1sdef178/MiniMax-H3-Semantic-Bridge/resolve/main/MiniMax_H3_Semantic_Bridge_v1.0.zip"         || echo "  ⚠️  Semantic Bridge zip download failed (non-fatal)"
    if [ -s /tmp/semantic_bridge.zip ]; then
        "$COMFY_PYTHON" -c "import zipfile; zipfile.ZipFile('/tmp/semantic_bridge.zip').extractall('$CUSTOM_NODES_DIR')" || true
        rm -f /tmp/semantic_bridge.zip
        [ -d MiniMax_H3_Semantic_Bridge ] && echo "  ✅ Semantic Bridge node installed"
    fi
fi
cd "$COMFYUI_DIR"

# ── Create model directories ──
echo "==> Creating model directories..."
mkdir -p "$BASE_DIR"/{vae,vae_approx,text_encoders,diffusion_models,loras,latent_upscale_models,semantic_bridge}

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
echo "[1/12] minimax_h3_video_vae_fp16.safetensors (VAE - video)..."
hf_download "Comfy-Org/MiniMax-H3" "vae/minimax_h3_video_vae_fp16.safetensors" "$BASE_DIR"

# ── VAE (audio) ──
echo "[2/12] minimax_h3_audio_vae_fp32.safetensors (VAE - audio)..."
hf_download "Comfy-Org/MiniMax-H3" "vae/minimax_h3_audio_vae_fp32.safetensors" "$BASE_DIR"

# ── Text Encoder ──
echo "[3/12] qwen3vl_32b_minimax_h3_int8_convrot.safetensors (Text Encoder)..."
hf_download "Comfy-Org/MiniMax-H3" "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" "$BASE_DIR"

# ── Diffusion Model ──
echo "[4/12] Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors (Diffusion Model)..."
hf_download "WarmBloodAban/Minimax-h3_Singularity" "Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors" "$BASE_DIR/diffusion_models"

# ── LoRA: fl2v turbo 4-step v1.2 768p (comfyui) ──
echo "[5/12] minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors (LoRA - fl2v turbo 4-step v1.2 768p)..."
hf_download "lightx2v/Minimax-h3-Turbo" "minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors" "$BASE_DIR/loras"

# ── LoRA: ref2v turbo 8-step 768p (comfyui) ──
echo "[6/12] minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors (LoRA - ref2v turbo 8-step 768p)..."
hf_download "lightx2v/Minimax-h3-Turbo" "minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors" "$BASE_DIR/loras"

# ── LoRA: fl2v lightx2v turbo 4-step ──
echo "[7/12] minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors (LoRA - fl2v turbo 4-step)..."
hf_download "Kijai/MiniMax-H3_comfy" "loras/minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors" "$BASE_DIR"

# ── LoRA: ref2v lightx2v turbo 4-step resized avg rank 20 ──
echo "[8/12] minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors (LoRA - ref2v turbo 4-step rank 20)..."
hf_download "Kijai/MiniMax-H3_comfy" "loras/minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors" "$BASE_DIR"
# ── LoRA: H3 Realism People (fal) ──
echo "[9/12] h3-realism-people-t2v-i2v-r2v.safetensors (LoRA - H3 Realism People)..."
hf_download "fal/MiniMax-H3-Realism-People-LoRA" "h3-realism-people-t2v-i2v-r2v.safetensors" "$BASE_DIR/loras"


# ── Latent Upscale Model ──
echo "[10/12] minimax_h3_latent_upscaler_3d_fp16.safetensors (Latent Upscaler 3D)..."
hf_download "LBH-123-AI/Minimax_h3_latent_Upscaler" "minimax_h3_latent_upscaler_3d_fp16.safetensors" "$BASE_DIR/latent_upscale_models"

# ── Tiny VAE for live preview ──
echo "[11/12] taeh3.safetensors (Tiny VAE - live preview)..."
hf_download "Kijai/MiniMax-H3-TAE" "vae_approx/taeh3.safetensors" "$BASE_DIR/vae_approx"

# ── Semantic Bridge adapter model ──
echo "[12/12] MiniMaxH3_SemanticBridge_v1.safetensors (Semantic Bridge adapter)..."
hf_download "speach1sdef178/MiniMax-H3-Semantic-Bridge" "MiniMaxH3_SemanticBridge_v1.safetensors" "$BASE_DIR/semantic_bridge"

echo "==> All downloads completed!"

# ── Restart ComfyUI ──
echo "==> Restarting ComfyUI..."
supervisorctl restart comfyui || true

echo "✅ Setup complete!"
echo "👉 Open ComfyUI and load the workflow"
echo "👉 Upload an image in the LoadImage node"
