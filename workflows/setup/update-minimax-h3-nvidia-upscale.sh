#!/bin/bash
# ---
# name: MiniMax H3 NVIDIA Upscale - Incremental Update
# description: Runs ONLY the missing custom nodes and models for MinimaxH3_2Stage-NVIDIA_UPSCALE on a server that already ran minimax-h3-bunny-selflift-12gb-1080p-lora.sh
# size: ~23GB
# ---

set -e

# ── CLI args ──
INTERACTIVE=0
for arg in "$@"; do
    case "$arg" in
        --interactive|-i) INTERACTIVE=1 ;;
    esac
done

# ── Interactive HF_TOKEN prompt if requested ──
if [ "$INTERACTIVE" = "1" ]; then
    if [ -n "${HF_TOKEN:-}" ]; then
        echo "  ℹ️  HF_TOKEN already in env — press Enter to keep it."
    fi
    if [ -r /dev/tty ]; then
        read -rsp "🔑 Enter HF_TOKEN (hidden, Enter to skip/keep): " _HF_INPUT < /dev/tty 2>/dev/null || true
    else
        read -rsp "🔑 Enter HF_TOKEN (hidden, Enter to skip/keep): " _HF_INPUT || true
    fi
    echo
    if [ -n "${_HF_INPUT:-}" ]; then
        export HF_TOKEN="$_HF_INPUT"
        echo "  ✅ HF_TOKEN set"
    fi
fi

echo "==> Detecting platform..."
if [ -d "/workspace/runpod" ]; then
    PLATFORM="runpod"
    COMFYUI_DIR="/workspace/ComfyUI"
    echo "  ✅ RunPod detected"
elif [ -d "/workspace/runpod-slim" ]; then
    PLATFORM="runpod"
    COMFYUI_DIR="/workspace/runpod-slim/ComfyUI"
    echo "  ✅ RunPod (slim) detected"
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

# ── Install Missing Custom Nodes ──
echo "==> Installing missing custom node packs..."
cd "$COMFYUI_DIR"

if command -v comfy >/dev/null 2>&1; then
    echo "  Using comfy-cli..."
    comfy node install https://github.com/bbaudio-2025/Comfyui-MMH3-UltimateUpscale 2>/dev/null || true
    comfy node install https://github.com/rdh9616/ComfyUI-Open-H3-Regenerate 2>/dev/null || true
    comfy node install https://github.com/1038lab/ComfyUI-RMBG 2>/dev/null || true
else
    echo "  comfy-cli not found, cloning manually..."
    cd "$CUSTOM_NODES_DIR"
    [ -d Comfyui-MMH3-UltimateUpscale ] || git clone --depth=1 https://github.com/bbaudio-2025/Comfyui-MMH3-UltimateUpscale || true
    [ -d ComfyUI-Open-H3-Regenerate ] || git clone --depth=1 https://github.com/rdh9616/ComfyUI-Open-H3-Regenerate || true
    [ -d ComfyUI-RMBG ] || git clone --depth=1 https://github.com/1038lab/ComfyUI-RMBG || true
    cd "$COMFYUI_DIR"
fi

# ── Install dependencies for the new nodes ──
echo "==> Installing node dependencies..."
for repo in Comfyui-MMH3-UltimateUpscale comfyui-mmh3-ultimateupscale \
            ComfyUI-Open-H3-Regenerate comfyui-open-h3-regenerate \
            ComfyUI-RMBG comfyui-rmbg; do
    [ -d "$CUSTOM_NODES_DIR/$repo" ] || continue
    REQ="$CUSTOM_NODES_DIR/$repo/requirements.txt"
    if [ -f "$REQ" ]; then
        echo "  Installing $repo deps..."
        $COMFY_PIP install -q -r "$REQ" 2>&1 | tail -5 || true
    fi
done

# ── Load shared HF download helper ──
mkdir -p "$BASE_DIR"/{vae,latent_upscale_models,loras,RMBG}
if [ ! -f "$BASE_DIR/_hf_download.sh" ]; then
    echo "  Fetching _hf_download.sh from GitHub..."
    curl -sSL -o "$BASE_DIR/_hf_download.sh" \
        "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/workflows/setup/_hf_download.sh" || true
fi
source "$BASE_DIR/_hf_download.sh"

