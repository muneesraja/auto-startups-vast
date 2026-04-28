#!/bin/bash
# =============================================================================
# ComfyUI Provisioning Script (PROVISIONING_SCRIPT)
# =============================================================================
# Called by the vastai/comfy image's entrypoint AFTER ComfyUI is running.
# Handles: system extras, portal tunnel fix, workflow script, Discord webhook.
#
# Image: vastai/comfy:v0.19.3-cuda-13.2-py312
#
# Environment Variables:
#   DISCORD_WEBHOOK_URL — Discord webhook for notifications
#   WORKFLOW_SCRIPT     — (optional) URL to a workflow download script
#   CF_TUNNEL_TOKEN     — (optional) Cloudflare tunnel token
# =============================================================================
set -e

# JUPYTER_TOKEN: vastai passes this as OPEN_BUTTON_TOKEN env var
JUPYTER_TOKEN="${OPEN_BUTTON_TOKEN:-${JUPYTER_TOKEN:-}}"

echo "============================================"
echo "  Provisioning Script — Starting"
echo "============================================"

# ── [1/5] System extras ──────────────────────────────────────────────────────
echo "=== [1/5] System extras ==="
apt-get update && apt-get install -y \
  ffmpeg \
  aria2 \
  tmux \
  zip

# ── [2/5] Cloudflare tunnel (optional) ──────────────────────────────────────
echo "=== [2/5] Cloudflare tunnel ==="
if [ -n "$CF_TUNNEL_TOKEN" ]; then
  echo "CF_TUNNEL_TOKEN found — installing Cloudflare tunnel..."
  curl -L --output /tmp/cloudflared.deb \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
  dpkg -i /tmp/cloudflared.deb || true
  cloudflared service install "$CF_TUNNEL_TOKEN" || true
  rm -f /tmp/cloudflared.deb
  echo "Cloudflare tunnel installed."
else
  echo "No CF_TUNNEL_TOKEN set — skipping Cloudflare tunnel service."
  # Always set up quick tunnels so ComfyUI and Jupyter URLs are available for the Discord webhook.
  CLOUDFLARED_BIN=$(which cloudflared 2>/dev/null || echo "/opt/instance-tools/bin/cloudflared")
  if [ -x "$CLOUDFLARED_BIN" ]; then
    echo "Setting up quick tunnels for ComfyUI and Jupyter..."
    nohup $CLOUDFLARED_BIN tunnel --no-tls-verify --url http://127.0.0.1:18188 > /tmp/comfy_tunnel.log 2>&1 &
    nohup $CLOUDFLARED_BIN tunnel --no-tls-verify --url http://127.0.0.1:8080 > /tmp/jupyter_tunnel.log 2>&1 &
    sleep 15
    COMFY_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/comfy_tunnel.log 2>/dev/null | tail -1 || echo "")
    JUPYTER_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/jupyter_tunnel.log 2>/dev/null | tail -1 || echo "")
    echo "Quick tunnels — ComfyUI: ${COMFY_URL:-NOT READY}, Jupyter: ${JUPYTER_URL:-NOT READY}"
  else
    echo "cloudflared not found at ${CLOUDFLARED_BIN} — quick tunnels skipped."
  fi
fi

echo "=== [3/5] Fix Instance Portal tunnel (known vastai/comfy image bug) ==="
# NOTE: If CF_TUNNEL_TOKEN was absent, COMFY_URL and JUPYTER_URL are already set from quick tunnels above.
echo "=== [3/5] Fix portal tunnel ==="

# Wait for tunnel_manager to create tunnels
echo "Waiting for tunnels to initialize..."
for i in $(seq 1 30); do
  if grep -q 'trycloudflare.com' /var/log/portal/tunnel_manager.log 2>/dev/null; then
    echo "Tunnels detected in logs."
    break
  fi
  sleep 2
done

# Save ComfyUI and Jupyter tunnel URLs — only from portal log if present, otherwise keep quick tunnel values
PORTAL_COMFY_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /var/log/portal/tunnel_manager.log 2>/dev/null | sed -n '2p' || echo "")
PORTAL_JUPYTER_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /var/log/portal/tunnel_manager.log 2>/dev/null | sed -n '3p' || echo "")
[ -n "$PORTAL_COMFY_URL" ] && COMFY_URL="$PORTAL_COMFY_URL"
[ -n "$PORTAL_JUPYTER_URL" ] && JUPYTER_URL="$PORTAL_JUPYTER_URL"

# Test if portal is broken (tunnel on :1111, app on :11111)
PORTAL_STATUS=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:11111/ 2>/dev/null || echo "000")
PORTAL_TUNNEL_STATUS=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:1111/ 2>/dev/null || echo "000")
echo "Portal app on :11111 = ${PORTAL_STATUS}, tunnel on :1111 = ${PORTAL_TUNNEL_STATUS}"

