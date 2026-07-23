#!/bin/bash
# ---
# name: SCAIL-2 Wan2.1 (mxfp8 + DPO + Lightx2v rank128)
# workflow: SCAIL-2_Workflow
# aliases: [scail 2 mxfp8, scail-2 dpo, wan scail mxfp8, scail-2 rank128, scaill2 dpo loop]
# description: Downloads all models for the SCAIL-2 character-replacement workflow with the mxfp8 diffusion + DPO LoRA + Lightx2v rank128 bf16 distill LoRA combo, plus the forLoop + per-frame color-transfer chain. Files: wan2.1_14B_SCAIL_2_mxfp8.safetensors (diffusion, in diffusion_models/SCAIL2/ to match the UNETLoader widget's "SCAIL2\\<file>" path), wan2.1_SCAIL_2_DPO_lora_bf16.safetensors (DPO LoRA), lightx2v_I2V_14B_480p_cfg_step_distill_rank128_bf16.safetensors (Lightx2v I2V distill), sam3.1_multiplex_fp16.safetensors (SAM3 checkpoint), UMT5-XXL FP8 text encoder, CLIP-ViT-H vision, Wan 2.1 VAE. Upgrades ComfyUI to master (runpod/comfyui image's v0.27.0 release is too old — WanSCAILToVideo + SCAIL2ColoredMask + SAM3_VideoTrack + ColorTransfer + BatchImagesNode were added after 2026-06-30) and installs ComfyUI-KJNodes, ComfyUI-VideoHelperSuite, ComfyUI-easy-use, ComfyUI-Custom-Scripts. Restarts ComfyUI at the end.
# size: ~28GB
# min_vram: 24GB
# nodes: [comfy-core (must be on master — see script body), ComfyUI-KJNodes, ComfyUI-VideoHelperSuite, ComfyUI-easy-use, ComfyUI-Custom-Scripts]
# node_patches: [comfy-core/upgrade-to-master (mandatory: v0.27.0 lacks WanSCAILToVideo/SCAIL2ColoredMask/SAM3_VideoTrack/ColorTransfer/BatchImagesNode)]
# ---
set -e

# Platform-aware base directory detection.
# IMPORTANT: BASE_DIR must be the ComfyUI root (NOT .../models) so that
# hf_hub_download(local_dir=BASE_DIR, filename="<sub>/foo.safetensors") lands files
# at $BASE_DIR/<sub>/foo.safetensors, which we then move-rename to the canonical
# $BASE_DIR/models/<sub>/foo.safetensors location. (See existing scail-2-replacement.sh
# for the same pattern + Bug-15 background on why the local_dir dance matters.)
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

# Detect the Python that ComfyUI actually runs with (Vast.ai images use /venv/main/).
# COMFY_PIP is the "python -m pip" form so it works on RunPod slim venvs that lack
# a `pip` symlink (Bug 10, 2026-07-14).
COMFY_PYTHON=""
COMFY_PIP=""
if [ -f /venv/main/bin/python3 ]; then
    COMFY_PYTHON="/venv/main/bin/python3"
    COMFY_PIP="$COMFY_PYTHON -m pip"
elif [ -f venv/bin/activate ]; then
    source venv/bin/activate
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$COMFY_PYTHON -m pip"
elif [ -f .venv-cu128/bin/activate ]; then
    source .venv-cu128/bin/activate
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$COMFY_PYTHON -m pip"
else
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$COMFY_PYTHON -m pip"
fi
echo "  Using ComfyUI Python: $COMFY_PYTHON"

