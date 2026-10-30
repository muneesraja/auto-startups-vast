#!/bin/bash
# ---
# name: MiniMax H3 2-Stage NVIDIA Upscale
# workflow: MinimaxH3_2Stage-NVIDIA_UPSCALE
# aliases: [minimax-h3-2stage-nvidia-upscale, minimax-h3-nvidia-upscale, h3-nvidia-upscale, MinimaxH3_2Stage-NVIDIA_UPSCALE, minimaxh3-2stage-nvidia-upscale]
# description: MiniMax H3 2-stage latent upscaling with NVIDIA Open-H3-Regenerate-2K (Fast VAE Decode StreamRender-H3 + Open-H3 2K LoRAs) and MMH3 Ultimate Upscale tiling/chunking. Includes RMBG-2.0 background segmentation, H3 LMS LoRA, and the BUNNY / H3 hybrid fl2va+ref2va base pipeline.
# size: ~110.6GB measured with the hybrid base (~123.7GB with the Singularity V2 base, which is unpruned at ~31.7GiB; ~111.8GB with the FastH3 Omni 8-step base at ~20.7GiB)
# min_vram: 24GB
# nodes: [comfyui-kjnodes, comfyui-minimax-h3-audio-T8, Comfyui_Minimax_h3_latent_Upscaler, ComfyUI-VideoHelperSuite, MiniMax_H3_Semantic_Bridge, BUNNY_H3_Conditioning_Bridge, ComfyUI-Easy-Use, ComfyUI-Easy-Media, ComfyLiterals, ComfyUI-ShellAgent-Plugin, comfyui-minimax-h3-prompt-enhancer-T8, selflift-Avatar, ComfyUI-YCNodes-MiniMax-H3, Comfyui-MMH3-UltimateUpscale, ComfyUI-Open-H3-Regenerate, ComfyUI-RMBG]
# usage: ./minimax-h3-2stage-nvidia-upscale.sh [--interactive]
#   --interactive  Prompt for HF_TOKEN (hidden) and ask which diffusion model to
#                  download. Needs a TTY (tmux pane or foreground shell).
#                  Enter = keep env/config token, hybrid diffusion model.
#   Diffusion model — non-interactive runs ALWAYS take the hybrid:
#     [default]   minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors
#                 (smhfacct/Minimax-H3-fl2va-ref2va-hybrid-models)
#     [choice 2]  Minimax-h3_Singularity_ref2va_v2_int8.safetensors
#                 (WarmBloodAban/Minimax-h3_Singularity)
#     [choice 3]  fasth3_omniref_8step_pruned_int8_convrot.safetensors
#                 (FastVideo/FastH3-Omni-Comfy, inside its diffusion_models/ subdir)
#   All three are DIFFERENT weight files (hybrid ~19.5GiB, Singularity V2
#   ~31.7GiB — the V2 int8 release is NOT pruned, FastH3 Omni ~20.7GiB), NOT
#   aliases — the workflow's UNETLoader widget must name the one you downloaded:
#     hybrid      -> workflows/comfyui/minimax/MinimaxH3_2Stage-NVIDIA_UPSCALE.json   <- the workflow THIS script targets
#                    workflows/comfyui/minimax/minimax-h3-i2v-2stage-latent-upscale.json
#                    workflows/comfyui/minimax/BUNNY_SelfLift_12GB1080P_LORA__1.json
#     Singularity -> workflows/comfyui/minimax/minimax-h3-i2v-2stage-latent-upscale-Singularity-Semantic_Bridge.json
#     FastH3 Omni -> no bundled graph yet (state 2026-10): the two shipped graphs run
#                    a turbo LoRA on a 4/5/6-step ManualSigmas schedule, while this
#                    base is already 8-step distilled (cfg 1.0, video shift 12.0,
#                    audio shift 3.0, no turbo LoRA). Load the core "MiniMax H3
#                    Reference to Video" template or re-point either graph's
#                    UNETLoader, bypass its LoRA, and use an 8-step schedule.
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
            echo "  Interactive choice 2 is the Singularity ref2va V2 base (unpruned, ~31.7GiB):"
            echo "    Minimax-h3_Singularity_ref2va_v2_int8.safetensors"
            echo "  Interactive choice 3 is the FastH3 Omni ref2v 8-step pruned int8 base (~20.7GiB):"
            echo "    fasth3_omniref_8step_pruned_int8_convrot.safetensors"
            echo "    (download only — no bundled graph matches it yet; 8 steps, cfg 1.0,"
            echo "     video shift 12.0, audio shift 3.0, no turbo LoRA; its VAEs AND text"
            echo "     encoder are pulled from FastVideo/FastH3-Omni-Comfy, same files as Comfy-Org)"
            echo "  The three are different weight files — match the workflow's UNETLoader widget."
            echo "  This script targets the NVIDIA 2-stage upscale graph, whose UNETLoader names the hybrid:"
            echo "    workflows/comfyui/minimax/MinimaxH3_2Stage-NVIDIA_UPSCALE.json"
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
# Three different weights (hybrid ~19.5GiB, Singularity V2 ~31.7GiB unpruned int8,
# FastH3 Omni ~20.7GiB 8-step pruned int8), NOT aliases, so the download is a
# straight choice and the workflow's UNETLoader widget must name the file that
# landed. Non-interactive runs always take the hybrid fl2va+ref2va UNET.
DIFFUSION_REPO="smhfacct/Minimax-H3-fl2va-ref2va-hybrid-models"
DIFFUSION_FILE="minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors"
DIFFUSION_WORKFLOW="MinimaxH3_2Stage-NVIDIA_UPSCALE.json"
SINGULARITY_REPO="WarmBloodAban/Minimax-h3_Singularity"
SINGULARITY_FILE="Minimax-h3_Singularity_ref2va_v2_int8.safetensors"
SINGULARITY_WORKFLOW="minimax-h3-i2v-2stage-latent-upscale-Singularity-Semantic_Bridge.json"
# FastH3 Omni ships inside the repo's diffusion_models/ subdir — the filename keeps
# that prefix so hf_download mirrors it, and step [5/29] points the helper at
# $BASE_DIR instead of $BASE_DIR/diffusion_models (otherwise it nests twice and the
# UNETLoader dropdown never sees the file). Its card also pins its own vae/ and
# text_encoders/ copies, so steps [1/29]-[4/29] source ALL from this repo when
# choice 3 is picked (byte-identical to Comfy-Org's — same LFS sha256 + size, verified
# 2026-10 — so the paths land the same files; the switch is provenance, not a
# different decode).
FASTH3_REPO="FastVideo/FastH3-Omni-Comfy"
FASTH3_FILE="diffusion_models/fasth3_omniref_8step_pruned_int8_convrot.safetensors"
FASTH3_WORKFLOW=""

