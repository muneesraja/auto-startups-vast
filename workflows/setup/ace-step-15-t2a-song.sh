#!/bin/bash
# ---
# name: ACE-Step 1.5 Text-to-Audio (Song)
# workflow: 05_audio_ace_step_1_t2a_song_subgraphed
# aliases: [ace-step, ace step 1.5, ace-step-1.5, ace-step-t2a, ace-step-song, t2a-ace-step, acestep-15]
# description: Self-contained provisioning script for ComfyUI's ACE-Step 1.5 text-to-audio song workflow. Installs no custom node packs (100% comfy-core), downloads the acestep_v1.5_turbo diffusion model + Qwen 0.6B & 4B ACE15 text encoders + ace_1.5 VAE from Comfy-Org HF repos, and restarts ComfyUI. Inputs: `tags` (style/mood) and `lyrics` (with optional `[zh]`/`[ja]`/`[ko]`/`[es]`/`[fr]` language tags per the MarkdownNote) plus song duration.
# size: ~13.7GB
# min_vram: 16GB
# nodes: []                ← workflow uses only comfy-core nodes, no custom packs required
# node_patches: []
# notes: |
#   - Subgraph workflow: 1 subgraph container + 3 top-level nodes (MarkdownNote x2, SaveAudioMP3, subgraph).
#   - All loaders live inside definitions.subgraphs[0].nodes[] (Text to Audio ACE-Step 1.5 subgraph, 11 nodes).
#   - Custom-node detection: every node's properties.cnr_id is "comfy-core" — zero third-party packs.
#   - All 4 model URLs verified via curl -sIL (HTTP 200, content-length matches).
#   - Multi-language lyrics: the workflow converts non-English text to English chars internally; users can
#     hint languages at the start of a lyrics stanza with [zh] / [ja] / [ko] / [es] / [fr] tags.
#   - HF repo: Comfy-Org/ace_step_1.5_ComfyUI_files (pre-split, all files under split_files/ subdirs).
# ---
set -e

# ─── Platform-aware base directory detection (Vast.ai vs RunPod) ───
# IMPORTANT: BASE_DIR must be the ComfyUI root (NOT .../models) so that
# hf_hub_download(local_dir=BASE_DIR, filename="split_files/<sub>/<file>")
# lands files at $BASE_DIR/split_files/<sub>/<file>. We then move them into
# $BASE_DIR/models/<sub>/<file> (the path ComfyUI's loaders expect). Setting
# BASE_DIR to .../models and passing split_files/... would create nested
# paths like models/split_models/<sub>/<file>. See workflow-researcher §8 pitfall.
if [ -d "/workspace/runpod-slim/ComfyUI" ]; then
  BASE_DIR="/workspace/runpod-slim/ComfyUI"
  COMFYUI_DIR="/workspace/runpod-slim/ComfyUI"
  echo "  Platform: RunPod (base: $BASE_DIR)"
elif [ -d "/workspace/ComfyUI" ]; then
  BASE_DIR="/workspace/ComfyUI"
  COMFYUI_DIR="/workspace/ComfyUI"
  echo "  Platform: Vast.ai (base: $BASE_DIR)"
else
  BASE_DIR="/workspace/ComfyUI"
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
# ACE-Step 1.5 text-to-audio workflow uses ONLY comfy-core nodes
# (cnr_id=comfy-core on all 14 non-container nodes, including the loaders and
# TextEncodeAceStepAudio1.5). No third-party custom node packs required.
# No git clone, no comfy-cli install, no pip deps.

# ─── Model directory creation ───
echo "==> Creating directories..."
mkdir -p "$BASE_DIR/models"/{diffusion_models,text_encoders,vae}

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
echo "==> Starting downloads (4 files, ~13.7GB total)..."

# All Comfy-Org/ace_step_1.5_ComfyUI_files entries live under split_files/...
# (HF browse-tree convention). Pass local_dir=$BASE_DIR so the helper creates
# $BASE_DIR/split_files/<sub>/<file>, then move into the final home at
# $BASE_DIR/models/<sub>/<file>. See workflow-researcher §8 pitfall.

# [1/4] acestep_v1.5_turbo diffusion model (~4.5GB) — UNETLoader
echo "[1/4] acestep_v1.5_turbo diffusion model (UNETLoader)..."
BLOB_PATH="$BASE_DIR/split_files/diffusion_models/acestep_v1.5_turbo.safetensors"
FINAL_PATH="$BASE_DIR/models/diffusion_models/acestep_v1.5_turbo.safetensors"
hf_download "Comfy-Org/ace_step_1.5_ComfyUI_files" "split_files/diffusion_models/acestep_v1.5_turbo.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  echo "  ✅ Moved to $FINAL_PATH"
fi

