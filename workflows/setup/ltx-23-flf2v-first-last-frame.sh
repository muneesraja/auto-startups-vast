#!/bin/bash
# ---
# name: LTX 2.3 FLF2V First-Last-Frame
# workflow: LTX-2.3_-_FLF2V_First-Last-Frame
# aliases: [ltx flf2v, ltx 2.3 flf2v, ltx23 flf2v, ltx first last frame, ltx-2.3 flf2v, ltx-23-flf2v-first-last-frame, ltx-23-fl2v, ltx first-last-frame, ltx 2.3 first-last-frame]
# description: Downloads all models for the LTX 2.3 FLF2V (First-Last-Frame-to-Video) workflow — distilled 1.1 FP8 transformer, spatial upscaler v1.1, audio + video VAEs, gemma FP8-scaled text encoder, and LTX text projection. Includes KJNodes + LTXVideo custom nodes and restarts ComfyUI.
# size: ~43.6GB
# min_vram: 24GB
# nodes: [ComfyUI-KJNodes, ComfyUI-LTXVideo, rgthree-comfy, ComfyUI-VideoHelperSuite, ComfyUI-Impact-Pack, ComfyUI-Easy-Use]
# node_patches: [ComfyUI-LTXVideo/kornia-pad (kornia 0.8.x compat, idempotent)]
# ---
set -e

# Platform-aware base directory detection.
# IMPORTANT: BASE_DIR must be the ComfyUI root (NOT .../models) so that
# hf_hub_download(local_dir=BASE_DIR, filename="<sub>/foo.safetensors")
# lands files at $BASE_DIR/<sub>/foo.safetensors. Setting BASE_DIR to
# .../models and then pre-creating $BASE_DIR/<sub>/ caused nested paths like
# models/<sub>/<sub>/foo.safetensors (fixed 2026-06-18).
if [ -d "/workspace/runpod-slim/ComfyUI" ]; then
  BASE_DIR="/workspace/runpod-slim/ComfyUI"
  COMFYUI_DIR="/workspace/runpod-slim/ComfyUI"
  echo "  Platform: RunPod (base: $BASE_DIR)"
elif [ -d "/workspace/ComfyUI" ]; then
  BASE_DIR="/workspace/ComfyUI"
  COMFYUI_DIR="/workspace/ComfyUI"
  echo "  Platform: Vast.ai (base: $BASE_DIR)"
else
  BASE_DIR="/workspace/ComfyUI"
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

# Install custom nodes required by this workflow (derived from LTX-2.3_-_FLF2V_First-Last-Frame.json):
#   - ComfyUI-KJNodes           (VAELoaderKJ, GetNode, SetNode, SimpleCalculatorKJ, LTXVImgToVideoInplaceKJ,
#                                PathchSageAttentionKJ, LTX2SamplingPreviewOverride, ImageResizeKJv2,
#                                ResizeImageMaskNode, ImagePadForOutpaint, ImageStitch, ImageScaleBy)
#   - ComfyUI-LTXVideo          (core LTX nodes: LTXVAddGuide, LTXVConditioning, LTXVCropGuides,
#                                LTXVConcatAVLatent, LTXVSeparateAVLatent, LTXVScheduler,
#                                LTX2_NAG, LTXVAudioVAEDecode, LTXVEmptyLatentAudio, LTXVLatentUpsampler,
#                                LTXVPreprocess, LTXVChunkFeedForward, LTX2AttentionTunerPatch,
#                                LTX2MemoryEfficientSageAttentionPatch)
#   - rgthree-comfy             (Power Lora Loader (rgthree))
#   - ComfyUI-VideoHelperSuite  (VHS_VideoCombine, VHS_BatchManager, VHS_FILENAMES)
#   - ComfyUI-Impact-Pack       (SAMPLER utilities + downstream Impact nodes referenced via aux chains)
#   - ComfyUI-Easy-Use          (easy showAnything)
if command -v comfy &> /dev/null; then
    echo "  Using comfy-cli to install nodes..."
    comfy node install https://github.com/kijai/ComfyUI-KJNodes
    comfy node install https://github.com/Lightricks/ComfyUI-LTXVideo
    comfy node install https://github.com/rgthree/rgthree-comfy
    comfy node install https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite
    comfy node install https://github.com/ltdrdata/ComfyUI-Impact-Pack
    comfy node install https://github.com/yolain/ComfyUI-Easy-Use
