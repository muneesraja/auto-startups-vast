#!/bin/bash
# ---
# name: MiniMax H3 I2V 2-Stage Latent Upscale (Singularity + Semantic Bridge)
# workflow: minimax-h3-i2v-2stage-latent-upscale-Singularity-Semantic_Bridge
# aliases: [minimax-h3-i2v, h3-i2v-2stage, h3-latent-upscale, minimax-h3-i2v-singularity, minimax-h3-i2v-singularity-semantic-bridge]
# description: MiniMax H3 image-to-video with 2-stage sampling, sigma split, latent upscaling; Singularity ref2va pruned base + Semantic Bridge (FL2VA/text-conditioning adapter)
# size: ~71GB + taeh3
# min_vram: 24GB
# nodes: [comfyui-kjnodes, comfyui-minimax-h3-audio-T8, Comfyui_Minimax_h3_latent_Upscaler, ComfyUI-VideoHelperSuite, MiniMax_H3_Semantic_Bridge]
# ---

set -e

# ── Platform Detection ──
echo "==> Detecting platform..."
if [ -d "/workspace/runpod" ]; then
    PLATFORM="runpod"
    COMFYUI_DIR="/workspace/ComfyUI"
    echo "  ✅ RunPod detected"
elif [ -d "/workspace/runpod-slim" ]; then
    PLATFORM="runpod"
    COMFYUI_DIR="/workspace/runpod-slim/ComfyUI"
    echo "  ✅ RunPod (slim) detected"
elif [ -d "/workspace/ComfyUI" ]; then
    PLATFORM="vast"
    COMFYUI_DIR="/workspace/ComfyUI"
    echo "  ✅ Vast.ai detected"
else
    echo "❌ Unknown platform - ComfyUI directory not found"
    exit 1
fi

BASE_DIR="$COMFYUI_DIR/models"
CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"

# ── Phase 0: Check ComfyUI version (H3 needs v0.30.0+) ──
echo "==> Phase 0: Checking ComfyUI version..."
# Use git describe first — importlib.metadata.version('comfy') prints "unknown"
# (PackageNotFoundError) even at v0.30.0 on some images, which spuriously trips
# the upgrade branch and git-checkouts a newer master over a running instance.
CURRENT_VERSION=$(git -C "$COMFYUI_DIR" describe --tags 2>/dev/null | sed 's/^v//')
if [ -z "$CURRENT_VERSION" ]; then
    CURRENT_VERSION=$(python3 -c "import importlib.metadata; print(importlib.metadata.version('comfy'))" 2>/dev/null || echo "unknown")
fi
echo "  Current ComfyUI version: $CURRENT_VERSION"

if [[ "$CURRENT_VERSION" == "unknown" ]] || [[ "$(printf '%s\n' "0.30.0" "$CURRENT_VERSION" | sort -V | head -n1)" != "0.30.0" ]]; then
    echo "  ⚠️  ComfyUI < v0.30.0 detected (or unknown) — upgrading to master..."
    cd "$COMFYUI_DIR"
    git fetch origin master --depth=1 2>/dev/null || git fetch origin main --depth=1 2>/dev/null
    git stash 2>/dev/null || true
    git checkout origin/master -- . 2>/dev/null || git checkout origin/main -- . 2>/dev/null
    echo "  ✅ ComfyUI upgraded to master"
else
    echo "  ✅ ComfyUI $CURRENT_VERSION >= v0.30.0 — no upgrade needed"
fi

# ── Detect ComfyUI Python ──
echo "==> Detecting ComfyUI Python..."
if [ -f "/venv/main/bin/python" ]; then
    COMFY_PYTHON="/venv/main/bin/python"
    COMFY_PIP="/venv/main/bin/pip"
    echo "  ✅ Found /venv/main/bin/python"
elif [ -f "$COMFYUI_DIR/venv/bin/activate" ]; then
    source "$COMFYUI_DIR/venv/bin/activate"
    COMFY_PYTHON="python"
    COMFY_PIP="pip"
    echo "  ✅ Found $COMFYUI_DIR/venv"
elif [ -f "$COMFYUI_DIR/.venv-cu128/bin/activate" ]; then
    source "$COMFYUI_DIR/.venv-cu128/bin/activate"
    COMFY_PYTHON="python"
    COMFY_PIP="pip"
    echo "  ✅ Found $COMFYUI_DIR/.venv-cu128"
else
    COMFY_PYTHON="python3"
    COMFY_PIP="pip3"
    echo "  ⚠️  Using system Python"
fi

# ── Phase 1: Install Custom Nodes ──
echo "==> Phase 1: Installing custom node packs..."
cd "$COMFYUI_DIR"

