#!/bin/bash
# ---
# name: Wan 2.2 Animate (Preprocess)
# workflow: wan22_animate_preprocess_MDMZ_071025
# aliases: [wan 2.2 animate, wan22 animate, wan animate preprocess, wan 2.2 character replace, wan animate relight]
# description: Downloads all models for the Wan 2.2 Animate (Kijai) preprocessing + generation workflow — 14B FP8 Animate diffusion, WanAnimate relight LoRA + Lightx2v 14B I2V distill LoRA, UMT5-XXL text encoder, CLIP-ViT-H vision, Wan 2.1 VAE, SAM2.1 base+ segmentation, YOLOv10m + ViTPose-L wholebody pose detection. Installs custom nodes (WanVideoWrapper, WanAnimatePreprocess, KJNodes, VideoHelperSuite, segment-anything-2) and restarts ComfyUI.
# size: ~32.6GB
# min_vram: 24GB
# nodes: [ComfyUI-WanVideoWrapper, ComfyUI-WanAnimatePreprocess, ComfyUI-KJNodes, ComfyUI-VideoHelperSuite, ComfyUI-segment-anything-2]
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
#   - ComfyUI-WanVideoWrapper        (WanVideo* nodes — model/VAE/LoRA/sampler/decoder/embed)
#   - ComfyUI-WanAnimatePreprocess   (PoseAndFaceDetection, OnnxDetectionModelLoader, DrawViTPose — Kijai)
#   - ComfyUI-KJNodes                (ImageResizeKJv2, GetNode/SetNode, ImageConcatMulti, Mask grow/blockify, etc.)
#   - ComfyUI-VideoHelperSuite       (VHS_LoadVideo, VHS_VideoCombine)
#   - ComfyUI-segment-anything-2     (DownloadAndLoadSAM2Model, Sam2Segmentation)
if command -v comfy &> /dev/null; then
    echo "  Using comfy-cli to install nodes..."
    comfy node install https://github.com/kijai/ComfyUI-WanVideoWrapper
    comfy node install https://github.com/kijai/ComfyUI-WanAnimatePreprocess
    comfy node install https://github.com/kijai/ComfyUI-KJNodes
    comfy node install https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite
    comfy node install https://github.com/kijai/ComfyUI-segment-anything-2
else
    echo "  comfy-cli not found, cloning node repositories manually..."
    mkdir -p "$CUSTOM_NODES_DIR"
    cd "$CUSTOM_NODES_DIR"
    [ -d ComfyUI-WanVideoWrapper ]      || git clone https://github.com/kijai/ComfyUI-WanVideoWrapper      || true
    [ -d ComfyUI-WanAnimatePreprocess ] || git clone https://github.com/kijai/ComfyUI-WanAnimatePreprocess || true
    [ -d ComfyUI-KJNodes ]              || git clone https://github.com/kijai/ComfyUI-KJNodes              || true
    [ -d ComfyUI-VideoHelperSuite ]     || git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite || true
    [ -d ComfyUI-segment-anything-2 ]   || git clone https://github.com/kijai/ComfyUI-segment-anything-2   || true
    cd "$COMFYUI_DIR"
fi

# Install pip dependencies into ComfyUI's Python (not system Python)
echo "==> Installing node dependencies..."
for repo in ComfyUI-WanVideoWrapper ComfyUI-WanAnimatePreprocess ComfyUI-KJNodes ComfyUI-VideoHelperSuite ComfyUI-segment-anything-2; do
    REQ="$CUSTOM_NODES_DIR/$repo/requirements.txt"
    if [ -f "$REQ" ]; then
        echo "  Installing $repo deps..."
        $COMFY_PIP install -q -r "$REQ" 2>&1 | tail -3 || true
    fi
done

# ⚠️  RunPod slim ships CUDA 12.8; onnxruntime-gpu>=1.21 expects CUDA 13.
# Pin to 1.20.1 (last CUDA 12 build) to prevent libcudart.so.13 import error
# that breaks ComfyUI-WanAnimatePreprocess. (Discovered 2026-07-07.)
$COMFY_PIP install -q --upgrade-strategy only-if-needed \
    onnxruntime-gpu==1.20.1 2>&1 | tail -3 || true

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
    curl -sSL --fail "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/workflows/setup/_hf_download.sh" -o "$_HF_HELPER" \
      || { echo "❌ FATAL: could not download _hf_download.sh"; exit 1; }
  fi
  chmod +x "$_HF_HELPER"
fi
source "$_HF_HELPER"
unset _HF_HELPER

echo "==> Starting downloads..."

# ⚠️  Download-then-move pattern fix (2026-07-07):
# hf_hub_download(local_dir=$BASE_DIR, filename="X/Y/Z") preserves the full HF path,
# landing the file at $BASE_DIR/X/Y/Z. We compute BLOB_PATH from the actual HF
# filename, then move to the final models/<sub>/ location. The previous version
# of this script assumed the first path component got stripped — that was wrong.

# 1. Diffusion model — Wan2.2 Animate 14B FP8 (Kijai repackaged, ~17.5GB)
echo "[1/9] Diffusion model — Wan2.2 Animate 14B FP8 (Kijai)..."
BLOB_PATH="$BASE_DIR/Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors"
FINAL_PATH="$BASE_DIR/models/diffusion_models/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors"
mkdir -p "$BASE_DIR/models/diffusion_models"
hf_download "Kijai/WanVideo_comfy_fp8_scaled" "Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && rmdir "$BASE_DIR/Wan22Animate" 2>/dev/null && echo "  ✅ Moved to $FINAL_PATH"

