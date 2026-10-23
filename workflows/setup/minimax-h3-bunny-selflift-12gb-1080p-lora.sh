#!/bin/bash
# ---
# name: BUNNY H3 SelfLift 2-Stage Latent Upscale (12GB 1080P LoRA)
# workflow: BUNNY_SelfLift_12GB1080P_LORA__1
# aliases: [bunny-selflift, h3-bunny-selflift, minimax-h3-bunny-selflift, h3-selflift-2stage, bunny-h3-1080p, h3-bunny-12gb, minimax-h3-bunny-lora]
# description: MiniMax H3 2-stage SelfLift (avatar) render with 3D latent upscaling — H3SigmaRefiner sigma refine + Sol-Attn sparse attention + the BUNNY two-stage LoRA chain (Combat V2 / Fight-Flow V1 / Motion Repair / Superhuman Combat); int8 hybrid fl2va+ref2va base. Superset of the Singularity/Semantic-Bridge script (Semantic Bridge + BUNNY conditioning-bridge packs + Easy-Media are still installed)
# size: ~64.6GB measured with the hybrid base (~77.7GB with the Singularity V2 base, which is unpruned at ~31.7GiB; ~65.8GB with the FastH3 Omni 8-step base at ~20.7GiB)
# min_vram: 24GB
# nodes: [comfyui-kjnodes, comfyui-minimax-h3-audio-T8, Comfyui_Minimax_h3_latent_Upscaler, ComfyUI-VideoHelperSuite, MiniMax_H3_Semantic_Bridge, BUNNY_H3_Conditioning_Bridge, ComfyUI-Easy-Use, ComfyUI-Easy-Media, ComfyLiterals, ComfyUI-ShellAgent-Plugin, comfyui-minimax-h3-prompt-enhancer-T8, selflift-Avatar, ComfyUI-YCNodes-MiniMax-H3]
# usage: ./minimax-h3-bunny-selflift-12gb-1080p-lora.sh [--interactive]
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
#     hybrid      -> workflows/comfyui/minimax/minimax-h3-i2v-2stage-latent-upscale.json
#                    workflows/comfyui/minimax/BUNNY_SelfLift_12GB1080P_LORA__1.json   <- the workflow THIS script targets
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
            echo "     video shift 12.0, audio shift 3.0, no turbo LoRA)"
            echo "  The three are different weight files — match the workflow's UNETLoader widget."
            echo "  This script targets the BUNNY SelfLift graph, whose UNETLoader names the hybrid:"
            echo "    workflows/comfyui/minimax/BUNNY_SelfLift_12GB1080P_LORA__1.json"
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
DIFFUSION_WORKFLOW="minimax-h3-i2v-2stage-latent-upscale.json"
SINGULARITY_REPO="WarmBloodAban/Minimax-h3_Singularity"
SINGULARITY_FILE="Minimax-h3_Singularity_ref2va_v2_int8.safetensors"
SINGULARITY_WORKFLOW="minimax-h3-i2v-2stage-latent-upscale-Singularity-Semantic_Bridge.json"
# FastH3 Omni ships inside the repo's diffusion_models/ subdir — the filename keeps
# that prefix so hf_download mirrors it, and step [4/21] points the helper at
# $BASE_DIR instead of $BASE_DIR/diffusion_models (otherwise it nests twice and the
# UNETLoader dropdown never sees the file). Its card pairs it with the SAME text
# encoder + video/audio VAEs this script already pulls from Comfy-Org — verified
# byte-identical (same LFS sha256/size) in both repos, so only the UNET is extra.
FASTH3_REPO="FastVideo/FastH3-Omni-Comfy"
FASTH3_FILE="diffusion_models/fasth3_omniref_8step_pruned_int8_convrot.safetensors"
# No bundled graph: the shipped H3 graphs drive a turbo LoRA on a 4/5/6-step
# ManualSigmas schedule, while this base is natively 8-step (cfg 1.0, video shift
# 12.0, audio shift 3.0, NO turbo LoRA — a turbo LoRA on a distilled 8-step base
# over-accelerates). Deliberately left empty so the script cannot print a
# "load workflow:" line for a graph whose sigmas/LoRA would be wrong.
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
        # `|| true` keeps `set -e` from aborting on EOF (piped stdin).
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
        # FastH3 Omni: be explicit instead of pretending a bundled graph fits.
        echo "     workflow: none bundled — load the core 'MiniMax H3 Reference to Video'"
        echo "               template (or re-point a graph's UNETLoader at this file),"
        echo "               bypass its turbo LoRA, then use: 8 steps, cfg 1.0,"
        echo "               video shift 12.0, audio shift 3.0, euler sampler."
        echo "               Prompt reference tags: <Picture 1> <Video 1> <Audio 1>"
    fi
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
MIN_CORE="0.35.0"
NEED_UPGRADE=0
if [[ "$CURRENT_VERSION" == "unknown" ]] || \
   [[ "$(printf '%s\n' "$MIN_CORE" "$CURRENT_VERSION" | sort -V | head -n1)" != "$MIN_CORE" ]]; then
    NEED_UPGRADE=1
