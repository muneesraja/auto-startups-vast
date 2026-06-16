#!/bin/bash
# ---
# name: Flux.2 Klein 9B T2I
# workflow: flkl_002
# aliases: [flux-2-klein-t2i, flux-klein-t2i, flux2-klein-t2i]
# description: Downloads Flux.2 Klein 9B FP8 diffusion model + Qwen 3 8B text encoder + full encoder/small decoder VAE for text-to-image (T2I) generation.
# size: ~18.4GB
# min_vram: 24GB
# ---
set -e

# Platform-aware base directory detection
if [ -d "/workspace/runpod-slim/ComfyUI" ]; then
  BASE_DIR="/workspace/runpod-slim/ComfyUI/models"
  echo "  Platform: RunPod (base: $BASE_DIR)"
elif [ -d "/workspace/ComfyUI" ]; then
  BASE_DIR="/workspace/ComfyUI/models"
  echo "  Platform: Vast.ai (base: $BASE_DIR)"
else
  BASE_DIR="/workspace/ComfyUI/models"
  echo "  ⚠️  No ComfyUI dir found, defaulting to $BASE_DIR"
fi

echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/{diffusion_models,text_encoders,vae}

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

# 1. Flux.2 Klein 9B FP8 diffusion model (~9.43GB)
echo "[1/3] Flux.2 Klein 9B FP8 diffusion model..."
hf_download "black-forest-labs/FLUX.2-klein-9b-fp8" "flux-2-klein-9b-fp8.safetensors" "$BASE_DIR/diffusion_models"

# 2. Qwen 3 8B FP8 text encoder (~8.7GB)
# HF repo stores this under split_files/text_encoders/ prefix
# Use local_dir_use_symlinks=False to get a real file (not a broken symlink)
echo "[2/3] Qwen 3 8B FP8 text encoder..."
mkdir -p "$BASE_DIR/text_encoders"
python3 << 'PYEOF'
import os, time, sys, shutil
os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '1'
token = os.environ.get('HF_TOKEN') or None
local_dir = os.path.join(os.environ['BASE_DIR'], 'text_encoders')
start = time.time()
try:
    from huggingface_hub import hf_hub_download
    hf_hub_download(
        repo_id='Comfy-Org/flux2-klein-9B',
        filename='split_files/text_encoders/qwen_3_8b_fp8mixed.safetensors',
        local_dir=local_dir,
        local_dir_use_symlinks=False,
        token=token,
    )
    dest = os.path.join(local_dir, 'split_files', 'text_encoders', 'qwen_3_8b_fp8mixed.safetensors')
    final_dest = os.path.join(local_dir, 'qwen_3_8b_fp8mixed.safetensors')
    if os.path.exists(dest) and dest != final_dest:
        shutil.move(dest, final_dest)
    # Clean up empty split_files directory tree
    split_dir = os.path.join(local_dir, 'split_files')
    if os.path.isdir(split_dir):
        import pathlib; pathlib.Path(split_dir).rmdir() if not any(split_dir.iterdir()) and os.path.isdir(split_dir) else None
        try:
            os.removedirs(split_dir)
        except OSError:
            pass
    elapsed = time.time() - start
    size = os.path.getsize(final_dest)
    speed = size / elapsed / 1024 / 1024
    print(f"✅ qwen_3_8b_fp8mixed.safetensors — {size/1024/1024:.0f}MB in {elapsed:.1f}s ({speed:.0f} MB/s)")
except Exception as e:
    print(f"❌ Failed: Qwen 3 8B text encoder — {e}", file=sys.stderr)
    sys.exit(1)
PYEOF

# 3. Full encoder + small decoder VAE (~249.5MB)
echo "[3/3] Full encoder small decoder VAE..."
hf_download "black-forest-labs/FLUX.2-small-decoder" "full_encoder_small_decoder.safetensors" "$BASE_DIR/vae"

echo "==> All downloads completed!"
echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
