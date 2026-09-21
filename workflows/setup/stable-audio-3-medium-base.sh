#!/bin/bash
# ---
# name: Stable Audio 3 Medium Base (Text-to-Audio)
# workflow: Stable_Audio_3.0_Medium_Base_workflow_in_ComfyUI_Text-to-Audio
# aliases: [stable-audio-3, stable-audio, sa3, sa3-medium-base, t2a-stable-audio-3]
# description: Self-contained provisioning script for ComfyUI's Stable Audio 3 Medium Base text-to-audio workflow. Installs no custom node packs (100% comfy-core), downloads the Stable Audio 3 Medium Base checkpoint + Qwen3.5 2B text encoder + T5Gemma text encoder from Comfy-Org HF repos, and restarts ComfyUI. Subgraph inputs: user_input, duration, seed, use_reprompt, category (Music/Instrument/SFX/One-shot), ckpt_name, sa_clip, qwen_clip → output AUDIO.
# size: ~14.9GB
# min_vram: 12GB
# nodes: []                ← workflow uses only comfy-core nodes, no custom packs required
# node_patches: []
# notes: |
#   - Subgraph workflow: 1 UUID-typed container + 4 top-level nodes (MarkdownNote x2, SaveAudioMP3, subgraph).
#   - All loaders live inside definitions.subgraphs[0].nodes[] (Audio Generation (Stable Audio 3 Medium Base), 21 nodes).
#   - Custom-node detection: every node's properties.cnr_id is "comfy-core" — zero third-party packs.
#   - Core version floor: v0.22.0 (verified — nodes_textgen.py TextGenerate, nodes_logic.py CustomComboNode,
#     nodes_math.py MathExpressionNode, nodes_string.py JsonExtractString/StringReplace, nodes_preview_any.py,
#     nodes_primitive.py, nodes_audio.py SaveAudioMP3, comfy/text_encoders/sa3.py + qwen35.py, comfy/sd.py STABLE_AUDIO
#     all present at tag v0.22.0). Vast base image ships v0.23.0 → no upgrade needed.
#   - Model paths: Comfy-Org repos store files under real ComfyUI subdirs (checkpoints/, text_encoders/) —
#     NO split_files/ prefix, so hf_hub_download(local_dir=$BASE_DIR/models) lands them correctly with no move step.
#   - Repo stabilityai/stable-audio-3-medium is GATED — not used. All 3 Comfy-Org URLs verified HTTP 200.
# ---
set -e

# ─── Platform-aware base directory detection (Vast.ai vs RunPod) ───
# NOTE: BASE_DIR here is the ComfyUI *models* dir (NOT the ComfyUI root). It is correct for this
# workflow because the Comfy-Org files use real subdir prefixes (checkpoints/, text_encoders/):
# hf_hub_download(local_dir=<models>, filename="checkpoints/<f>") → <models>/checkpoints/<f>.
# If this workflow ever moves to a repo that stores blobs under split_files/, switch to the
# ace-step-15-t2a-song.sh pattern (BASE_DIR=ComfyUI root + explicit mv) to avoid double-nesting.
if [ -d "/workspace/runpod-slim/ComfyUI" ]; then
  COMFYUI_DIR="/workspace/runpod-slim/ComfyUI"
  echo "  Platform: RunPod (base: $COMFYUI_DIR)"
elif [ -d "/workspace/ComfyUI" ]; then
  COMFYUI_DIR="/workspace/ComfyUI"
  echo "  Platform: Vast.ai (base: $COMFYUI_DIR)"
else
  COMFYUI_DIR="/workspace/ComfyUI"
  echo "  ⚠️  No ComfyUI dir found, defaulting to $COMFYUI_DIR"
fi
BASE_DIR="$COMFYUI_DIR/models"
CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"

echo "==> Setting up ComfyUI nodes..."
cd "$COMFYUI_DIR"

# ─── ComfyUI Python detection ───
# COMFY_PIP is always "$COMFY_PYTHON -m pip" — RunPod slim venvs ship no bare `pip` symlink (Bug 10).
COMFY_PYTHON=""
if [ -f /venv/main/bin/python3 ]; then
    COMFY_PYTHON="/venv/main/bin/python3"
elif [ -f venv/bin/activate ]; then
    source venv/bin/activate
    COMFY_PYTHON="$(which python3)"
elif [ -f .venv-cu128/bin/activate ]; then
    source .venv-cu128/bin/activate
    COMFY_PYTHON="$(which python3)"
else
    COMFY_PYTHON="$(which python3)"