fi
grep -q "AttentionTensorContainer" "$COMFYUI_DIR/comfy/ldm/modules/attention.py" 2>/dev/null || NEED_UPGRADE=1
grep -rq "class ModelAttentionBackend" "$COMFYUI_DIR/comfy_extras/" 2>/dev/null || NEED_UPGRADE=1
# BUNNY SelfLift graph additions (workflow records core ver 0.35.0):
#   SaveVideo / CreateVideo  — comfy_extras/nodes_video.py (stage-2 AV output)
#   ComfyMathExpression      — comfy_extras/nodes_math.py (auto frame-count node)
#   comfy_api/latest (io.ComfyNode + ComfyExtension) — imported at module top level by
#   the SolAttnMiniMax node (vendored in comfyui-minimax-h3-audio-T8); without it the
#   pack logs IMPORT FAILED and
#   the workflow loads with Missing Node Packs while a tag-only check stays green.
grep -rq "class SaveVideo" "$COMFYUI_DIR/comfy_extras/" 2>/dev/null || NEED_UPGRADE=1
grep -rq "class MathExpressionNode" "$COMFYUI_DIR/comfy_extras/" 2>/dev/null || NEED_UPGRADE=1
[ -f "$COMFYUI_DIR/comfy_api/latest/__init__.py" ] || NEED_UPGRADE=1

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
       grep -rq "class ModelAttentionBackend" "$COMFYUI_DIR/comfy_extras/" 2>/dev/null && \
       grep -rq "class SaveVideo" "$COMFYUI_DIR/comfy_extras/" 2>/dev/null && \
       [ -f "$COMFYUI_DIR/comfy_api/latest/__init__.py" ]; then
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
    # BUNNY SelfLift graph packs (see Phases 1e/1f/1g for what each one registers).
    # NOTE: xm6018924/BSAI-ComfyUI-Sol-H3 is deliberately NOT installed here — its
    # SolAttnMiniMax node id is already provided by comfyui-minimax-h3-audio-T8
    # (installed above). Two packs registering one node id makes the winner
    # load-order dependent. Phase 1f clones BSAI only as a fallback.
    comfy node install https://github.com/slmonker/selflift-Avatar 2>/dev/null || true
    comfy node install https://github.com/yichengup/ComfyUI-YCNodes-MiniMax-H3 2>/dev/null || true
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
            comfyui-minimax-h3-prompt-enhancer-T8 \
            selflift-Avatar ComfyUI-YCNodes-MiniMax-H3; do
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