# ⚠️  CRITICAL: This workflow requires WanSCAILToVideo, SCAIL2ColoredMask,
# SAM3_VideoTrack, ColorTransfer, BatchImagesNode, plus the KSampler/SamplerCustom
# + BasicScheduler + ModelSamplingSD3 surface that the workflow uses in non-
# default order — all of which live in comfy-core MASTER but not in v0.27.0
# (the runpod/comfyui image's pinned version, released 2026-06-30).
# Upgrade in-place via git pull if ComfyUI is a git checkout. Idempotent.
# See https://github.com/comfyanonymous/ComfyUI/blob/master/comfy_extras/nodes_scail.py
echo "==> Upgrading ComfyUI to master (required for WanSCAILToVideo / SCAIL2ColoredMask / SAM3_VideoTrack / ColorTransfer / BatchImagesNode)..."
if [ -d "$COMFYUI_DIR/.git" ]; then
    if git -C "$COMFYUI_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        CURRENT=$(git -C "$COMFYUI_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
        REMOTE=$(git -C "$COMFYUI_DIR" ls-remote origin master 2>/dev/null | cut -f1 | head -1 | cut -c1-7)
        if [ "$CURRENT" = "$(echo "$REMOTE" | cut -c1-7)" ]; then
            echo "  ComfyUI already at master HEAD ($CURRENT)"
        else
            echo "  Current: $CURRENT | Remote master HEAD: $REMOTE — pulling..."
            # Use `git stash` (NOT --include-untracked) to keep the untracked
            # .venv-cu128/ in place. Bug 9 (2026-07-14): --include-untracked
            # clobbered the venv, every subsequent $COMFY_PYTHON invocation
            # silently failed, the script still printed ✅. Confirmed live
            # on this pod (194.14.47.19) during the 2026-07-23 run.
            git -C "$COMFYUI_DIR" fetch --depth=1 origin master 2>&1 | tail -2
            git -C "$COMFYUI_DIR" reset --hard origin/master 2>&1 | tail -2
        fi
    else
        echo "  ⚠️  .git exists but not a git work tree — skipping upgrade"
    fi
else
    echo "  ⚠️  No .git directory — cannot upgrade in-place. Manually clone master to $COMFYUI_DIR"
    echo "     (this script assumes the pod was started from the runpod/comfyui image which has a git checkout)"
fi

# Install pip dependencies (in case master added new requirements)
if [ -f "$COMFYUI_DIR/requirements.txt" ]; then
    echo "  Installing ComfyUI deps..."
    $COMFY_PIP install -q -r "$COMFYUI_DIR/requirements.txt" 2>&1 | tail -3 || true
fi

# ⚠️  comfy-kitchen 0.2.10 (shipped with runpod/comfyui image) is missing
# TensorCoreConvRotW4A4Layout AND its CUDA apply_rope kernel is built for cu13xx
# driver ABI, which crashes on cu12.x images with "CUDA driver version is
# insufficient for CUDA runtime version" the moment SAM3's tracker hits apply_rope.
# Upgrading to 0.2.19+ fixes the missing import AND aligns the cu13xx detection
# (now disabled-by-default for cu12.x, so the broken kernel never executes).
# See: scail-2-replacement.sh 2026-07-14 patch notes.
echo "==> Upgrading comfy-kitchen to 0.2.19+ (fixes SAM3 apply_rope CUDA-driver crash)..."
$COMFY_PIP install -q -U --pre comfy-kitchen 2>&1 | tail -3 || true

# Custom nodes required (every one is observable in the workflow via cnr_id/aux_id):
#   - ComfyUI-KJNodes             → GetNode/SetNode (kijai/ComfyUI-KJNodes)
#   - ComfyUI-VideoHelperSuite    → VHS_LoadVideo / VHS_VideoCombine / VHS_VideoInfo
#   - ComfyUI-easy-use            → easy forLoopStart / easy forLoopEnd / easy imageRemBg
#                                   (cnr_id "comfyui_fearnworksnodes")
#   - ComfyUI-Custom-Scripts      → MathExpression|pysssss
#   - ComfyUI-KJNodes (ImageResizeKJv2 + GetImageRangeFromBatch) — cnr_id "comfyui-kjnodes"
#     is the same upstream pack, included by the kijai repo above.
# WanSCAILToVideo, SCAIL2ColoredMask, SAM3_VideoTrack, ColorTransfer, BatchImagesNode,
# KSamplerSelect, SamplerCustom, BasicScheduler, ModelSamplingSD3, VAEDecode, VHS_* etc.
# are all in comfy-core master as of 2026-07-23.
echo "==> Installing custom node packs..."
mkdir -p "$CUSTOM_NODES_DIR"
cd "$CUSTOM_NODES_DIR"

install_node_pack() {
    local url="$1"
    local name="$(basename "$url" .git)"
    if [ -d "$name" ]; then
        echo "  $name already present"
    else
        if command -v comfy &> /dev/null; then
            echo "  Installing $name via comfy-cli..."
            comfy node install "$url" 2>&1 | tail -3 || \
                git clone "$url"
        else
            echo "  Cloning $name..."
            git clone "$url"
        fi
    fi
}

install_node_pack "https://github.com/kijai/ComfyUI-KJNodes"
install_node_pack "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite"
install_node_pack "https://github.com/yolain/ComfyUI-Easy-Use"
install_node_pack "https://github.com/pythongosssss/ComfyUI-Custom-Scripts"

cd "$COMFYUI_DIR"

