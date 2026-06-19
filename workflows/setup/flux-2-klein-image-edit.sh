#!/bin/bash
# ---
# name: Flux.2 Klein 9B Image Edit
# workflow: flkl_001
# aliases: [flux-2-klein, flux-2-klein-image-edit, flux-klein, flux2-klein]
# description: Installs KJNodes, then downloads Flux.2 Klein 9B FP8 diffusion model + Qwen 3 8B text encoder + full encoder/small decoder VAE for image editing. Auto-restarts ComfyUI after node install.
# size: ~18.4GB
# min_vram: 24GB
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
export BASE_DIR
export COMFYUI_DIR

# ─── Detect ComfyUI launch args from running process ───
detect_comfyui_args() {
  local args
  args=$(ps aux | grep '[p]ython.*main.py' | head -1 | sed 's/.*main\.py//')
  if [ -n "$args" ]; then
    echo "$args"
  else
    echo "--listen 0.0.0.0 --port 8188 --enable-cors-header"
  fi
}

# ─── Get the Python binary used by ComfyUI ───
detect_comfyui_python() {
  local python_bin
  local comfyui_pid
  comfyui_pid=$(ps -eo pid,comm,args | awk '$2 ~ /python/ && /main\.py/ && !/tcl/ {print $1; exit}')
  if [ -n "$comfyui_pid" ] && [ -f "/proc/$comfyui_pid/exe" ]; then
    python_bin=$(readlink -f "/proc/$comfyui_pid/exe" 2>/dev/null)
    if [ -n "$python_bin" ] && [ -x "$python_bin" ] && [[ "$python_bin" == *python* ]]; then
      echo "$python_bin"
      return
    fi
  fi
  if [ -f /venv/main/bin/python3 ]; then
    echo "/venv/main/bin/python3"
    return
  elif [ -f "$COMFYUI_DIR/venv/bin/python3" ]; then
    echo "$COMFYUI_DIR/venv/bin/python3"
    return
  fi
  echo "$(which python3)"
}

COMFYUI_PYTHON=$(detect_comfyui_python)
COMFYUI_ARGS=$(detect_comfyui_args)
echo "  ComfyUI Python: $COMFYUI_PYTHON"
echo "  ComfyUI Args: $COMFYUI_ARGS"

# ─── Create model directories ───
echo ""
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
    # raw.githubusercontent.com fallback
    curl -sSL --fail "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/workflows/setup/_hf_download.sh" -o "$_HF_HELPER" \
      || { echo "❌ FATAL: could not download _hf_download.sh"; exit 1; }
  fi
  chmod +x "$_HF_HELPER"
fi
source "$_HF_HELPER"
unset _HF_HELPER

# ─── PHASE 1: Install custom nodes ───
echo ""
echo "==> [Phase 1] Setting up ComfyUI nodes..."
cd "$COMFYUI_DIR"
NODES_DIR="custom_nodes"
NODES_INSTALLED=0

# KJNodes (required by Flux.2 Klein image edit workflow — nodes 75, 92)
# Use PascalCase (ComfyUI-KJNodes) to match the canonical GitHub repo name
# and stay consistent with the LTX 2.3 FFLF script — otherwise the LTX phase
# would see a missing dir (its check is also PascalCase) and re-clone.
if [ -d "$NODES_DIR/ComfyUI-KJNodes" ] || [ -d "$NODES_DIR/comfyui-kjnodes" ]; then
  echo "  ✅ KJNodes already installed"
else
  echo "  📥 Installing KJNodes (kijai/ComfyUI-KJNodes)..."
  git clone https://github.com/kijai/ComfyUI-KJNodes "$NODES_DIR/ComfyUI-KJNodes" || true
  if [ -f "$NODES_DIR/ComfyUI-KJNodes/requirements.txt" ]; then
    $COMFYUI_PYTHON -m pip install -r "$NODES_DIR/ComfyUI-KJNodes/requirements.txt" -q 2>/dev/null || true
  fi
  NODES_INSTALLED=$((NODES_INSTALLED + 1))
fi

echo ""
echo "==> Starting model downloads..."

# 1. Flux.2 Klein 9B FP8 diffusion model (~9.43GB)
echo "[1/3] Flux.2 Klein 9B FP8 diffusion model..."
hf_download "black-forest-labs/FLUX.2-klein-9b-fp8" "flux-2-klein-9b-fp8.safetensors" "$BASE_DIR/models/diffusion_models"