# ── Latent Upscaler Alias: Link existing FP16 weights for BF16 widget ──
echo "==> Setting up Latent Upscaler alias..."
TGT_BF16="$BASE_DIR/latent_upscale_models/minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors"
TGT_FP16="$BASE_DIR/latent_upscale_models/minimax_h3_latent_upscaler_3d_fp16.safetensors"
if [ ! -s "$TGT_BF16" ]; then
    if [ -s "$TGT_FP16" ]; then
        ln "$TGT_FP16" "$TGT_BF16" 2>/dev/null || ln -s "$TGT_FP16" "$TGT_BF16" 2>/dev/null || cp "$TGT_FP16" "$TGT_BF16"
        echo "  ✅ linked existing fp16 upscaler as $(basename "$TGT_BF16")"
    elif [ -s "$BASE_DIR/latent_upscale_models/minimax_h3_latent_upscaler_3d_fp16_V2.safetensors" ]; then
        SRC_V2="$BASE_DIR/latent_upscale_models/minimax_h3_latent_upscaler_3d_fp16_V2.safetensors"
        ln "$SRC_V2" "$TGT_BF16" 2>/dev/null || ln -s "$SRC_V2" "$TGT_BF16" 2>/dev/null || cp "$SRC_V2" "$TGT_BF16"
        echo "  ✅ linked existing fp16_V2 upscaler as $(basename "$TGT_BF16")"
    fi
else
    echo "  ✅ already present: $TGT_BF16"
fi

echo "==> Starting missing model downloads (~22.5GB total)..."

# [1/5] Fast VAE: NVIDIA StreamRender-H3 non-causal 24L (~6.5GB)
echo "[1/5] fast_h3_vae_noncausal_24l.safetensors (Fast VAE)..."
if [ ! -s "$BASE_DIR/vae/fast_h3_vae_noncausal_24l.safetensors" ]; then
    hf_download "Efficient-Large-Model/Open-H3-Regenerate-2K" "vae_fast/fast_h3_vae_noncausal_24l.safetensors" "$BASE_DIR/vae"
    if [ -s "$BASE_DIR/vae/vae_fast/fast_h3_vae_noncausal_24l.safetensors" ]; then
        mv "$BASE_DIR/vae/vae_fast/fast_h3_vae_noncausal_24l.safetensors" "$BASE_DIR/vae/fast_h3_vae_noncausal_24l.safetensors"
        rmdir "$BASE_DIR/vae/vae_fast" 2>/dev/null || true
    fi
    mkdir -p "$BASE_DIR/vae/vae_fast"
    ln "$BASE_DIR/vae/fast_h3_vae_noncausal_24l.safetensors" "$BASE_DIR/vae/vae_fast/fast_h3_vae_noncausal_24l.safetensors" 2>/dev/null || \
    ln -s "$BASE_DIR/vae/fast_h3_vae_noncausal_24l.safetensors" "$BASE_DIR/vae/vae_fast/fast_h3_vae_noncausal_24l.safetensors" 2>/dev/null || true
else
    echo "  ✅ already present"
fi

# [2/5] LoRA: MiniMax H3 LMS v1.0 r64 (~1.2GB)
echo "[2/5] minimax_h3_lms_v1.0_r64.safetensors (LoRA - LMS)..."
mkdir -p "$BASE_DIR/loras/minimax-h3"
if [ ! -s "$BASE_DIR/loras/minimax_h3_lms_v1.0_r64.safetensors" ] && [ ! -s "$BASE_DIR/loras/minimax-h3/minimax_h3_lms_v1.0_r64.safetensors" ]; then
    hf_download "Alissonerdx/Minimax-H3-ComfyUI" "loras/minimax_h3_lms_v1.0_r64.safetensors" "$BASE_DIR"
    ln "$BASE_DIR/loras/minimax_h3_lms_v1.0_r64.safetensors" "$BASE_DIR/loras/minimax-h3/minimax_h3_lms_v1.0_r64.safetensors" 2>/dev/null || \
    ln -s "$BASE_DIR/loras/minimax_h3_lms_v1.0_r64.safetensors" "$BASE_DIR/loras/minimax-h3/minimax_h3_lms_v1.0_r64.safetensors" 2>/dev/null || true
else
    echo "  ✅ already present"
fi