# Install pip deps for each pack into ComfyUI's Python
for pack in ComfyUI-KJNodes ComfyUI-VideoHelperSuite ComfyUI-Easy-Use ComfyUI-Custom-Scripts; do
    REQ="$CUSTOM_NODES_DIR/$pack/requirements.txt"
    if [ -f "$REQ" ]; then
        echo "  Installing $pack deps..."
        $COMFY_PIP install -q -r "$REQ" 2>&1 | tail -3 || true
    fi
done

# RMBG-1.4 (used by easy imageRemBg) lives under models/rmbg/ — installed by ComfyUI-Easy-Use
# on first run, but we pre-stage the dir to avoid a race:
mkdir -p "$BASE_DIR/models/rmbg"

echo "==> Creating model directories..."
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

# ⚠️  Download-then-move pattern (2026-07-07): hf_hub_download preserves the
# full HF path, so the blob lands at $BASE_DIR/<full_hf_path>. We move it to
# the final models/<sub>/ location after download.

# 1. Diffusion model — wan2.1_14B_SCAIL_2_mxfp8 (15.98GB)
#    The workflow's UNETLoader widget is "SCAIL2\\wan2.1_14B_SCAIL_2_mxfp8.safetensors"
#    — the "SCAIL2\\" prefix is a ComfyUI secondary-directory marker, so the loader
#    looks under models/diffusion_models/SCAIL2/<file>. We land the file there.
echo "[1/7] Diffusion model — wan2.1_14B_SCAIL_2_mxfp8 (in diffusion_models/SCAIL2/)..."
BLOB_PATH="$BASE_DIR/diffusion_models/wan2.1_14B_SCAIL_2_mxfp8.safetensors"
FINAL_PATH="$BASE_DIR/models/diffusion_models/SCAIL2/wan2.1_14B_SCAIL_2_mxfp8.safetensors"
mkdir -p "$BASE_DIR/models/diffusion_models/SCAIL2"
hf_download "Comfy-Org/SCAIL-2" "diffusion_models/wan2.1_14B_SCAIL_2_mxfp8.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && rmdir "$BASE_DIR/diffusion_models" 2>/dev/null && echo "  ✅ Moved to $FINAL_PATH"

# 2. DPO LoRA — wan2.1_SCAIL_2_DPO_lora_bf16 (1.17GB) → loras/
#    Widget path is the bare filename (no subdir) → flat in models/loras/
echo "[2/7] LoRA — wan2.1_SCAIL_2_DPO_lora_bf16 (DPO)..."
BLOB_PATH="$BASE_DIR/loras/wan2.1_SCAIL_2_DPO_lora_bf16.safetensors"
FINAL_PATH="$BASE_DIR/models/loras/wan2.1_SCAIL_2_DPO_lora_bf16.safetensors"
mkdir -p "$BASE_DIR/models/loras"
hf_download "Comfy-Org/SCAIL-2" "loras/wan2.1_SCAIL_2_DPO_lora_bf16.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && rmdir "$BASE_DIR/loras" 2>/dev/null && echo "  ✅ Moved to $FINAL_PATH"

# 3. Lightx2v distill LoRA — lightx2v_I2V_14B_480p_cfg_step_distill_rank128_bf16 (1.4GB)
#    ⚠️ NOT in the lightx2v/Wan2.1-I2V-14B-480P-StepDistill-CfgDistill-Lightx2v repo
#    (that one only has the rank64 variant). The rank128 bf16 lives in Kijai's mirror
#    under Lightx2v/<file> — needs the move-rename because the path has a subdir.
#    Widget path is bare filename → flat in models/loras/
echo "[3/7] LoRA — lightx2v_I2V_14B_480p_cfg_step_distill_rank128_bf16..."
BLOB_PATH="$BASE_DIR/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank128_bf16.safetensors"
FINAL_PATH="$BASE_DIR/models/loras/lightx2v_I2V_14B_480p_cfg_step_distill_rank128_bf16.safetensors"
mkdir -p "$BASE_DIR/models/loras"
hf_download "Kijai/WanVideo_comfy" "Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank128_bf16.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && rmdir "$BASE_DIR/Lightx2v" 2>/dev/null && echo "  ✅ Moved to $FINAL_PATH"

# 4. SAM3 checkpoint — sam3.1_multiplex_fp16 (1.66GB) → checkpoints/
echo "[4/7] SAM3 checkpoint — sam3.1_multiplex_fp16..."
BLOB_PATH="$BASE_DIR/checkpoints/sam3.1_multiplex_fp16.safetensors"
FINAL_PATH="$BASE_DIR/models/checkpoints/sam3.1_multiplex_fp16.safetensors"
mkdir -p "$BASE_DIR/models/checkpoints"
hf_download "Comfy-Org/sam3.1" "checkpoints/sam3.1_multiplex_fp16.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && rmdir "$BASE_DIR/checkpoints" 2>/dev/null && echo "  ✅ Moved to $FINAL_PATH"

