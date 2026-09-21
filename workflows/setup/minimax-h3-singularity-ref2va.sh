#!/bin/bash
# ---
# name: MiniMax H3 Singularity Ref2V (ref2va int8 + latent upscale)
# workflow: Minimax_H3_Singularity_by_Author
# aliases: [minimax-h3-singularity, h3-singularity, h3-singularity-ref2v, minimax-h3-ref2va-singularity, minimax-h3-singularity-ref2va]
# description: Upgrades ComfyUI to >= v0.35.0 (BlockSparseAttention + ModelAttentionBackend "comfy kitchen attention" are new core nodes), installs ComfyUI-KJNodes, ComfyUI-VideoHelperSuite, rgthree-comfy, ComfyUI-Easy-Use and the H3 latent-upscaler pack, then downloads the Singularity ref2va int8 model set (7 files, ~64 GB) and restarts ComfyUI.
# size: ~64GB
# min_vram: 24GB
# nodes: [ComfyUI-KJNodes, ComfyUI-VideoHelperSuite, rgthree-comfy, ComfyUI-Easy-Use, Comfyui_Minimax_h3_latent_Upscaler]
# ---

set -e

# ─── Platform-aware ComfyUI root discovery ───────────────────────────────────
# ⚠️  BASE_DIR is the ComfyUI ROOT (not .../models). The hf_download helper
#     creates the models/<subdir>/ path from the filename prefix, so passing
#     .../models here would double-nest every file.
echo "==> Detecting platform..."
if [ -d "/workspace/runpod-slim/ComfyUI" ]; then
  COMFYUI_DIR="/workspace/runpod-slim/ComfyUI"
  echo "  ✅ RunPod (slim) detected"
elif [ -d "/workspace/ComfyUI" ]; then
  COMFYUI_DIR="/workspace/ComfyUI"
  echo "  ✅ Vast.ai detected"
else
  echo "  ❌ No ComfyUI directory found — aborting"
  exit 1
fi
BASE_DIR="$COMFYUI_DIR"
MODELS_DIR="$COMFYUI_DIR/models"
CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"   # never a double-dollar prefix — see script standards pitfall 16
export COMFYUI_DIR BASE_DIR MODELS_DIR

# ─── Detect the Python interpreter the running ComfyUI uses ──────────────────
detect_comfyui_python() {
  local pid
  pid=$(ps -eo pid,comm,args | awk '$2 ~ /python/ && /main\.py/ && !/tcl/ {print $1; exit}') || true
  if [ -n "${pid:-}" ] && [ -f "/proc/$pid/exe" ]; then
    readlink -f "/proc/$pid/exe" 2>/dev/null && return
  fi
  for p in /venv/main/bin/python /venv/main/bin/python3 \
           "$COMFYUI_DIR/.venv-cu128/bin/python" "$COMFYUI_DIR/venv/bin/python" \
           "$COMFYUI_DIR/.venv/bin/python"; do
    [ -x "$p" ] && { echo "$p"; return; }
  done
  echo "python3"
}
COMFYUI_PYTHON=$(detect_comfyui_python)
COMFYUI_PIP="${COMFYUI_PYTHON%/*}/pip"
[ -x "$COMFYUI_PIP" ] || COMFYUI_PIP="$COMFYUI_PYTHON -m pip"
echo "  Using ComfyUI python: $COMFYUI_PYTHON"

# ─── Phase 0: ComfyUI version floor ──────────────────────────────────────────
# This workflow needs THREE post-v0.30.0 core features:
#   • MiniMaxH3ReferenceToVideo      → v0.30.0+  (comfy_extras/nodes_minimax_h3.py)
#   • ModelAttentionBackend          → v0.32.0+  (comfy_extras/nodes_model_advanced.py)
#   • BlockSparseAttention (sol-attn)→ v0.35.0+  (comfy_extras/nodes_sparse_attention.py)
# The highest floor wins: v0.35.0. Vast's base image ships v0.23.0, so this is
# mandatory. BlockSparseAttention imports `comfy_kitchen`, and ModelAttentionBackend
# only exposes "comfy kitchen attention" when comfy-kitchen's INT8 attention is
# available — both are pinned in ComfyUI's requirements.txt, which we re-install.
REQUIRED_VERSION="v0.35.0"
echo ""
echo "==> Phase 0: ComfyUI version check (need >= $REQUIRED_VERSION)"