# 2. Qwen 3 8B FP8 text encoder (~8.7GB)
# HF repo stores this under split_files/text_encoders/ prefix
# Use local_dir_use_symlinks=False to get a real file (not a broken symlink)
echo "[2/3] Qwen 3 8B FP8 text encoder..."
python3 << 'PYEOF'
import os, time, sys, shutil
os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '1'
token = os.environ.get('HF_TOKEN') or None
local_dir = os.path.join(os.environ['BASE_DIR'], 'models', 'text_encoders')
start = time.time()
try:
    from huggingface_hub import hf_hub_download
    hf_hub_download(
        repo_id='Comfy-Org/flux2-klein-9B',
        filename='split_files/text_encoders/qwen_3_8b_fp8mixed.safetensors',
        local_dir=local_dir,
        token=token,
    )
    dest = os.path.join(local_dir, 'split_files', 'text_encoders', 'qwen_3_8b_fp8mixed.safetensors')
    final_dest = os.path.join(local_dir, 'qwen_3_8b_fp8mixed.safetensors')
    if os.path.exists(dest) and dest != final_dest:
        shutil.move(dest, final_dest)
    # Clean up empty split_files directory tree (best-effort, never fatal)
    import pathlib
    split_dir = pathlib.Path(local_dir) / 'split_files'
    try:
        if split_dir.is_dir():
            # Walk bottom-up, remove only empty directories
            for p in sorted(split_dir.rglob('*'), reverse=True):
                if p.is_dir():
                    try:
                        p.rmdir()
                    except OSError:
                        pass
                else:
                    try:
                        p.unlink()
                    except OSError:
                        pass
            # Final root remove
            if not any(split_dir.iterdir()):
                split_dir.rmdir()
    except Exception as cleanup_err:
        print(f"  ⚠️  split_files cleanup skipped: {cleanup_err}")
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
hf_download "black-forest-labs/FLUX.2-small-decoder" "full_encoder_small_decoder.safetensors" "$BASE_DIR/models/vae"

echo "==> All downloads completed!"

# ─── PHASE 3: Restart ComfyUI if nodes were installed ───
echo ""
if [ "$NODES_INSTALLED" -gt 0 ]; then
  echo "==> [Phase 3] Restarting ComfyUI to load new nodes..."

  # Prefer supervisorctl (Vast.ai manages ComfyUI via supervisord)
  if command -v supervisorctl >/dev/null 2>&1 && supervisorctl status comfyui >/dev/null 2>&1; then
    echo "  🔄 supervisorctl restart comfyui"
    supervisorctl restart comfyui 2>&1
  else
    # Fallback: find and kill the main.py process tree, then relaunch
    COMFYUI_PID=$(ps -eo pid,comm,args | awk '$2 ~ /python/ && /main\.py/ && !/tcl/ {print $1; exit}')
    if [ -n "$COMFYUI_PID" ]; then
      echo "  🛑 Stopping ComfyUI (PID: $COMFYUI_PID)..."
      kill "$COMFYUI_PID" 2>/dev/null || true
      for i in $(seq 1 10); do
        if ! kill -0 "$COMFYUI_PID" 2>/dev/null; then break; fi
        sleep 1
      done
      if kill -0 "$COMFYUI_PID" 2>/dev/null; then
        kill -9 "$COMFYUI_PID" 2>/dev/null || true
      fi
    fi
    cd "$COMFYUI_DIR"
    echo "  🚀 Starting ComfyUI..."
    nohup $COMFYUI_PYTHON main.py $COMFYUI_ARGS > /workspace/comfyui.log 2>&1 &
    NEW_PID=$!
    echo "  ✅ ComfyUI started (PID: $NEW_PID)"
  fi

  # Wait for ComfyUI to be ready (check the actual port from $COMFYUI_ARGS)
  COMFYUI_PORT=$(echo "$COMFYUI_ARGS" | grep -oE -- '--port [0-9]+' | awk '{print $2}' | head -1)
  [ -z "$COMFYUI_PORT" ] && COMFYUI_PORT=8188
  echo "  ⏳ Waiting for ComfyUI on port $COMFYUI_PORT..."
  for i in $(seq 1 40); do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:$COMFYUI_PORT/system_stats 2>/dev/null | grep -q 200; then
      echo "  ✅ ComfyUI is ready!"
      break
    fi
    sleep 2
  done
else
  echo "==> [Phase 3] No new nodes installed — restart skipped"
  echo "  💡 To load models, click Refresh in the ComfyUI UI"
fi

echo ""
echo "==> All tasks completed!"
echo "📊 Summary:"
echo "  • Custom nodes installed this run: $NODES_INSTALLED"
echo "  • Models: 3 downloaded to $BASE_DIR/models"
echo "👉 Restart ComfyUI or click Refresh in the UI."
