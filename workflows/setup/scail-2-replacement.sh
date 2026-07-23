#!/bin/bash
# ---
# name: SCAIL-2 Character Replacement
# workflow: SCAIL-2_Replacement
# aliases: [scail 2, scail-2, scail2, character replacement scail, scail replacement, wan scail]
# description: Downloads all models for the SCAIL-2 character-replacement workflow (ComfyUI built-in WanSCAILToVideo + SCAIL2ColoredMask + SAM3_VideoTrack nodes + Kosinkadink VideoHelperSuite for VHS_LoadVideo/VHS_VideoCombine). Files: wan2.1_14B_SCAIL_2_fp8_scaled.safetensors (diffusion), sam3.1_multiplex_fp16.safetensors (checkpoint), UMT5-XXL FP8 text encoder, CLIP-ViT-H vision, Wan 2.1 VAE, Lightx2v 14B I2V CFG step distill LoRA. Upgrades ComfyUI to master (the runpod/comfyui image's v0.27.0 release is too old — WanSCAILToVideo + SCAIL2ColoredMask + SAM3_VideoTrack were added after 2026-06-30) and installs ComfyUI-VideoHelperSuite. Restarts ComfyUI at the end.
# size: ~26.5GB
# min_vram: 24GB
# nodes: [comfy-core (must be on master — see script body), ComfyUI-VideoHelperSuite]
# node_patches: [comfy-core/upgrade-to-master (mandatory: v0.27.0 lacks WanSCAILToVideo/SCAIL2ColoredMask/SAM3_VideoTrack)]
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