# ── Phase 1e: selflift-Avatar (SelfLiftAvatarH3Sampler / SelfLiftAvatarH3TST) ──
# https://github.com/slmonker/selflift-Avatar — an independent SelfLift branch for
# MiniMax H3 (audio-video latent masks, source-audio preservation, selectable
# high-res spatial tiling). Registers its OWN node ids
# (SelfLiftAvatarH3Sampler, SelfLiftAvatarImageSampler, SelfLiftAvatarH3TST), so it
# coexists with facok's original comfyui-SelfLift without a clash.
# No pip deps ("adds no dependencies"; PROVENANCE.json ships file hashes).
# ⚠️ Keep the clone dir name `selflift-Avatar` — it is what the README documents
# (`git clone ... custom_nodes/selflift-Avatar`) and what users look for on disk.
# Its sampler's `upscaler_model` dropdown lists every filename containing "h3" from
# models/latent_upscale_models/ — which is why the [10/21] step installs the V2 alias.
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
    echo "  ⚠️  selflift-Avatar missing SelfLiftAvatarH3Sampler — the graph will report Missing Node Packs"
fi

# ── Phase 1f: Sol-Attn provider check (SolAttnMiniMax) ──
# The workflow's "Patch Sol-Attn (MiniMax)" node is provided by
# `comfyui-minimax-h3-audio-T8`, installed in Phase 1 — T8mars vendors the same
# single-file node at the pack root (`sol_attn_minimax_v2.py`). Verified live
# 2026-10-13: /object_info's python_module for SolAttnMiniMax =
# `custom_nodes.comfyui-minimax-h3-audio-T8`.
# So xm6018924/BSAI-ComfyUI-Sol-H3 is deliberately NOT installed here: it registers
# the SAME node id, and a second provider makes the winner load-order dependent
# (the two files even differ — bundled 39.6KB vs BSAI 40.9KB / v2.9.2 — while both
# expose an identical 14-widget schema, so the choice is invisible until it isn't).
# This block asserts the class is really present and only then clones BSAI as a
# fallback, so a future audio-T8 that drops the vendored file fails LOUDLY instead
# of shipping a graph with a Missing Node Pack.
echo "==> Verifying the Sol-Attn provider (SolAttnMiniMax)..."
SOLATTN_SRC="$CUSTOM_NODES_DIR/comfyui-minimax-h3-audio-T8/sol_attn_minimax_v2.py"
if grep -q "class SolAttnMiniMax" "$SOLATTN_SRC" 2>/dev/null; then
    echo "  ✅ SolAttnMiniMax provided by comfyui-minimax-h3-audio-T8 (no extra pack needed)"
else
    echo "  ⚠️  comfyui-minimax-h3-audio-T8 no longer vendors SolAttnMiniMax —"
    echo "      falling back to the standalone pack xm6018924/BSAI-ComfyUI-Sol-H3"
    BSAI_REPO="https://github.com/xm6018924/BSAI-ComfyUI-Sol-H3"
    BSAI_DIR="$CUSTOM_NODES_DIR/BSAI-ComfyUI-Sol-H3"
    if command -v comfy >/dev/null 2>&1; then
        comfy node install "$BSAI_REPO" 2>/dev/null || true
    fi
    [ -f "$BSAI_DIR/sol_attn_minimax_v2.py" ] || \
        ( cd "$CUSTOM_NODES_DIR" && git clone --depth=1 "$BSAI_REPO" BSAI-ComfyUI-Sol-H3 ) \
            || echo "  ⚠️  BSAI fallback clone failed (non-fatal)"
    if grep -q "class SolAttnMiniMax" "$BSAI_DIR/sol_attn_minimax_v2.py" 2>/dev/null; then
        echo "  ✅ SolAttnMiniMax present at $BSAI_DIR"
    else
        echo "  ❌ SolAttnMiniMax unavailable from BOTH packs — the graph will report Missing Node Packs."
    fi
fi