fi
COMFY_PIP="$COMFY_PYTHON -m pip"
echo "  Using ComfyUI Python: $COMFY_PYTHON"

ver_ge() { [[ "$(printf '%s\n' "$1" "$2" | sort -V | tail -1)" == "$1" ]]; }

# ─── Phase 0: comfy-core version floor (v0.22.0) ───
# This workflow is 100% comfy-core, but its nodes/support are relatively new. Below v0.22.0 the
# frontend shows missing node types (TextGenerate, CustomCombo, JsonExtractString, ...) and the
# Stable Audio 3 CLIP/VAE support is absent. Base image v0.23.0 already satisfies this.
REQUIRED_VERSION=v0.22.0
CURRENT_VERSION="$($COMFY_PYTHON -c 'import comfyui_version; print(comfyui_version.__version__)' 2>/dev/null || echo unknown)"
echo "==> Phase 0: ComfyUI version=$CURRENT_VERSION; required>=$REQUIRED_VERSION"
if [ "$CURRENT_VERSION" == "unknown" ]; then
    echo "  ⚠️  Could not detect ComfyUI version — continuing without upgrade."
    echo "      If the workflow shows missing nodes, run: git -C $COMFYUI_DIR checkout <latest tag>"
elif ! ver_ge "$CURRENT_VERSION" "$REQUIRED_VERSION"; then
    echo "  Upgrading ComfyUI to the latest tag (Stable Audio 3 needs >= $REQUIRED_VERSION)"
    git -C "$COMFYUI_DIR" stash --quiet || true
    git -C "$COMFYUI_DIR" fetch origin --tags --quiet
    latest_tag=$(git -C "$COMFYUI_DIR" tag --sort=-version:refname | grep -E '^v[0-9]' | head -1 || true)
    if [ -n "$latest_tag" ]; then
        git -C "$COMFYUI_DIR" checkout --quiet "$latest_tag"
    else
        git -C "$COMFYUI_DIR" checkout --quiet origin/master
    fi
    [ -f "$COMFYUI_DIR/requirements.txt" ] && $COMFY_PIP install -q -r "$COMFYUI_DIR/requirements.txt" || true
else
    echo "  ✅ ComfyUI version OK — no upgrade needed"
fi

# ─── Custom node install ───
# Stable Audio 3 text-to-audio workflow uses ONLY comfy-core nodes (cnr_id=comfy-core on every
# non-container node). No third-party custom node packs required — no git clone, no comfy-cli,
# no per-pack requirements.txt.

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

# [1/3] Stable Audio 3 Medium Base checkpoint (9.2GB) — CheckpointLoaderSimple
echo "[1/3] Stable Audio 3 Medium Base checkpoint (CheckpointLoaderSimple)..."
hf_download "Comfy-Org/stable-audio-3" "checkpoints/stable_audio_3_medium_base.safetensors" "$BASE_DIR"

# [2/3] Qwen3.5 2B text encoder (4.5GB) — CLIPLoader, feeds the TextGenerate reprompt path (qwen_clip)
echo "[2/3] Qwen3.5 2B text encoder (qwen_clip)..."
hf_download "Comfy-Org/Qwen3.5" "text_encoders/qwen3.5_2b_bf16.safetensors" "$BASE_DIR"

# [3/3] T5Gemma text encoder (1.2GB) — CLIPLoader type=stable_audio, Stable Audio conditioning (sa_clip)
echo "[3/3] T5Gemma B-B UL2 text encoder (sa_clip)..."
hf_download "Comfy-Org/stable-audio-3" "text_encoders/t5gemma_b_b_ul2.safetensors" "$BASE_DIR"

echo "==> All downloads completed!"

# ─── Restart ComfyUI so new nodes + models are picked up ───
# Mandatory: a zero-node-pack workflow still needs this so ComfyUI re-scans models and the
# frontend picks up the (possibly upgraded) core node set. See workflow-researcher Bug 18.
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
    # RunPod images pre-start ComfyUI via the entrypoint → a printed hint never gets acted on
    # and the script exits 0 with stale state (Bug 16b). Do the full tmux restart here.
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
echo "👉 ComfyUI should now be loading the new models. Open the workflow, edit the"
echo '   Prompt Text (PrimitiveStringMultiline) node and the duration / use_reprompt /'
echo '   reprompt_category widgets on the subgraph, then hit Queue Prompt.'
echo '   Output audio lands at: <ComfyUI>/output/audio/stable_audio_3/V0*.mp3 (per SaveAudioMP3).'
echo "   If nodes show up as missing, hard-refresh the browser tab (Ctrl+Shift+R)."