if [ "$INTERACTIVE" = "1" ]; then
    echo "==> Interactive mode — choose the diffusion model"
    echo "    1) $DIFFUSION_FILE"
    echo "         hybrid fl2va+ref2va int8, ~19.5GiB  [default]"
    echo "    2) $SINGULARITY_FILE"
    echo "         Singularity ref2va V2 int8 (unpruned), ~31.7GiB"
    echo "    3) $(basename "$FASTH3_FILE")"
    echo "         FastH3 Omni ref2v 8-step pruned int8, ~20.7GiB (download only)"
    if [ ! -t 0 ]; then
        echo "  ⚠️  stdin is not a TTY — keeping the default (1): $DIFFUSION_FILE"
    else
        read -rp "  🎬 Which diffusion model? [1]: " _MDL_INPUT || true
        case "${_MDL_INPUT:-1}" in
            2|singularity|Singularity)
                DIFFUSION_REPO="$SINGULARITY_REPO"
                DIFFUSION_FILE="$SINGULARITY_FILE"
                DIFFUSION_WORKFLOW="$SINGULARITY_WORKFLOW"
                ;;
            3|fasth3|FastH3|omni|Omni)
                DIFFUSION_REPO="$FASTH3_REPO"
                DIFFUSION_FILE="$FASTH3_FILE"
                DIFFUSION_WORKFLOW="$FASTH3_WORKFLOW"
                ;;
            1|hybrid|Hybrid|"") ;;
            *) echo "  ⚠️  Unrecognised choice '$_MDL_INPUT' — using the default (1)." ;;
        esac
        unset _MDL_INPUT
    fi
    echo "  ✅ Diffusion model: $DIFFUSION_FILE"
    echo "     from: $DIFFUSION_REPO"
    if [ -n "$DIFFUSION_WORKFLOW" ]; then
        echo "     load workflow: workflows/comfyui/minimax/$DIFFUSION_WORKFLOW"
    else
        echo "     workflow: none bundled — load the core 'MiniMax H3 Reference to Video'"
        echo "               template (or re-point a graph's UNETLoader at this file),"
        echo "               bypass its turbo LoRA, then use: 8 steps, cfg 1.0,"
        echo "               video shift 12.0, audio shift 3.0, euler sampler."
        echo "               Prompt reference tags: <Picture 1> <Video 1> <Audio 1>"
        echo "     VAEs + text encoder: pulled from $FASTH3_REPO (its card's copies)"
    fi
else
    echo "==> Non-interactive: diffusion model = $DIFFUSION_FILE (hybrid fl2va+ref2va int8)"
fi

BASE_DIR="$COMFYUI_DIR/models"
CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"

# ── Phase 0: Check ComfyUI core meets the H3 prerequisites (>= 0.42.0) ──
echo "==> Phase 0: Checking ComfyUI version..."
CURRENT_VERSION=$(git -C "$COMFYUI_DIR" describe --tags 2>/dev/null | sed 's/^v//')
if [ -z "$CURRENT_VERSION" ]; then
    CURRENT_VERSION=$(python3 -c "import importlib.metadata; print(importlib.metadata.version('comfy'))" 2>/dev/null || echo "unknown")
fi
echo "  Current ComfyUI version: $CURRENT_VERSION"

MIN_CORE="0.42.0"
NEED_UPGRADE=0
if [[ "$CURRENT_VERSION" == "unknown" ]] || \
   [[ "$(printf '%s\n' "$MIN_CORE" "$CURRENT_VERSION" | sort -V | head -n1)" != "$MIN_CORE" ]]; then
    NEED_UPGRADE=1
fi
grep -q "AttentionTensorContainer" "$COMFYUI_DIR/comfy/ldm/modules/attention.py" 2>/dev/null || NEED_UPGRADE=1
grep -rq "class ModelAttentionBackend" "$COMFYUI_DIR/comfy_extras/" 2>/dev/null || NEED_UPGRADE=1
grep -rq "class SaveVideo" "$COMFYUI_DIR/comfy_extras/" 2>/dev/null || NEED_UPGRADE=1
grep -rq "class MathExpressionNode" "$COMFYUI_DIR/comfy_extras/" 2>/dev/null || NEED_UPGRADE=1
[ -f "$COMFYUI_DIR/comfy_api/latest/__init__.py" ] || NEED_UPGRADE=1
grep -q "pdd_steps" "$COMFYUI_DIR/comfy/model_detection.py" 2>/dev/null || NEED_UPGRADE=1