if command -v comfy >/dev/null 2>&1; then
    echo "  Using comfy-cli..."
    comfy node install https://github.com/kijai/ComfyUI-KJNodes 2>/dev/null || true
    comfy node install https://github.com/T8mars/comfyui-minimax-h3-audio-T8 2>/dev/null || true
    comfy node install https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler 2>/dev/null || true
    comfy node install https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite 2>/dev/null || true
    echo "  ✅ comfy-cli done"
else
    echo "  comfy-cli not found, cloning manually..."
    cd "$CUSTOM_NODES_DIR"
    [ -d ComfyUI-KJNodes ] || git clone --depth=1 https://github.com/kijai/ComfyUI-KJNodes || true
    [ -d comfyui-minimax-h3-audio-T8 ] || git clone --depth=1 https://github.com/T8mars/comfyui-minimax-h3-audio-T8 || true
    [ -d Comfyui_Minimax_h3_latent_Upscaler ] || git clone --depth=1 https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler || true
    [ -d ComfyUI-VideoHelperSuite ] || git clone --depth=1 https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite || true
    cd "$COMFYUI_DIR"
fi

# ── Install node dependencies ──
echo "==> Installing node dependencies..."
for repo in ComfyUI-KJNodes comfyui-minimax-h3-audio-T8 Comfyui_Minimax_h3_latent_Upscaler ComfyUI-VideoHelperSuite; do
    REQ="$CUSTOM_NODES_DIR/$repo/requirements.txt"
    if [ -f "$REQ" ]; then
        echo "  Installing $repo deps..."
        $COMFY_PIP install -q -r "$REQ" 2>&1 | tail -5 || true
    fi
done

# ── SageAttention v2 (fixes MiniMaxH3MemoryEfficientSageAttentionPatch) ──
# KJNodes' H3 patch imports `get_cuda_arch_versions` from sageattention.core,
# which only exists in SageAttention v2 (v2.0.1/v2.2.0). PyPI 'latest' is 1.0.6
# and lacks it — the node hard-fails at queue time with "sageattention is not
# new enough version or could not determine CUDA architecture".
#
# ⚠️ The prebuilt wheel MUST match the pod's torch CUDA major. The snw35 release
# tag `cu12-2.2.0-cu13-2.2.0` hosts BOTH the `+cu12` and `+cu13` assets under one
# tag. Picking the wrong one installs cleanly, then dies at import with
# "libcudart.so.13: cannot open shared object file" on a cu128 pod (observed).
# So select the wheel from torch.version.cuda — never hardcode.
#
# A prebuilt wheel can ALSO fail on a torch ABI mismatch with the pod's exact
# torch build (observed: "undefined symbol ..._ZNK3c1010TensorImpl15decref_pyobjectEv"
# on torch 2.8.0+cu128). That is why the compile-from-source fallback has to be
# reachable: do NOT pipe the wheel install straight into `tail`, or the status
# you test is tail's (always 0) and the fallback silently never fires.
if $COMFY_PYTHON -c "from sageattention.core import get_cuda_arch_versions" >/dev/null 2>&1; then
    echo "  ✅ sageattention v2 API (get_cuda_arch_versions) present"
else
    echo "  ⚠️  sageattention missing or stale v1 (lacks get_cuda_arch_versions) — installing v2.2.0..."
    CUDA_MAJOR="$($COMFY_PYTHON -c 'import torch;print((torch.version.cuda or "12.0").split(".")[0])' 2>/dev/null || echo 12)"
    PY_TAG="$($COMFY_PYTHON -c 'import sys;print("cp%d%d" % sys.version_info[:2])' 2>/dev/null || echo cp312)"
    WHEEL_URL="https://github.com/snw35/sageattention-wheel/releases/download/cu12-2.2.0-cu13-2.2.0/sageattention-2.2.0%2Bcu${CUDA_MAJOR}-${PY_TAG}-${PY_TAG}-linux_x86_64.whl"
    echo "  torch is CUDA ${CUDA_MAJOR} → $(basename "$WHEEL_URL")"
    WHEEL_OK=1
    $COMFY_PIP install --no-cache-dir "$WHEEL_URL" > /tmp/sage_wheel.log 2>&1 || WHEEL_OK=0
    tail -3 /tmp/sage_wheel.log 2>/dev/null || true
    # An install can exit 0 and still be unimportable (wrong CUDA major, or a torch
    # ABI mismatch). Verify the IMPORT, never the pip exit code.
    if [ "$WHEEL_OK" = "1" ] && \
       $COMFY_PYTHON -c "from sageattention.core import get_cuda_arch_versions" >/dev/null 2>&1; then
        echo "  ✅ SageAttention v2 installed (prebuilt wheel)"
    else
        echo "  ⚠️  Prebuilt wheel unusable for this torch build — compiling v2.0.1 from source..."
        ARCHS="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d ' .' | sed 's/^/sm/')"
        [ -n "$ARCHS" ] && export TORCH_CUDA_ARCH_LIST="$ARCHS"
        $COMFY_PIP install --no-cache-dir --no-build-isolation \
            'git+https://github.com/thu-ml/SageAttention.git@v2.0.1' > /tmp/sage_src.log 2>&1 || true
        tail -5 /tmp/sage_src.log 2>/dev/null || true
        $COMFY_PYTHON -c "from sageattention.core import get_cuda_arch_versions" >/dev/null 2>&1 \
            && echo "  ✅ SageAttention v2 installed (source build)" \
            || echo "  ⚠️  SageAttention unavailable — not fatal: this workflow's ModelAttentionBackend also offers 'pytorch attention', which needs no sage install."
    fi
