#!/usr/bin/env bash
# quickstart_auth.sh — Auth + connectivity one-shot for ComfyUI workers.
#
# Usage:
#   bash quickstart_auth.sh
#
# Behavior:
#   1. Sources /root/.hermes/.env to load COMFYUI_AUTH (combined user:pass token)
#      OR COMFYUI_URL + COMFYUI_USER + COMFYUI_PASS (split form).
#   2. Exits 1 with a clear error if neither form is available.
#   3. Calls /system_stats on the tunnel with Basic auth.
#   4. Prints the JSON response and exits 0 on success.
#
# Why this exists:
#   In the 2026-06-11 panda-pippin T3 run, the worker spent ~15 turns discovering
#   the correct auth header and 80+ turns debugging a Python f-string with
#   embedded double quotes (the classic f-string-with-quotes SyntaxError loop).
#   This script replaces BOTH discoveries with one command.
#
# After this returns 0, the worker can safely call:
#   python3 -c "from comfyui_api import curl_json; print(curl_json('GET', '/object_info', 'URL', auth=('USER', 'PASS')))"

set -eu

ENV_FILE="/root/.hermes/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "❌ $ENV_FILE not found. ComfyUI credentials live there."
  exit 1
fi

# shellcheck disable=SC1090
set -a
. "$ENV_FILE"
set +a

# Resolve URL. CLI arg > env COMFYUI_URL > env COMFYUI_HOST (legacy).
URL="${1:-${COMFYUI_URL:-${COMFYUI_HOST:-}}}"
if [ -z "$URL" ]; then
  echo "❌ COMFYUI_URL (or COMFYUI_HOST) is not set in $ENV_FILE and no URL passed as arg."
  echo "   Usage: $0 https://your-comfyui.trycloudflare.com"
  exit 1
fi

# Resolve user:pass.
# Two forms supported:
#   1) COMFYUI_AUTH = "user:pass"   (combined, has a colon)
#   2) COMFYUI_AUTH = "token"        (raw token; user from COMFYUI_USER, default "vastai")
#   3) COMFYUI_USER + COMFYUI_PASS  (split vars; fall back)
USER_VAL=""
PASS_VAL=""
if [ -n "${COMFYUI_AUTH:-}" ] && [[ "$COMFYUI_AUTH" == *:* ]]; then
  # Form 1: combined user:pass
  USER_VAL="${COMFYUI_AUTH%%:*}"
  PASS_VAL="${COMFYUI_AUTH#*:}"
elif [ -n "${COMFYUI_AUTH:-}" ]; then
  # Form 2: raw token; use COMFYUI_USER (default "vastai") as the username
  USER_VAL="${COMFYUI_USER:-vastai}"
  PASS_VAL="$COMFYUI_AUTH"
elif [ -n "${COMFYUI_USER:-}" ] && [ -n "${COMFYUI_PASS:-}" ]; then
  # Form 3: split vars
  USER_VAL="$COMFYUI_USER"
  PASS_VAL="$COMFYUI_PASS"
else
  echo "❌ No auth in $ENV_FILE. Need COMFYUI_AUTH (combined or token), or COMFYUI_USER + COMFYUI_PASS."
  exit 1
fi

# Strip trailing slash — Cloudflare 301s on /object_info/ with an HTML body
# that json.loads chokes on. (Lesson from 2026-06-05, t_beb4767d.)
URL="${URL%/}"

# Redact the user for display (don't print the full token).
USER_DISPLAY="${USER_VAL:0:4}***"
echo "🔍 Testing $URL with user '$USER_DISPLAY'..."
TMPBODY=$(mktemp)
HTTP_CODE=$(curl -sS -o "$TMPBODY" -w "%{http_code}" \
  -u "${USER_VAL}:${PASS_VAL}" \
  "${URL}/system_stats" 2>/dev/null) || HTTP_CODE="000"
BODY=$(cat "$TMPBODY" 2>/dev/null || echo "")
rm -f "$TMPBODY"

if [ "$HTTP_CODE" = "200" ]; then
  echo "✅ Auth OK (HTTP 200). /system_stats response:"
  echo "$BODY" | head -c 500
  echo ""
  echo ""
  echo "👉 Use this Python pattern for further calls:"
  echo "   import sys"
  echo "   sys.path.insert(0, '/root/.hermes/skills/creative/story-to-video-filmmaking/scripts')"
  echo "   from comfyui_api import curl_json, wait_for_prompt, download_output"
  echo "   AUTH = ('$USER_VAL', '***')"
  echo "   URL = '$URL'"
  exit 0
else
  echo "❌ HTTP $HTTP_CODE — check URL, username, password, and that the tunnel is alive."
  echo "Body: $BODY"
  exit 1
fi
