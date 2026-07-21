#!/bin/bash
# ---
# name: LTX 2.3 Director 2 (Workflow Hotfix)
# workflow: LTX_Director_2_Workflow_Hotfix
# aliases: [ltx director hotfix, ltx 2.3 director hotfix, ltx23 director hotfix, whatdreamscost hotfix, ltx-director-2-hotfix]
# description: Downloads all models for the LTX 2.3 Director 2 "Workflow Hotfix" — by WhatDreamsCost. Same VAEs / text encoders / spatial upscaler as the original `ltx-23-director-subgraphs.sh`, but swaps the 29.1GB full FP8 transformer + 2.6GB distilled LoRA combo for a single 25.2GB distilled-1.1 FP8 transformer-only checkpoint. Saves ~6.5GB. Installs required custom nodes and restarts ComfyUI.
# size: ~62.3GB
# min_vram: 24GB
# nodes: [ComfyUI-KJNodes, ComfyUI-LTXVideo, WhatDreamsCost-ComfyUI]
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
COMFYUI_DIR="$BASE_DIR"
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
#   - ComfyUI-KJNodes        (VAELoaderKJ)
#   - ComfyUI-LTXVideo       (core LTX nodes: LTXVConcatAVLatent, BasicScheduler)
#   - WhatDreamsCost-ComfyUI (LTXDirector, LTXDirectorCropGuides)
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

# 1. Distilled-1.1 FP8 transformer-only (~25.2GB) — UNETLoader
#    Replaces the 29.1GB dev-fp8 + 2.6GB LoRA combo from the older director script.
echo "[1/7] Distilled-1.1 FP8 transformer (UNETLoader)..."
# Kijai repo stores this file under diffusion_models/ (HF repo browse-tree
# convention). If we pass local_dir=$BASE_DIR/models/diffusion_models with the
# full blob path, the file lands at $BASE_DIR/models/diffusion_models/diffusion_models/<file>
# (double-nested, see skill workflow-researcher §8 pitfalls).
# Workaround: download with local_dir=$BASE_DIR (helper creates
# $BASE_DIR/diffusion_models/<file>), then move to the final home.
BLOB_PATH="$BASE_DIR/diffusion_models/ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors"
FINAL_PATH="$BASE_DIR/models/diffusion_models/ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors"
mkdir -p "$BASE_DIR/models/diffusion_models"
hf_download "Kijai/LTX2.3_comfy" "diffusion_models/ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  rmdir "$BASE_DIR/diffusion_models" 2>/dev/null || true
  echo "  ✅ Moved to $FINAL_PATH"
fi

# 2. Tiny VAE for previews (taeltx2_3 — 23.5MB)
echo "[2/7] Tiny VAE for previews (taeltx2_3)..."
# Kijai repo stores this file under vae/ (HF repo browse-tree convention).
# Pass local_dir=$BASE_DIR so the helper creates $BASE_DIR/vae/<file>, then move.
BLOB_PATH="$BASE_DIR/vae/taeltx2_3.safetensors"
FINAL_PATH="$BASE_DIR/models/vae/taeltx2_3.safetensors"
mkdir -p "$BASE_DIR/models/vae"
hf_download "Kijai/LTX2.3_comfy" "vae/taeltx2_3.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  rmdir "$BASE_DIR/vae" 2>/dev/null || true
  echo "  ✅ Moved to $FINAL_PATH"
fi

# 3. Audio VAE (~365MB)
echo "[3/7] Audio VAE (LTX23_audio_vae_bf16)..."
BLOB_PATH="$BASE_DIR/vae/LTX23_audio_vae_bf16.safetensors"
FINAL_PATH="$BASE_DIR/models/vae/LTX23_audio_vae_bf16.safetensors"
mkdir -p "$BASE_DIR/models/vae"
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_audio_vae_bf16.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  rmdir "$BASE_DIR/vae" 2>/dev/null || true
  echo "  ✅ Moved to $FINAL_PATH"
fi

# 4. Video VAE (~1.5GB)
echo "[4/7] Video VAE (LTX23_video_vae_bf16)..."
BLOB_PATH="$BASE_DIR/vae/LTX23_video_vae_bf16.safetensors"
FINAL_PATH="$BASE_DIR/models/vae/LTX23_video_vae_bf16.safetensors"
mkdir -p "$BASE_DIR/models/vae"
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_video_vae_bf16.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  rmdir "$BASE_DIR/vae" 2>/dev/null || true
  echo "  ✅ Moved to $FINAL_PATH"
fi