# [2/4] Qwen 0.6B ACE15 text encoder (~1.1GB) — DualCLIPLoader clip_name1
echo "[2/4] Qwen 0.6B ACE15 text encoder (DualCLIPLoader clip_name1)..."
BLOB_PATH="$BASE_DIR/split_files/text_encoders/qwen_0.6b_ace15.safetensors"
FINAL_PATH="$BASE_DIR/models/text_encoders/qwen_0.6b_ace15.safetensors"
hf_download "Comfy-Org/ace_step_1.5_ComfyUI_files" "split_files/text_encoders/qwen_0.6b_ace15.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  echo "  ✅ Moved to $FINAL_PATH"
fi

# [3/4] Qwen 4B ACE15 text encoder (~7.8GB) — DualCLIPLoader clip_name2
echo "[3/4] Qwen 4B ACE15 text encoder (DualCLIPLoader clip_name2)..."
BLOB_PATH="$BASE_DIR/split_files/text_encoders/qwen_4b_ace15.safetensors"
FINAL_PATH="$BASE_DIR/models/text_encoders/qwen_4b_ace15.safetensors"
hf_download "Comfy-Org/ace_step_1.5_ComfyUI_files" "split_files/text_encoders/qwen_4b_ace15.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  echo "  ✅ Moved to $FINAL_PATH"
fi

# [4/4] ACE 1.5 VAE (~322MB) — VAELoader
echo "[4/4] ACE 1.5 VAE (VAELoader)..."
BLOB_PATH="$BASE_DIR/split_files/vae/ace_1.5_vae.safetensors"
FINAL_PATH="$BASE_DIR/models/vae/ace_1.5_vae.safetensors"
hf_download "Comfy-Org/ace_step_1.5_ComfyUI_files" "split_files/vae/ace_1.5_vae.safetensors" "$BASE_DIR"
if [ -f "$BLOB_PATH" ] && [ "$BLOB_PATH" != "$FINAL_PATH" ]; then
  mv "$BLOB_PATH" "$FINAL_PATH"
  echo "  ✅ Moved to $FINAL_PATH"
fi

# Clean up empty split_files/ scaffolding dirs created by hf_hub_download
rmdir "$BASE_DIR/split_files/diffusion_models" 2>/dev/null || true
rmdir "$BASE_DIR/split_files/text_encoders"   2>/dev/null || true
rmdir "$BASE_DIR/split_files/vae"             2>/dev/null || true
rmdir "$BASE_DIR/split_files"                 2>/dev/null || true

echo "==> All downloads completed!"

# ─── Restart ComfyUI so new nodes + models are picked up ───
echo "==> Restarting ComfyUI..."
if command -v supervisorctl &> /dev/null; then
    # NOTE: --lowvram flag added 2026-07-21 per muneesraja — keep all ComfyUI
    # restarts (Vast supervisorctl + RunPod tmux fallback) consistent.
    supervisorctl restart comfyui 2>/dev/null \
        && echo "✅ ComfyUI restarted via supervisorctl" \
        || echo "⚠️  supervisorctl failed — restart ComfyUI manually"
elif [ -f /etc/supervisor/supervisord.conf ]; then
    supervisord -c /etc/supervisor/supervisord.conf 2>/dev/null \
        && echo "✅ ComfyUI supervisor started" \
        || echo "⚠️  supervisord failed — restart ComfyUI manually"
else
    # Detect the ComfyUI listen port from the running process (default 8188)
    COMFY_PORT=$(ps aux | grep '[p]ython.*main.py' | grep -oE -- '--port [0-9]+' | awk '{print $2}' | head -1)
    [ -z "$COMFY_PORT" ] && COMFY_PORT=8188

    cat > /root/start_comfyui.sh << EOF
#!/bin/bash
cd $COMFYUI_DIR
exec $COMFY_PYTHON main.py --listen 0.0.0.0 --port $COMFY_PORT --enable-cors-header --lowvram 2>&1
EOF
    chmod +x /root/start_comfyui.sh

    pkill -9 -f "main.py --listen" 2>/dev/null || true
    sleep 3
    rm -f "$COMFYUI_DIR/user/comfyui.db.lock" 2>/dev/null || true
    tmux kill-session -t comfyui 2>/dev/null || true
    tmux new-session -d -s comfyui "/root/start_comfyui.sh 2>&1 | tee /workspace/comfyui.log"
    echo "✅ ComfyUI restarted in tmux session 'comfyui' (port $COMFY_PORT)"
    echo "    Tail log: tmux attach -t comfyui"
fi

echo "==> Done!"
echo "👉 ComfyUI should now be loading the new models. Open the workflow and edit the"
echo '   TextEncodeAceStepAudio1.5 node'\''s `tags` and `lyrics` widgets, then hit Queue Prompt.'
echo '   Output audio lands at: <ComfyUI output>/audio/ComfyUI/V0*.mp3 (per SaveAudioMP3).'