if [ "$NEED_UPGRADE" = "1" ]; then
    echo "  ⚠️  core $CURRENT_VERSION lacks the H3 prerequisites (need >= $MIN_CORE) — upgrading..."
    ver_ge() { [ "$(printf '%s\n' "$1" "$2" | sort -V | tail -1)" = "$1" ]; }
    git -C "$COMFYUI_DIR" stash --quiet 2>/dev/null || true
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
    V2=$(git -C "$COMFYUI_DIR" describe --tags 2>/dev/null | sed 's/^v//')
    if grep -q "AttentionTensorContainer" "$COMFYUI_DIR/comfy/ldm/modules/attention.py" 2>/dev/null && \
       grep -rq "class ModelAttentionBackend" "$COMFYUI_DIR/comfy_extras/" 2>/dev/null && \
       grep -rq "class SaveVideo" "$COMFYUI_DIR/comfy_extras/" 2>/dev/null && \
       [ -f "$COMFYUI_DIR/comfy_api/latest/__init__.py" ] && \
       grep -q "pdd_steps" "$COMFYUI_DIR/comfy/model_detection.py" 2>/dev/null; then
        echo "  ✅ ComfyUI upgraded to $V2 — H3 prerequisites present"
    else
        echo "  ❌ Upgrade incomplete: H3 prerequisites STILL missing after checkout ($V2)."
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
    comfy node install https://github.com/yolain/ComfyUI-Easy-Use 2>/dev/null || true
    comfy node install https://github.com/M1kep/ComfyLiterals 2>/dev/null || true
    comfy node install https://github.com/myshell-ai/ComfyUI-ShellAgent-Plugin 2>/dev/null || true
    comfy node install https://github.com/T8mars/comfyui-minimax-h3-prompt-enhancer-T8 2>/dev/null || true
    comfy node install https://github.com/slmonker/selflift-Avatar 2>/dev/null || true
    comfy node install https://github.com/yichengup/ComfyUI-YCNodes-MiniMax-H3 2>/dev/null || true
    # NVIDIA 2-Stage Upscale workflow packs:
    comfy node install https://github.com/bbaudio-2025/Comfyui-MMH3-UltimateUpscale 2>/dev/null || true
    comfy node install https://github.com/rdh9616/ComfyUI-Open-H3-Regenerate 2>/dev/null || true
    comfy node install https://github.com/1038lab/ComfyUI-RMBG 2>/dev/null || true
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
    [ -d selflift-Avatar ] || git clone --depth=1 https://github.com/slmonker/selflift-Avatar || true
    [ -d ComfyUI-YCNodes-MiniMax-H3 ] || git clone --depth=1 https://github.com/yichengup/ComfyUI-YCNodes-MiniMax-H3 || true
    [ -d Comfyui-MMH3-UltimateUpscale ] || git clone --depth=1 https://github.com/bbaudio-2025/Comfyui-MMH3-UltimateUpscale || true
    [ -d ComfyUI-Open-H3-Regenerate ] || git clone --depth=1 https://github.com/rdh9616/ComfyUI-Open-H3-Regenerate || true
    [ -d ComfyUI-RMBG ] || git clone --depth=1 https://github.com/1038lab/ComfyUI-RMBG || true
    cd "$COMFYUI_DIR"
fi

# ── Install node dependencies ──
echo "==> Installing node dependencies..."
for repo in ComfyUI-KJNodes comfyui-minimax-h3-audio-T8 Comfyui_Minimax_h3_latent_Upscaler ComfyUI-VideoHelperSuite \
            ComfyLiterals ComfyUI-ShellAgent-Plugin comfyui-easy-use ComfyUI-Easy-Use \
            ComfyUI-Easy-Media comfyui-easy-media \
            comfyui-minimax-h3-prompt-enhancer-T8 \
            selflift-Avatar ComfyUI-YCNodes-MiniMax-H3 \
            Comfyui-MMH3-UltimateUpscale comfyui-mmh3-ultimateupscale \
            ComfyUI-Open-H3-Regenerate comfyui-open-h3-regenerate \
            ComfyUI-RMBG comfyui-rmbg; do
    [ -d "$CUSTOM_NODES_DIR/$repo" ] || continue
    REQ="$CUSTOM_NODES_DIR/$repo/requirements.txt"
    if [ -f "$REQ" ]; then
        echo "  Installing $repo deps..."
        $COMFY_PIP install -q -r "$REQ" 2>&1 | tail -5 || true
    fi
done

# ── SageAttention v2 (fixes MiniMaxH3MemoryEfficientSageAttentionPatch) ──
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
            || echo "  ⚠️  SageAttention unavailable — not fatal: ModelAttentionBackend fallback is active."
    fi
fi

# ── AVX2-less host guard: kornia_rs SIGILLs ComfyUI at boot ──
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
        else
            echo "  ✅ kornia $KV pinned — ComfyUI can boot on this AVX-less host"
        fi
    else
        echo "  ✅ no AVX2 host, but kornia 0.7.1 is already pinned"
    fi
fi

# ── ComfyUI launch flags for H3 on 24GB ──
H3_FLAGS="--lowvram --disable-pinned-memory"
if ( cd "$COMFYUI_DIR" && "$COMFY_PYTHON" main.py --help 2>&1 ) | grep -q -- "--disable-comfy-compiler"; then
    H3_FLAGS="$H3_FLAGS --disable-comfy-compiler"
    echo "  ✅ build ships the Comfy model compiler — adding --disable-comfy-compiler"
else
    echo "  ℹ️  build has no --disable-comfy-compiler — omitting it"
fi

# ── Vast.ai: ComfyUI supervisord command line flag injection ──
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

# ── RunPod launcher ──
LAUNCHER=/root/start_comfyui.sh
if [ ! -f /opt/supervisor-scripts/comfyui.sh ]; then
    LAUNCH_PY="$(command -v "$COMFY_PYTHON" 2>/dev/null || command -v python3)"
    if grep -qsF "main.py --listen 0.0.0.0 --port 8188 --enable-cors-header $H3_FLAGS" "$LAUNCHER"; then
        echo "  ✅ $LAUNCHER already carries the H3 flags"
    else
        echo "  📥 Writing RunPod launcher $LAUNCHER with H3 memory flags..."
        cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/bin/bash
# Auto-generated by $(basename "$0"). Launch flags: $H3_FLAGS
cd $COMFYUI_DIR
exec $LAUNCH_PY main.py --listen 0.0.0.0 --port 8188 --enable-cors-header $H3_FLAGS
LAUNCHER_EOF
        chmod +x "$LAUNCHER"
    fi
fi