fi

# ── ComfyUI launch flags for H3 on 24GB — all three are load-bearing ──
#   --lowvram                 keep VRAM headroom on a 24GB card (standing rule)
#   --disable-comfy-compiler  ComfyUI's torch.compile "model compiler" (on by default,
#                             incl. CUDA graphs) traces the H3 int8 linear with fake/CPU
#                             tensors, so comfy_kitchen's eager int8 kernel dies in
#                             int8_linear -> torch.cat with
#                             "torch.OutOfMemoryError: Allocation on device".
#   --disable-pinned-memory   PRIMARY OOM FIX. ComfyUI pins MAX_PINNED_MEMORY = ram*0.90
#                             of system RAM (comfy/model_management.py). Pinned pages are
#                             UNSWAPPABLE and UNRECLAIMABLE, so on a cgroup-capped pod the
#                             allocation simply fails mid-run. Observed: "Enabled pinned
#                             memory 42743" (41.7GB) against a 59GiB cgroup with no swap.
#                             Ref: growthlabs-docs/comfyui/minimax-h3-local-24gb.md
#                             (29866MB -> 7508MB host RAM, 0 OOM-kills).
#   Escalation if still tight: add --fp16-intermediates (experimental; changes
#   intermediate precision, so opt in deliberately).
#   Do NOT use --disable-smart-memory / --high-ram / --reserve-vram / --cache-lru:
#   all of them make this failure mode strictly worse.
H3_FLAGS="--lowvram --disable-comfy-compiler --disable-pinned-memory"

# ── Vast.ai: ComfyUI is supervisord-managed; inject the flags into its command line ──
# (Vast injects COMFYUI_ARGS, which overrides the default in the supervisor script.)
if [ -f /opt/supervisor-scripts/comfyui.sh ]; then
    for FLAG in $H3_FLAGS; do
        if grep -q -- "$FLAG" /opt/supervisor-scripts/comfyui.sh; then
            echo "  ✅ supervisor launch line already has $FLAG"
        else
            echo "  📥 Adding $FLAG to the supervisor launch line..."
            sed -i "s#\${COMFYUI_ARGS} 2>&1#\${COMFYUI_ARGS} $FLAG 2>\&1#" \
                /opt/supervisor-scripts/comfyui.sh || true
        fi
    done
fi

# ── RunPod bare pods (runpod/pytorch): there is NO supervisor, so the block above ──
# can never apply and the trailing `supervisorctl restart` is a silent no-op. Write a
# launcher that carries the flags, and let the restart block at the end of this script
# use it. Without this, RunPod runs H3 with no memory flags at all while Vast looks fine.
LAUNCHER=/root/start_comfyui.sh
if [ ! -f /opt/supervisor-scripts/comfyui.sh ]; then
    LAUNCH_PY="$(command -v "$COMFY_PYTHON" 2>/dev/null || command -v python3)"
    # Match the exec/launch line only: a comment that merely *mentions* the flag must
    # not be able to mask a launcher that does not actually pass it.
    if grep -qsE 'main\.py.*--disable-pinned-memory' "$LAUNCHER"; then
        echo "  ✅ $LAUNCHER already carries the H3 flags"
    else
        echo "  📥 Writing RunPod launcher $LAUNCHER with H3 memory flags..."
        cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/bin/bash
# Auto-generated by $(basename "$0") — H3 needs all of: --lowvram,
# --disable-comfy-compiler, --disable-pinned-memory. See the script header for why.
cd $COMFYUI_DIR
exec $LAUNCH_PY main.py --listen 0.0.0.0 --port 8188 --enable-cors-header $H3_FLAGS
LAUNCHER_EOF
        chmod +x "$LAUNCHER"
    fi