# ⚠️  CRITICAL: This workflow requires WanSCAILToVideo, SCAIL2ColoredMask, and
# SAM3_VideoTrack nodes which are in comfy-core MASTER but not in v0.27.0
# (the runpod/comfyui image's pinned version, released 2026-06-30).
# Upgrade in-place via git pull if ComfyUI is a git checkout. Idempotent.
# See https://github.com/comfyanonymous/ComfyUI/blob/master/comfy_extras/nodes_scail.py
echo "==> Upgrading ComfyUI to master (required for WanSCAILToVideo / SCAIL2ColoredMask / SAM3_VideoTrack)..."
if [ -d "$COMFYUI_DIR/.git" ]; then
    if git -C "$COMFYUI_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        # Check current branch / commit
        CURRENT=$(git -C "$COMFYUI_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
        REMOTE=$(git -C "$COMFYUI_DIR" ls-remote origin master 2>/dev/null | cut -f1 | head -1 | cut -c1-7)
        if [ "$CURRENT" = "$(echo "$REMOTE" | cut -c1-7)" ]; then
            echo "  ComfyUI already at master HEAD ($CURRENT)"
        else
            echo "  Current: $CURRENT | Remote master HEAD: $REMOTE — pulling..."
            # Use `git stash` (NOT --include-untracked) to keep the untracked
            # .venv-cu128/ in place. Bug 9 (2026-07-14, confirmed live on
            # 194.14.47.19): --include-untracked clobbered the venv, every
            # subsequent $COMFY_PYTHON invocation silently failed, the
            # script still printed ✅.
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

# ⚠️  CRITICAL: comfy-kitchen 0.2.10 (shipped with runpod/comfyui image) is missing
# TensorCoreConvRotW4A4Layout AND its CUDA apply_rope kernel is built for cu13xx driver
# ABI, which crashes on this image's driver with "CUDA driver version is insufficient for
# CUDA runtime version" the moment SAM3's tracker hits apply_rope. ComfyUI's own
# comfy/quant_ops.py detects torch.version.cuda < 13 and calls ck.registry.disable("cuda"),
# which routes to the eager backend — but ONLY if the import of comfy_kitchen hasn't
# crashed first. Upgrading to 0.2.19 fixes the missing import AND aligns the cu13xx
# detection (now disabled-by-default for cu12.x, so the broken kernel never executes).
# See: workflow SAM3_VideoTrack error log on pod 64.119.209.250:17376 (2026-07-14).
echo "==> Upgrading comfy-kitchen to 0.2.19+ (fixes SAM3 apply_rope CUDA-driver crash)..."
$COMFY_PIP install -q -U --pre comfy-kitchen 2>&1 | tail -3 || true

# Custom nodes required:
#   - ComfyUI-VideoHelperSuite  (VHS_LoadVideo, VHS_VideoCombine)
# WanSCAILToVideo, SCAIL2ColoredMask, SAM3_VideoTrack, ResizeImageMaskNode,
# GetImageSize, MarkdownNote are all in comfy-core master as of 2026-07-13.
echo "==> Installing custom node packs..."
mkdir -p "$CUSTOM_NODES_DIR"
cd "$CUSTOM_NODES_DIR"
if [ -d ComfyUI-VideoHelperSuite ]; then
    echo "  ComfyUI-VideoHelperSuite already present"
else
    if command -v comfy &> /dev/null; then
        echo "  Installing ComfyUI-VideoHelperSuite via comfy-cli..."
        comfy node install https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite 2>&1 | tail -3 || \
            git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite
    else
        echo "  Cloning ComfyUI-VideoHelperSuite..."
        git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite
    fi
fi
cd "$COMFYUI_DIR"

# Install pip deps for VHS into ComfyUI's Python (avif, imageio, etc.)
VHS_REQ="$CUSTOM_NODES_DIR/ComfyUI-VideoHelperSuite/requirements.txt"
if [ -f "$VHS_REQ" ]; then
    echo "  Installing ComfyUI-VideoHelperSuite deps..."
    $COMFY_PIP install -q -r "$VHS_REQ" 2>&1 | tail -3 || true
fi

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

# ⚠️  Download-then-move pattern (2026-07-07): hf_hub_download preserves the
# full HF path, so the blob lands at $BASE_DIR/<full_hf_path>. We move it to
# the final models/<sub>/ location after download.

# 1. Diffusion model — wan2.1_14B_SCAIL_2_fp8_scaled (16.9GB) → diffusion_models/
echo "[1/6] Diffusion model — wan2.1_14B_SCAIL_2_fp8_scaled..."
BLOB_PATH="$BASE_DIR/diffusion_models/wan2.1_14B_SCAIL_2_fp8_scaled.safetensors"
FINAL_PATH="$BASE_DIR/models/diffusion_models/wan2.1_14B_SCAIL_2_fp8_scaled.safetensors"
mkdir -p "$BASE_DIR/models/diffusion_models"
hf_download "Comfy-Org/SCAIL-2" "diffusion_models/wan2.1_14B_SCAIL_2_fp8_scaled.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && rmdir "$BASE_DIR/diffusion_models" 2>/dev/null && echo "  ✅ Moved to $FINAL_PATH"

# 2. SAM3 checkpoint — sam3.1_multiplex_fp16 (1.66GB) → checkpoints/
echo "[2/6] SAM3 checkpoint — sam3.1_multiplex_fp16..."
BLOB_PATH="$BASE_DIR/checkpoints/sam3.1_multiplex_fp16.safetensors"
FINAL_PATH="$BASE_DIR/models/checkpoints/sam3.1_multiplex_fp16.safetensors"
mkdir -p "$BASE_DIR/models/checkpoints"
hf_download "Comfy-Org/sam3.1" "checkpoints/sam3.1_multiplex_fp16.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && rmdir "$BASE_DIR/checkpoints" 2>/dev/null && echo "  ✅ Moved to $FINAL_PATH"

# 3. Text encoder — UMT5-XXL FP8 (6.4GB) → text_encoders/
echo "[3/6] Text encoder — UMT5-XXL FP8 e4m3fn scaled..."
BLOB_PATH="$BASE_DIR/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
FINAL_PATH="$BASE_DIR/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
mkdir -p "$BASE_DIR/models/text_encoders"
hf_download "Comfy-Org/Wan_2.1_ComfyUI_repackaged" "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && rmdir "$BASE_DIR/split_files/text_encoders" "$BASE_DIR/split_files" 2>/dev/null && echo "  ✅ Moved to $FINAL_PATH"

# 4. CLIP Vision — CLIP-ViT-H (1.2GB) → clip_vision/
echo "[4/6] CLIP Vision — CLIP-ViT-H laion2B s32B b79K..."
BLOB_PATH="$BASE_DIR/split_files/clip_vision/clip_vision_h.safetensors"
FINAL_PATH="$BASE_DIR/models/clip_vision/clip_vision_h.safetensors"
mkdir -p "$BASE_DIR/models/clip_vision"
hf_download "Comfy-Org/Wan_2.1_ComfyUI_repackaged" "split_files/clip_vision/clip_vision_h.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && echo "  ✅ Moved to $FINAL_PATH"

# 5. VAE — Wan 2.1 VAE (242MB) → vae/
echo "[5/6] VAE — Wan 2.1 VAE..."
BLOB_PATH="$BASE_DIR/split_files/vae/wan_2.1_vae.safetensors"
FINAL_PATH="$BASE_DIR/models/vae/wan_2.1_vae.safetensors"
mkdir -p "$BASE_DIR/models/vae"
hf_download "Comfy-Org/Wan_2.1_ComfyUI_repackaged" "split_files/vae/wan_2.1_vae.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && echo "  ✅ Moved to $FINAL_PATH"

# 6. LoRA — Lightx2v I2V 14B CFG step distill rank64 (705MB) → loras/Wan2.1/
#    The workflow's LoraLoaderModelOnly widget stores "Wan2.1/Wan21_I2V_..._rank64.safetensors"
#    where "Wan2.1/" is ComfyUI's secondary-directory display. The file must land at
#    models/loras/Wan2.1/<file> for the dropdown to show it as "Wan2.1/Wan21_...".
echo "[6/6] LoRA — Lightx2v I2V 14B 480P CFG step distill rank64 (in loras/Wan2.1/)..."
BLOB_PATH="$BASE_DIR/loras/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors"
FINAL_PATH="$BASE_DIR/models/loras/Wan2.1/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors"
mkdir -p "$BASE_DIR/models/loras/Wan2.1"
hf_download "lightx2v/Wan2.1-I2V-14B-480P-StepDistill-CfgDistill-Lightx2v" "loras/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors" "$BASE_DIR"
[ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ] && mv "$BLOB_PATH" "$FINAL_PATH" && rmdir "$BASE_DIR/loras" 2>/dev/null && echo "  ✅ Moved to $FINAL_PATH"

echo "==> All downloads completed!"

# Restart ComfyUI so it picks up the master upgrade + new model files
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
    # RunPod pattern — pre-started container, must kill + relaunch with same args
    pkill -f "python main.py --listen" 2>/dev/null || true
    sleep 3
    cd "$COMFYUI_DIR"
    setsid bash -c "nohup $COMFY_PYTHON main.py --listen 0.0.0.0 --port 8188 --enable-cors-header > /root/comfyui.log 2>&1 < /dev/null &"
    echo "  ✅ ComfyUI relaunched (RunPod pattern)"
fi

echo "==> Done!"
echo "👉 ComfyUI should now be loading the new nodes and models."
echo ""
echo "Required custom nodes:"
echo "  - ComfyUI-VideoHelperSuite (cloned into custom_nodes/ by this script)"
echo "    — used for VHS_LoadVideo and VHS_VideoCombine"
echo "  - comfy-core (must be on master HEAD, not the v0.27.0 release)"
echo "    — provides WanSCAILToVideo, SCAIL2ColoredMask, SAM3_VideoTrack,"
echo "      ResizeImageMaskNode, GetImageSize. The upgrade section of this"
echo "      script handles that."