# ⚠️ The BSAI repo also ships an install.py that pip-installs comfy_kitchen and
# downloads a ~300MB "FastH3" 4-step LoRA into models/loras/. We never run it — this
# graph brings its own turbo LoRA and takes comfy_kitchen from ComfyUI itself. A
# later ComfyUI-Manager pass may run it; harmless (one extra LoRA on disk).

# ── Sol-Attn runtime prerequisites: comfy_kitchen kernels + triton ──
# SolAttnMiniMax needs comfy_kitchen with the sol_attn sink_blocks / sink_q / tail
# kernels (>= 0.2.37) and Triton 3.6.0+. Both degrade to "falling back" instead of
# raising, so an old kernel shows up as a slower render, not as an error — probe
# explicitly, because the script's green log would otherwise hide it.
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
        if $COMFY_PYTHON -c "from comfy_kitchen.backends import cuda" >/dev/null 2>&1; then
            echo "  ✅ comfy_kitchen upgraded"
        else
            echo "  ⚠️  comfy_kitchen still lacks the Sol-Attn kernels — SolAttnMiniMax falls"
            echo "      back to the dense attention backend (render works, no sparse speedup)."
        fi
        ;;
esac
if $COMFY_PYTHON -c "import triton" >/dev/null 2>&1; then
    echo "  ✅ triton present ($($COMFY_PYTHON -c 'import triton;print(triton.__version__)' 2>/dev/null))"
else
    echo "  ⚠️  triton NOT importable — Sol-Attn wants Triton 3.6.0+; without it SolAttnMiniMax"
    echo "      falls back to dense attention (render works, no sparse speedup)."
fi

# ── Phase 1g: ComfyUI-YCNodes-MiniMax-H3 (H3SigmaRefiner) ──
# https://github.com/yichengup/ComfyUI-YCNodes-MiniMax-H3 — the workflow's
# "H3 refine +1 · total 9 NFE" sigma-refiner node (aux_id yichengup/...).
# Self-loading pack: __init__.py imports every py/*.py and merges the mappings
# (H3SigmaRefiner, H3TiledSampler, H3PromptRelay, H3DistanceAttentionPatcher, ...).
# No requirements.txt and no install.py → nothing to pip-install.
# ⚠️ Its __init__.py sets WEB_DIRECTORY = "./js" while the repo ships no js/ dir;
# ComfyUI logs a harmless "web directory not found" warning. Do not "fix" it by
# creating an empty dir — a later `git pull` in that pack would then conflict.
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
else
    echo "  ⚠️  H3SigmaRefiner missing — the graph will report Missing Node Packs"
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
echo "[1/21] minimax_h3_video_vae_fp16.safetensors (VAE - video)..."
hf_download "Comfy-Org/MiniMax-H3" "vae/minimax_h3_video_vae_fp16.safetensors" "$BASE_DIR"

# ── VAE (audio) ──
echo "[2/21] minimax_h3_audio_vae_fp32.safetensors (VAE - audio)..."
hf_download "Comfy-Org/MiniMax-H3" "vae/minimax_h3_audio_vae_fp32.safetensors" "$BASE_DIR"

# ── Text Encoder ──
echo "[3/21] qwen3vl_32b_minimax_h3_int8_convrot.safetensors (Text Encoder)..."
hf_download "Comfy-Org/MiniMax-H3" "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" "$BASE_DIR"

# ── Diffusion Model ──
# Selected at startup: hybrid fl2va+ref2va int8 by default, Singularity ref2va V2
# int8 via `--interactive` choice 2, FastH3 Omni 8-step via choice 3. One file
# only — see the header for which workflow JSON matches which file.
echo "[4/21] $(basename "$DIFFUSION_FILE") (Diffusion Model)..."
# ⚠️ FastH3 Omni lives at <repo>/diffusion_models/<file>, i.e. DIFFUSION_FILE already
# carries a `diffusion_models/` prefix. hf_download mirrors the repo-relative path,
# so its local_dir must be $BASE_DIR — passing $BASE_DIR/diffusion_models would
# land it at models/diffusion_models/diffusion_models/<file>, on disk but invisible
# to the UNETLoader dropdown. The other two repos ship bare filenames at the root.
if [ "$DIFFUSION_REPO" = "$FASTH3_REPO" ]; then
    DIFFUSION_DEST="$BASE_DIR"