# ── Phase 1b: MiniMax_H3_Semantic_Bridge custom node (zip node) ──
echo "==> Installing MiniMax_H3_Semantic_Bridge custom node..."
mkdir -p "$CUSTOM_NODES_DIR"
cd "$CUSTOM_NODES_DIR"
if [ -d MiniMax_H3_Semantic_Bridge ]; then
    echo "  ✅ MiniMax_H3_Semantic_Bridge already installed"
else
    echo "  📥 Downloading + extracting MiniMax_H3_Semantic_Bridge (zip node)..."
    curl -fsSL --max-time 120 -o /tmp/semantic_bridge.zip \
        "https://huggingface.co/speach1sdef178/MiniMax-H3-Semantic-Bridge/resolve/main/MiniMax_H3_Semantic_Bridge_v1.0.zip" \
        || echo "  ⚠️  Semantic Bridge zip download failed (non-fatal)"
    if [ -s /tmp/semantic_bridge.zip ]; then
        "$COMFY_PYTHON" -c "import zipfile; zipfile.ZipFile('/tmp/semantic_bridge.zip').extractall('$CUSTOM_NODES_DIR')" || true
        rm -f /tmp/semantic_bridge.zip
        [ -d MiniMax_H3_Semantic_Bridge ] && echo "  ✅ Semantic Bridge node installed"
    fi
fi
cd "$COMFYUI_DIR"

# ── Phase 1c: BUNNY_H3_Conditioning_Bridge custom node ──
echo "==> Installing BUNNY_H3_Conditioning_Bridge custom node..."
BUNNY_REPO="https://github.com/aa335615543-ux/BUNNY_H3_Conditioning_Bridge"
BUNNY_DIR="$CUSTOM_NODES_DIR/BUNNY_H3_Conditioning_Bridge"
mkdir -p "$CUSTOM_NODES_DIR"
if command -v comfy >/dev/null 2>&1; then
    comfy node install "$BUNNY_REPO" 2>/dev/null || true
fi
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
    echo "  ⚠️  BUNNY bridge node missing"
fi
BUNNY_MODELS_DIR="$BUNNY_DIR/models"
mkdir -p "$BUNNY_MODELS_DIR"
if [ -f "$BUNNY_DIR/requirements.txt" ]; then
    echo "  Installing BUNNY bridge deps..."
    $COMFY_PIP install -q -r "$BUNNY_DIR/requirements.txt" 2>&1 | tail -3 || true
fi

# ── Phase 1d: ComfyUI-Easy-Media custom node ──
echo "==> Installing ComfyUI-Easy-Media custom node..."
EASY_MEDIA_REPO="https://github.com/yolain/ComfyUI-Easy-Media"
EASY_MEDIA_TAG="v1.3.4"
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
    echo "  ✅ ComfyUI-Easy-Media installed at $EASY_MEDIA_DIR"
else
    echo "  ⚠️  ComfyUI-Easy-Media missing MultiTrack Project nodes"
fi
if command -v ffmpeg >/dev/null 2>&1; then
    echo "  ✅ ffmpeg present"
else
    echo "  ⚠️  ffmpeg NOT found — ComfyUI-Easy-Media video nodes need it"
fi

# ── Phase 1e: selflift-Avatar ──
echo "==> Installing selflift-Avatar custom node..."
SELFLIFT_REPO="https://github.com/slmonker/selflift-Avatar"
SELFLIFT_DIR="$CUSTOM_NODES_DIR/selflift-Avatar"
mkdir -p "$CUSTOM_NODES_DIR"
if command -v comfy >/dev/null 2>&1; then
    comfy node install "$SELFLIFT_REPO" 2>/dev/null || true
fi
[ -f "$SELFLIFT_DIR/nodes.py" ] || \
    ( cd "$CUSTOM_NODES_DIR" && git clone --depth=1 "$SELFLIFT_REPO" selflift-Avatar ) \
        || echo "  ⚠️  selflift-Avatar clone failed (non-fatal)"
if grep -q "SelfLiftAvatarH3Sampler" "$SELFLIFT_DIR/nodes.py" 2>/dev/null; then
    echo "  ✅ selflift-Avatar installed at $SELFLIFT_DIR"
else
    echo "  ⚠️  selflift-Avatar missing SelfLiftAvatarH3Sampler"
fi

# ── Phase 1f: Sol-Attn provider check (SolAttnMiniMax) ──
echo "==> Verifying the Sol-Attn provider (SolAttnMiniMax)..."
SOLATTN_SRC="$CUSTOM_NODES_DIR/comfyui-minimax-h3-audio-T8/sol_attn_minimax_v2.py"
if grep -q "class SolAttnMiniMax" "$SOLATTN_SRC" 2>/dev/null; then
    echo "  ✅ SolAttnMiniMax provided by comfyui-minimax-h3-audio-T8"
else
    echo "  ⚠️  comfyui-minimax-h3-audio-T8 no longer vendors SolAttnMiniMax — falling back to standalone BSAI pack"
    BSAI_REPO="https://github.com/xm6018924/BSAI-ComfyUI-Sol-H3"
    BSAI_DIR="$CUSTOM_NODES_DIR/BSAI-ComfyUI-Sol-H3"
    if command -v comfy >/dev/null 2>&1; then
        comfy node install "$BSAI_REPO" 2>/dev/null || true
    fi
    [ -f "$BSAI_DIR/sol_attn_minimax_v2.py" ] || \
        ( cd "$CUSTOM_NODES_DIR" && git clone --depth=1 "$BSAI_REPO" BSAI-ComfyUI-Sol-H3 ) \
            || echo "  ⚠️  BSAI fallback clone failed (non-fatal)"
fi

# ── Sol-Attn runtime prerequisites: comfy_kitchen kernels + triton ──
COMFY_KITCHEN_STATE="$("$COMFY_PYTHON" - <<'PYEOF' 2>/dev/null || echo "absent (probe failed)"
try:
    import inspect
    import comfy_kitchen as ck
    from comfy_kitchen.backends import cuda as c
    sig = inspect.signature(c.sol_attn).parameters
    print("%s sink_blocks=%s tail=%s" % (getattr(ck, "__version__", "?"),
                                         "sink_blocks" in sig, "tail" in sig))