# 5. Text encoder — UMT5-XXL FP8 (6.4GB) → text_encoders/
echo "[5/7] Text encoder — UMT5-XXL FP8 e4m3fn scaled..."
BLOB_PATH="$BASE_DIR/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
FINAL_PATH="$BASE_DIR/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
mkdir -p "$BASE_DIR/models/text_encoders"
hf_download "Comfy-Org/Wan_2.1_ComfyUI_repackaged" "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && rmdir "$BASE_DIR/split_files/text_encoders" "$BASE_DIR/split_files" 2>/dev/null && echo "  ✅ Moved to $FINAL_PATH"

# 6. CLIP Vision — CLIP-ViT-H (1.2GB) → clip_vision/
echo "[6/7] CLIP Vision — CLIP-ViT-H laion2B s32B b79K..."
BLOB_PATH="$BASE_DIR/split_files/clip_vision/clip_vision_h.safetensors"
FINAL_PATH="$BASE_DIR/models/clip_vision/clip_vision_h.safetensors"
mkdir -p "$BASE_DIR/models/clip_vision"
hf_download "Comfy-Org/Wan_2.1_ComfyUI_repackaged" "split_files/clip_vision/clip_vision_h.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && echo "  ✅ Moved to $FINAL_PATH"

# 7. VAE — Wan 2.1 VAE (242MB) → vae/
echo "[7/7] VAE — Wan 2.1 VAE..."
BLOB_PATH="$BASE_DIR/split_files/vae/wan_2.1_vae.safetensors"
FINAL_PATH="$BASE_DIR/models/vae/wan_2.1_vae.safetensors"
mkdir -p "$BASE_DIR/models/vae"
hf_download "Comfy-Org/Wan_2.1_ComfyUI_repackaged" "split_files/vae/wan_2.1_vae.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && echo "  ✅ Moved to $FINAL_PATH"

echo "==> All downloads completed!"

# Restart ComfyUI so it picks up the master upgrade + new node packs + model files.
# Standing rule (muneesraja, 2026-07-21): every main.py launch on 24GB GPUs MUST
# include --lowvram, including the manual-hint echo on RunPod where the script
# relaunches the process itself.
echo "==> Restarting ComfyUI..."
if command -v supervisorctl &> /dev/null; then
    supervisorctl restart comfyui 2>/dev/null \
        && echo "✅ ComfyUI restarted via supervisorctl" \
        || echo "⚠️  supervisorctl failed — restart ComfyUI manually with --lowvram"
elif [ -f /etc/supervisor/supervisord.conf ]; then
    supervisord -c /etc/supervisor/supervisord.conf 2>/dev/null \
        && echo "✅ ComfyUI supervisor started" \
        || echo "⚠️  supervisord failed — restart ComfyUI manually with --lowvram"
else
    # RunPod pattern — pre-started container, must kill + relaunch with --lowvram
    pkill -f "python main.py --listen" 2>/dev/null || true
    sleep 3
    cd "$COMFYUI_DIR"
    setsid bash -c "nohup $COMFY_PYTHON main.py --listen 0.0.0.0 --port 8188 --enable-cors-header --lowvram > /root/comfyui.log 2>&1 < /dev/null &"
    echo "  ✅ ComfyUI relaunched (RunPod pattern, --lowvram enabled)"
fi

echo "==> Done!"
echo "👉 ComfyUI should now be loading the new nodes and models."
echo ""
echo "Required custom nodes (cloned into custom_nodes/ by this script):"
echo "  - ComfyUI-KJNodes          → GetNode/SetNode/ImageResizeKJv2/GetImageRangeFromBatch"
echo "  - ComfyUI-VideoHelperSuite → VHS_LoadVideo / VHS_VideoCombine / VHS_VideoInfo"
echo "  - ComfyUI-Easy-Use         → easy forLoopStart / easy forLoopEnd / easy imageRemBg"
echo "  - ComfyUI-Custom-Scripts   → MathExpression|pysssss"
echo ""
echo "Required comfy-core (master, NOT v0.27.0):"
echo "  - WanSCAILToVideo"
echo "  - SCAIL2ColoredMask"
echo "  - SAM3_VideoTrack"
echo "  - ColorTransfer / BatchImagesNode"
echo "  - The upgrade section of this script handles the version pin."