ver_ge() { [ "$(printf '%s\n' "$1" "$2" | sort -V | tail -1)" = "$1" ]; }

# Probe order matters: importlib.metadata.version('comfy') prints "unknown" on
# the Vast/RunPod images and would trip the upgrade branch every run.
detect_comfyui_version() {
  local v
  v=$("$COMFYUI_PYTHON" -c "import comfyui_version; print(comfyui_version.__version__)" 2>/dev/null || true)
  if [ -z "$v" ] || [ "$v" = "unknown" ]; then
    v=$(git -C "$COMFYUI_DIR" describe --tags --abbrev=0 2>/dev/null || true)
  fi
  [ -z "$v" ] && v="unknown"
  printf '%s' "$v"
}
CURRENT_VERSION=$(detect_comfyui_version)
echo "  Current: $CURRENT_VERSION"

NODES_INSTALLED=0
if [ "$CURRENT_VERSION" = "unknown" ] || ! ver_ge "$CURRENT_VERSION" "$REQUIRED_VERSION"; then
  echo "  ⚠️  Upgrading ComfyUI (plain 'git stash' only — NEVER --include-untracked,"
  echo "      it would clobber the untracked .venv-cu128/ and leave ComfyUI dead)"
  git -C "$COMFYUI_DIR" stash --quiet 2>/dev/null || true
  git -C "$COMFYUI_DIR" fetch origin --tags --quiet 2>/dev/null || true
  TARGET_TAG=$(git -C "$COMFYUI_DIR" tag --sort=-version:refname | grep -E '^v[0-9]' | head -1 || true)
  if [ -n "$TARGET_TAG" ] && ver_ge "$TARGET_TAG" "$REQUIRED_VERSION"; then
    echo "  Checking out $TARGET_TAG"
    git -C "$COMFYUI_DIR" checkout "$TARGET_TAG" --quiet 2>/dev/null || true
  else
    echo "  No tag >= $REQUIRED_VERSION found — falling back to origin/master"
    git -C "$COMFYUI_DIR" checkout origin/master -- . 2>/dev/null || true
  fi
  if [ -f "$COMFYUI_DIR/requirements.txt" ]; then
    echo "  Installing ComfyUI requirements (brings comfy-kitchen for sparse/kitchen attention)..."
    $COMFYUI_PIP install -q -r "$COMFYUI_DIR/requirements.txt" 2>&1 | tail -3 || true
  fi
  NODES_INSTALLED=$((NODES_INSTALLED + 1))
  echo "  ✅ ComfyUI upgraded"
else
  echo "  ✅ ComfyUI $CURRENT_VERSION already satisfies $REQUIRED_VERSION"
fi

# ─── Phase 1: Custom node packs ──────────────────────────────────────────────
# Workflow node → pack map (every non-core class in the graph):
#   MiniMaxChunkFeedForward                     → ComfyUI-KJNodes
#   MiniMaxLowVRAMAttention (bypassed, mode=4)  → ComfyUI-KJNodes
#   MiniMaxH3MemoryEfficientSageAttentionPatch  → ComfyUI-KJNodes
#   VHS_LoadVideo / VHS_VideoCombine            → ComfyUI-VideoHelperSuite
#   Lora Loader Stack (rgthree)                 → rgthree-comfy
#   easy float                                  → ComfyUI-Easy-Use
#   MinimaxH3LatentUpscaler3D                   → Comfyui_Minimax_h3_latent_Upscaler
#   BlockSparseAttention / ModelAttentionBackend / LTXVConcatAVLatent /
#   LTXVSeparateAVLatent / MiniMaxH3ReferenceToVideo → comfy-core (Phase 0)
echo ""
echo "==> Phase 1: Installing custom node packs..."
mkdir -p "$CUSTOM_NODES_DIR"

