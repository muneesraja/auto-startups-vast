#!/bin/bash
# ---
# name: MiniMax H3 I2V 2-Stage Latent Upscale (Singularity + Semantic Bridge)
# workflow: minimax-h3-i2v-2stage-latent-upscale-Singularity-Semantic_Bridge
# aliases: [minimax-h3-i2v, h3-i2v-2stage, h3-latent-upscale, minimax-h3-i2v-singularity, minimax-h3-i2v-singularity-semantic-bridge, h3-bunny-bridge]
# description: MiniMax H3 image-to-video with 2-stage sampling, sigma split, latent upscaling; int8 diffusion base — hybrid fl2va+ref2va by default, Singularity ref2va pruned via --interactive + Semantic Bridge (FL2VA/text-conditioning adapter) + BUNNY H3 Conditioning Bridge (action-logic residual adapter)
# size: ~71GB + taeh3 + 3 JOKER141 LoRAs (~465MB) + BUNNY bridge adapters (~44MB) + DMAD 4-step LoRA (~350MB)
# min_vram: 24GB
# nodes: [comfyui-kjnodes, comfyui-minimax-h3-audio-T8, Comfyui_Minimax_h3_latent_Upscaler, ComfyUI-VideoHelperSuite, MiniMax_H3_Semantic_Bridge, BUNNY_H3_Conditioning_Bridge, ComfyUI-Easy-Use, ComfyUI-Easy-Media, ComfyLiterals, ComfyUI-ShellAgent-Plugin, comfyui-minimax-h3-prompt-enhancer-T8]
# usage: ./minimax-h3-i2v-2stage-latent-upscale-Singularity-Semantic_Bridge.sh [--interactive]
#   --interactive  Prompt for HF_TOKEN (hidden) and ask which diffusion model to
#                  download. Needs a TTY (tmux pane or foreground shell).
#                  Enter = keep env/config token, hybrid diffusion model.
#   Diffusion model — non-interactive runs ALWAYS take the hybrid:
#     [default]   minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors
#                 (smhfacct/Minimax-H3-fl2va-ref2va-hybrid-models)
#     [choice 2]  Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors
#                 (WarmBloodAban/Minimax-h3_Singularity)
#   These are two DIFFERENT weight files (~19.5GiB each), NOT aliases — the
#   workflow's UNETLoader widget must name the one you downloaded:
#     hybrid      -> workflows/comfyui/minimax/minimax-h3-i2v-2stage-latent-upscale.json
#     Singularity -> workflows/comfyui/minimax/minimax-h3-i2v-2stage-latent-upscale-Singularity-Semantic_Bridge.json
# ---

set -e

# ── CLI args ──
# --interactive prompts for HF_TOKEN before any long work. Manual/foreground runs
# usually have no token in the env and no /root/config/token.json, so the helper
# would abort mid-Phase-2 after the custom nodes were already installed.
INTERACTIVE=0
for arg in "$@"; do
    case "$arg" in
        --interactive|-i) INTERACTIVE=1 ;;
        -h|--help)
            echo "Usage: $0 [--interactive]"
            echo "  --interactive   Prompt for HF_TOKEN on stdin (hidden input) and which"
            echo "                  diffusion model to download. Needs a TTY (tmux pane /"
            echo "                  foreground shell) — do NOT pipe stdin in."
            echo "                  Enter = keep token, hybrid diffusion model."
            echo "  Without --interactive the hybrid fl2va+ref2va int8 UNET is always used:"
            echo "    minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors"
            echo "  Interactive choice 2 is the Singularity ref2va pruned base:"
            echo "    Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors"
            echo "  The two are different weight files — match the workflow's UNETLoader widget."
            exit 0
            ;;
        *) echo "⚠️  Ignoring unknown argument: $arg" ;;
    esac
done

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

# ── Interactive HF_TOKEN prompt (--interactive) ──
if [ "$INTERACTIVE" = "1" ]; then
    echo "==> Interactive mode — collecting HF_TOKEN"
    if [ ! -t 0 ]; then
        echo "  ⚠️  stdin is not a TTY — nothing to read."
        echo "      Run in a tmux pane or a foreground shell (no stdin pipe), then re-run."
    else
        if [ -n "${HF_TOKEN:-}" ]; then
            echo "  ℹ️  HF_TOKEN already in env (${#HF_TOKEN} chars) — press Enter to keep it."
        fi
        # -s hides the token from the terminal; `|| true` keeps `set -e` from
        # aborting the whole script on EOF (e.g. someone pipes stdin in anyway).
        read -rsp "  🔑 Enter HF_TOKEN (hidden, Enter = use existing env/config): " _HF_INPUT || true
        echo
        if [ -n "${_HF_INPUT:-}" ]; then
            export HF_TOKEN="$_HF_INPUT"
            case "$HF_TOKEN" in
                hf_*) echo "  ✅ HF_TOKEN set (${#HF_TOKEN} chars)" ;;
                *)    echo "  ⚠️  HF_TOKEN does not start with 'hf_' — continuing, but downloads may 401." ;;
            esac
            unset _HF_INPUT
        else
            echo "  ℹ️  No input — falling back to \$HF_TOKEN / /root/config/token.json"
        fi
    fi