# [3/5] LoRA: NVIDIA Open-H3 Sharp Curve (~1.2GB)
echo "[3/5] sharp_curve_branches.safetensors (LoRA - Open-H3 Sharp Curve)..."
mkdir -p "$BASE_DIR/loras/Open-H3-Regenerate-2K"
if [ ! -s "$BASE_DIR/loras/Open-H3-Regenerate-2K/sharp_curve_branches.safetensors" ]; then
    hf_download "Efficient-Large-Model/Open-H3-Regenerate-2K" "lora/sharp_curve_branches.safetensors" "$BASE_DIR/loras"
    if [ -s "$BASE_DIR/loras/lora/sharp_curve_branches.safetensors" ]; then
        mv "$BASE_DIR/loras/lora/sharp_curve_branches.safetensors" "$BASE_DIR/loras/Open-H3-Regenerate-2K/sharp_curve_branches.safetensors"
        rmdir "$BASE_DIR/loras/lora" 2>/dev/null || true
    fi
    ln "$BASE_DIR/loras/Open-H3-Regenerate-2K/sharp_curve_branches.safetensors" "$BASE_DIR/loras/sharp_curve_branches.safetensors" 2>/dev/null || \
    ln -s "$BASE_DIR/loras/Open-H3-Regenerate-2K/sharp_curve_branches.safetensors" "$BASE_DIR/loras/sharp_curve_branches.safetensors" 2>/dev/null || true
else
    echo "  ✅ already present"
fi

# [4/5] LoRA: NVIDIA Open-H3 Regenerate 2K (~12.5GB)
echo "[4/5] open_h3_regenerate_2k_lora.safetensors (LoRA - Open-H3 Regenerate 2K)..."
mkdir -p "$BASE_DIR/loras/Open-H3-Regenerate-2K"
if [ ! -s "$BASE_DIR/loras/Open-H3-Regenerate-2K/open_h3_regenerate_2k_lora.safetensors" ]; then
    hf_download "Efficient-Large-Model/Open-H3-Regenerate-2K" "lora/open_h3_regenerate_2k_lora.safetensors" "$BASE_DIR/loras"
    if [ -s "$BASE_DIR/loras/lora/open_h3_regenerate_2k_lora.safetensors" ]; then
        mv "$BASE_DIR/loras/lora/open_h3_regenerate_2k_lora.safetensors" "$BASE_DIR/loras/Open-H3-Regenerate-2K/open_h3_regenerate_2k_lora.safetensors"
        rmdir "$BASE_DIR/loras/lora" 2>/dev/null || true
    fi
    ln "$BASE_DIR/loras/Open-H3-Regenerate-2K/open_h3_regenerate_2k_lora.safetensors" "$BASE_DIR/loras/open_h3_regenerate_2k_lora.safetensors" 2>/dev/null || \
    ln -s "$BASE_DIR/loras/Open-H3-Regenerate-2K/open_h3_regenerate_2k_lora.safetensors" "$BASE_DIR/loras/open_h3_regenerate_2k_lora.safetensors" 2>/dev/null || true
else
    echo "  ✅ already present"
fi

# [5/5] RMBG-2.0 Background Removal model (~884MB)
echo "[5/5] RMBG-2.0 (Background Removal model - 1038lab)..."
mkdir -p "$BASE_DIR/RMBG/RMBG-2.0"
for rmbg_file in model.safetensors config.json BiRefNet_config.py birefnet.py; do
    if [ ! -s "$BASE_DIR/RMBG/RMBG-2.0/$rmbg_file" ]; then
        hf_download "1038lab/RMBG-2.0" "$rmbg_file" "$BASE_DIR/RMBG/RMBG-2.0"
    fi
done

echo "==> All missing items installed!"

# ── Restart ComfyUI ──
echo "==> Restarting ComfyUI..."
if command -v supervisorctl >/dev/null 2>&1 && supervisorctl status comfyui >/dev/null 2>&1; then
    supervisorctl restart comfyui || true
elif [ -f /root/start_comfyui.sh ]; then
    tmux kill-session -t comfyui 2>/dev/null || true
    sleep 2
    for pid in $(ps -eo pid,args | awk '$0 ~ /main\.py/ && $0 !~ /awk/ {print $1}'); do
        kill -9 "$pid" 2>/dev/null || true
    done
    sleep 2
    rm -f "$COMFYUI_DIR/user/comfyui.db.lock" 2>/dev/null || true
    tmux new-session -d -s comfyui "/root/start_comfyui.sh 2>&1 | tee /workspace/comfyui.log"
fi

echo "✅ Update complete! Nodes and models are ready."