else
    DIFFUSION_DEST="$BASE_DIR/diffusion_models"
fi
hf_download "$DIFFUSION_REPO" "$DIFFUSION_FILE" "$DIFFUSION_DEST"
if [ ! -s "$BASE_DIR/diffusion_models/$(basename "$DIFFUSION_FILE")" ]; then
    echo "  ⚠️  expected models/diffusion_models/$(basename "$DIFFUSION_FILE") — not on disk."
    echo "      The UNETLoader dropdown will not list it; re-run or check the download log."
fi

# ── LoRA: fl2v turbo 4-step v1.2 768p (comfyui) ──
echo "[5/21] minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors (LoRA - fl2v turbo 4-step v1.2 768p)..."
hf_download "lightx2v/Minimax-h3-Turbo" "minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors" "$BASE_DIR/loras"

# ── LoRA: ref2v turbo 8-step 768p (comfyui) ──
echo "[6/21] minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors (LoRA - ref2v turbo 8-step 768p)..."
hf_download "lightx2v/Minimax-h3-Turbo" "minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors" "$BASE_DIR/loras"

# ── LoRA: fl2v lightx2v turbo 4-step ──
echo "[7/21] minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors (LoRA - fl2v turbo 4-step)..."
hf_download "Kijai/MiniMax-H3_comfy" "loras/minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors" "$BASE_DIR"

# ── LoRA: ref2v lightx2v turbo 4-step resized avg rank 20 ──
echo "[8/21] minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors (LoRA - ref2v turbo 4-step rank 20)..."
hf_download "Kijai/MiniMax-H3_comfy" "loras/minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors" "$BASE_DIR"
# ── LoRA: H3 Realism People (fal) ──
echo "[9/21] h3-realism-people-t2v-i2v-r2v.safetensors (LoRA - H3 Realism People)..."
hf_download "fal/MiniMax-H3-Realism-People-LoRA" "h3-realism-people-t2v-i2v-r2v.safetensors" "$BASE_DIR/loras"


# ── Latent Upscale Model ──
# NOTE: HF repo LBH-123-AI/Minimax_h3_latent_Upscaler reshuffled the weights into a
# `minimax_h3_latent_upscaler_3d_conv_v1/` subdir (2026-09). The bare filename 404s.
# Download the nested file then flatten it to the exact name the workflow references
# (minimax_h3_latent_upscaler_3d_fp16.safetensors) so the node's dropdown picks it up.
echo "[10/21] minimax_h3_latent_upscaler_3d_fp16.safetensors (Latent Upscaler 3D, nested repo)..."
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

# ── Upstream-V2 alias for the SelfLift-Avatar upscaler dropdown ──
# The BUNNY workflow's SelfLiftAvatarH3Sampler stores the widget value
# `minimax_h3_latent_upscaler_3d_fp16_V2.safetensors`. LBH-123-AI has NOT released a
# public 3d_conv_v2 checkpoint — its own root config.json registers 3d_conv_v2 as
# `in_training` and the only shipped 3D weights are the v1 fp16/bf16 pair — so "V2" is
# a local rename in the workflow author's workspace. selflift-Avatar picks the first
# filename containing "h3", so the SAME v1 fp16 weights are installed under both names
# and the stored widget value resolves instead of silently falling back to `none`
# (which would disable the learned latent lift the whole SelfLift stage depends on).
TGT_V2="$BASE_DIR/latent_upscale_models/minimax_h3_latent_upscaler_3d_fp16_V2.safetensors"
if [ -s "$TGT" ] && [ ! -s "$TGT_V2" ]; then
    ln "$TGT" "$TGT_V2" 2>/dev/null || cp "$TGT" "$TGT_V2"
    echo "  ✅ v1 fp16 weights also installed as $(basename "$TGT_V2") (workflow widget name)"