if [ "$PORTAL_TUNNEL_STATUS" != "200" ] && ([ "$PORTAL_STATUS" = "200" ] || [ "$PORTAL_STATUS" = "302" ]); then
  echo "Portal app is up on :11111 but tunnel on :1111 is broken. Fixing..."
  pkill -f 'cloudflared.*localhost:1111' 2>/dev/null || true
  sleep 2

  CLOUDFLARED_BIN=$(which cloudflared 2>/dev/null || echo "/opt/portal-aio/tunnel_manager/cloudflared")
  nohup $CLOUDFLARED_BIN tunnel --no-tls-verify --url http://127.0.0.1:11111 > /tmp/portal_tunnel_fix.log 2>&1 &

  echo "Waiting for new portal tunnel URL..."
  PORTAL_URL=""
  for i in $(seq 1 20); do
    PORTAL_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/portal_tunnel_fix.log 2>/dev/null | tail -1 || echo "")
    if [ -n "$PORTAL_URL" ]; then
      echo "New portal tunnel: $PORTAL_URL"
      break
    fi
    sleep 2
  done
else
  echo "Portal tunnel appears OK. No fix needed."
  PORTAL_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /var/log/portal/tunnel_manager.log 2>/dev/null | head -1 || echo "")
fi

# ── [4/5] Workflow script (optional) ─────────────────────────────────────────
echo "=== [4/5] Workflow script ==="
WORKFLOW_STATUS=""
if [ -n "$WORKFLOW_SCRIPT" ]; then
  echo "WORKFLOW_SCRIPT found: $WORKFLOW_SCRIPT"
  curl --fail -sSL "$WORKFLOW_SCRIPT" -o /workspace/workflow-setup.sh
  chmod +x /workspace/workflow-setup.sh

  # Write workflow-completion webhook as a separate script with full retry/relay support
  # (tmux session runs in a subprocess — bake all needed values via sed)
  WEBHOOK_URL="${DISCORD_WEBHOOK_URL}"
  cat > /workspace/workflow-complete.sh << 'WEBSCRIPT'
#!/bin/bash
# Workflow-completion webhook — implements full retry + LXC relay fallback
_notify_workflow_complete() {
  local webhook_url="$1"
  local timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  local payload="{\"embeds\": [{\"title\": \"✅ Workflow Download Complete!\", \"description\": \"All models have been downloaded. ComfyUI is ready to use.\", \"color\": 5763719, \"footer\": {\"text\": \"Aurora • GrowthLabs\"}, \"timestamp\": \"$timestamp\"}]}"
  local sent=false
  local relay_url="https://relay.lxc.muneesraja.com/hook?url=$(echo -n "$webhook_url" | base64 -w0)"

  # Retry direct 3 times with backoff
  for attempt in 1 2 3; do
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
      -H "Content-Type: application/json" \
      -d "$payload" \
      "$webhook_url" 2>/dev/null) || true
    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
      echo "Workflow notification sent! (direct, attempt $attempt, http=$http_code)"
      sent=true
      break
    fi
    if [ "$attempt" -lt 3 ]; then
echo "Direct send failed (http=$http_code), not retrying. (attempt $attempt/3)"
      sleep 2
    else
      echo "Direct send failed (http=$http_code), not retrying. (attempt $attempt/3)"
    fi
  done

  # Fallback to LXC relay
  if [ "$sent" = false ]; then
    for attempt in 1 2 3; do
      local http_code
      http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 \
        -H "Content-Type: application/json" \
        -d "$payload" \
        "$relay_url" 2>/dev/null) || true
      if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo "Workflow notification sent! (relay, attempt $attempt, http=$http_code)"
        sent=true
        break
      fi
      if [ "$attempt" -lt 3 ]; then
echo "Relay send failed (http=$http_code), not retrying. (attempt $attempt/3)"
        sleep 3
      else
        echo "Relay send failed (http=$http_code), not retrying. (attempt $attempt/3)"
      fi
    done
  fi
  if [ "$sent" = false ]; then
    echo "Workflow notification failed (non-critical)."
  fi
}
_notify_workflow_complete "$WEBHOOK_URL_PLACEHOLDER"
WEBSCRIPT
  sed -i "s|WEBHOOK_URL_PLACEHOLDER|${WEBHOOK_URL}|" /workspace/workflow-complete.sh
  chmod +x /workspace/workflow-complete.sh

  # Run in tmux (background)
  tmux kill-session -t workflow 2>/dev/null || true
  tmux new-session -d -s workflow "bash /workspace/workflow-setup.sh 2>&1 | tee /workspace/workflow.log; bash /workspace/workflow-complete.sh"

  WORKFLOW_STATUS="⏳ Workflow models downloading in background (tmux session: \`workflow\`)"
  echo "Workflow script running in background tmux session 'workflow'."
else
  echo "No WORKFLOW_SCRIPT set — skipping."
  WORKFLOW_STATUS=""
fi

# ── [5/5] Discord webhook notification ───────────────────────────────────────
echo "=== [5/5] Discord notification ==="

