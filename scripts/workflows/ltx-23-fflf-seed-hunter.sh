#!/bin/bash
# ---
# name: LTX 2.3 FFLF Seed Hunter
# workflow: ltx23_FFLFSeedHunter_v10
# aliases: [ltx fflf, ltx 2.3 fflf, ltx23 fflf, ltx fflf seed hunter, ltx 2.3 fflf seed hunter, ltx23-fflf-seed-hunter, ltx-23-fflf-seed-hunter]
# description: Downloads all models for the LTX 2.3 FFLF (First/Last Frame) Seed Hunter workflow — 3-stage with spatial upscaler v1.1, audio + video VAEs, distilled FP8 transformer, and OmniNFT-RL LoRA. Includes KJNodes-dependent custom nodes and restarts ComfyUI.
# size: ~44.9GB
# min_vram: 24GB
# nodes: [ComfyUI-KJNodes, ComfyUI-LTXVideo, rgthree-comfy, ComfyUI-VideoHelperSuite, ComfyUI-Impact-Pack, cg-use-everywhere, ComfyUI-Easy-Use, ComfyUI-mxToolkit, ComfyUI-Manager]
# node_patches: [ComfyUI-LTXVideo/kornia-pad (kornia 0.8.x compat, idempotent)]
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

# Install custom nodes required by this workflow (derived from ltx23FFLFSeedHunter_v10.json):
#   - ComfyUI-KJNodes           (LTX2SamplingPreviewOverride, VAELoaderKJ, LatentUpscaleModelLoader, PathchSageAttentionKJ, LTXVLatentUpsampler, ImageResizeKJv2, SimpleCalculatorKJ)
#   - ComfyUI-LTXVideo          (core LTX nodes: LTXVAddGuide, LTXVConditioning, LTXVCropGuides, LTXVConcatAVLatent, LTXVSeparateAVLatent, etc.)
#   - ComfyUI-VideoHelperSuite  (VHS_LoadVideo, VHS_VideoCombine, VHS_GetImageCount, VHS_BatchManager, VHS_FILENAMES, VHS_VIDEOINFO)
#   - ComfyUI-Impact-Pack       (SAMLoader, UltralyticsDetectorProvider, and other utilities)
#   - rgthree-comfy             (Any Switch, Fast Groups Bypasser/Muter, Power Lora Loader, RandomNoise)
#   - cg-use-everywhere         (Anything Everywhere — global reroute nodes)
#   - ComfyUI-Easy-Use          (easy seed and ~80 other utility nodes)
#   - ComfyUI-mxToolkit         (mxSlider — slider/reroute UI nodes)
#   - ComfyUI-Manager           (already in base image, included for transparency)
if command -v comfy &> /dev/null; then
    echo "  Using comfy-cli to install nodes..."
    comfy node install https://github.com/kijai/ComfyUI-KJNodes
    comfy node install https://github.com/Lightricks/ComfyUI-LTXVideo
    comfy node install https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite
    comfy node install https://github.com/ltdrdata/ComfyUI-Impact-Pack
    comfy node install https://github.com/rgthree/rgthree-comfy
    comfy node install https://github.com/chrisgoringe/cg-use-everywhere
    comfy node install https://github.com/yolain/ComfyUI-Easy-Use
    comfy node install https://github.com/Smirnov75/ComfyUI-mxToolkit
else
    echo "  comfy-cli not found, cloning node repositories manually..."
    mkdir -p "$CUSTOM_NODES_DIR"
    cd "$CUSTOM_NODES_DIR"
    [ -d ComfyUI-KJNodes ]              || git clone https://github.com/kijai/ComfyUI-KJNodes                 || true
    [ -d ComfyUI-LTXVideo ]             || git clone https://github.com/Lightricks/ComfyUI-LTXVideo         || true
    [ -d ComfyUI-VideoHelperSuite ]     || git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite || true
    [ -d ComfyUI-Impact-Pack ]          || git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack         || true
    [ -d rgthree-comfy ]                || git clone https://github.com/rgthree/rgthree-comfy                 || true
    [ -d cg-use-everywhere ]            || git clone https://github.com/chrisgoringe/cg-use-everywhere       || true
    [ -d ComfyUI-Easy-Use ]             || git clone https://github.com/yolain/ComfyUI-Easy-Use              || true
    [ -d ComfyUI-mxToolkit ]            || git clone https://github.com/Smirnov75/ComfyUI-mxToolkit         || true
    cd "$COMFYUI_DIR"
fi