fi

# ── Diffusion-model selection ──
# The two models are different weights (both ~19.5GiB int8), NOT aliases, so the
# download is a straight choice and the workflow's UNETLoader widget must name the
# file that landed. Non-interactive runs always take the hybrid fl2va+ref2va UNET.
DIFFUSION_REPO="smhfacct/Minimax-H3-fl2va-ref2va-hybrid-models"
DIFFUSION_FILE="minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors"
DIFFUSION_WORKFLOW="minimax-h3-i2v-2stage-latent-upscale.json"
SINGULARITY_REPO="WarmBloodAban/Minimax-h3_Singularity"
SINGULARITY_FILE="Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors"
SINGULARITY_WORKFLOW="minimax-h3-i2v-2stage-latent-upscale-Singularity-Semantic_Bridge.json"

if [ "$INTERACTIVE" = "1" ]; then
    echo "==> Interactive mode — choose the diffusion model"
    echo "    1) $DIFFUSION_FILE"
    echo "         hybrid fl2va+ref2va int8, ~19.5GiB  [default]"
    echo "    2) $SINGULARITY_FILE"
    echo "         Singularity ref2va pruned v1.3 int8, ~19.5GiB"
    if [ ! -t 0 ]; then
        echo "  ⚠️  stdin is not a TTY — keeping the default (1): $DIFFUSION_FILE"
    else
        # `|| true` keeps `set -e` from aborting on EOF (piped stdin).
        read -rp "  🎬 Which diffusion model? [1]: " _MDL_INPUT || true
        case "${_MDL_INPUT:-1}" in
            2|singularity|Singularity)
                DIFFUSION_REPO="$SINGULARITY_REPO"
                DIFFUSION_FILE="$SINGULARITY_FILE"
                DIFFUSION_WORKFLOW="$SINGULARITY_WORKFLOW"
                ;;
            1|hybrid|Hybrid|"") ;;
            *) echo "  ⚠️  Unrecognised choice '$_MDL_INPUT' — using the default (1)." ;;
        esac
        unset _MDL_INPUT
    fi
    echo "  ✅ Diffusion model: $DIFFUSION_FILE"
    echo "     from: $DIFFUSION_REPO"
    echo "     load workflow: workflows/comfyui/minimax/$DIFFUSION_WORKFLOW"
else
    echo "==> Non-interactive: diffusion model = $DIFFUSION_FILE (hybrid fl2va+ref2va int8)"
fi

BASE_DIR="$COMFYUI_DIR/models"
CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"

# ── Phase 0: Check ComfyUI core meets the H3 prerequisites (>= 0.33.2) ──
echo "==> Phase 0: Checking ComfyUI version..."
# Use git describe first — importlib.metadata.version('comfy') prints "unknown"
# (PackageNotFoundError) even at v0.30.0 on some images, which spuriously trips
# the upgrade branch and git-checkouts a newer master over a running instance.
CURRENT_VERSION=$(git -C "$COMFYUI_DIR" describe --tags 2>/dev/null | sed 's/^v//')
if [ -z "$CURRENT_VERSION" ]; then
    CURRENT_VERSION=$(python3 -c "import importlib.metadata; print(importlib.metadata.version('comfy'))" 2>/dev/null || echo "unknown")
fi
echo "  Current ComfyUI version: $CURRENT_VERSION"

# The version tag alone is NOT a sufficient gate. This workflow needs core >= 0.33.2:
#   * ModelAttentionBackend is a comfy-core node (the workflow records core ver 0.33.2)
#   * comfyui-minimax-h3-audio-T8 imports AttentionTensorContainer from
#     comfy.ldm.modules.attention at module top level
# On v0.30.0 both are absent: the pack's import dies ("IMPORT FAILED") and
# MiniMaxH3DualClockSamplerT8 / ModelAttentionBackend never register, so the workflow
# loads with Missing Node Packs — while a tag-only ">= 0.30.0" check reports
# "no upgrade needed" and the script's log stays green. Gate on capability, not the tag.
MIN_CORE="0.33.2"
NEED_UPGRADE=0
if [[ "$CURRENT_VERSION" == "unknown" ]] || \
   [[ "$(printf '%s\n' "$MIN_CORE" "$CURRENT_VERSION" | sort -V | head -n1)" != "$MIN_CORE" ]]; then
    NEED_UPGRADE=1
fi
grep -q "AttentionTensorContainer" "$COMFYUI_DIR/comfy/ldm/modules/attention.py" 2>/dev/null || NEED_UPGRADE=1
grep -rq "class ModelAttentionBackend" "$COMFYUI_DIR/comfy_extras/" 2>/dev/null || NEED_UPGRADE=1

