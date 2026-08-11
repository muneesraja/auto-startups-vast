#!/usr/bin/env bash
# MiniMax H3 Seamless Chain / Global References setup
# Installs required custom nodes, upgrades ComfyUI to >= v0.30.0,
# downloads the exact models referenced by the workflow, and restarts ComfyUI.
set -Eeuo pipefail

# -------- Platform-aware ComfyUI discovery --------
if [[ -d /workspace/runpod-slim/ComfyUI ]]; then
  COMFYUI_DIR=/workspace/runpod-slim/ComfyUI
elif [[ -d /workspace/ComfyUI ]]; then
  COMFYUI_DIR=/workspace/ComfyUI
elif [[ -d /workspace/ComfyUI_windows_portable/ComfyUI ]]; then
  COMFYUI_DIR=/workspace/ComfyUI_windows_portable/ComfyUI
else
  COMFYUI_DIR="${COMFYUI_DIR:-$PWD}"
fi
BASE_DIR="$COMFYUI_DIR"
NODES_DIR="$COMFYUI_DIR/custom_nodes"
MODELS_DIR="$COMFYUI_DIR/models"
mkdir -p "$NODES_DIR" "$MODELS_DIR" "$COMFYUI_DIR/input"

# Use the interpreter belonging to the running ComfyUI when possible.
detect_python() {
  local pid
  pid=$(ps -eo pid,comm,args | awk '$2 ~ /python/ && /main\.py/ && !/tcl/ {print $1; exit}') || true
  if [[ -n "${pid:-}" && -f "/proc/$pid/exe" ]]; then readlink -f "/proc/$pid/exe"; return; fi
  for p in "$COMFYUI_DIR/.venv/bin/python" "$COMFYUI_DIR/.venv-cu128/bin/python" /venv/main/bin/python3 python3; do
    command -v "$p" >/dev/null 2>&1 || [[ -x "$p" ]] && { echo "$p"; return; }
  done
  echo python3
}
COMFYUI_PYTHON=$(detect_python)

ver_ge() { [[ "$(printf '%s\n' "$1" "$2" | sort -V | tail -1)" == "$1" ]]; }
current_version=$($COMFYUI_PYTHON -c 'import comfyui_version; print(comfyui_version.__version__)' 2>/dev/null || echo unknown)
required_version=v0.30.0

# -------- Phase 0: H3 core version floor --------
echo "==> Phase 0: ComfyUI version=$current_version; required>=$required_version"
if [[ "$current_version" == unknown ]] || ! ver_ge "$current_version" "$required_version"; then
  echo "  Upgrading ComfyUI to the latest master tag (H3 nodes require >= v0.30.0)"
  git -C "$COMFYUI_DIR" stash --quiet || true
  git -C "$COMFYUI_DIR" fetch origin --tags --quiet
  latest_tag=$(git -C "$COMFYUI_DIR" tag --sort=-version:refname | grep -E '^v0\.3[0-9]' | head -1 || true)
  if [[ -n "$latest_tag" ]]; then git -C "$COMFYUI_DIR" checkout "$latest_tag"; else git -C "$COMFYUI_DIR" checkout origin/master; fi
  [[ -f "$COMFYUI_DIR/requirements.txt" ]] && $COMFYUI_PYTHON -m pip install -r "$COMFYUI_DIR/requirements.txt" -q
fi

# -------- Phase 1: custom nodes --------
# These are required by the H3 Chain loop and attention patch nodes.
install_node() {
  local dir="$1" url="$2"
  if [[ -d "$NODES_DIR/$dir/.git" ]]; then
    echo "  ✅ $dir already installed"
  else
    echo "  📥 Installing $dir"
    git clone --depth 1 "$url" "$NODES_DIR/$dir"
    if [[ -f "$NODES_DIR/$dir/requirements.txt" ]]; then
      $COMFYUI_PYTHON -m pip install -r "$NODES_DIR/$dir/requirements.txt" -q
    fi
  fi
}
install_node ComfyUI-KJNodes https://github.com/kijai/ComfyUI-KJNodes.git
install_node ComfyUI-SolAttn_triton https://github.com/kijai/ComfyUI-SolAttn_triton.git
install_node ComfyUI-MiniMaxH3-Contex-Loop https://github.com/ethanfel/ComfyUI-MiniMaxH3-Contex-Loop.git

