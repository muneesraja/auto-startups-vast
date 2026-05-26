#!/bin/bash
# ---
# name: Flux.2 Dev Turbo
# workflow: fl2dt_001
# aliases: [flux-2-dev-turbo, flux2-dev-turbo, flux-dev-turbo, flux2-turbo]
# description: Downloads Flux.2 Dev Turbo FP8 diffusion model + Mistral 3 Small FP8 text encoder + Flux2 VAE for T2I generation.
# size: ~51GB
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

export BASE_DIR

echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/{diffusion_models,text_encoders,vae}

# Load shared HF download helper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh"; do
  [ -f "$f" ] && source "$f" && break
done

echo "==> Setting up ComfyUI nodes..."
# Platform-aware ComfyUI directory detection
if [ -d "/workspace/runpod-slim/ComfyUI" ]; then
  COMFYUI_DIR="/workspace/runpod-slim/ComfyUI"
elif [ -d "/workspace/ComfyUI" ]; then
  COMFYUI_DIR="/workspace/ComfyUI"
else
  COMFYUI_DIR="/workspace/ComfyUI"
fi
cd "$COMFYUI_DIR"
if [ -f /venv/main/bin/activate ]; then
  source /venv/main/bin/activate
fi
NODES_DIR="custom_nodes"

# rgthree-comfy
if [ -d "$NODES_DIR/rgthree-comfy" ]; then
  echo "  ✅ rgthree-comfy already installed"
else
  echo "  Installing rgthree-comfy..."
  git clone https://github.com/rgthree/rgthree-comfy "$NODES_DIR/rgthree-comfy" || true
  if [ -f "$NODES_DIR/rgthree-comfy/requirements.txt" ]; then
    /venv/main/bin/pip install -r "$NODES_DIR/rgthree-comfy/requirements.txt" -q 2>/dev/null || true
  fi
fi

# KJNodes
if [ -d "$NODES_DIR/comfyui-kjnodes" ]; then
  echo "  ✅ KJNodes already installed"
else
  echo "  Installing KJNodes..."
  git clone https://github.com/kijai/ComfyUI-KJNodes "$NODES_DIR/comfyui-kjnodes" || true
  if [ -f "$NODES_DIR/comfyui-kjnodes/requirements.txt" ]; then
    /venv/main/bin/pip install -r "$NODES_DIR/comfyui-kjnodes/requirements.txt" -q 2>/dev/null || true
  fi
fi

echo "==> Starting downloads..."

# 1. Flux.2 Dev Turbo FP8 diffusion model (~32.2GB)
echo "[1/3] Flux.2 Dev Turbo FP8 diffusion model..."
hf_download "silveroxides/FLUX.2-dev-fp8_scaled" "flux2-dev-turbo-fp8mixed.safetensors" "$BASE_DIR/diffusion_models"

# 2. Mistral 3 Small FP8 text encoder (~18.5GB)
echo "[2/3] Mistral 3 Small FP8 text encoder..."
hf_download "silveroxides/FLUX.2-dev-fp8_scaled" "mistral_3_small_flux2_fp8mixed.safetensors" "$BASE_DIR/text_encoders"

# 3. Flux2 VAE (~336.2MB)
echo "[3/3] Flux2 VAE..."
python3 << 'PYEOF'
import os, time, sys, shutil
os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '1'
token = os.environ.get('HF_TOKEN') or None
local_dir = os.path.join(os.environ['BASE_DIR'], 'vae')
start = time.time()
try:
    from huggingface_hub import hf_hub_download
    hf_hub_download(
        repo_id='Comfy-Org/flux2-dev',
        filename='split_files/vae/flux2-vae.safetensors',
        local_dir=local_dir,
        local_dir_use_symlinks=False,
        token=token,
    )
    # Move from split_files/vae/ to vae/ directly
    dest = os.path.join(local_dir, 'split_files', 'vae', 'flux2-vae.safetensors')
    final_dest = os.path.join(local_dir, 'flux2-vae.safetensors')
    if os.path.exists(dest) and dest != final_dest:
        shutil.move(dest, final_dest)
    # Clean up empty split_files directory tree
    split_dir = os.path.join(local_dir, 'split_files')
    if os.path.isdir(split_dir):
        try:
            os.removedirs(split_dir)
        except OSError:
            pass
    elapsed = time.time() - start
    size = os.path.getsize(final_dest)
    speed = size / elapsed / 1024 / 1024
    print(f"✅ flux2-vae.safetensors — {size/1024/1024:.0f}MB in {elapsed:.1f}s ({speed:.0f} MB/s)")
except Exception as e:
    print(f"❌ Failed: Flux2 VAE — {e}", file=sys.stderr)
    sys.exit(1)
PYEOF

echo "==> All downloads completed!"
echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."