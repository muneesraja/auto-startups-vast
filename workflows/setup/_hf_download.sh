#!/bin/bash
# =============================================================================
# _hf_download.sh — Shared HuggingFace download helper
# =============================================================================
# Source this from workflow scripts: source /workspace/_hf_download.sh
#
# Provides: hf_download REPO_ID FILENAME LOCAL_DIR
# - Authenticated with HF token (uncapped speed)
# - Uses hf_transfer for maximum throughput
# - Automatic resume on failure
# =============================================================================
# NOTE: Do NOT use set -euo pipefail here — this file is source'd into workflow
# scripts, and those flags would kill the entire parent process on any failure.

# Activate ComfyUI venv if available (hf/huggingface_hub need torch)
# Paths: RunPod standard /venv/main → RunPod slim /workspace/runpod-slim/ComfyUI/.venv-cu128
#        → Vast.ai /workspace/ComfyUI/.venv-cu128 (legacy)
for VENV in \
  /venv/main/bin/activate \
  /workspace/runpod-slim/ComfyUI/.venv-cu128/bin/activate \
  /workspace/ComfyUI/.venv-cu128/bin/activate; do
  [ -f "$VENV" ] && source "$VENV" && break
done

# Load HF token: explicit env var → RunPod secret → JSON config files
# RunPod Secrets inject as RUNPOD_SECRET_HF_TOKEN (not HF_TOKEN)
HF_TOKEN="${HF_TOKEN:-}"
if [ -z "$HF_TOKEN" ] && [ -n "${RUNPOD_SECRET_HF_TOKEN:-}" ]; then
    HF_TOKEN="$RUNPOD_SECRET_HF_TOKEN"
    echo "HF token loaded from RunPod secret (RUNPOD_SECRET_HF_TOKEN)"
fi
if [ -z "$HF_TOKEN" ]; then
    for TOKEN_PATH in /root/config/token.json /workspace/config/token.json; do
      if [ -f "$TOKEN_PATH" ]; then
        HF_TOKEN=$(python3 -c "import json; print(json.load(open('$TOKEN_PATH'))['huggingface_token'])" 2>/dev/null || true)
        if [ -n "$HF_TOKEN" ]; then
          echo "HF token loaded from $TOKEN_PATH"
          break
        fi
      fi
    done
fi

if [ -z "$HF_TOKEN" ]; then
  echo "⚠️  No HF token found — downloads will be rate-limited (10.4 MB/s)"
else
  echo "✅ HF token available"
fi

# Enable Xet high-performance transfer (replaces deprecated hf_transfer)
export HF_XET_HIGH_PERFORMANCE=1

# Download function: hf_download REPO_ID FILENAME LOCAL_DIR
hf_download() {
  local repo_id="$1"
  local filename="$2"
  local local_dir="$3"
  local token_flag=""

  [ -n "$HF_TOKEN" ] && token_flag="--token $HF_TOKEN"

  mkdir -p "$local_dir"

  python3 << PYEOF
import os, time, sys
from huggingface_hub import hf_hub_download

os.environ['HF_XET_HIGH_PERFORMANCE'] = '1'

token = "$HF_TOKEN" or None
repo_id = "$repo_id"
filename = "$filename"
local_dir = "$local_dir"

start = time.time()
try:
    hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=local_dir,
        token=token,
    )
    elapsed = time.time() - start
    size = os.path.getsize(os.path.join(local_dir, filename))
    speed = size / elapsed / 1024 / 1024
    print(f"✅ {filename} — {size/1024/1024:.0f}MB in {elapsed:.1f}s ({speed:.0f} MB/s)")
except Exception as e:
    print(f"❌ Failed: {filename} — {e}", file=sys.stderr)
    sys.exit(1)
PYEOF
}

echo "hf_download helper loaded"
