#!/bin/bash
# =============================================================================
# ComfyUI Provisioning Script (PROVISIONING_SCRIPT)
# =============================================================================
# Called by the vastai/comfy image's entrypoint AFTER ComfyUI is running.
# Handles: system extras, portal tunnel fix, workflow script, Discord webhook.
#
# Image: vastai/comfy:v0.18.2-cuda-12.9-py312
#
# Environment Variables:
#   DISCORD_WEBHOOK_URL — Discord webhook for notifications
#   WORKFLOW_SCRIPT     — (optional) URL to a workflow download script
#   CF_TUNNEL_TOKEN     — (optional) Cloudflare tunnel token
# =============================================================================
set -e

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
  echo "No CF_TUNNEL_TOKEN set — skipping Cloudflare tunnel."
fi

# ── [3/5] Fix Instance Portal tunnel (known vastai/comfy image bug) ──────────
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

# Save ComfyUI and Jupyter tunnel URLs BEFORE killing anything
COMFY_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /var/log/portal/tunnel_manager.log 2>/dev/null | sed -n '2p' || echo "")
JUPYTER_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /var/log/portal/tunnel_manager.log 2>/dev/null | sed -n '3p' || echo "")

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
  curl -sSL "$WORKFLOW_SCRIPT" -o /workspace/workflow-setup.sh
  chmod +x /workspace/workflow-setup.sh

  # Run in tmux (background) so it doesn't block the webhook
  tmux new-session -d -s workflow "bash /workspace/workflow-setup.sh 2>&1 | tee /workspace/workflow.log; \
    curl -s -H 'Content-Type: application/json' \
    -d '{\"embeds\": [{\"title\": \"✅ Workflow Download Complete!\", \"description\": \"All models have been downloaded. ComfyUI is ready to use.\", \"color\": 5763719, \"footer\": {\"text\": \"Aurora • GrowthLabs\"}, \"timestamp\": \"'\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"'\"}]}' \
    "$DISCORD_WEBHOOK_URL" 2>/dev/null || true"

  WORKFLOW_STATUS="⏳ Workflow models downloading in background (tmux session: \`workflow\`)"
  echo "Workflow script running in background tmux session 'workflow'."
else
  echo "No WORKFLOW_SCRIPT set — skipping."
  WORKFLOW_STATUS=""
fi

# ── [5/5] Discord webhook notification ───────────────────────────────────────
echo "=== [5/5] Discord notification ==="

if [ -n "$DISCORD_WEBHOOK_URL" ]; then
  GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo "Unknown")
  VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1 || echo "Unknown")
  PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "Unknown")
  LABEL="${VAST_CONTAINERLABEL:-GPU Server}"

  # Build access lines
  PORTAL_LINE=""
  [ -n "$PORTAL_URL" ] && PORTAL_LINE="[🖥️ Instance Portal](${PORTAL_URL})"
  COMFY_LINE=""
  [ -n "$COMFY_URL" ] && COMFY_LINE="[🎨 ComfyUI](${COMFY_URL})"
  JUPYTER_LINE=""
  [ -n "$JUPYTER_URL" ] && JUPYTER_LINE="[📓 Jupyter](${JUPYTER_URL})"

  ACCESS_LINES="${PORTAL_LINE}"
  [ -n "$COMFY_LINE" ] && ACCESS_LINES="${ACCESS_LINES}\\n${COMFY_LINE}"
  [ -n "$JUPYTER_LINE" ] && ACCESS_LINES="${ACCESS_LINES}\\n${JUPYTER_LINE}"
  [ -z "$ACCESS_LINES" ] && ACCESS_LINES="Use Vast.ai dashboard → OPEN button"

  # Build description with optional workflow status
  DESC="Instance **${LABEL}** is up and running."
  [ -n "$WORKFLOW_STATUS" ] && DESC="${DESC}\\n\\n${WORKFLOW_STATUS}"

  curl -s -H "Content-Type: application/json" \
    -d "{
      \"embeds\": [{
        \"title\": \"🟢 GPU Server Ready!\",
        \"description\": \"${DESC}\",
        \"color\": 5763719,
        \"fields\": [
          {\"name\": \"🖥️ GPU\", \"value\": \"${GPU_NAME}\", \"inline\": true},
          {\"name\": \"💾 VRAM\", \"value\": \"${VRAM}\", \"inline\": true},
          {\"name\": \"🌐 IP\", \"value\": \"\`${PUBLIC_IP}\`\", \"inline\": true},
          {\"name\": \"Access\", \"value\": \"${ACCESS_LINES}\", \"inline\": false},
          {\"name\": \"🔑 Login\", \"value\": \"User: \`vastai\` — Password: \`${JUPYTER_TOKEN}\`\", \"inline\": false}
        ],
        \"footer\": {\"text\": \"Provisioned via Aurora • GrowthLabs\"},
        \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
      }]
    }" \
    "$DISCORD_WEBHOOK_URL" && echo "Discord notification sent!" || echo "Discord notification failed (non-critical)."
else
  echo "No DISCORD_WEBHOOK_URL set — skipping notification."
fi

echo "============================================"
echo "  Provisioning complete"
echo "  Portal:  ${PORTAL_URL:-N/A}"
echo "  ComfyUI: ${COMFY_URL:-N/A}"
echo "  Jupyter: ${JUPYTER_URL:-N/A}"
echo "============================================"