if [ "$NEED_UPGRADE" = "1" ]; then
    echo "  ⚠️  core $CURRENT_VERSION lacks the H3 prerequisites (need >= $MIN_CORE) — upgrading..."
    ver_ge() { [ "$(printf '%s\n' "$1" "$2" | sort -V | tail -1)" = "$1" ]; }
    # Plain `git stash` ONLY — never --include-untracked: that would clobber the
    # untracked .venv-cu128/ and leave ComfyUI unable to start at all.
    git -C "$COMFYUI_DIR" stash --quiet 2>/dev/null || true
    # Prefer a released tag >= MIN_CORE (deterministic); fall back to origin/master.
    git -C "$COMFYUI_DIR" fetch origin --tags --quiet 2>/dev/null || \
        git -C "$COMFYUI_DIR" fetch origin master --depth=1 --quiet 2>/dev/null || true
    TARGET_TAG=$(git -C "$COMFYUI_DIR" tag --sort=-version:refname 2>/dev/null | grep -E '^v[0-9]' | head -1 || true)
    if [ -n "$TARGET_TAG" ] && ver_ge "$TARGET_TAG" "v$MIN_CORE"; then
        echo "  Checking out $TARGET_TAG"
        git -C "$COMFYUI_DIR" checkout "$TARGET_TAG" --quiet 2>/dev/null || true
    else
        echo "  No tag >= v$MIN_CORE found — falling back to origin/master"
        git -C "$COMFYUI_DIR" checkout origin/master -- . 2>/dev/null || \
            git -C "$COMFYUI_DIR" checkout origin/main -- . 2>/dev/null || true
    fi
    UPGRADED=1
    # Verify the checkout actually delivered what the gate just tested for.
    V2=$(git -C "$COMFYUI_DIR" describe --tags 2>/dev/null | sed 's/^v//')
    if grep -q "AttentionTensorContainer" "$COMFYUI_DIR/comfy/ldm/modules/attention.py" 2>/dev/null && \
       grep -rq "class ModelAttentionBackend" "$COMFYUI_DIR/comfy_extras/" 2>/dev/null; then
        echo "  ✅ ComfyUI upgraded to $V2 — H3 prerequisites present"
    else
        echo "  ❌ Upgrade incomplete: H3 prerequisites STILL missing after checkout ($V2)."
        echo "      MiniMaxH3DualClockSamplerT8 / ModelAttentionBackend will not register —"
        echo "      the workflow would load with Missing Node Packs. Not queueing a run."
        exit 1
    fi
else
    echo "  ✅ ComfyUI $CURRENT_VERSION >= $MIN_CORE with H3 prerequisites — no upgrade needed"
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

# ── Phase 0b: refresh ComfyUI python deps after a core upgrade ──
# An upgraded core can import new packages (e.g. comfy-kitchen, pulled in by
# ModelAttentionBackend / sparse attention). Without this the new core can fail at
# import time and ComfyUI never binds — the same silent-green failure class as the
# unknown-flag bug. Runs only when Phase 0 actually upgraded.
if [ "${UPGRADED:-0}" = "1" ] && [ -f "$COMFYUI_DIR/requirements.txt" ]; then
    echo "==> Phase 0b: Installing ComfyUI requirements after core upgrade..."
    $COMFY_PIP install -q -r "$COMFYUI_DIR/requirements.txt" 2>&1 | tail -3 || true
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
    # Extra packs some imported graphs need (ComfyUI Manager's "missing nodes" list).
    # ComfyUI-Easy-Use installs under its REGISTRY name (comfyui-easy-use), not the repo
    # name (ComfyUI-Easy-Use) — the deps loop below tolerates both.
    comfy node install https://github.com/yolain/ComfyUI-Easy-Use 2>/dev/null || true
    comfy node install https://github.com/M1kep/ComfyLiterals 2>/dev/null || true
    comfy node install https://github.com/myshell-ai/ComfyUI-ShellAgent-Plugin 2>/dev/null || true
    # MiniMaxH3PromptEnhancerT8 (separate repo from the audio-T8 pack — the node class is
    # NOT in comfyui-minimax-h3-audio-T8). Ships no requirements.txt; its pyproject needs
    # numpy/Pillow/requests/comfyui-frontend-package>=1.49.6.
    comfy node install https://github.com/T8mars/comfyui-minimax-h3-prompt-enhancer-T8 2>/dev/null || true
    echo "  ✅ comfy-cli done"
else
    echo "  comfy-cli not found, cloning manually..."
    cd "$CUSTOM_NODES_DIR"
    [ -d ComfyUI-KJNodes ] || git clone --depth=1 https://github.com/kijai/ComfyUI-KJNodes || true
    [ -d comfyui-minimax-h3-audio-T8 ] || git clone --depth=1 https://github.com/T8mars/comfyui-minimax-h3-audio-T8 || true
    [ -d Comfyui_Minimax_h3_latent_Upscaler ] || git clone --depth=1 https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler || true
    [ -d ComfyUI-VideoHelperSuite ] || git clone --depth=1 https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite || true
    [ -d ComfyUI-Easy-Use ] || git clone --depth=1 https://github.com/yolain/ComfyUI-Easy-Use || true
    [ -d ComfyLiterals ] || git clone --depth=1 https://github.com/M1kep/ComfyLiterals || true
    [ -d ComfyUI-ShellAgent-Plugin ] || git clone --depth=1 https://github.com/myshell-ai/ComfyUI-ShellAgent-Plugin || true
    [ -d comfyui-minimax-h3-prompt-enhancer-T8 ] || git clone --depth=1 https://github.com/T8mars/comfyui-minimax-h3-prompt-enhancer-T8 || true
    cd "$COMFYUI_DIR"