else
    echo "  comfy-cli not found, cloning node repositories manually..."
    mkdir -p "$CUSTOM_NODES_DIR"
    cd "$CUSTOM_NODES_DIR"
    [ -d ComfyUI-KJNodes ] || [ -d comfyui-kjnodes ] || git clone https://github.com/kijai/ComfyUI-KJNodes ComfyUI-KJNodes || true
    [ -d ComfyUI-LTXVideo ]             || git clone https://github.com/Lightricks/ComfyUI-LTXVideo         || true
    [ -d rgthree-comfy ]                || git clone https://github.com/rgthree/rgthree-comfy                 || true
    [ -d ComfyUI-VideoHelperSuite ]     || git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite || true
    [ -d ComfyUI-Impact-Pack ]          || git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack         || true
    [ -d ComfyUI-Easy-Use ]             || git clone https://github.com/yolain/ComfyUI-Easy-Use              || true
    cd "$COMFYUI_DIR"

    # Self-heal: re-clone any node that disappeared (race with manager prestartup_scripts etc.)
    EXPECTED_NODES=(
        "ComfyUI-KJNodes|kijai/ComfyUI-KJNodes"
        "ComfyUI-LTXVideo|Lightricks/ComfyUI-LTXVideo"
        "rgthree-comfy|rgthree/rgthree-comfy"
        "ComfyUI-VideoHelperSuite|Kosinkadink/ComfyUI-VideoHelperSuite"
        "ComfyUI-Impact-Pack|ltdrdata/ComfyUI-Impact-Pack"
        "ComfyUI-Easy-Use|yolain/ComfyUI-Easy-Use"
    )
    NEEDS_HEAL=0
    for entry in "${EXPECTED_NODES[@]}"; do
        dir="${entry%%|*}"
        if [ ! -d "$CUSTOM_NODES_DIR/$dir" ]; then
            NEEDS_HEAL=1
        fi
    done
    if [ "$NEEDS_HEAL" -eq 1 ]; then
        echo "  ⚠️  Some nodes missing after initial clone — re-cloning (self-heal)..."
        cd "$CUSTOM_NODES_DIR"
        for entry in "${EXPECTED_NODES[@]}"; do
            dir="${entry%%|*}"
            repo="${entry##*|}"
            if [ ! -d "$dir" ]; then
                echo "    📥 Re-cloning $dir..."
                git clone "https://github.com/$repo.git" "$dir" 2>&1 | tail -1 || true
            fi
        done
        cd "$COMFYUI_DIR"
    fi
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
for repo in ComfyUI-LTXVideo ComfyUI-VideoHelperSuite ComfyUI-Impact-Pack rgthree-comfy ComfyUI-Easy-Use; do
    REQ="$CUSTOM_NODES_DIR/$repo/requirements.txt"
    if [ -f "$REQ" ]; then
        echo "  Installing $repo deps..."
        $COMFY_PIP install -q -r "$REQ" 2>&1 | tail -3 || true
    fi
done
for kj_dir in ComfyUI-KJNodes comfyui-kjnodes; do
    REQ="$CUSTOM_NODES_DIR/$kj_dir/requirements.txt"
    if [ -f "$REQ" ]; then
        echo "  Installing $kj_dir deps..."
        $COMFY_PIP install -q -r "$REQ" 2>&1 | tail -3 || true
        break
    fi
done

echo "==> Creating directories..."
# Don't pre-create model subdirs here — hf_download uses hf_hub_download(local_dir=BASE_DIR, filename="<subdir>/foo")
# which preserves the prefix. We just need the BASE_DIR itself.
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

# 1. Distilled 1.1 FP8 Scaled transformer (25.2GB) — primary LTX diffusion model
echo "[1/6] Distilled 1.1 FP8 Scaled transformer..."
# Comfy-Org / Kijai repo stores this file under diffusion_models/ (HF repo
# browse-tree convention). If we pass local_dir=$BASE_DIR/models/diffusion_models
# with the full blob path, the file lands at
# $BASE_DIR/models/diffusion_models/diffusion_models/<file> (double-nested).
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