# 5. Text encoder: Gemma 3 12B FP4 mixed (~9.4GB) — DualCLIPLoader clip_name1
echo "[5/7] Text encoder (Gemma 3 12B FP4 mixed)..."
# Comfy-Org/ltx-2 stores this file under split_files/text_encoders/ (HF repo
# browse-tree convention). Pass local_dir=$BASE_DIR so the helper creates
# $BASE_DIR/split_files/text_encoders/<file>, then move into the final home.
BLOB_PATH="$BASE_DIR/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors"
FINAL_PATH="$BASE_DIR/models/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors"
mkdir -p "$BASE_DIR/models/text_encoders"
hf_download "Comfy-Org/ltx-2" "split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  rmdir "$BASE_DIR/split_files/text_encoders" 2>/dev/null || true
  rmdir "$BASE_DIR/split_files" 2>/dev/null || true
  echo "  ✅ Moved to $FINAL_PATH"
fi

# 6. LTX text projection (~2.3GB) — DualCLIPLoader clip_name2
echo "[6/7] LTX text projection (clip_name2)..."
# Kijai repo stores this file under text_encoders/ (HF repo browse-tree convention).
# Pass local_dir=$BASE_DIR so the helper creates $BASE_DIR/text_encoders/<file>, then move.
BLOB_PATH="$BASE_DIR/text_encoders/ltx-2.3_text_projection_bf16.safetensors"
FINAL_PATH="$BASE_DIR/models/text_encoders/ltx-2.3_text_projection_bf16.safetensors"
mkdir -p "$BASE_DIR/models/text_encoders"
hf_download "Kijai/LTX2.3_comfy" "text_encoders/ltx-2.3_text_projection_bf16.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  rmdir "$BASE_DIR/text_encoders" 2>/dev/null || true
  echo "  ✅ Moved to $FINAL_PATH"
fi

# 7. Spatial upscaler v1.1 (~996MB) — LatentUpscaleModelLoader
echo "[7/7] Spatial upscaler (v1.1)..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "$BASE_DIR/models/latent_upscale_models"

echo "==> All downloads completed!"

# Restart ComfyUI so it picks up the newly installed custom nodes + model files.
# On RunPod's runpod/comfyui image, the entrypoint pre-starts ComfyUI and there
# is no supervisord — so the script MUST kill the old process and relaunch it
# itself, otherwise the new custom_nodes/ clones never get imported. Using
# tmux new-session is the only pattern that survives SSH disconnect on RunPod
# slim (nohup/setsid+disown are killed when the SSH session ends — see
# vast-ai-script-runner skill pitfalls).
echo "==> Restarting ComfyUI..."
if command -v supervisorctl &> /dev/null; then
    # NOTE: --lowvram flag added 2026-07-21 per muneesraja — keep all ComfyUI
    # restarts (Vast supervisorctl + RunPod tmux fallback) consistent.
    supervisorctl restart comfyui 2>/dev/null \
        && echo "✅ ComfyUI restarted via supervisorctl" \
        || echo "⚠️  supervisorctl failed — restart ComfyUI manually"
elif [ -f /etc/supervisor/supervisord.conf ]; then
    supervisord -c /etc/supervisor/supervisord.conf 2>/dev/null \
        && echo "✅ ComfyUI supervisor started" \
        || echo "⚠️  supervisord failed — restart ComfyUI manually"
else
    # Detect the ComfyUI listen port from the running process (default 8188)
    COMFY_PORT=$(ps aux | grep '[p]ython.*main.py' | grep -oE -- '--port [0-9]+' | awk '{print $2}' | head -1)
    [ -z "$COMFY_PORT" ] && COMFY_PORT=8188

    # Write a launcher script (avoids tmux-quoting traps from inline env vars)
    cat > /root/start_comfyui.sh << EOF
#!/bin/bash
cd $COMFYUI_DIR
exec $COMFY_PYTHON main.py --listen 0.0.0.0 --port $COMFY_PORT --enable-cors-header --lowvram 2>&1
EOF
    chmod +x /root/start_comfyui.sh

    # Kill old process + clean db lock, then relaunch in tmux
    pkill -9 -f "main.py --listen" 2>/dev/null || true
    sleep 3
    rm -f "$COMFYUI_DIR/user/comfyui.db.lock" 2>/dev/null || true
    tmux kill-session -t comfyui 2>/dev/null || true
    tmux new-session -d -s comfyui "/root/start_comfyui.sh 2>&1 | tee /workspace/comfyui.log"
    echo "✅ ComfyUI restarted in tmux session 'comfyui' (port $COMFY_PORT)"
    echo "    Tail log: tmux attach -t comfyui"
fi

echo "==> Done!"
echo "👉 ComfyUI should now be loading the new nodes and models."
