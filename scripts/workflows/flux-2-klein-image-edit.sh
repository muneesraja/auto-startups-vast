#!/bin/bash
# ---
# name: Flux.2 Klein 9B Image Edit
# workflow: flkl_001
# aliases: [flux-2-klein, flux-2-klein-image-edit, flux-klein, flux2-klein]
# description: Downloads Flux.2 Klein 9B FP8 diffusion model + Qwen 3 8B text encoder + full encoder/small decoder VAE for image editing.
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

# Load shared HF download helper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh"; do
  [ -f "$f" ] && source "$f" && break
done

echo "==> Starting downloads..."

# 1. Flux.2 Klein 9B FP8 diffusion model (~9.43GB)
echo "[1/3] Flux.2 Klein 9B FP8 diffusion model..."
hf_download "black-forest-labs/FLUX.2-klein-9b-fp8" "flux-2-klein-9b-fp8.safetensors" "$BASE_DIR/diffusion_models"

# 2. Qwen 3 8B FP8 text encoder (~8.7GB)
# HF repo stores this under split_files/text_encoders/ prefix
# hf_download helper can't handle nested paths properly, so use direct Python
echo "[2/3] Qwen 3 8B FP8 text encoder..."
mkdir -p "$BASE_DIR/text_encoders"
python3 << 'PYEOF'
import os, time, sys, shutil
os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '1'
token = os.environ.get('HF_TOKEN') or None
dest = os.path.join(os.environ['BASE_DIR'], 'text_encoders', 'qwen_3_8b_fp8mixed.safetensors')
start = time.time()
try:
    from huggingface_hub import hf_hub_download
    downloaded = hf_hub_download(
        repo_id='Comfy-Org/flux2-klein-9B',
        filename='split_files/text_encoders/qwen_3_8b_fp8mixed.safetensors',
        token=token,
    )
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        os.remove(dest)
    shutil.move(downloaded, dest)
    elapsed = time.time() - start
    size = os.path.getsize(dest)
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