# 2. VAE — Wan 2.1 VAE (~242MB, lowercase filename in Comfy-Org repackaged)
echo "[2/9] VAE — Wan 2.1 VAE..."
BLOB_PATH="$BASE_DIR/split_files/vae/wan_2.1_vae.safetensors"
FINAL_PATH="$BASE_DIR/models/vae/wan_2.1_vae.safetensors"
mkdir -p "$BASE_DIR/models/vae"
hf_download "Comfy-Org/Wan_2.1_ComfyUI_repackaged" "split_files/vae/wan_2.1_vae.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && rmdir "$BASE_DIR/split_files/vae" "$BASE_DIR/split_files" 2>/dev/null && echo "  ✅ Moved to $FINAL_PATH"

# 3. CLIP Vision — CLIP-ViT-H (laion2B s32B, ~1.2GB)
echo "[3/9] CLIP Vision — CLIP-ViT-H laion2B s32B b79K..."
BLOB_PATH="$BASE_DIR/split_files/clip_vision/clip_vision_h.safetensors"
FINAL_PATH="$BASE_DIR/models/clip_vision/clip_vision_h.safetensors"
mkdir -p "$BASE_DIR/models/clip_vision"
hf_download "Comfy-Org/Wan_2.1_ComfyUI_repackaged" "split_files/clip_vision/clip_vision_h.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && echo "  ✅ Moved to $FINAL_PATH"

# 4. Text encoder — UMT5-XXL encoder bf16 (~10.8GB, Kijai repackaged, at root)
echo "[4/9] Text encoder — UMT5-XXL encoder bf16..."
BLOB_PATH="$BASE_DIR/umt5-xxl-enc-bf16.safetensors"
FINAL_PATH="$BASE_DIR/models/text_encoders/umt5-xxl-enc-bf16.safetensors"
mkdir -p "$BASE_DIR/models/text_encoders"
hf_download "Kijai/WanVideo_comfy" "umt5-xxl-enc-bf16.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && echo "  ✅ Moved to $FINAL_PATH"

# 5. LoRA — WanAnimate relight fp16 (~1.37GB, in LoRAs/Wan22_relight/)
echo "[5/9] LoRA — WanAnimate relight fp16..."
BLOB_PATH="$BASE_DIR/LoRAs/Wan22_relight/WanAnimate_relight_lora_fp16.safetensors"
FINAL_PATH="$BASE_DIR/models/loras/WanAnimate_relight_lora_fp16.safetensors"
mkdir -p "$BASE_DIR/models/loras"
hf_download "Kijai/WanVideo_comfy" "LoRAs/Wan22_relight/WanAnimate_relight_lora_fp16.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && rmdir "$BASE_DIR/LoRAs/Wan22_relight" "$BASE_DIR/LoRAs" 2>/dev/null && echo "  ✅ Moved to $FINAL_PATH"

# 6. LoRA — Lightx2v I2V 14B 480p CFG step distill rank64 bf16 (~703MB, in Lightx2v/)
echo "[6/9] LoRA — Lightx2v I2V 14B 480p cfg step distill rank64 bf16..."
BLOB_PATH="$BASE_DIR/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"
FINAL_PATH="$BASE_DIR/models/loras/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"
hf_download "Kijai/WanVideo_comfy" "Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && rmdir "$BASE_DIR/Lightx2v" 2>/dev/null && echo "  ✅ Moved to $FINAL_PATH"

# 7. SAM2 model — sam2.1 hiera base plus (~308MB, Kijai safetensors port, at root)
echo "[7/9] SAM2 — sam2.1 hiera base plus (Kijai safetensors port)..."
BLOB_PATH="$BASE_DIR/sam2.1_hiera_base_plus.safetensors"
FINAL_PATH="$BASE_DIR/models/sam2/sam2.1_hiera_base_plus.safetensors"
mkdir -p "$BASE_DIR/models/sam2"
hf_download "Kijai/sam2-safetensors" "sam2.1_hiera_base_plus.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && echo "  ✅ Moved to $FINAL_PATH"

# 8. Pose detection — ViTPose-L wholebody ONNX (~1.18GB, in onnx/wholebody/)
#    WanAnimatePreprocess nodes load from models/detection/, not models/onnx/
echo "[8/9] Pose — ViTPose-L wholebody ONNX..."
BLOB_PATH="$BASE_DIR/onnx/wholebody/vitpose-l-wholebody.onnx"
FINAL_PATH="$BASE_DIR/models/detection/vitpose-l-wholebody.onnx"
mkdir -p "$BASE_DIR/models/detection"
hf_download "JunkyByte/easy_ViTPose" "onnx/wholebody/vitpose-l-wholebody.onnx" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && rmdir "$BASE_DIR/onnx/wholebody" "$BASE_DIR/onnx" 2>/dev/null && echo "  ✅ Moved to $FINAL_PATH"

# 9. Object detection — YOLOv10m ONNX (~58MB, in process_checkpoint/det/)
#    Also goes to models/detection/ (same loader reads both vitpose + yolo)
echo "[9/9] Detector — YOLOv10m ONNX..."
BLOB_PATH="$BASE_DIR/process_checkpoint/det/yolov10m.onnx"
FINAL_PATH="$BASE_DIR/models/detection/yolov10m.onnx"
hf_download "Wan-AI/Wan2.2-Animate-14B" "process_checkpoint/det/yolov10m.onnx" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && rmdir "$BASE_DIR/process_checkpoint/det" "$BASE_DIR/process_checkpoint" 2>/dev/null && echo "  ✅ Moved to $FINAL_PATH"

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
