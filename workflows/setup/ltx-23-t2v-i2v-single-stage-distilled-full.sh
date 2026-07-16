#!/bin/bash
# ---
# name: LTX 2.3 T2V/I2V Single-Stage Distilled + Full
# workflow: LTX-2.3_T2V_I2V_Single_Stage_Distilled_Full
# aliases: [ltx-23-single-stage, ltx-23-distilled-full, ltx23 t2v i2v single stage, ltx 2.3 distilled full]
# description: Downloads all models for the LTX 2.3 Single-Stage Distilled + Full dual-pass workflow (T2V & I2V with audio). Uses full bf16 dev checkpoint + distilled LoRA 384 rank 1.1 + Gemma 3 12B BF16 text encoder.
# size: ~78GB
# min_vram: 24GB
# nodes: [ComfyUI-LTXVideo, ComfyUI-KJNodes, RES4LYF]
# ---
set -e

# ─── Platform-aware base directory detection (Vast.ai vs RunPod) ───
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
if [ -f /venv/main/bin/python3 ]; then
    COMFY_PYTHON="/venv/main/bin/python3"
elif [ -f venv/bin/python3 ]; then
    COMFY_PYTHON="$(pwd)/venv/bin/python3"
elif [ -f .venv-cu128/bin/python3 ]; then
    COMFY_PYTHON="$(pwd)/.venv-cu128/bin/python3"
else
    COMFY_PYTHON="$(which python3)"
fi
COMFY_PIP="$COMFY_PYTHON -m pip"
echo "  Using ComfyUI Python: $COMFY_PYTHON"

# ─── Custom node install (comfy-cli first, manual fallback) ───
echo "==> Installing custom node packs..."
if command -v comfy &> /dev/null; then
    echo "  Using comfy-cli to install nodes..."
    comfy node install https://github.com/Lightricks/ComfyUI-LTXVideo || true
    comfy node install https://github.com/kijai/ComfyUI-KJNodes || true
    comfy node install https://github.com/ClownsharkBatwing/RES4LYF || true
else
    echo "  comfy-cli not found, cloning node repositories manually..."
    mkdir -p "$CUSTOM_NODES_DIR"
    cd "$CUSTOM_NODES_DIR"
    [ -d ComfyUI-LTXVideo ] || git clone https://github.com/Lightricks/ComfyUI-LTXVideo || true
    [ -d ComfyUI-KJNodes ]  || git clone https://github.com/kijai/ComfyUI-KJNodes  || true
    [ -d RES4LYF ]          || git clone https://github.com/ClownsharkBatwing/RES4LYF || true
    cd "$COMFYUI_DIR"
fi

# ─── Pip deps for each pack into ComfyUI's Python ───
echo "==> Installing node dependencies..."
for repo in ComfyUI-LTXVideo ComfyUI-KJNodes RES4LYF; do
    REQ="$CUSTOM_NODES_DIR/$repo/requirements.txt"
    if [ -f "$REQ" ]; then
        echo "  Installing $repo deps..."
        $COMFY_PIP install -q -r "$REQ" 2>&1 | tail -3 || true
    fi
done

# ─── kornia version pin ───
# RES4LYF's deps upgrade kornia to 0.8+ which removes `pad` from
# `kornia.geometry.transform.pyramid`, breaking ComfyUI-LTXVideo's
# `pyramid_blending.py` import with ImportError. Pin to 0.7.3
# in BOTH the venv AND system Python (RunPod slim venvs use
# --system-site-packages, so kornia 0.8 from /usr/local wins).
echo "==> Pinning kornia to 0.7.3 (RES4LYF deps break LTXVideo otherwise)..."
$COMFY_PYTHON -m pip install -q "kornia==0.7.3" 2>&1 | tail -2 || true
/usr/bin/python3 -m pip install -q "kornia==0.7.3" 2>&1 | tail -2 || true

# ─── Model directory creation ───
echo "==> Creating directories..."
mkdir -p "$BASE_DIR/models/checkpoints"
mkdir -p "$BASE_DIR/models/text_encoders"
mkdir -p "$BASE_DIR/models/loras"

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

echo "==> Starting downloads..."

# [1/3] THE BRAIN — Full bf16 dev checkpoint (46.1GB)
# Used by: CheckpointLoaderSimple → MODEL + CLIP + VAE
# Also used by: LTXVAudioVAELoader (audio VAE extracted from checkpoint)
echo "[1/3] Transformer checkpoint (full bf16, 46.1GB)..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-22b-dev.safetensors" "$BASE_DIR/models/checkpoints"

# [2/3] THE TEXT BRAIN — Gemma 3 12B IT BF16 (24.4GB)
# Used by: LTXAVTextEncoderLoader → CLIP for text encoding
# The workflow references "comfy_gemma_3_12B_it.safetensors" but the HF file
# is "gemma_3_12B_it.safetensors" from Comfy-Org/ltx-2. Download then rename.
echo "[2/3] Text encoder Gemma 3 12B BF16 (24.4GB)..."
TE_BLOB="split_files/text_encoders/gemma_3_12B_it.safetensors"
TE_FINAL="$BASE_DIR/models/text_encoders/comfy_gemma_3_12B_it.safetensors"
mkdir -p "$BASE_DIR/models/text_encoders"
hf_download "Comfy-Org/ltx-2" "$TE_BLOB" "$BASE_DIR"
# Handle double-nest: hf_download may create $BASE_DIR/split_files/text_encoders/<file>
if [ -f "$BASE_DIR/$TE_BLOB" ] && [ "$BASE_DIR/$TE_BLOB" != "$TE_FINAL" ]; then
  mv "$BASE_DIR/$TE_BLOB" "$TE_FINAL"
  rmdir "$BASE_DIR/split_files/text_encoders" 2>/dev/null || true
  rmdir "$BASE_DIR/split_files" 2>/dev/null || true
  echo "  ✅ Moved + renamed to $TE_FINAL"
elif [ -f "$BASE_DIR/models/text_encoders/gemma_3_12B_it.safetensors" ]; then
  # Already in the right place, just rename
  mv "$BASE_DIR/models/text_encoders/gemma_3_12B_it.safetensors" "$TE_FINAL"
  echo "  ✅ Renamed to $TE_FINAL"
fi

# [3/3] THE DISTILLATION — Distilled LoRA 384-rank v1.1 (7.6GB)
# Used by: LoraLoaderModelOnly (applied at strengths 0.5 and 0.2)
echo "[3/3] Distilled LoRA 384-rank v1.1 (7.6GB)..."
hf_download "Lightricks/LTX-2.3" "ltx-2.3-22b-distilled-lora-384-1.1.safetensors" "$BASE_DIR/models/loras"

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
echo "👉 ComfyUI should now be loading the new nodes and models."
echo ""
echo "📋 Workflow summary:"
echo "   Model: ltx-2.3-22b-dev.safetensors (full bf16, 46.1GB)"
echo "   LoRA:  ltx-2.3-22b-distilled-lora-384-1.1.safetensors (7.6GB)"
echo "   Text:  comfy_gemma_3_12B_it.safetensors (24.4GB)"
echo "   Nodes: ComfyUI-LTXVideo + ComfyUI-KJNodes"
echo ""
echo "💡 T2V: Set bypass_i2v=True (default)"
echo "💡 I2V: Set bypass_i2v=False + load an input image"