# 2. Video VAE (~1.5GB)
# The workflow widget references "LTX23_video_vae_bf16_KJ.safetensors" (with the _KJ suffix used by
# KJNodes workflows), but the HF blob in Kijai/LTX2.3_comfy is "LTX23_video_vae_bf16.safetensors"
# (no _KJ). We download the blob, then rename to the workflow-expected name so VAELoader can find it.
echo "[2/6] Video VAE (LTX23_video_vae_bf16_KJ)..."
mkdir -p "$BASE_DIR/models/vae"
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_video_vae_bf16.safetensors" "$BASE_DIR/models/vae"
if [ -f "$BASE_DIR/models/vae/LTX23_video_vae_bf16.safetensors" ]; then
  mv "$BASE_DIR/models/vae/LTX23_video_vae_bf16.safetensors" \
     "$BASE_DIR/models/vae/LTX23_video_vae_bf16_KJ.safetensors"
  echo "  ✅ Renamed to LTX23_video_vae_bf16_KJ.safetensors"
fi

# 3. Audio VAE (~365MB) — used by LTXVAudioVAEDecode for audio generation
# Same _KJ suffix situation as the video VAE.
echo "[3/6] Audio VAE (LTX23_audio_vae_bf16_KJ)..."
hf_download "Kijai/LTX2.3_comfy" "vae/LTX23_audio_vae_bf16.safetensors" "$BASE_DIR/models/vae"
if [ -f "$BASE_DIR/models/vae/LTX23_audio_vae_bf16.safetensors" ]; then
  mv "$BASE_DIR/models/vae/LTX23_audio_vae_bf16.safetensors" \
     "$BASE_DIR/models/vae/LTX23_audio_vae_bf16_KJ.safetensors"
  echo "  ✅ Renamed to LTX23_audio_vae_bf16_KJ.safetensors"
fi

# 4. Tiny VAE for sampling previews (taeltx2_3 — 23.5MB) — used by LTX2SamplingPreviewOverride
echo "[4/6] Tiny VAE for sampling previews (taeltx2_3)..."
mkdir -p "$BASE_DIR/models/vae/vae_approx"
hf_download "Kijai/LTX2.3_comfy" "vae/taeltx2_3.safetensors" "$BASE_DIR"
if [ -f "$BASE_DIR/vae/taeltx2_3.safetensors" ]; then
  mv "$BASE_DIR/vae/taeltx2_3.safetensors" "$BASE_DIR/models/vae/vae_approx/taeltx2_3.safetensors"
  rmdir "$BASE_DIR/vae" 2>/dev/null || true
  echo "  ✅ Moved to $BASE_DIR/models/vae/vae_approx/taeltx2_3.safetensors"
fi

# 5. Text encoder: Gemma 3 12B FP8 scaled (~13.2GB) — used as clip_name1 in DualCLIPLoader
# The workflow widget references "gemma_3_12B_it_fp8_scaled.safetensors" (NOT fp8_e4m3fn). Source is
# Comfy-Org/ltx-2 with the split_files/ prefix.
echo "[5/6] Text Encoder (Gemma 3 12B FP8 scaled)..."
BLOB_PATH="$BASE_DIR/split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors"
FINAL_PATH="$BASE_DIR/models/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors"
mkdir -p "$BASE_DIR/models/text_encoders"
hf_download "Comfy-Org/ltx-2" "split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  rm -rf "$BASE_DIR/split_files" 2>/dev/null || true
  echo "  ✅ Moved to $FINAL_PATH"
fi

# 6. LTX text projection (~2.3GB) — used as clip_name2 in DualCLIPLoader
echo "[6/6] LTX text projection (clip_name2)..."
# Comfy-Org / Kijai repo stores this file under text_encoders/ (HF repo
# browse-tree convention). If we pass local_dir=$BASE_DIR/models/text_encoders
# with the full blob path, the file lands at
# $BASE_DIR/models/text_encoders/text_encoders/<file> (double-nested).
# Workaround: download with local_dir=$BASE_DIR (helper creates
# $BASE_DIR/text_encoders/<file>), then move to the final home.
BLOB_PATH="$BASE_DIR/text_encoders/ltx-2.3_text_projection_bf16.safetensors"
FINAL_PATH="$BASE_DIR/models/text_encoders/ltx-2.3_text_projection_bf16.safetensors"
hf_download "Kijai/LTX2.3_comfy" "text_encoders/ltx-2.3_text_projection_bf16.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  rmdir "$BASE_DIR/text_encoders" 2>/dev/null || true
  echo "  ✅ Moved to $FINAL_PATH"
fi

# Spatial upscaler v1.1 (~996MB) — referenced by LatentUpscaleModelLoader for the 2x upscaling pass
echo "[extra] Spatial upscaler (v1.1)..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "$BASE_DIR/models/latent_upscale_models"

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
