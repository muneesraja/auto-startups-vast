#!/bin/bash
# ---
# name: LTX 2.3 Director (Subgraphs)
# workflow: ltx-23-director-subgraphs
# aliases: [ltx director, ltx 2.3 director, ltx23 director, whatdreamscost, ltx-director-subgraphs]
# description: Downloads all models for the LTX 2.3 Director workflow with subgraphs (2-stage with spatial upscaler v1.1) — by WhatDreamsCost. Uses LTXVGemmaCLIPModelLoader, tiny VAE, audio + video VAEs, distilled LoRA, and FP8 transformer. Installs required custom nodes and restarts ComfyUI.
# size: ~46.2GB
# min_vram: 24GB
# nodes: [ComfyUI-KJNodes, ComfyUI-LTXVideo, WhatDreamsCost-ComfyUI]
# ---
set -e

# Platform-aware base directory detection
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

echo "==> Setting up ComfyUI nodes..."
cd "$COMFYUI_DIR"

# Detect the Python that ComfyUI actually runs with (Vast.ai images use /venv/main/)
COMFY_PYTHON=""
COMFY_PIP=""
if [ -f /venv/main/bin/python3 ]; then
    COMFY_PYTHON="/venv/main/bin/python3"
    COMFY_PIP="/venv/main/bin/pip"
elif [ -f venv/bin/activate ]; then
    source venv/bin/activate
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$(which pip)"
elif [ -f .venv-cu128/bin/activate ]; then
    source .venv-cu128/bin/activate
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$(which pip)"
else
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$(which pip)"
fi
echo "  Using ComfyUI Python: $COMFY_PYTHON"

# Install custom nodes required by this workflow:
#   - ComfyUI-KJNodes        (LTX2SamplingPreviewOverride, VAELoaderKJ)
#   - ComfyUI-LTXVideo       (core LTX nodes)
#   - WhatDreamsCost-ComfyUI (LTXDirector, LTXDirectorGuide)
if command -v comfy &> /dev/null; then
    echo "  Using comfy-cli to install nodes..."
    comfy node install https://github.com/kijai/ComfyUI-KJNodes
    comfy node install https://github.com/Lightricks/ComfyUI-LTXVideo
    comfy node install https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI
else
    echo "  comfy-cli not found, cloning node repositories manually..."
    mkdir -p "$CUSTOM_NODES_DIR"
    cd "$CUSTOM_NODES_DIR"
    [ -d ComfyUI-KJNodes ]              || git clone https://github.com/kijai/ComfyUI-KJNodes              || true
    [ -d ComfyUI-LTXVideo ]             || git clone https://github.com/Lightricks/ComfyUI-LTXVideo      || true
    [ -d WhatDreamsCost-ComfyUI ]       || git clone https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI || true
    cd "$COMFYUI_DIR"
fi

# Install pip dependencies into ComfyUI's Python (not system Python)
echo "==> Installing node dependencies..."
for repo in ComfyUI-KJNodes ComfyUI-LTXVideo WhatDreamsCost-ComfyUI; do
    REQ="$CUSTOM_NODES_DIR/$repo/requirements.txt"
    if [ -f "$REQ" ]; then
        echo "  Installing $repo deps..."
        $COMFY_PIP install -q -r "$REQ" 2>&1 | tail -3 || true
    fi
done

echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/{checkpoints,loras,text_encoders,vae,latent_upscale_models}

# Load shared HF download helper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh"; do
  [ -f "$f" ] && source "$f" && break
done

echo "==> Starting downloads..."

# 1. Transformer checkpoint (Lightricks FP8 — 29.1GB)
echo "[1/8] Transformer checkpoint (FP8)... "
hf_download "Lightricks/LTX-2.3-fp8" "ltx-2.3-22b-dev-fp8.safetensors" "$BASE_DIR/checkpoints"

# 2. Distilled LoRA (Kijai dynamic fro9 rank 105 — ~2.6GB)
echo "[2/8] Distilled LoRA (Kijai dynamic fro9 rank 105)..."
hf_download "Kijai/LTX2.3_comfy" "loras/ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors" "$BASE_DIR/loras"

# 3. Tiny VAE for previews (taeltx2_3 — 23.5MB)
echo "[3/8] Tiny VAE for previews (taeltx2_3)..."
hf_download "Kijai/LTX2.3_comfy" "vae/taeltx2_3.safetensors" "$BASE_DIR/vae"

# 4. Audio VAE (~365MB)
echo "[4/8] Audio VAE (LTX23_audio_vae_bf16)..."
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_audio_vae_bf16.safetensors" "$BASE_DIR/vae"

# 5. Video VAE (~1.5GB)
echo "[5/8] Video VAE (LTX23_video_vae_bf16)..."
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_video_vae_bf16.safetensors" "$BASE_DIR/vae"

# 6. Text encoder: Gemma 3 12B FP4 mixed (~9.4GB)
echo "[6/8] Text encoder (Gemma 3 12B FP4 mixed)..."
hf_download "Comfy-Org/ltx-2" "split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" "$BASE_DIR/text_encoders"

# 7. LTX text projection (~2.3GB) — loaded as clip_name2 in DualCLIPLoader
echo "[7/8] LTX text projection (clip_name2)..."
hf_download "Kijai/LTX2.3_comfy" "text_encoders/ltx-2.3_text_projection_bf16.safetensors" "$BASE_DIR/text_encoders"

# 8. Spatial upscaler v1.1 (~996MB)
echo "[8/8] Spatial upscaler (v1.1)..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "$BASE_DIR/latent_upscale_models"

echo "==> All downloads completed!"

# Restart ComfyUI so it picks up the newly installed custom nodes + model files
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
