#!/usr/bin/env bash
# ---
# name: MiniMax H3 R2V Style LoRA
# workflow: minimax-h3-r2v-style-lora
# aliases: [minimax-h3-style-lora, minimax-style-lora, h3-style-lora]
# description: Sets up ComfyUI with MiniMax H3 reference-to-video workflow and installs H3-native style LoRAs (studio1939-light, looping_sketch_anime, ref2v turbo).
# size: ~44GB
# min_vram: 24GB minimum; 48GB recommended
# nodes: [ComfyUI-KJNodes, ComfyUI-VideoHelperSuite]
# ---
set -euo pipefail

# ─── Platform-aware base directory detection (Vast.ai vs RunPod) ───
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
export BASE_DIR COMFYUI_DIR CUSTOM_NODES_DIR

# ─── ComfyUI Python detection ───
detect_comfyui_python() {
  local pid
  pid=$(ps -eo pid,comm,args 2>/dev/null | awk '$2 ~ /python/ && /main\.py/ && !/tcl/ {print $1; exit}' || true)
  if [ -n "$pid" ] && [ -f "/proc/$pid/exe" ]; then
    readlink -f "/proc/$pid/exe" 2>/dev/null
    return
  fi
  for p in \
    /venv/main/bin/python3 \
    "$COMFYUI_DIR/.venv-cu128/bin/python3" \
    "$COMFYUI_DIR/venv/bin/python3"; do
    [ -x "$p" ] && { echo "$p"; return; }
  done
  command -v python3
}
COMFY_PYTHON="$(detect_comfyui_python)"
COMFY_PIP=("$COMFY_PYTHON" -m pip)
echo "  Using ComfyUI Python: $COMFY_PYTHON"

# ─── Custom node install (comfy-cli first, git clone fallback) ───
echo "==> Setting up custom nodes..."
mkdir -p "$CUSTOM_NODES_DIR"
cd "$CUSTOM_NODES_DIR"

install_node() {
  local repo_name="$1"
  local git_url="$2"
  if [ ! -d "$repo_name" ]; then
    echo "  Cloning $repo_name..."
    git clone --depth 1 "$git_url" "$repo_name" || true
  else
    echo "  $repo_name already installed."
  fi
  if [ -f "$repo_name/requirements.txt" ]; then
    "${COMFY_PIP[@]}" install -q -r "$repo_name/requirements.txt" 2>&1 | tail -3 || true
  fi
}

install_node "ComfyUI-KJNodes" "https://github.com/kijai/ComfyUI-KJNodes"
install_node "ComfyUI-VideoHelperSuite" "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite"

cd "$COMFYUI_DIR"

# ─── Create model directories ───
echo "==> Creating model directories..."
mkdir -p "$BASE_DIR"/{diffusion_models,text_encoders,vae,loras}

# ─── Load shared HF download helper ───
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

# ─── Download base MiniMax H3 models ───
echo "==> Downloading base MiniMax H3 models..."
echo "[1/7] Diffusion Model (int8)..."
hf_download "Comfy-Org/MiniMax-H3" \
  "diffusion_models/minimax_h3_ref2va_int8_convrot.safetensors" \
  "$BASE_DIR"
ln -sf "$BASE_DIR/diffusion_models/minimax_h3_ref2va_int8_convrot.safetensors" \
  "$BASE_DIR/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors" 2>/dev/null || true

echo "[2/7] Text Encoder (Qwen3-VL 32B int8)..."
hf_download "Comfy-Org/MiniMax-H3" \
  "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" \
  "$BASE_DIR"

echo "[3/7] Video VAE..."
hf_download "Comfy-Org/MiniMax-H3" \
  "vae/minimax_h3_video_vae_fp16.safetensors" \
  "$BASE_DIR"

echo "[4/7] Audio VAE..."
hf_download "Comfy-Org/MiniMax-H3" \
  "vae/minimax_h3_audio_vae_fp32.safetensors" \
  "$BASE_DIR"

# ─── Download Style LoRAs ───
echo "==> Downloading H3-native style LoRAs..."

echo "[5/7] studio1939-light LoRA..."
hf_download "lovis93/studio-1939-old-animation-lora-minimax-h3" \
  "studio1939-light.safetensors" \
  "$BASE_DIR/loras"

echo "[6/7] minimax_h3_looping_sketch_anime_v1 LoRA..."
hf_download "Inner-Reflections/MiniMax-H3-Looping-Sketch-Anime" \
  "minimax_h3_looping_sketch_anime_v1.safetensors" \
  "$BASE_DIR/loras"

echo "[7/7] minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16 LoRA..."
hf_download "Comfy-Org/MiniMax-H3" \
  "loras/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors" \
  "$BASE_DIR"

# Optional Community LoRAs
if [ "${STYLE_LORA_COMMUNITY:-0}" = "1" ]; then
  echo "==> Downloading community style LoRAs..."
  hf_download "EllaPriest45/MinimaxH3_Styles" \
    "h3_painterly.safetensors" \
    "$BASE_DIR/loras" || true
  hf_download "EllaPriest45/MinimaxH3_Styles" \
    "h3_anime_flat_style.safetensors" \
    "$BASE_DIR/loras" || true
fi

echo "==> All downloads completed!"

# ─── Restart ComfyUI ───
echo "==> Restarting ComfyUI..."
if command -v supervisorctl >/dev/null 2>&1 && supervisorctl status comfyui >/dev/null 2>&1; then
  supervisorctl restart comfyui
  echo "✅ ComfyUI restarted via supervisorctl"
else
  pid=$(ps -eo pid,comm,args 2>/dev/null | awk '$2 ~ /python/ && /main\.py/ && !/tcl/ {print $1; exit}' || true)
  [ -n "${pid:-}" ] && kill "$pid" 2>/dev/null || true
  sleep 3
  nohup "$COMFY_PYTHON" "$COMFYUI_DIR/main.py" --listen 0.0.0.0 --port 8188 >"$COMFYUI_DIR/comfyui.log" 2>&1 &
  echo "✅ ComfyUI background process restarted"
fi

echo "==> Done! Style LoRAs are ready."