_notify_discord() {
  local webhook_url="$1"
  local gpu_name="$2"
  local vram="$3"
  local public_ip="$4"
  local label="$5"
  local portal_url="$6"
  local comfy_url="$7"
  local jupyter_url="$8"
  local workflow_status="$9"
  local jupyter_token="${10}"

  # Build access lines
  local portal_line=""
  [ -n "$portal_url" ] && portal_line="[🖥️ Instance Portal](${portal_url})"
  local comfy_line=""
  [ -n "$comfy_url" ] && comfy_line="[🎨 ComfyUI](${comfy_url})"
  local jupyter_line=""
  [ -n "$jupyter_url" ] && jupyter_line="[📓 Jupyter](${jupyter_url})"

  local access_lines="${portal_line}"
  [ -n "$comfy_line" ] && access_lines="${access_lines}\\n${comfy_line}"
  [ -n "$jupyter_line" ] && access_lines="${access_lines}\\n${jupyter_line}"
  [ -z "$access_lines" ] && access_lines="Use Vast.ai dashboard → OPEN button"

  # Build description with optional workflow status
  local desc="Instance **${label}** is up and running."
  [ -n "$workflow_status" ] && desc="${desc}\\n\\n${workflow_status}"

  # Build Discord payload
  local timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  local payload="{
    \"embeds\": [{
      \"title\": \"🟢 GPU Server Ready!\",
      \"description\": \"${desc}\",
      \"color\": 5763719,
      \"fields\": [
        {\"name\": \"🖥️ GPU\", \"value\": \"${gpu_name}\", \"inline\": true},
        {\"name\": \"💾 VRAM\", \"value\": \"${vram}\", \"inline\": true},
        {\"name\": \"🌐 IP\", \"value\": \"\`${public_ip}\`\", \"inline\": true},
        {\"name\": \"Access\", \"value\": \"${access_lines}\", \"inline\": false},
        {\"name\": \"🔑 Login\", \"value\": \"User: \`vastai\` — Password: \`${jupyter_token}\`\", \"inline\": false}
      ],
      \"footer\": {\"text\": \"Provisioned via Aurora • GrowthLabs\"},
      \"timestamp\": \"${timestamp}\"
    }]
  }"

  # Try direct to Discord first (with retry), then fallback to LXC relay
  # IMPORTANT: We only want ONE successful send. Once sent=true, stop.
  # Use http_code >= 200 && < 300 as success criterion (2xx only).
  local sent=false
  local relay_url="https://relay.lxc.muneesraja.com/hook?url=$(echo -n "$webhook_url" | base64 -w0)"

  # Retry direct 3 times with backoff — stop immediately on first success
  for attempt in 1 2 3; do
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
      -H "Content-Type: application/json" \
      -d "$payload" \
      "$webhook_url" 2>/dev/null) || true
    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
      echo "Discord notification sent! (direct, attempt $attempt, http=$http_code)"
      sent=true
      break
    fi
    if [ "$attempt" -lt 3 ]; then
      echo "Direct send failed (http=$http_code), retrying in 2s... (attempt $attempt/3)"
      sleep 2
    else
      echo "Direct send failed (http=$http_code), not retrying. (attempt $attempt/3)"
    fi
  done

  # Fallback to LXC relay (handles regionally blocked Discord hosts)
  if [ "$sent" = false ]; then
    for attempt in 1 2 3; do
      local http_code
      http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 \
        -H "Content-Type: application/json" \
        -d "$payload" \
        "$relay_url" 2>/dev/null) || true
      if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo "Discord notification sent! (relay, attempt $attempt, http=$http_code)"
        sent=true
        break
      fi
      if [ "$attempt" -lt 3 ]; then
        echo "Relay send failed (http=$http_code), retrying in 3s... (attempt $attempt/3)"
        sleep 3
      else
        echo "Relay send failed (http=$http_code), not retrying. (attempt $attempt/3)"
      fi
    done
  fi

  if [ "$sent" = false ]; then
    echo "Discord notification failed (non-critical)."
  fi
}

if [ -n "$DISCORD_WEBHOOK_URL" ]; then
  GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo "Unknown")
  VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1 || echo "Unknown")
  PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "Unknown")
  LABEL="${VAST_CONTAINERLABEL:-GPU Server}"
  _notify_discord "$DISCORD_WEBHOOK_URL" "$GPU_NAME" "$VRAM" "$PUBLIC_IP" "$LABEL" "$PORTAL_URL" "$COMFY_URL" "$JUPYTER_URL" "$WORKFLOW_STATUS" "$JUPYTER_TOKEN"
else
  echo "No DISCORD_WEBHOOK_URL set — skipping notification."
fi

echo "============================================"
echo "  Provisioning complete"
echo "  Portal:  ${PORTAL_URL:-N/A}"
echo "  ComfyUI: ${COMFY_URL:-N/A}"
echo "  Jupyter: ${JUPYTER_URL:-N/A}"
echo "============================================"