fi

# ── Install node dependencies ──
echo "==> Installing node dependencies..."
# Folder names differ by install route: a comfy-cli install uses the registry name
# (comfyui-easy-use) while a manual clone uses the repo name (ComfyUI-Easy-Use) — list both
# variants and skip the ones that don't exist, so a missing dir can't abort a good run.
for repo in ComfyUI-KJNodes comfyui-minimax-h3-audio-T8 Comfyui_Minimax_h3_latent_Upscaler ComfyUI-VideoHelperSuite \
            ComfyLiterals ComfyUI-ShellAgent-Plugin comfyui-easy-use ComfyUI-Easy-Use \
            ComfyUI-Easy-Media comfyui-easy-media \
            comfyui-minimax-h3-prompt-enhancer-T8; do
    [ -d "$CUSTOM_NODES_DIR/$repo" ] || continue
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

# ── AVX2-less host guard: kornia_rs SIGILLs ComfyUI at boot ──
# The image ships kornia_rs, a Rust (maturin) wheel compiled with AVX2+FMA
# (~58k ymm / ~9k vfmadd instruction sites). On a host whose CPU predates AVX2
# (e.g. Intel i7-3770 / Ivy Bridge — /proc/cpuinfo has `avx` but no `avx2`),
# `import kornia_rs` raises SIGILL (exit 132). kornia/io/io.py imports it
# unconditionally at module top level and kornia/__init__.py imports io, so
# `import kornia` kills the interpreter; ComfyUI hits it via
# comfy_extras/nodes_post_processing.py and supervisord crash-loops it forever
# (`comfyui STARTING`, nothing on 18188) with NO error in the setup log — the
# script still prints "✅ Setup complete!". Upgrading kornia_rs does NOT help
# (0.2.0 adds AVX-512). Fix: pin kornia 0.7.1, which has no kornia-rs hard
# dependency (that only lands in 0.7.2+) and guards the import with
# try/except ImportError; ComfyUI's own floor is kornia>=0.7.1, and the only
# kornia APIs these graphs touch are kornia.color (+ kornia.morphology in
# KJNodes) — all present in 0.7.1. Nothing here uses kornia.io, the sole
# kornia_rs-dependent API.
if ! grep -qw avx2 /proc/cpuinfo; then
    KORNIA_VER="$($COMFY_PYTHON -c 'import kornia;print(kornia.__version__)' 2>/dev/null || echo none)"
    if [ "$KORNIA_VER" = "none" ] || \
       [ "$(printf '%s\n' 0.7.1 "$KORNIA_VER" | sort -V | tail -1)" != "0.7.1" ]; then
        echo "  ⚠️  Host has no AVX2 + kornia ${KORNIA_VER} — pinning kornia 0.7.1 (kornia_rs would SIGILL)..."
        $COMFY_PIP uninstall -y kornia-rs >/dev/null 2>&1 || true
        $COMFY_PIP install -q 'kornia==0.7.1' >/tmp/kornia_pin.log 2>&1 || true
        tail -2 /tmp/kornia_pin.log 2>/dev/null || true
        KV="$($COMFY_PYTHON -c 'import kornia;print(kornia.__version__)' 2>/dev/null || echo FAILED)"
        if [ "$KV" = "FAILED" ]; then
            echo "  ❌ kornia still unimportable — ComfyUI will NOT boot on this host."
            echo "      Move the instance to a host with AVX2 (a full model re-download is the cost)."
        else
            echo "  ✅ kornia $KV pinned — ComfyUI can boot on this AVX-less host"
        fi
    else
        echo "  ✅ no AVX2 host, but kornia 0.7.1 is already pinned"
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
#
# ⚠️ --disable-comfy-compiler only exists in builds that SHIP the Comfy model
# compiler (upstream master). The v0.30.0 release that runpod/comfyui:latest pins
# has no such argument, so passing it makes main.py abort at argparse with
#   main.py: error: unrecognized arguments: --disable-comfy-compiler
# and ComfyUI never binds its port — while this script still printed
# "✅ Setup complete!" and exited 0. Probe the build and pass only what it accepts.
H3_FLAGS="--lowvram --disable-pinned-memory"
if ( cd "$COMFYUI_DIR" && "$COMFY_PYTHON" main.py --help 2>&1 ) | grep -q -- "--disable-comfy-compiler"; then
    H3_FLAGS="$H3_FLAGS --disable-comfy-compiler"
    echo "  ✅ build ships the Comfy model compiler — adding --disable-comfy-compiler"