# -------- Phase 2: exact model manifest from the workflow --------
# Public repo; no HF token is required. local_dir is the ComfyUI root so the
# filename's subdirectory prefix is not duplicated.
$COMFYUI_PYTHON -m pip install -q huggingface_hub
export HF_HUB_DISABLE_PROGRESS_BARS=0
hf_file() {
  local repo=$1 file=$2
  echo "  📥 $repo/$file"
  $COMFYUI_PYTHON - "$repo" "$file" "$BASE_DIR" <<'PYEOF'
import os, sys
from huggingface_hub import hf_hub_download
repo, filename, local_dir = sys.argv[1:]
hf_hub_download(repo_id=repo, filename=filename, local_dir=local_dir)
PYEOF
}
REPO=Comfy-Org/MiniMax-H3
hf_file "$REPO" diffusion_models/minimax_h3_ref2va_pruned_bf16.safetensors
hf_file "$REPO" text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors
hf_file "$REPO" vae/minimax_h3_video_vae_fp16.safetensors
hf_file "$REPO" vae/minimax_h3_audio_vae_fp32.safetensors
hf_file "$REPO" "loras/minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors" 2>/dev/null || \
  echo "  ⚠️ LoRA is not in Comfy-Org/MiniMax-H3; obtain it separately and place it in models/loras/"

# Required user inputs are intentionally not downloaded:
#   input/ComfyUI_temp_erlqb_00140_.png (face reference)
#   input/ComfyUI_temp_pbrpk_00001_.png (character sheet)
#   input/The silver estate was a memory now,.wav (source song)
echo ""
echo "⚠️ Upload the two reference PNGs and source WAV named in the workflow to: $COMFYUI_DIR/input/"

# -------- Phase 3: restart and verify --------
COMFYUI_ARGS=$(ps aux | awk '/[p]ython.*main\.py/ {sub(/.*main\.py/, ""); print; exit}') || true
# Preserve the existing launch arguments, but ensure H3 memory optimizations
# are present for the manual fallback restart.
[[ -n "${COMFYUI_ARGS:-}" ]] || COMFYUI_ARGS="--listen 0.0.0.0 --port 18188 --enable-cors-header"
[[ " $COMFYUI_ARGS " == *" --disable-pinned-memory "* ]] || COMFYUI_ARGS+=" --disable-pinned-memory"
[[ " $COMFYUI_ARGS " == *" --fp16-intermediates "* ]] || COMFYUI_ARGS+=" --fp16-intermediates"
COMFYUI_PORT=$(grep -oE -- '--port [0-9]+' <<<"$COMFYUI_ARGS" | awk '{print $2}' | head -1 || true)
[[ -n "${COMFYUI_PORT:-}" ]] || COMFYUI_PORT=8188

if command -v supervisorctl >/dev/null 2>&1 && supervisorctl status comfyui >/dev/null 2>&1; then
  supervisorctl restart comfyui
else
  pid=$(ps -eo pid,comm,args | awk '$2 ~ /python/ && /main\.py/ && !/tcl/ {print $1; exit}') || true
  [[ -n "${pid:-}" ]] && kill "$pid" 2>/dev/null || true
  sleep 3
  (cd "$COMFYUI_DIR" && nohup "$COMFYUI_PYTHON" main.py $COMFYUI_ARGS > "$COMFYUI_DIR/comfyui.log" 2>&1 &)
fi
for _ in $(seq 1 45); do
  if curl -fsS --max-time 3 "http://127.0.0.1:$COMFYUI_PORT/system_stats" >/dev/null 2>&1; then
    echo "✅ ComfyUI is ready on port $COMFYUI_PORT"
    break
  fi
  sleep 2
done

for f in \
  "$MODELS_DIR/diffusion_models/minimax_h3_ref2va_pruned_bf16.safetensors" \
  "$MODELS_DIR/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" \
  "$MODELS_DIR/vae/minimax_h3_video_vae_fp16.safetensors" \
  "$MODELS_DIR/vae/minimax_h3_audio_vae_fp32.safetensors"; do
  [[ -f "$f" ]] && echo "✅ $(basename "$f")" || echo "❌ Missing: $f"
done
echo "🎉 MiniMax H3 seamless-chain setup complete."