except Exception as exc:
    print("absent (%s)" % type(exc).__name__)
PYEOF
)"
COMFY_KITCHEN_STATE=$(printf '%s' "$COMFY_KITCHEN_STATE" | tr -d '\r')
echo "  comfy_kitchen: $COMFY_KITCHEN_STATE"
case "$COMFY_KITCHEN_STATE" in
    *sink_blocks=True*tail=True*) ;;
    *)
        echo "  ⚠️  comfy_kitchen lacks the Sol-Attn sink_blocks/tail kernels — upgrading..."
        $COMFY_PIP install -q -U comfy-kitchen >/tmp/comfy_kitchen_up.log 2>&1 || true
        tail -2 /tmp/comfy_kitchen_up.log 2>/dev/null || true
        ;;
esac
if $COMFY_PYTHON -c "import triton" >/dev/null 2>&1; then
    echo "  ✅ triton present"
else
    echo "  ⚠️  triton NOT importable"
fi

# ── Phase 1g: ComfyUI-YCNodes-MiniMax-H3 (H3SigmaRefiner) ──
echo "==> Installing ComfyUI-YCNodes-MiniMax-H3 custom node..."
YC_REPO="https://github.com/yichengup/ComfyUI-YCNodes-MiniMax-H3"
YC_DIR="$CUSTOM_NODES_DIR/ComfyUI-YCNodes-MiniMax-H3"
if command -v comfy >/dev/null 2>&1; then
    comfy node install "$YC_REPO" 2>/dev/null || true
fi
[ -f "$YC_DIR/py/h3_sigma_refiner.py" ] || \
    ( cd "$CUSTOM_NODES_DIR" && git clone --depth=1 "$YC_REPO" ComfyUI-YCNodes-MiniMax-H3 ) \
        || echo "  ⚠️  YCNodes clone failed (non-fatal)"
if grep -q "H3SigmaRefiner" "$YC_DIR/py/h3_sigma_refiner.py" 2>/dev/null; then
    echo "  ✅ H3SigmaRefiner present at $YC_DIR"
fi

# ── Phase 1h: Comfyui-MMH3-UltimateUpscale (MMH3 Ultimate Upscale) ──
echo "==> Verifying Comfyui-MMH3-UltimateUpscale..."
MMH3_DIR=""
for CAND in "$CUSTOM_NODES_DIR/Comfyui-MMH3-UltimateUpscale" "$CUSTOM_NODES_DIR/comfyui-mmh3-ultimateupscale"; do
    [ -d "$CAND" ] && MMH3_DIR="$CAND" && break
done
if [ -n "$MMH3_DIR" ]; then
    echo "  ✅ Comfyui-MMH3-UltimateUpscale installed at $MMH3_DIR"
else
    echo "  ⚠️  Comfyui-MMH3-UltimateUpscale missing"
fi

# ── Phase 1i: ComfyUI-Open-H3-Regenerate (Open-H3 Fast VAE Decode) ──
echo "==> Verifying ComfyUI-Open-H3-Regenerate..."
OPEN_H3_DIR=""
for CAND in "$CUSTOM_NODES_DIR/ComfyUI-Open-H3-Regenerate" "$CUSTOM_NODES_DIR/comfyui-open-h3-regenerate"; do
    [ -d "$CAND" ] && OPEN_H3_DIR="$CAND" && break
done
if [ -n "$OPEN_H3_DIR" ]; then
    echo "  ✅ ComfyUI-Open-H3-Regenerate installed at $OPEN_H3_DIR"
else
    echo "  ⚠️  ComfyUI-Open-H3-Regenerate missing"
fi

# ── Phase 1j: ComfyUI-RMBG (RMBG-2.0 Background Removal) ──
echo "==> Verifying ComfyUI-RMBG..."
RMBG_DIR=""
for CAND in "$CUSTOM_NODES_DIR/ComfyUI-RMBG" "$CUSTOM_NODES_DIR/comfyui-rmbg"; do
    [ -d "$CAND" ] && RMBG_DIR="$CAND" && break
done
if [ -n "$RMBG_DIR" ]; then
    echo "  ✅ ComfyUI-RMBG installed at $RMBG_DIR"
else
    echo "  ⚠️  ComfyUI-RMBG missing"
fi

# ── Create model directories ──
echo "==> Creating model directories..."
mkdir -p "$BASE_DIR"/{vae,vae_approx,text_encoders,diffusion_models,loras,latent_upscale_models,semantic_bridge,RMBG}

# ── Load shared HF download helper ──
if [ ! -f "$BASE_DIR/_hf_download.sh" ]; then
    echo "  Fetching _hf_download.sh from GitHub..."
    curl -sSL -o "$BASE_DIR/_hf_download.sh" \
        "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/workflows/setup/_hf_download.sh" || true
fi
source "$BASE_DIR/_hf_download.sh"

# ── Downloads ──
echo "==> Starting model downloads..."

if [ "$DIFFUSION_REPO" = "$FASTH3_REPO" ]; then
    VAE_REPO="$FASTH3_REPO"
    TEXT_ENC_REPO="$FASTH3_REPO"
else
    VAE_REPO="Comfy-Org/MiniMax-H3"
    TEXT_ENC_REPO="Comfy-Org/MiniMax-H3"
fi

# ── VAE (video) ──
echo "[1/29] minimax_h3_video_vae_fp16.safetensors (VAE - video, $VAE_REPO)..."
hf_download "$VAE_REPO" "vae/minimax_h3_video_vae_fp16.safetensors" "$BASE_DIR"

# ── VAE (audio) ──
echo "[2/29] minimax_h3_audio_vae_fp32.safetensors (VAE - audio, $VAE_REPO)..."
hf_download "$VAE_REPO" "vae/minimax_h3_audio_vae_fp32.safetensors" "$BASE_DIR"