else
    echo "  ℹ️  build has no --disable-comfy-compiler (no Comfy model compiler here) — omitting it"
fi

# ── Vast.ai: ComfyUI is supervisord-managed; inject the flags into its command line ──
# (Vast injects COMFYUI_ARGS, which overrides the default in the supervisor script.)
# ⚠️ ONE substitution for ALL missing flags. A per-flag loop CANNOT work: the natural
# anchor `${COMFYUI_ARGS} 2>&1` is consumed by the first sed, so every later iteration
# matches nothing and `|| true` hides it. Observed on a fresh pod: the launch line came
# out with --lowvram only, silently missing --disable-comfy-compiler (H3 int8 OOM) and
# --disable-pinned-memory (the primary OOM fix). The replacement text below deliberately
# contains no `&` and no `$`, so it is immune to sed's whole-match `&` metachar and to
# shell `$` interpolation; the range starts at the `python main.py` line so the
# `COMFYUI_ARGS=` assignment above it is never rewritten.
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

# ── RunPod bare pods (runpod/pytorch): there is NO supervisor, so the block above ──
# can never apply and the trailing `supervisorctl restart` is a silent no-op. Write a
# launcher that carries the flags, and let the restart block at the end of this script
# use it. Without this, RunPod runs H3 with no memory flags at all while Vast looks fine.
LAUNCHER=/root/start_comfyui.sh
if [ ! -f /opt/supervisor-scripts/comfyui.sh ]; then
    LAUNCH_PY="$(command -v "$COMFY_PYTHON" 2>/dev/null || command -v python3)"
    # Match the exec/launch line only: a comment that merely *mentions* the flag must
    # not be able to mask a launcher that does not actually pass it. Require the EXACT
    # flag set computed above — a single sentinel flag is not enough: a stale launcher
    # that carries --disable-pinned-memory AND a flag this build rejects (e.g. an old
    # --disable-comfy-compiler) passes a sentinel check and makes every boot die at
    # argparse. Regenerating is idempotent, so prefer the exact match.
    if grep -qsF "main.py --listen 0.0.0.0 --port 8188 --enable-cors-header $H3_FLAGS" "$LAUNCHER"; then
        echo "  ✅ $LAUNCHER already carries the H3 flags"
    else
        echo "  📥 Writing RunPod launcher $LAUNCHER with H3 memory flags..."
        cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/bin/bash
# Auto-generated by $(basename "$0"). Launch flags: $H3_FLAGS
# (see the script header for why each one is load-bearing on a 24GB card).
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

# ── Phase 1c: BUNNY_H3_Conditioning_Bridge custom node (CONDITIONING adapter) ──
# JOKER141 / FourBunny continuation of the speach1sdef178 Semantic Bridge research
# direction, focused on high-dynamic action logic + complex multi-actor scenes.
# Node repo:  https://github.com/aa335615543-ux/BUNNY_H3_Conditioning_Bridge
# Adapters:   https://huggingface.co/JOKER141/BUNNY_H3_Conditioning_Bridge
# Registers exactly ONE class: BunnyH3ConditioningBridge -> "BUNNY H3 Conditioning
# Bridge" (category BUNNY/MiniMax H3, __version__ 0.3.0). It is inserted inline on
# the existing H3 CONDITIONING path (in: CONDITIONING, out: CONDITIONING) and
# applies a small residual (alpha 0.10-0.15, magnitude_match per_token) — no new
# ComfyUI model category and no extra sampler wiring needed.
# ⚠️ Kept ALONGSIDE MiniMax_H3_Semantic_Bridge (Phase 1b), not as a replacement:
# that pack provides SenseNovaH3DistilledBridge, which the *_fl2v.json variant
# still uses. The two register different class names, so they coexist safely.
echo "==> Installing BUNNY_H3_Conditioning_Bridge custom node..."
BUNNY_REPO="https://github.com/aa335615543-ux/BUNNY_H3_Conditioning_Bridge"
BUNNY_DIR="$CUSTOM_NODES_DIR/BUNNY_H3_Conditioning_Bridge"
mkdir -p "$CUSTOM_NODES_DIR"
if command -v comfy >/dev/null 2>&1; then
    comfy node install "$BUNNY_REPO" 2>/dev/null || true
fi
# comfy-cli/Marketplace installs it under the registry name
# (bunny-h3-semantic-bridge, from pyproject [tool.comfy] DisplayName); a manual clone
# lands as BUNNY_H3_Conditioning_Bridge. Both are valid to ComfyUI, so resolve
# whichever one actually exists instead of assuming the folder name.
for CAND in "$CUSTOM_NODES_DIR/bunny-h3-semantic-bridge" "$CUSTOM_NODES_DIR/BUNNY_H3_Conditioning_Bridge"; do
    [ -f "$CAND/nodes.py" ] && BUNNY_DIR="$CAND" && break