install_node() {
  local dir="$1" url="$2"
  if [ -d "$CUSTOM_NODES_DIR/$dir/.git" ]; then
    echo "  ✅ $dir already installed"
  else
    echo "  📥 Installing $dir"
    git clone --depth 1 "$url" "$CUSTOM_NODES_DIR/$dir" >/dev/null 2>&1 || {
      echo "  ⚠️  $dir clone failed — retrying without --depth"
      git clone "$url" "$CUSTOM_NODES_DIR/$dir" || true
    }
    NODES_INSTALLED=$((NODES_INSTALLED + 1))
  fi
  local req="$CUSTOM_NODES_DIR/$dir/requirements.txt"
  if [ -f "$req" ]; then
    echo "    installing $dir deps..."
    $COMFYUI_PIP install -q -r "$req" 2>&1 | tail -3 || true
  fi
}

install_node ComfyUI-KJNodes                      https://github.com/kijai/ComfyUI-KJNodes.git
install_node ComfyUI-VideoHelperSuite             https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
install_node rgthree-comfy                        https://github.com/rgthree/rgthree-comfy.git
install_node ComfyUI-Easy-Use                     https://github.com/yolain/ComfyUI-Easy-Use.git
install_node Comfyui_Minimax_h3_latent_Upscaler   https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler.git

# KJNodes' MiniMaxH3MemoryEfficientSageAttentionPatch needs SageAttention at
# runtime. The PyPI 'latest' (1.0.6) is STALE — KJNodes imports
# `get_cuda_arch_versions()` from sageattention.core, which only exists in
# SageAttention v2 (git tags v2.0.1/v2.2.0; PyPI 1.0.6 lacks it). Without a
# working v2, the node hard-fails at queue time:
#   RuntimeError: sageattention is not new enough version or could not determine
#   CUDA architecture, cannot apply MiniMax H3 Memory Efficient Sage Attention Patch.
# So we install v2.2.0 via the prebuilt Linux wheel (snw35/sageattention-wheel;
# built for cu13/cp312, no compile needed). If the wheel profile doesn't match
# this box, fall back to building v2.0.1 from GitHub (needs --no-build-isolation
# so setup.py sees torch already in the venv; pin TORCH_CUDA_ARCH_LIST to the
# GPU so nvcc doesn't try a wrong/failed arch).
if "$COMFYUI_PYTHON" -c "from sageattention.core import get_cuda_arch_versions" >/dev/null 2>&1; then
  echo "  ✅ sageattention v2 API (get_cuda_arch_versions) present"
else
  echo "  ⚠️  sageattention missing or is stale v1 (PyPI 1.0.6 lacks get_cuda_arch_versions) —"
  echo "      this would break the 'MiniMax H3 Mem Eff Sage Attention Patch' node."
  echo "  📥 Installing SageAttention v2.2.0 prebuilt wheel (cu13/cp312)..."
  WHEEL_URL="https://github.com/snw35/sageattention-wheel/releases/download/cu12-2.2.0-cu13-2.2.0/sageattention-2.2.0%2Bcu13-cp312-cp312-linux_x86_64.whl"
  if ! "$COMFYUI_PIP" install --no-cache-dir "$WHEEL_URL" 2>&1 | tail -3; then
    echo "  ⚠️  Wheel install failed — falling back to building v2.0.1 from GitHub..."
    ARCHS="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d ' .' | sed 's/^/sm/')"
    [ -n "$ARCHS" ] && export TORCH_CUDA_ARCH_LIST="$ARCHS"
    "$COMFYUI_PIP" install --no-cache-dir --no-build-isolation \
      'git+https://github.com/thu-ml/SageAttention.git@v2.0.1' 2>&1 | tail -5
  fi
  if "$COMFYUI_PYTHON" -c "from sageattention.core import get_cuda_arch_versions" >/dev/null 2>&1; then
    echo "  ✅ SageAttention v2 installed with get_cuda_arch_versions"
    NODES_INSTALLED=$((NODES_INSTALLED + 1))
  else
    echo "  ⚠️  Could not install SageAttention v2 — the patch node will fail; you can"
    echo "      bypass it in the UI (it is a VRAM optimisation, not a requirement)."
  fi