fi

# ── Tiny VAE for live preview ──
echo "[11/21] taeh3.safetensors (Tiny VAE - live preview)..."
hf_download "Kijai/MiniMax-H3-TAE" "vae_approx/taeh3.safetensors" "$BASE_DIR"

# ── Semantic Bridge adapter model ──
echo "[12/21] MiniMaxH3_SemanticBridge_v1.safetensors (Semantic Bridge adapter)..."
hf_download "speach1sdef178/MiniMax-H3-Semantic-Bridge" "MiniMaxH3_SemanticBridge_v1.safetensors" "$BASE_DIR/semantic_bridge"

# ── LoRA: ref2v turbo 4-step v0.1 (comfyui) ──
echo "[13/21] minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors (LoRA - ref2v turbo 4-step v0.1)..."
hf_download "lightx2v/Minimax-h3-Turbo" "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors" "$BASE_DIR/loras"

# ── LoRA: General Motion Continuity Repair V2 (JOKER141) ──
# V2 is the rebuilt checkpoint and the one this repo standardises on (the sibling
# Singularity script was switched to it in commit 425d853 "Lora added"). The BUNNY
# graph's node 45 still stores the v1 widget value `Motion_Repair.safetensors`, so the
# v1 name is hardlinked to the V2 file below — one 155MB file on disk, and node 45
# loads instead of erroring on a missing file. Select `Motion_Repair_V2.safetensors`
# in the dropdown to make the choice explicit.
echo "[14/21] Motion_Repair_V2.safetensors (LoRA - General Motion Continuity Repair V2)..."
hf_download "JOKER141/MiniMax-H3-General-Motion-Continuity-Repair" "Motion_Repair_V2.safetensors" "$BASE_DIR/loras"

# ── v1-name alias so the shipped graph loads with no manual dropdown change ──
MR_V1="$BASE_DIR/loras/Motion_Repair.safetensors"
MR_V2="$BASE_DIR/loras/Motion_Repair_V2.safetensors"
if [ -s "$MR_V2" ] && [ ! -s "$MR_V1" ]; then
    ln "$MR_V2" "$MR_V1" 2>/dev/null || cp "$MR_V2" "$MR_V1"
    echo "  ✅ V2 weights also installed as Motion_Repair.safetensors (node 45's stored value)"
fi

# ── LoRA: Combat Base V2 (JOKER141) ──
echo "[15/21] H3_Combat_V2.safetensors (LoRA - Combat Base V2)..."
hf_download "JOKER141/MiniMax-H3-Combat-Base-V2" "H3_Combat_V2.safetensors" "$BASE_DIR/loras"

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
echo "[16/21] BUNNY_H3_ActionLogic_Bridge_V1.safetensors (BUNNY H3 bridge adapter - V1, default)..."
hf_download "JOKER141/BUNNY_H3_Conditioning_Bridge" "BUNNY_H3_ActionLogic_Bridge_V1.safetensors" "$BUNNY_MODELS_DIR"

echo "[17/21] BUNNY_H3_ActionLogic_Bridge_V2.safetensors (BUNNY H3 bridge adapter - V2)..."
hf_download "JOKER141/BUNNY_H3_Conditioning_Bridge" "BUNNY_H3_ActionLogic_Bridge_V2.safetensors" "$BUNNY_MODELS_DIR"