# ── Fast VAE: NVIDIA StreamRender-H3 non-causal 24L ──
echo "[3/29] fast_h3_vae_noncausal_24l.safetensors (Fast VAE - NVIDIA StreamRender-H3)..."
hf_download "Efficient-Large-Model/Open-H3-Regenerate-2K" "vae_fast/fast_h3_vae_noncausal_24l.safetensors" "$BASE_DIR/vae"
if [ -s "$BASE_DIR/vae/vae_fast/fast_h3_vae_noncausal_24l.safetensors" ] && [ ! -s "$BASE_DIR/vae/fast_h3_vae_noncausal_24l.safetensors" ]; then
    mv "$BASE_DIR/vae/vae_fast/fast_h3_vae_noncausal_24l.safetensors" "$BASE_DIR/vae/fast_h3_vae_noncausal_24l.safetensors"
    rmdir "$BASE_DIR/vae/vae_fast" 2>/dev/null || true
    echo "  ✅ flattened to models/vae/fast_h3_vae_noncausal_24l.safetensors"
fi
if [ -s "$BASE_DIR/vae/fast_h3_vae_noncausal_24l.safetensors" ] && [ ! -s "$BASE_DIR/vae/vae_fast/fast_h3_vae_noncausal_24l.safetensors" ]; then
    mkdir -p "$BASE_DIR/vae/vae_fast"
    ln "$BASE_DIR/vae/fast_h3_vae_noncausal_24l.safetensors" "$BASE_DIR/vae/vae_fast/fast_h3_vae_noncausal_24l.safetensors" 2>/dev/null || \
    ln -s "$BASE_DIR/vae/fast_h3_vae_noncausal_24l.safetensors" "$BASE_DIR/vae/vae_fast/fast_h3_vae_noncausal_24l.safetensors" 2>/dev/null || true
fi

# ── Text Encoder ──
echo "[4/29] qwen3vl_32b_minimax_h3_int8_convrot.safetensors (Text Encoder, $TEXT_ENC_REPO)..."
hf_download "$TEXT_ENC_REPO" "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" "$BASE_DIR"

# ── Diffusion Model ──
echo "[5/29] $(basename "$DIFFUSION_FILE") (Diffusion Model)..."
if [ "$DIFFUSION_REPO" = "$FASTH3_REPO" ]; then
    DIFFUSION_DEST="$BASE_DIR"
else
    DIFFUSION_DEST="$BASE_DIR/diffusion_models"
fi
hf_download "$DIFFUSION_REPO" "$DIFFUSION_FILE" "$DIFFUSION_DEST"
if [ ! -s "$BASE_DIR/diffusion_models/$(basename "$DIFFUSION_FILE")" ]; then
    echo "  ⚠️  expected models/diffusion_models/$(basename "$DIFFUSION_FILE") — not on disk."
fi

# ── LoRA: fl2v turbo 4-step v1.2 768p (comfyui) ──
echo "[6/29] minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors (LoRA - fl2v turbo 4-step v1.2 768p)..."
hf_download "lightx2v/Minimax-h3-Turbo" "minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors" "$BASE_DIR/loras"

# ── LoRA: ref2v turbo 8-step 768p (comfyui) ──
echo "[7/29] minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors (LoRA - ref2v turbo 8-step 768p)..."
hf_download "lightx2v/Minimax-h3-Turbo" "minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors" "$BASE_DIR/loras"

# ── LoRA: fl2v lightx2v turbo 4-step ──
echo "[8/29] minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors (LoRA - fl2v turbo 4-step)..."
hf_download "Kijai/MiniMax-H3_comfy" "loras/minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors" "$BASE_DIR"

# ── LoRA: ref2v lightx2v turbo 4-step resized avg rank 20 ──
echo "[9/29] minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors (LoRA - ref2v turbo 4-step rank 20)..."
hf_download "Kijai/MiniMax-H3_comfy" "loras/minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors" "$BASE_DIR"

# ── LoRA: H3 Realism People (fal) ──
echo "[10/29] h3-realism-people-t2v-i2v-r2v.safetensors (LoRA - H3 Realism People)..."
hf_download "fal/MiniMax-H3-Realism-People-LoRA" "h3-realism-people-t2v-i2v-r2v.safetensors" "$BASE_DIR/loras"

# ── Latent Upscale Model: 3D fp16 ──
echo "[11/29] minimax_h3_latent_upscaler_3d_fp16.safetensors (Latent Upscaler 3D, nested repo)..."
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

# ── Upstream-V2 alias for SelfLift upscaler dropdown ──
TGT_V2="$BASE_DIR/latent_upscale_models/minimax_h3_latent_upscaler_3d_fp16_V2.safetensors"
if [ -s "$TGT" ] && [ ! -s "$TGT_V2" ]; then
    ln "$TGT" "$TGT_V2" 2>/dev/null || cp "$TGT" "$TGT_V2"
    echo "  ✅ v1 fp16 weights also installed as $(basename "$TGT_V2")"
fi

# ── Latent Upscaler: 3D Conv v1 bf16 (NVIDIA / LBH) ──
echo "[12/29] minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors (Latent Upscaler 3D Conv v1 bf16)..."
SRC_BF16="latent_upsampler/minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors"
TGT_BF16="$BASE_DIR/latent_upscale_models/minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors"
if [ ! -s "$TGT_BF16" ]; then
    hf_download "Efficient-Large-Model/Open-H3-Regenerate-2K" "$SRC_BF16" "$BASE_DIR/latent_upscale_models"
    if [ -s "$BASE_DIR/latent_upscale_models/$SRC_BF16" ]; then
        mv "$BASE_DIR/latent_upscale_models/$SRC_BF16" "$TGT_BF16"
        rmdir "$BASE_DIR/latent_upscale_models/latent_upsampler" 2>/dev/null || true
        echo "  ✅ flattened to $TGT_BF16"
    fi
else
    echo "  ✅ already present: $TGT_BF16"
fi

# ── Tiny VAE for live preview ──
echo "[13/29] taeh3.safetensors (Tiny VAE - live preview)..."
hf_download "Kijai/MiniMax-H3-TAE" "vae_approx/taeh3.safetensors" "$BASE_DIR"