fi

# ── Phase 1b: MiniMax_H3_Semantic_Bridge custom node (zip node, no pip deps) ──
echo "==> Installing MiniMax_H3_Semantic_Bridge custom node..."
mkdir -p "$CUSTOM_NODES_DIR"
cd "$CUSTOM_NODES_DIR"
if [ -d MiniMax_H3_Semantic_Bridge ]; then
    echo "  ✅ MiniMax_H3_Semantic_Bridge already installed"
else
    echo "  📥 Downloading + extracting MiniMax_H3_Semantic_Bridge (zip node)..."
    curl -fsSL --max-time 120 -o /tmp/semantic_bridge.zip         "https://huggingface.co/speach1sdef178/MiniMax-H3-Semantic-Bridge/resolve/main/MiniMax_H3_Semantic_Bridge_v1.0.zip"         || echo "  ⚠️  Semantic Bridge zip download failed (non-fatal)"
    if [ -s /tmp/semantic_bridge.zip ]; then
        "$COMFY_PYTHON" -c "import zipfile; zipfile.ZipFile('/tmp/semantic_bridge.zip').extractall('$CUSTOM_NODES_DIR')" || true
        rm -f /tmp/semantic_bridge.zip
        [ -d MiniMax_H3_Semantic_Bridge ] && echo "  ✅ Semantic Bridge node installed"
    fi
fi
cd "$COMFYUI_DIR"

# ── Create model directories ──
echo "==> Creating model directories..."
mkdir -p "$BASE_DIR"/{vae,vae_approx,text_encoders,diffusion_models,loras,latent_upscale_models,semantic_bridge}

# ── Load shared HF download helper ──
if [ ! -f "$BASE_DIR/_hf_download.sh" ]; then
    echo "  Fetching _hf_download.sh from GitHub..."
    curl -sSL -o "$BASE_DIR/_hf_download.sh" \
        "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/workflows/setup/_hf_download.sh" || true
fi
source "$BASE_DIR/_hf_download.sh"

# ── Downloads ──
echo "==> Starting model downloads..."

# ── VAE (video) ──
echo "[1/13] minimax_h3_video_vae_fp16.safetensors (VAE - video)..."
hf_download "Comfy-Org/MiniMax-H3" "vae/minimax_h3_video_vae_fp16.safetensors" "$BASE_DIR"

# ── VAE (audio) ──
echo "[2/13] minimax_h3_audio_vae_fp32.safetensors (VAE - audio)..."
hf_download "Comfy-Org/MiniMax-H3" "vae/minimax_h3_audio_vae_fp32.safetensors" "$BASE_DIR"

# ── Text Encoder ──
echo "[3/13] qwen3vl_32b_minimax_h3_int8_convrot.safetensors (Text Encoder)..."
hf_download "Comfy-Org/MiniMax-H3" "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" "$BASE_DIR"

# ── Diffusion Model ──
echo "[4/13] Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors (Diffusion Model)..."
hf_download "WarmBloodAban/Minimax-h3_Singularity" "Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors" "$BASE_DIR/diffusion_models"

# ── LoRA: fl2v turbo 4-step v1.2 768p (comfyui) ──
echo "[5/13] minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors (LoRA - fl2v turbo 4-step v1.2 768p)..."
hf_download "lightx2v/Minimax-h3-Turbo" "minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors" "$BASE_DIR/loras"

# ── LoRA: ref2v turbo 8-step 768p (comfyui) ──
echo "[6/13] minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors (LoRA - ref2v turbo 8-step 768p)..."
hf_download "lightx2v/Minimax-h3-Turbo" "minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors" "$BASE_DIR/loras"

# ── LoRA: fl2v lightx2v turbo 4-step ──
echo "[7/13] minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors (LoRA - fl2v turbo 4-step)..."
hf_download "Kijai/MiniMax-H3_comfy" "loras/minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors" "$BASE_DIR"

# ── LoRA: ref2v lightx2v turbo 4-step resized avg rank 20 ──
echo "[8/13] minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors (LoRA - ref2v turbo 4-step rank 20)..."
hf_download "Kijai/MiniMax-H3_comfy" "loras/minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors" "$BASE_DIR"
# ── LoRA: H3 Realism People (fal) ──
echo "[9/13] h3-realism-people-t2v-i2v-r2v.safetensors (LoRA - H3 Realism People)..."
hf_download "fal/MiniMax-H3-Realism-People-LoRA" "h3-realism-people-t2v-i2v-r2v.safetensors" "$BASE_DIR/loras"


