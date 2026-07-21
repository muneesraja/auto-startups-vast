#!/bin/bash
# ---
# name: Stable Audio 3 Medium Base (Text-to-Audio)
# workflow: Stable_Audio_3.0_Medium_Base_workflow_in_ComfyUI_Text-to-Audio
# aliases: [stable-audio-3, stable-audio, sa3, sa3-medium-base, t2a-stable-audio-3]
# description: Self-contained provisioning script for ComfyUI's Stable Audio 3 Medium Base text-to-audio workflow. Installs no custom node packs (100% comfy-core), downloads the Stable Audio 3 Medium Base checkpoint + Qwen3.5 2B text encoder + T5Gemma text encoder from Comfy-Org HF repos, and restarts ComfyUI.
# size: ~14.9GB
# min_vram: 12GB
# nodes: []                ← workflow uses only comfy-core nodes, no custom packs required
# node_patches: []
# notes: |
#   - Subgraph workflow: 1 subgraph container + 4 top-level nodes (MarkdownNote x2, SaveAudioMP3, subgraph).
#   - All loaders live inside definitions.subgraphs[0].nodes[] (Audio Generation subgraph, 21 nodes).
#   - Custom-node detection: every node's properties.cnr_id is "comfy-core" — zero third-party packs.
#   - All 3 model URLs verified via curl -sI (HTTP 200). Repo stabilityai/stable-audio-3-medium is GATED — not used.
# ---
set -e

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

echo "==> Setting up ComfyUI nodes..."
cd "$COMFYUI_DIR"

# ─── ComfyUI Python detection ───
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

# ─── Custom node install ───
# Stable Audio 3 workflow uses ONLY comfy-core nodes (cnr_id=comfy-core on all 22 non-container nodes).
# No third-party custom node packs required. No git clone, no comfy-cli install, no pip deps.

# ─── Pip deps ───
# No custom packs → no per-pack requirements.txt to install.

# ─── Model directory creation ───
echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/{checkpoints,text_encoders}

# ─── Load shared HF download helper (auto-fetch if missing) ───
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

# ─── Downloads ───
echo "==> Starting downloads (3 files, ~14.9GB total)..."

# [1/3] Stable Audio 3 Medium Base checkpoint (9.2GB) — Comfy-Org pre-split
echo "[1/3] Stable Audio 3 Medium Base checkpoint..."
hf_download "Comfy-Org/stable-audio-3" "checkpoints/stable_audio_3_medium_base.safetensors" "$BASE_DIR"

# [2/3] Qwen3.5 2B text encoder (4.5GB) — used by CLIPLoader for Qwen TextGenerate reprompt path
echo "[2/3] Qwen3.5 2B text encoder (qwen_clip input)..."
hf_download "Comfy-Org/Qwen3.5" "text_encoders/qwen3.5_2b_bf16.safetensors" "$BASE_DIR"

# [3/3] T5Gemma text encoder (1.2GB) — used by CLIPLoader for Stable Audio conditioning
echo "[3/3] T5Gemma B-B UL2 text encoder (sa_clip input)..."
hf_download "Comfy-Org/stable-audio-3" "text_encoders/t5gemma_b_b_ul2.safetensors" "$BASE_DIR"

echo "==> All downloads completed!"

# ─── Restart ComfyUI so new nodes + models are picked up ───
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
echo "👉 ComfyUI should now be loading the new models. Open the workflow and hit Queue Prompt."
echo "   If nodes don't show up, hard-refresh the ComfyUI browser tab (Ctrl+Shift+R)."