done
if [ ! -f "$BUNNY_DIR/nodes.py" ]; then
    echo "  📥 Cloning $BUNNY_REPO ..."
    ( cd "$CUSTOM_NODES_DIR" && git clone --depth=1 "$BUNNY_REPO" BUNNY_H3_Conditioning_Bridge ) \
        || echo "  ⚠️  BUNNY bridge clone failed (non-fatal)"
fi
if [ -f "$BUNNY_DIR/nodes.py" ]; then
    echo "  ✅ BUNNY H3 Conditioning Bridge installed at $BUNNY_DIR"
else
    echo "  ⚠️  BUNNY bridge node missing — its adapters below cannot be used"
fi
# Adapter lookup in nodes.py is: bundled <node>/models/ FIRST, then the external
# models/semantic_bridge/ dir (which the node registers as a model folder path).
# We use the bundled dir — it is what the README documents, it wins the lookup,
# and it keeps the adapter travelling with the node install.
BUNNY_MODELS_DIR="$BUNNY_DIR/models"
mkdir -p "$BUNNY_MODELS_DIR"
# requirements.txt is just `safetensors` (already a ComfyUI dependency), but install
# it defensively against the node's own dir so a future dep can't be missed.
if [ -f "$BUNNY_DIR/requirements.txt" ]; then
    echo "  Installing BUNNY bridge deps..."
    $COMFY_PIP install -q -r "$BUNNY_DIR/requirements.txt" 2>&1 | tail -3 || true
fi

# ── Phase 1d: ComfyUI-Easy-Media custom node (MultiTrack editor + H3 project pipeline) ──
# yolain's media/video-pipeline pack: https://github.com/yolain/ComfyUI-Easy-Media
# The MultiTrack graph needs FIVE of its classes:
#   easy modelLoaderPack, easy multiTrackEditor, easy multitrackProject,
#   easy multitrackProjectVideoCombine, easy saveVideo
# ⚠️ HARD FLOOR v1.3.0 — easy multitrackProject / easy multitrackProjectVideoCombine /
# easy modelLoaderPack only exist from v1.3.0 (the MultiTrack Project pipeline landed
# then). An OUT-OF-DATE ComfyUI-Manager registry cache serves v1.2.1, which installs
# "successfully", registers 66 classes, and still reports "Missing Node Packs:
# ComfyUI-Easy-Media" for exactly those three (observed 2026-10-07 on Vast
# 85.30.169.224:40517 — Manager logged "ComfyRegistry cache update is still in
# progress, so an outdated cache is being used"). So pin the clone, and REPLACE any
# below-floor copy already on disk instead of trusting it. Zero pip deps
# (pyproject `dependencies = []`); FFmpeg IS a hard runtime prerequisite.
echo "==> Installing ComfyUI-Easy-Media custom node..."
EASY_MEDIA_REPO="https://github.com/yolain/ComfyUI-Easy-Media"
EASY_MEDIA_TAG="v1.3.4"
# comfy-cli/Manager lands the REGISTRY name (comfyui-easy-media); a clone lands the
# repo name (ComfyUI-Easy-Media). Resolve whichever exists — never clone a second
# copy beside it, two dirs would register the same node ids twice.
EASY_MEDIA_DIR=""
if [ -d "$CUSTOM_NODES_DIR/ComfyUI-Easy-Media" ]; then
    EASY_MEDIA_DIR="$CUSTOM_NODES_DIR/ComfyUI-Easy-Media"
elif [ -d "$CUSTOM_NODES_DIR/comfyui-easy-media" ]; then
    EASY_MEDIA_DIR="$CUSTOM_NODES_DIR/comfyui-easy-media"
fi
if [ -n "$EASY_MEDIA_DIR" ] && \
   ! grep -rq -- "easy multitrackProject" "$EASY_MEDIA_DIR" --include=*.py 2>/dev/null; then
    echo "  ⚠️  $(basename "$EASY_MEDIA_DIR") predates $EASY_MEDIA_TAG — replacing with the pinned release"
    rm -rf "$EASY_MEDIA_DIR"
    EASY_MEDIA_DIR=""
fi
if [ -z "$EASY_MEDIA_DIR" ]; then
    echo "  📥 Cloning $EASY_MEDIA_REPO @ $EASY_MEDIA_TAG ..."
    ( cd "$CUSTOM_NODES_DIR" && git clone --depth=1 --branch "$EASY_MEDIA_TAG" \
        "$EASY_MEDIA_REPO" ComfyUI-Easy-Media ) || echo "  ⚠️  Easy-Media clone failed (non-fatal)"
    EASY_MEDIA_DIR="$CUSTOM_NODES_DIR/ComfyUI-Easy-Media"
fi
if grep -rq -- "easy multitrackProject" "$EASY_MEDIA_DIR" --include=*.py 2>/dev/null; then
    echo "  ✅ ComfyUI-Easy-Media installed at $EASY_MEDIA_DIR ($(git -C "$EASY_MEDIA_DIR" describe --tags 2>/dev/null || echo 'no tag'))"
else
    echo "  ⚠️  ComfyUI-Easy-Media is missing the MultiTrack Project nodes — the graph will report 'Missing Node Packs'"