# ── Latent Upscale Model ──
# NOTE: HF repo LBH-123-AI/Minimax_h3_latent_Upscaler reshuffled the weights into a
# `minimax_h3_latent_upscaler_3d_conv_v1/` subdir (2026-09). The bare filename 404s.
# Download the nested file then flatten it to the exact name the workflow references
# (minimax_h3_latent_upscaler_3d_fp16.safetensors) so the node's dropdown picks it up.
echo "[10/13] minimax_h3_latent_upscaler_3d_fp16.safetensors (Latent Upscaler 3D, nested repo)..."
SRC="minimax_h3_latent_upscaler_3d_conv_v1/minimax_h3_latent_upscaler_3d_conv_v1_fp16.safetensors"
TGT="$BASE_DIR/latent_upscale_models/minimax_h3_latent_upscaler_3d_fp16.safetensors"
if [ ! -s "$TGT" ]; then
    hf_download "LBH-123-AI/Minimax_h3_latent_Upscaler" "$SRC" "$BASE_DIR/latent_upscale_models"
    if [ -s "$BASE_DIR/latent_upscale_models/$SRC" ]; then
        mv "$BASE_DIR/latent_upscale_models/$SRC" "$TGT"
        echo "  ✅ flattened to $TGT"
    fi
else
    echo "  ✅ already present: $TGT"
fi

# ── Tiny VAE for live preview ──
echo "[11/13] taeh3.safetensors (Tiny VAE - live preview)..."
hf_download "Kijai/MiniMax-H3-TAE" "vae_approx/taeh3.safetensors" "$BASE_DIR"

# ── Semantic Bridge adapter model ──
echo "[12/13] MiniMaxH3_SemanticBridge_v1.safetensors (Semantic Bridge adapter)..."
hf_download "speach1sdef178/MiniMax-H3-Semantic-Bridge" "MiniMaxH3_SemanticBridge_v1.safetensors" "$BASE_DIR/semantic_bridge"

# ── LoRA: ref2v turbo 4-step v0.1 (comfyui) ──
echo "[13/13] minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors (LoRA - ref2v turbo 4-step v0.1)..."
hf_download "lightx2v/Minimax-h3-Turbo" "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors" "$BASE_DIR/loras"

echo "==> All downloads completed!"

# ── Restart ComfyUI ──
echo "==> Restarting ComfyUI..."
if command -v supervisorctl >/dev/null 2>&1 && supervisorctl status comfyui >/dev/null 2>&1; then
    # Vast.ai / supervisord-managed: the flags were injected into its command line above.
    echo "  Restarting via supervisorctl..."
    supervisorctl restart comfyui || true
    COMFYUI_PORT=8188
elif [ -x "$LAUNCHER" ]; then
    # RunPod bare pod: no supervisorctl exists, so `supervisorctl restart` would be a
    # silent no-op that exits 0 and leaves the new custom_nodes unimported. The launcher
    # written earlier already carries --lowvram --disable-comfy-compiler
    # --disable-pinned-memory. tmux is the only launch method that survives SSH exit.
    echo "  No supervisor found — restarting via tmux launcher $LAUNCHER"
    tmux kill-session -t comfyui 2>/dev/null || true
    sleep 2
    for pid in $(ps -eo pid,args | awk '$0 ~ /main\.py/ && $0 !~ /awk/ {print $1}'); do
        kill -9 "$pid" 2>/dev/null || true
    done
    sleep 2
    rm -f "$COMFYUI_DIR/user/comfyui.db.lock" 2>/dev/null || true
    tmux new-session -d -s comfyui "$LAUNCHER 2>&1 | tee /workspace/comfyui.log"
    # Wait for the API before claiming success.
    for i in $(seq 1 40); do
        CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
               http://localhost:8188/system_stats 2>/dev/null)
        if [ "$CODE" = "200" ]; then
            echo "  ✅ ComfyUI ready (http://localhost:8188)"
            break
        fi
        sleep 3
    done
    if [ "$CODE" != "200" ]; then
        echo "  ⚠️  ComfyUI did not answer on :8188 — last 20 log lines:"
        tail -20 /workspace/comfyui.log 2>/dev/null || true
    fi
else
    echo "  ⚠️  No supervisor and no launcher at $LAUNCHER — start ComfyUI manually:"
    echo "      cd $COMFYUI_DIR && $COMFY_PYTHON main.py $H3_FLAGS"
fi

echo "✅ Setup complete!"
echo "👉 Open ComfyUI and load the workflow"
echo "👉 Upload an image in the LoadImage node"