fi

# ─── Comfy model compiler fix ──────────────────────────────────────────────
# This ComfyUI build enables a torch.compile "model compiler" (+ CUDA graphs) by
# default. It traces the model with fake/CPU tensors, and the SageAttention
# int8 kernel rejects CPU input:
#   RuntimeError: Tensor query must be on CUDA   (SamplerCustomAdvanced)
# The clean fix is `--disable-comfy-compiler` (it also disables CUDA graphs).
# Vast's template injects COMFYUI_ARGS from /etc/environment which OVERRIDES the
# default in /opt/supervisor-scripts/comfyui.sh, so append the flag to the
# launch line, not the default. Dynamic VRAM is a separate feature and stays on.
# ALL THREE flags are load-bearing on a 24GB card (same set as the sibling
# SemBridge script - keep them in sync):
#   --lowvram                standing rule on 24GB
#   --disable-comfy-compiler torch.compile traces the model with fake/CPU tensors and
#                            the int8 kernel rejects CPU input -> phantom OOM
#   --disable-pinned-memory  PRIMARY OOM FIX. ComfyUI pins ram*0.90 of system RAM and
#                            pinned pages are unswappable AND unreclaimable, so a
#                            cgroup-capped pod fails allocations mid-run.
#                            Ref: growthlabs-docs/comfyui/minimax-h3-local-24gb.md
H3_FLAGS="--lowvram --disable-comfy-compiler --disable-pinned-memory"

# Vast.ai: supervisord-managed; inject every MISSING flag in ONE substitution. A per-flag
# loop silently drops all but the first — its `${COMFYUI_ARGS} 2>&1` anchor is consumed by
# the first sed and `|| true` hides the miss. Replacement text has no `&`/`$`, dodging
# sed's whole-match metachar and shell expansion; range starts at the launch line so the
# `COMFYUI_ARGS=` assignment above it is untouched.
if [ -f /opt/supervisor-scripts/comfyui.sh ]; then
  WRAP=/opt/supervisor-scripts/comfyui.sh
  MISSING=""
  for FLAG in $H3_FLAGS; do
    grep -q -- "$FLAG" "$WRAP" || MISSING="$MISSING $FLAG"
  done
  if [ -z "$MISSING" ]; then
    echo "  ✅ supervisor launch line already has:$H3_FLAGS"
  else
    echo "  📥 Adding missing H3 flags to the supervisor launch line:$MISSING"
    cp "$WRAP" "${WRAP}.bak.$(date +%Y%m%d_%H%M%S)"
    sed -i "/python main\.py/,\$ s#\${COMFYUI_ARGS}#\${COMFYUI_ARGS}${MISSING}#" "$WRAP"
    sed -n '/python main\.py/,+2p' "$WRAP" | sed 's/^/    /'
  fi
fi

# RunPod bare pods: NO supervisor exists, so the block above can never apply. Write a
# launcher carrying the flags; the restart block below prefers it.
LAUNCHER=/root/start_comfyui.sh
if [ ! -f /opt/supervisor-scripts/comfyui.sh ]; then
  LAUNCH_PY="$(command -v "$COMFYUI_PYTHON" 2>/dev/null || command -v python3)"
  if grep -qsE 'main\.py.*--disable-pinned-memory' "$LAUNCHER"; then
    echo "  ✅ $LAUNCHER already carries the H3 flags"
  else
    echo "  📥 Writing RunPod launcher $LAUNCHER with H3 memory flags..."
    cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/bin/bash
cd $COMFYUI_DIR
exec $LAUNCH_PY main.py --listen 0.0.0.0 --port 8188 --enable-cors-header $H3_FLAGS
LAUNCHER_EOF
    chmod +x "$LAUNCHER"
  fi
fi

# ─── Phase 2: Models ─────────────────────────────────────────────────────────
echo ""
echo "==> Phase 2: Downloading models..."
mkdir -p "$MODELS_DIR"/{diffusion_models,text_encoders,vae,loras,latent_upscale_models}