fi
# FFmpeg is a README-flagged hard prerequisite for the whole pack (every video node shells out to it).
if command -v ffmpeg >/dev/null 2>&1; then
    echo "  ✅ ffmpeg present ($(ffmpeg -version 2>/dev/null | head -1 | awk '{print $3}'))"
else
    echo "  ⚠️  ffmpeg NOT found — ComfyUI-Easy-Media video nodes need it: apt-get install -y ffmpeg"
fi

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
echo "[1/19] minimax_h3_video_vae_fp16.safetensors (VAE - video)..."
hf_download "Comfy-Org/MiniMax-H3" "vae/minimax_h3_video_vae_fp16.safetensors" "$BASE_DIR"

# ── VAE (audio) ──
echo "[2/19] minimax_h3_audio_vae_fp32.safetensors (VAE - audio)..."
hf_download "Comfy-Org/MiniMax-H3" "vae/minimax_h3_audio_vae_fp32.safetensors" "$BASE_DIR"

# ── Text Encoder ──
echo "[3/19] qwen3vl_32b_minimax_h3_int8_convrot.safetensors (Text Encoder)..."
hf_download "Comfy-Org/MiniMax-H3" "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" "$BASE_DIR"

# ── Diffusion Model ──
# Selected at startup: hybrid fl2va+ref2va int8 by default, Singularity ref2va
# pruned via `--interactive` choice 2. One file only — see the header for which
# workflow JSON matches which file.
echo "[4/19] $DIFFUSION_FILE (Diffusion Model)..."
hf_download "$DIFFUSION_REPO" "$DIFFUSION_FILE" "$BASE_DIR/diffusion_models"

# ── LoRA: fl2v turbo 4-step v1.2 768p (comfyui) ──
echo "[5/19] minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors (LoRA - fl2v turbo 4-step v1.2 768p)..."
hf_download "lightx2v/Minimax-h3-Turbo" "minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors" "$BASE_DIR/loras"

# ── LoRA: ref2v turbo 8-step 768p (comfyui) ──
echo "[6/19] minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors (LoRA - ref2v turbo 8-step 768p)..."
hf_download "lightx2v/Minimax-h3-Turbo" "minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors" "$BASE_DIR/loras"

# ── LoRA: fl2v lightx2v turbo 4-step ──
echo "[7/19] minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors (LoRA - fl2v turbo 4-step)..."
hf_download "Kijai/MiniMax-H3_comfy" "loras/minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors" "$BASE_DIR"

# ── LoRA: ref2v lightx2v turbo 4-step resized avg rank 20 ──
echo "[8/19] minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors (LoRA - ref2v turbo 4-step rank 20)..."
hf_download "Kijai/MiniMax-H3_comfy" "loras/minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors" "$BASE_DIR"
# ── LoRA: H3 Realism People (fal) ──
echo "[9/19] h3-realism-people-t2v-i2v-r2v.safetensors (LoRA - H3 Realism People)..."
hf_download "fal/MiniMax-H3-Realism-People-LoRA" "h3-realism-people-t2v-i2v-r2v.safetensors" "$BASE_DIR/loras"


# ── Latent Upscale Model ──
# NOTE: HF repo LBH-123-AI/Minimax_h3_latent_Upscaler reshuffled the weights into a
# `minimax_h3_latent_upscaler_3d_conv_v1/` subdir (2026-09). The bare filename 404s.
# Download the nested file then flatten it to the exact name the workflow references
# (minimax_h3_latent_upscaler_3d_fp16.safetensors) so the node's dropdown picks it up.
echo "[10/19] minimax_h3_latent_upscaler_3d_fp16.safetensors (Latent Upscaler 3D, nested repo)..."
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
echo "[11/19] taeh3.safetensors (Tiny VAE - live preview)..."
hf_download "Kijai/MiniMax-H3-TAE" "vae_approx/taeh3.safetensors" "$BASE_DIR"

# ── Semantic Bridge adapter model ──
echo "[12/19] MiniMaxH3_SemanticBridge_v1.safetensors (Semantic Bridge adapter)..."
hf_download "speach1sdef178/MiniMax-H3-Semantic-Bridge" "MiniMaxH3_SemanticBridge_v1.safetensors" "$BASE_DIR/semantic_bridge"

# ── LoRA: ref2v turbo 4-step v0.1 (comfyui) ──
echo "[13/19] minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors (LoRA - ref2v turbo 4-step v0.1)..."
hf_download "lightx2v/Minimax-h3-Turbo" "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors" "$BASE_DIR/loras"

# ── LoRA: General Motion Continuity Repair V2 (JOKER141) ──
echo "[14/19] Motion_Repair_V2.safetensors (LoRA - General Motion Continuity Repair V2)..."
hf_download "JOKER141/MiniMax-H3-General-Motion-Continuity-Repair" "Motion_Repair_V2.safetensors" "$BASE_DIR/loras"