# ── Semantic Bridge adapter model ──
echo "[14/29] MiniMaxH3_SemanticBridge_v1.safetensors (Semantic Bridge adapter)..."
hf_download "speach1sdef178/MiniMax-H3-Semantic-Bridge" "MiniMaxH3_SemanticBridge_v1.safetensors" "$BASE_DIR/semantic_bridge"

# ── LoRA: ref2v turbo 4-step v0.1 (comfyui) ──
echo "[15/29] minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors (LoRA - ref2v turbo 4-step v0.1)..."
hf_download "lightx2v/Minimax-h3-Turbo" "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors" "$BASE_DIR/loras"

# ── LoRA: General Motion Continuity Repair V2 (JOKER141) ──
echo "[16/29] Motion_Repair_V2.safetensors (LoRA - General Motion Continuity Repair V2)..."
hf_download "JOKER141/MiniMax-H3-General-Motion-Continuity-Repair" "Motion_Repair_V2.safetensors" "$BASE_DIR/loras"

# ── v1-name alias ──
MR_V1="$BASE_DIR/loras/Motion_Repair.safetensors"
MR_V2="$BASE_DIR/loras/Motion_Repair_V2.safetensors"
if [ -s "$MR_V2" ] && [ ! -s "$MR_V1" ]; then
    ln "$MR_V2" "$MR_V1" 2>/dev/null || cp "$MR_V2" "$MR_V1"
    echo "  ✅ V2 weights also installed as Motion_Repair.safetensors"
fi

# ── LoRA: Combat Base V2 (JOKER141) ──
echo "[17/29] H3_Combat_V2.safetensors (LoRA - Combat Base V2)..."
hf_download "JOKER141/MiniMax-H3-Combat-Base-V2" "H3_Combat_V2.safetensors" "$BASE_DIR/loras"

# ── BUNNY H3 ActionLogic Bridge adapters (JOKER141) ──
echo "[18/29] BUNNY_H3_ActionLogic_Bridge_V1.safetensors (BUNNY H3 bridge adapter - V1, default)..."
hf_download "JOKER141/BUNNY_H3_Conditioning_Bridge" "BUNNY_H3_ActionLogic_Bridge_V1.safetensors" "$BUNNY_MODELS_DIR"

echo "[19/29] BUNNY_H3_ActionLogic_Bridge_V2.safetensors (BUNNY H3 bridge adapter - V2)..."
hf_download "JOKER141/BUNNY_H3_Conditioning_Bridge" "BUNNY_H3_ActionLogic_Bridge_V2.safetensors" "$BUNNY_MODELS_DIR"

# ── LoRA: DMAD 4-step full ──
echo "[20/29] minimax_h3_DMAD_4step_full_lora_avg_rank_39_bf16.safetensors (LoRA - DMAD 4-step full)..."
hf_download "Kijai/MiniMax-H3-experimental" "loras/minimax_h3_DMAD_4step_full_lora_avg_rank_39_bf16.safetensors" "$BASE_DIR"

# ── LoRA: Turbo v4 step600 EMA pruned ──
echo "[21/29] minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors (LoRA - Turbo v4 step600 EMA pruned)..."
hf_download "Momoking/MiniMax-H3-Turbo-Lora-ComfyUI" "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors" "$BASE_DIR/loras"

# ── LoRA: H3 Fight Flow V1 ──
echo "[22/29] H3_Fight_Flow_V1.safetensors (LoRA - Fight Flow fight-interaction V1)..."
hf_download "JOKER141/H3-Fight-Flow-Fight-Interaction-LoRA" "H3_Fight_Flow_V1.safetensors" "$BASE_DIR/loras"

# ── LoRA: Superhuman Combat ──
echo "[23/29] SuperHunman.safetensors (LoRA - Superhuman Combat)..."
hf_download "JOKER141/H3-superhuman-combat-lora" "SuperHunman.safetensors" "$BASE_DIR/loras"

# ── LoRA: Pika H3 Flex Ref2va V1 (Comfy-Org) ──
echo "[24/29] pika_h3_flex_ref2va_v1_bf16.safetensors (LoRA - Pika H3 Flex Ref2va V1)..."
hf_download "Comfy-Org/MiniMax-H3" "loras/pika_h3_flex_ref2va_v1_bf16.safetensors" "$BASE_DIR"

# ── Diffusion Model / LoRA: MiniMax H3 ref2va pruned int8 (Comfy-Org) ──
echo "[25/29] minimax_h3_ref2va_pruned_int8_convrot.safetensors (Diffusion Model / LoRA - ref2va pruned int8)..."
hf_download "Comfy-Org/MiniMax-H3" "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors" "$BASE_DIR"
if [ -s "$BASE_DIR/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors" ] && [ ! -s "$BASE_DIR/loras/minimax_h3_ref2va_pruned_int8_convrot.safetensors" ]; then
    ln "$BASE_DIR/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors" "$BASE_DIR/loras/minimax_h3_ref2va_pruned_int8_convrot.safetensors" 2>/dev/null || \
    ln -s "$BASE_DIR/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors" "$BASE_DIR/loras/minimax_h3_ref2va_pruned_int8_convrot.safetensors" 2>/dev/null || true
fi

# ── LoRA: MiniMax H3 LMS v1.0 r64 (Alissonerdx) ──
echo "[26/29] minimax_h3_lms_v1.0_r64.safetensors (LoRA - MiniMax H3 LMS v1.0 r64)..."
hf_download "Alissonerdx/Minimax-H3-ComfyUI" "loras/minimax_h3_lms_v1.0_r64.safetensors" "$BASE_DIR"
mkdir -p "$BASE_DIR/loras/minimax-h3"
if [ -s "$BASE_DIR/loras/minimax_h3_lms_v1.0_r64.safetensors" ] && [ ! -s "$BASE_DIR/loras/minimax-h3/minimax_h3_lms_v1.0_r64.safetensors" ]; then
    ln "$BASE_DIR/loras/minimax_h3_lms_v1.0_r64.safetensors" "$BASE_DIR/loras/minimax-h3/minimax_h3_lms_v1.0_r64.safetensors" 2>/dev/null || \
    ln -s "$BASE_DIR/loras/minimax_h3_lms_v1.0_r64.safetensors" "$BASE_DIR/loras/minimax-h3/minimax_h3_lms_v1.0_r64.safetensors" 2>/dev/null || true
    echo "  ✅ LMS LoRA also installed in models/loras/minimax-h3/ (workflow widget path)"