# Load the shared HF helper (self-fetch if the image doesn't ship it)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_HF_HELPER=""
for f in "$SCRIPT_DIR/_hf_download.sh" "$BASE_DIR/_hf_download.sh" /tmp/_hf_download.sh; do
  [ -f "$f" ] && _HF_HELPER="$f" && break
done
if [ -z "$_HF_HELPER" ]; then
  echo "  Fetching _hf_download.sh from GitHub..."
  _HF_HELPER="/tmp/_hf_download.sh"
  curl -sSL --fail "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/workflows/setup/_hf_download.sh" -o "$_HF_HELPER" \
    || { echo "  ❌ FATAL: could not fetch _hf_download.sh"; exit 1; }
  chmod +x "$_HF_HELPER"
fi
source "$_HF_HELPER"

# Pre-flight: every repo below is public + ungated. Fail loudly on the first one
# rather than dying halfway through a 64 GB run (see script-standards sub-rule a).
for repo in WarmBloodAban/Minimax-h3_Singularity Comfy-Org/MiniMax-H3 \
            GuangyuanSD/minimax_h3_video_vae_int8_convrot lightx2v/Minimax-h3-Turbo \
            Alissonerdx/Minimax-H3-ComfyUI LBH-123-AI/Minimax_h3_latent_Upscaler; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
    "https://huggingface.co/api/models/$repo" || echo 000)
  if [ "$code" != "200" ]; then
    echo "  ⚠️  Pre-flight: $repo returned HTTP $code (expected 200)"
    echo "      If this is 401/403 the repo is gated — accept its licence on HF first."
  fi
done

TOTAL=7
STEP=0
step() { STEP=$((STEP + 1)); echo "[$STEP/$TOTAL] $1"; }

# 1. Diffusion model — Singularity ref2va v1.3 INT8 (note: the NON-pruned v1.3
#    variant; the sibling SemBridge script downloads the Pruned one, not this).
# Filename must be the ref2vA variant: the repo has no "ref2v" file, and this
# script's OWN verification block below expects "...ref2va_v1.3_int8.safetensors".
# (The download line said ref2v and would have 404'd on a 31.7GB pull.)
step "Minimax-h3_Singularity_ref2va_v1.3_int8.safetensors (diffusion model, ~31.7GB)"
hf_download "WarmBloodAban/Minimax-h3_Singularity" \
  "Minimax-h3_Singularity_ref2va_v1.3_int8.safetensors" "$MODELS_DIR/diffusion_models"

# 2. Text encoder (filename carries a text_encoders/ prefix → local_dir=$MODELS_DIR)
step "qwen3vl_32b_minimax_h3_int8_convrot.safetensors (text encoder, ~25.3GB)"
hf_download "Comfy-Org/MiniMax-H3" \
  "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" "$MODELS_DIR"

# 3. Video VAE — INT8 ConvRot variant (3.2GB), NOT the fp16 one from Comfy-Org
step "minimax_h3_video_vae_int8_convrot.safetensors (video VAE, ~3.0GB)"
hf_download "GuangyuanSD/minimax_h3_video_vae_int8_convrot" \
  "minimax_h3_video_vae_int8_convrot.safetensors" "$MODELS_DIR/vae"

# 4. Audio VAE (prefix form)
step "minimax_h3_audio_vae_fp32.safetensors (audio VAE, ~0.6GB)"
hf_download "Comfy-Org/MiniMax-H3" \
  "vae/minimax_h3_audio_vae_fp32.safetensors" "$MODELS_DIR"

# 5. LoRA — ref2v turbo 4-step v0.1 (rgthree Lora Loader Stack)
step "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors (turbo LoRA, ~1.8GB)"
hf_download "lightx2v/Minimax-h3-Turbo" \
  "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors" "$MODELS_DIR/loras"