# ── LoRA: DMAD 4-step full (Kijai/MiniMax-H3-experimental, avg rank 39) ──
# The file lives under the repo's `loras/` subdir, so dest is $BASE_DIR — NOT $BASE_DIR/loras.
# The helper mirrors the repo-relative path, so it lands at models/loras/<name>; passing
# $BASE_DIR/loras would nest it as loras/loras/<name> (on disk, but invisible to the dropdown).
# Download-only, like Motion_Repair / Combat V2: no shipped graph references it — add a
# LoraLoaderModelOnly node and select it to use it.
echo "[18/21] minimax_h3_DMAD_4step_full_lora_avg_rank_39_bf16.safetensors (LoRA - DMAD 4-step full)..."
hf_download "Kijai/MiniMax-H3-experimental" "loras/minimax_h3_DMAD_4step_full_lora_avg_rank_39_bf16.safetensors" "$BASE_DIR"

# ── BUNNY SelfLift graph additions (BUNNY_SelfLift_12GB1080P_LORA__1.json) ──
# The three files below are the only model references in the new workflow that the
# Singularity/Semantic-Bridge script did not already cover:
#   node 5  LoraLoaderBypassModelOnly  minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors @0.70
#   node 47 LoraLoaderModelOnly        H3_Fight_Flow_V1.safetensors                                       @0.65
#   node 45 LoraLoaderModelOnly        Motion_Repair.safetensors (v1 widget name — served by the V2 file)  @0.25
# (Everything else — video/audio VAE, qwen3vl text encoder, the int8 hybrid base,
#  Combat V2, the latent upscaler, taeh3 — is already downloaded above.)

# ── LoRA: Turbo v4 step600 EMA pruned (comfyui) ── ("H3 Turbo 加速 LoRA", node 5)
# The workflow loads it through a LoraLoaderBypassModelOnly at strength 0.7 — the
# model-only path, since the H3 int8 UNET has no CLIP half to adapt.
echo "[19/21] minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors (LoRA - Turbo v4 step600 EMA pruned)..."
hf_download "Momoking/MiniMax-H3-Turbo-Lora-ComfyUI" "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors" "$BASE_DIR/loras"

# ── LoRA: H3 Fight Flow V1 (JOKER141 fight-interaction) ── (node 47, strength 0.65)
# Drives unarmed / melee-weapon / gun-fu combat choreography (see the workflow's
# "fight flow LORA" note: "Unarmed combat interaction", "Melee weapon interaction",
# "Gun-fu interaction"). This graph's prompt is a sword-fight sequence, hence 0.65.
echo "[20/21] H3_Fight_Flow_V1.safetensors (LoRA - Fight Flow fight-interaction V1)..."
hf_download "JOKER141/H3-Fight-Flow-Fight-Interaction-LoRA" "H3_Fight_Flow_V1.safetensors" "$BASE_DIR/loras"

# ── LoRA: Superhuman Combat (JOKER141) ──
# https://huggingface.co/JOKER141/H3-superhuman-combat-lora
# The third member of the same author's fight chain, and the only one this graph
# does NOT wire up yet: the checkpoint's own recommended stack is
#   Combat Base V2 0.65 (node 83, graph currently 0.5) + Motion Repair V2 0.35
#   (node 45, graph currently 0.25) + Superhuman Combat 0.65
# — the first two are installed above ([14/21] / [15/21]), so this completes the
# chain for anyone who adds a LoraLoaderModelOnly at ~0.65. It targets explosive
# power / momentum transfer / cinematic superhuman choreography, i.e. exactly the
# "burst speed with weight and consequence" layer that motion repair cannot add.
# Download-only, like Motion_Repair / Combat V2 / DMAD: no shipped graph references
# it, so nothing silently changes for existing renders.
# ⚠️ The upstream filename is misspelled ("SuperHunman", not "Superhuman") — keep it
# verbatim or the download 404s. Renaming it locally would also break the name.
echo "[21/21] SuperHunman.safetensors (LoRA - Superhuman Combat)..."
hf_download "JOKER141/H3-superhuman-combat-lora" "SuperHunman.safetensors" "$BASE_DIR/loras"

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