# Patch known incompatible deps in the cloned nodes (Vast base image ships kornia 0.8.x,
# which dropped the `pad` re-export that older ComfyUI-LTXVideo requires).
# See: https://github.com/Lightricks/ComfyUI-LTXVideo/issues/505
# This block is idempotent — re-running on an already-patched file is a no-op.
LTXVIDEO_PYRAMID="$CUSTOM_NODES_DIR/ComfyUI-LTXVideo/pyramid_blending.py"
if [ -f "$LTXVIDEO_PYRAMID" ] && grep -q "from kornia.geometry.transform.pyramid import" "$LTXVIDEO_PYRAMID"; then
    if grep -q "patched: pad re-export was dropped" "$LTXVIDEO_PYRAMID"; then
        echo "  ComfyUI-LTXVideo kornia pad patch already applied"
    else
        echo "  Patching ComfyUI-LTXVideo pyramid_blending.py for kornia 0.8.x compatibility..."
        sed -i 's|    pad,|    # patched: pad re-export was dropped in kornia 0.8.x; use torch.nn.functional directly|' "$LTXVIDEO_PYRAMID"
        sed -i 's|\bpad(|F.pad(|g' "$LTXVIDEO_PYRAMID"
    fi
fi

# Install pip dependencies into ComfyUI's Python (not system Python)
echo "==> Installing node dependencies..."
for repo in ComfyUI-KJNodes ComfyUI-LTXVideo ComfyUI-VideoHelperSuite ComfyUI-Impact-Pack rgthree-comfy cg-use-everywhere ComfyUI-Easy-Use ComfyUI-mxToolkit; do
    REQ="$CUSTOM_NODES_DIR/$repo/requirements.txt"
    if [ -f "$REQ" ]; then
        echo "  Installing $repo deps..."
        $COMFY_PIP install -q -r "$REQ" 2>&1 | tail -3 || true
    fi
done

echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/{checkpoints,diffusion_models,loras,text_encoders,vae,latent_upscale_models}

# Load shared HF download helper (auto-fetch if not present — Vast instances don't bundle it)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_HF_HELPER=""
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh" "/tmp/_hf_download.sh"; do
  [ -f "$f" ] && _HF_HELPER="$f" && break
done
if [ -z "$_HF_HELPER" ]; then
  echo "  Fetching _hf_download.sh from GitHub..."
  GITHUB_BASE="https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/workflows"
  _HF_HELPER="/tmp/_hf_download.sh"
  if ! curl -sSL --fail "$GITHUB_BASE/_hf_download.sh" -o "$_HF_HELPER" 2>/dev/null; then
    # raw.githubusercontent.com fallback
    curl -sSL --fail "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/workflows/_hf_download.sh" -o "$_HF_HELPER" \
      || { echo "❌ FATAL: could not download _hf_download.sh"; exit 1; }
  fi
  chmod +x "$_HF_HELPER"
fi
source "$_HF_HELPER"
unset _HF_HELPER

echo "==> Starting downloads..."

# 1. Transformer (Distilled 1.1 FP8 Scaled — 25.2GB)
echo "[1/7] Transformer (Distilled 1.1 FP8 Scaled)..."
hf_download "Kijai/LTX2.3_comfy" "diffusion_models/ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors" "$BASE_DIR/diffusion_models"

# 2. Video VAE (~1.5GB)
echo "[2/7] Video VAE (LTX23_video_vae_bf16)..."
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_video_vae_bf16.safetensors" "$BASE_DIR/vae"

# 3. Audio VAE (~365MB) — used by LTXVAudioVAEDecode for audio generation
echo "[3/7] Audio VAE (LTX23_audio_vae_bf16)..."
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_audio_vae_bf16.safetensors" "$BASE_DIR/vae"

# 4. Tiny VAE for sampling previews (taeltx2_3 — 23.5MB)
echo "[4/7] Tiny VAE for sampling previews (taeltx2_3)..."
hf_download "Kijai/LTX2.3_comfy" "vae/taeltx2_3.safetensors" "$BASE_DIR/vae"

# 5. Text encoder: Gemma 3 12B FP8 e4m3fn (~13.2GB) — used as clip_name1 in DualCLIPLoader
echo "[5/7] Text Encoder (Gemma 3 12B FP8 e4m3fn)..."
hf_download "GitMylo/LTX-2-comfy_gemma_fp8_e4m3fn" "gemma_3_12B_it_fp8_e4m3fn.safetensors" "$BASE_DIR/text_encoders"

# 6. LTX text projection (~2.3GB) — used as clip_name2 in DualCLIPLoader
echo "[6/7] LTX text projection (clip_name2)..."
hf_download "Kijai/LTX2.3_comfy" "text_encoders/ltx-2.3_text_projection_bf16.safetensors" "$BASE_DIR/text_encoders"

# 7. Spatial upscaler v1.1 (~996MB)
echo "[7/7] Spatial upscaler (v1.1)..."
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