# 6. LoRA — LMS v1.0 r64 sharpener (LoraLoaderModelOnly, strength 0.3)
step "minimax_h3_lms_v1.0_r64.safetensors (LMS LoRA r64, ~1.2GB)"
hf_download "Alissonerdx/Minimax-H3-ComfyUI" \
  "loras/minimax_h3_lms_v1.0_r64.safetensors" "$MODELS_DIR"

# 7. Latent upscaler 3D (bf16 — the workflow names the bf16 file, not fp16)
# NOTE: LBH-123-AI/Minimax_h3_latent_Upscaler reshuffled its weights into a
# `minimax_h3_latent_upscaler_3d_conv_v1/` subdir (2026-09) - the same reshuffle the
# sibling SemBridge script already handles for the fp16 variant. The bare filename
# 404s. Download the nested file, then flatten it to the exact name this script's
# verification block (and the workflow) expects.
step "minimax_h3_latent_upscaler_3d_bf16.safetensors (latent upscaler, ~0.6GB, nested repo)"
UP_SRC="minimax_h3_latent_upscaler_3d_conv_v1/minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors"
UP_TGT="$MODELS_DIR/latent_upscale_models/minimax_h3_latent_upscaler_3d_bf16.safetensors"
if [ -s "$UP_TGT" ]; then
  echo "  ✅ already present: $UP_TGT"
else
  hf_download "LBH-123-AI/Minimax_h3_latent_Upscaler" "$UP_SRC" "$MODELS_DIR/latent_upscale_models" || true
  if [ -s "$MODELS_DIR/latent_upscale_models/$UP_SRC" ]; then
    mv "$MODELS_DIR/latent_upscale_models/$UP_SRC" "$UP_TGT"
    echo "  ✅ flattened to $UP_TGT"
  fi
fi

echo "  ✅ All $TOTAL files downloaded"

# ─── Phase 3: Restart + verify ───────────────────────────────────────────────
echo ""
echo "==> Phase 3: Restarting ComfyUI..."
COMFYUI_ARGS=$(ps aux | grep '[p]ython.*main\.py' | head -1 | sed 's/.*main\.py//') || true
[ -z "${COMFYUI_ARGS:-}" ] && COMFYUI_ARGS="--listen 0.0.0.0 --port 8188 --enable-cors-header"
COMFYUI_PORT=$(echo "$COMFYUI_ARGS" | grep -oE -- '--port [0-9]+' | awk '{print $2}' | head -1)
[ -z "$COMFYUI_PORT" ] && COMFYUI_PORT=8188

comfyui_alive() {
  curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
    "http://127.0.0.1:$COMFYUI_PORT/system_stats" 2>/dev/null | grep -q 200
}

# Restart if we installed/upgraded anything OR ComfyUI is simply not alive.
if [ "$NODES_INSTALLED" -gt 0 ] || ! comfyui_alive; then
  if command -v supervisorctl >/dev/null 2>&1 && supervisorctl status comfyui >/dev/null 2>&1; then
    supervisorctl restart comfyui || true
  else
    PID=$(ps -eo pid,comm,args | awk '$2 ~ /python/ && /main\.py/ && !/tcl/ {print $1; exit}') || true
    [ -n "${PID:-}" ] && kill "$PID" 2>/dev/null || true
    sleep 4
    PID2=$(ps -eo pid,comm,args | awk '$2 ~ /python/ && /main\.py/ && !/tcl/ {print $1}') || true
    [ -n "${PID2:-}" ] && kill -9 "$PID2" 2>/dev/null || true
    # `nohup ... &` does NOT survive SSH session end (documented pitfall); tmux does.
    # COMFYUI_ARGS was captured from the live process above, so the H3 flags survive.
    if command -v tmux >/dev/null 2>&1; then
      tmux kill-session -t comfyui 2>/dev/null || true
      sleep 1
      tmux new-session -d -s comfyui \
        "cd '$COMFYUI_DIR' && exec '$COMFYUI_PYTHON' main.py $COMFYUI_ARGS > /workspace/comfyui.log 2>&1"
    else
      (cd "$COMFYUI_DIR" && nohup "$COMFYUI_PYTHON" main.py $COMFYUI_ARGS > "$COMFYUI_DIR/comfyui.log" 2>&1 &)
    fi
  fi
  for _ in $(seq 1 60); do
    if comfyui_alive; then echo "  ✅ ComfyUI ready on port $COMFYUI_PORT"; break; fi
    sleep 2
  done