fi

# ── LoRA: NVIDIA Open-H3 Sharp Curve Branches ──
echo "[27/29] sharp_curve_branches.safetensors (LoRA - NVIDIA Open-H3 Sharp Curve)..."
mkdir -p "$BASE_DIR/loras/Open-H3-Regenerate-2K"
hf_download "Efficient-Large-Model/Open-H3-Regenerate-2K" "lora/sharp_curve_branches.safetensors" "$BASE_DIR/loras"
if [ -s "$BASE_DIR/loras/lora/sharp_curve_branches.safetensors" ]; then
    mv "$BASE_DIR/loras/lora/sharp_curve_branches.safetensors" "$BASE_DIR/loras/Open-H3-Regenerate-2K/sharp_curve_branches.safetensors"
    rmdir "$BASE_DIR/loras/lora" 2>/dev/null || true
fi
if [ -s "$BASE_DIR/loras/Open-H3-Regenerate-2K/sharp_curve_branches.safetensors" ] && [ ! -s "$BASE_DIR/loras/sharp_curve_branches.safetensors" ]; then
    ln "$BASE_DIR/loras/Open-H3-Regenerate-2K/sharp_curve_branches.safetensors" "$BASE_DIR/loras/sharp_curve_branches.safetensors" 2>/dev/null || \
    ln -s "$BASE_DIR/loras/Open-H3-Regenerate-2K/sharp_curve_branches.safetensors" "$BASE_DIR/loras/sharp_curve_branches.safetensors" 2>/dev/null || true
fi

# ── LoRA: NVIDIA Open-H3 Regenerate 2K ──
echo "[28/29] open_h3_regenerate_2k_lora.safetensors (LoRA - NVIDIA Open-H3 Regenerate 2K)..."
mkdir -p "$BASE_DIR/loras/Open-H3-Regenerate-2K"
hf_download "Efficient-Large-Model/Open-H3-Regenerate-2K" "lora/open_h3_regenerate_2k_lora.safetensors" "$BASE_DIR/loras"
if [ -s "$BASE_DIR/loras/lora/open_h3_regenerate_2k_lora.safetensors" ]; then
    mv "$BASE_DIR/loras/lora/open_h3_regenerate_2k_lora.safetensors" "$BASE_DIR/loras/Open-H3-Regenerate-2K/open_h3_regenerate_2k_lora.safetensors"
    rmdir "$BASE_DIR/loras/lora" 2>/dev/null || true
fi
if [ -s "$BASE_DIR/loras/Open-H3-Regenerate-2K/open_h3_regenerate_2k_lora.safetensors" ] && [ ! -s "$BASE_DIR/loras/open_h3_regenerate_2k_lora.safetensors" ]; then
    ln "$BASE_DIR/loras/Open-H3-Regenerate-2K/open_h3_regenerate_2k_lora.safetensors" "$BASE_DIR/loras/open_h3_regenerate_2k_lora.safetensors" 2>/dev/null || \
    ln -s "$BASE_DIR/loras/Open-H3-Regenerate-2K/open_h3_regenerate_2k_lora.safetensors" "$BASE_DIR/loras/open_h3_regenerate_2k_lora.safetensors" 2>/dev/null || true
fi

# ── Background Removal Model: RMBG-2.0 (1038lab / BiRefNet) ──
echo "[29/29] RMBG-2.0 (Background Removal model - 1038lab / BiRefNet)..."
mkdir -p "$BASE_DIR/RMBG/RMBG-2.0"
for rmbg_file in model.safetensors config.json BiRefNet_config.py birefnet.py; do
    if [ ! -s "$BASE_DIR/RMBG/RMBG-2.0/$rmbg_file" ]; then
        hf_download "1038lab/RMBG-2.0" "$rmbg_file" "$BASE_DIR/RMBG/RMBG-2.0"
    fi
done

echo "==> All downloads completed!"

# ── Restart ComfyUI ──
echo "==> Restarting ComfyUI..."
if command -v supervisorctl >/dev/null 2>&1 && supervisorctl status comfyui >/dev/null 2>&1; then
    echo "  Restarting via supervisorctl..."
    supervisorctl restart comfyui || true
    COMFYUI_PORT=8188
elif [ -x "$LAUNCHER" ]; then
    echo "  No supervisor found — restarting via tmux launcher $LAUNCHER"
    tmux kill-session -t comfyui 2>/dev/null || true
    sleep 2
    for pid in $(ps -eo pid,args | awk '$0 ~ /main\.py/ && $0 !~ /awk/ {print $1}'); do
        kill -9 "$pid" 2>/dev/null || true
    done
    sleep 2
    rm -f "$COMFYUI_DIR/user/comfyui.db.lock" 2>/dev/null || true
    tmux new-session -d -s comfyui "$LAUNCHER 2>&1 | tee /workspace/comfyui.log"
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
        echo "❌ Setup finished but ComfyUI is NOT serving on :8188 (see log above)."
        exit 1
    fi
else
    echo "  ⚠️  No supervisor and no launcher at $LAUNCHER — start ComfyUI manually:"
    echo "      cd $COMFYUI_DIR && $COMFY_PYTHON main.py $H3_FLAGS"
fi

echo "✅ Setup complete!"
echo "👉 Open ComfyUI and load the workflow: workflows/comfyui/minimax/MinimaxH3_2Stage-NVIDIA_UPSCALE.json"
echo "👉 Upload an image in the LoadImage node"