# ── LoRA: Combat Base V2 (JOKER141) ──
echo "[15/19] H3_Combat_V2.safetensors (LoRA - Combat Base V2)..."
hf_download "JOKER141/MiniMax-H3-Combat-Base-V2" "H3_Combat_V2.safetensors" "$BASE_DIR/loras"

# ── LoRA: Fight Flow Fight Interaction V1 (JOKER141) ──
echo "[16/19] H3_Fight_Flow_V1.safetensors (LoRA - Fight Flow Fight Interaction V1)..."
hf_download "JOKER141/H3-Fight-Flow-Fight-Interaction-LoRA" "H3_Fight_Flow_V1.safetensors" "$BASE_DIR/loras"

# ── BUNNY H3 ActionLogic Bridge adapters (JOKER141) ──
# 22MB residual MLPs (5120 -> 512 -> 512 -> 5120) that plug inline on the H3
# CONDITIONING path. They target what motion repair cannot fix: who is doing what,
# attacker/target confusion, weapon/object ownership, spatial continuity after a
# position exchange, identity+state after occlusion, prompt/environment continuity.
# Both go into the node's own models/ dir, which nodes.py checks FIRST.
#   V1 — the documented default: the README install step, its "Recommended
#        settings", the repo's Example Workflow, and nodes.py all pin V1 (it is
#        force-listed at the top of the node's `adapter` dropdown).
#   V2 — the rebuilt-pipeline adapter described in the V2 update notes. Same
#        architecture/dims as V1 and only ~22MB, so it ships too and you pick it
#        from the dropdown. Drop this line if you want V1 only.
echo "[17/19] BUNNY_H3_ActionLogic_Bridge_V1.safetensors (BUNNY H3 bridge adapter - V1, default)..."
hf_download "JOKER141/BUNNY_H3_Conditioning_Bridge" "BUNNY_H3_ActionLogic_Bridge_V1.safetensors" "$BUNNY_MODELS_DIR"

echo "[18/19] BUNNY_H3_ActionLogic_Bridge_V2.safetensors (BUNNY H3 bridge adapter - V2)..."
hf_download "JOKER141/BUNNY_H3_Conditioning_Bridge" "BUNNY_H3_ActionLogic_Bridge_V2.safetensors" "$BUNNY_MODELS_DIR"

# ── LoRA: DMAD 4-step full (Kijai/MiniMax-H3-experimental, avg rank 39) ──
# The file lives under the repo's `loras/` subdir, so dest is $BASE_DIR — NOT $BASE_DIR/loras.
# The helper mirrors the repo-relative path, so it lands at models/loras/<name>; passing
# $BASE_DIR/loras would nest it as loras/loras/<name> (on disk, but invisible to the dropdown).
# Download-only, like Motion_Repair_V2 / Combat V2 / Fight Flow: no shipped graph references it — add a
# LoraLoaderModelOnly node and select it to use it.
echo "[19/19] minimax_h3_DMAD_4step_full_lora_avg_rank_39_bf16.safetensors (LoRA - DMAD 4-step full)..."
hf_download "Kijai/MiniMax-H3-experimental" "loras/minimax_h3_DMAD_4step_full_lora_avg_rank_39_bf16.safetensors" "$BASE_DIR"

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
    # ⚠️ `set -e` trap: a bare `CODE=$(curl ...)` assignment inherits curl's exit
    # status, and curl exits 7 (couldn't connect) while ComfyUI is still loading.
    # That aborted the whole script on the FIRST loop iteration, so the health-wait
    # never ran and "✅ Setup complete!" never printed (observed 2026-09-23 on
    # RunPod pod ua8s0lfrmisoqt: EXIT_CODE=7 with a perfectly healthy ComfyUI).
    # Always swallow curl's status here — a failed probe is expected, not fatal.
    for i in $(seq 1 60); do
        CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
               http://localhost:8188/system_stats 2>/dev/null || true)
        [ -n "$CODE" ] || CODE=000
        if [ "$CODE" = "200" ]; then
            echo "  ✅ ComfyUI ready (http://localhost:8188)"
            break
        fi
        sleep 3
    done
    if [ "$CODE" != "200" ]; then
        echo "  ⚠️  ComfyUI did not answer on :8188 — last 20 log lines:"
        tail -20 /workspace/comfyui.log 2>/dev/null || true
        # A green setup log is NOT a health verdict. main.py can abort at argparse
        # (e.g. a flag this build doesn't know) or at import, AFTER the restart line
        # returned 0 — the run then reports ✅/EXIT_CODE=0 with ComfyUI dead. Fail
        # loudly so EXIT_CODE is a real verdict instead of a lie.
        echo "❌ Setup finished but ComfyUI is NOT serving on :8188 (see log above)."
        exit 1
    fi
else
    echo "  ⚠️  No supervisor and no launcher at $LAUNCHER — start ComfyUI manually:"
    echo "      cd $COMFYUI_DIR && $COMFY_PYTHON main.py $H3_FLAGS"
fi

echo "✅ Setup complete!"
echo "👉 Open ComfyUI and load the workflow"
echo "👉 Upload an image in the LoadImage node"