else
  echo "  ✅ ComfyUI already running (no restart needed)"
fi

echo ""
echo "==> Verifying model files via the ComfyUI API (not just ls)..."
for pair in "diffusion_models:Minimax-h3_Singularity_ref2va_v1.3_int8.safetensors" \
            "text_encoders:qwen3vl_32b_minimax_h3_int8_convrot.safetensors" \
            "vae:minimax_h3_video_vae_int8_convrot.safetensors" \
            "vae:minimax_h3_audio_vae_fp32.safetensors" \
            "loras:minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors" \
            "loras:minimax_h3_lms_v1.0_r64.safetensors" \
            "latent_upscale_models:minimax_h3_latent_upscaler_3d_bf16.safetensors"; do
  sub="${pair%%:*}"; file="${pair#*:}"
  if [ -f "$MODELS_DIR/$sub/$file" ]; then
    echo "  ✅ $sub/$file"
  else
    echo "  ❌ MISSING on disk: $MODELS_DIR/$sub/$file"
  fi
done

echo ""
echo "==> Verifying required node classes are registered..."
curl -s --max-time 15 "http://127.0.0.1:$COMFYUI_PORT/object_info" | "$COMFYUI_PYTHON" - <<'PYEOF' || echo "  ⚠️  Could not read /object_info (ComfyUI may still be starting)"
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("  ⚠️  /object_info not parseable yet — re-check the UI in a minute")
    sys.exit(0)
expected = [
    # core (Phase 0)
    "MiniMaxH3ReferenceToVideo", "BlockSparseAttention", "ModelAttentionBackend",
    "LTXVConcatAVLatent", "LTXVSeparateAVLatent", "MiniMaxH3SigmaShift",
    # custom packs (Phase 1)
    "MiniMaxChunkFeedForward", "MiniMaxH3MemoryEfficientSageAttentionPatch",
    "VHS_LoadVideo", "VHS_VideoCombine", "Lora Loader Stack (rgthree)",
    "easy float", "MinimaxH3LatentUpscaler3D",
]
missing = [c for c in expected if c not in d]
if missing:
    print(f"  ❌ MISSING NODE CLASSES: {missing}")
else:
    print(f"  ✅ All {len(expected)} required node classes registered ({len(d)} total)")

# Silent-option check: the workflow requests "comfy kitchen attention"
if "ModelAttentionBackend" in d:
    opts = d["ModelAttentionBackend"].get("input", {}).get("required", {}).get("attention", [[]])[0]
    opts = [o[0] if isinstance(o, list) else o for o in opts]
    if "comfy kitchen attention" not in opts:
        print(f"  ⚠️  'comfy kitchen attention' NOT available (options: {opts}).")
        print("      The workflow's ModelAttentionBackend falls back to an invalid value —")
        print("      re-pick 'pytorch attention' in that node, or upgrade comfy-kitchen.")
PYEOF

echo ""
echo "🎉 MiniMax H3 Singularity setup complete."
echo ""
echo "👉 Next: load workflows/comfyui/Minimax_H3_Singularity_by_Author.fixed.json in the ComfyUI UI."
echo "👉 This workflow is REFERENCE-DRIVEN — upload your inputs to $COMFYUI_DIR/input/ :"
echo "     • up to 9 reference images  (LoadImage nodes, currently empty pickers)"
echo "     • up to 3 reference videos  (VHS_LoadVideo nodes)"
echo "     • up to 3 reference audios  (LoadAudio nodes)"
echo "   Then re-select each file in its loader node; the pickers ship empty on purpose."
echo "⚠️  The 3 '忽略多组孤海' nodes are a third-party frontend-only widget (no inputs,"
echo "    no outputs, no links). They will show as a red 'missing node type' box but they"
echo "    never execute — the graph runs fine without that extension."
