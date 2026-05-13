#!/bin/bash
# =============================================================================
# ComfyUI Provisioning Script (PROVISIONING_SCRIPT)
# =============================================================================
# Called by the vastai/comfy image's entrypoint AFTER ComfyUI is running.
# Handles: system extras, FRP/Cloudflare tunnel, portal fix, workflow, Discord.
#
# Image: vastai/comfy:v0.20.1-cuda-12.9-py312
#
# Environment Variables:
#   DISCORD_WEBHOOK_URL — Discord webhook for notifications
#   WORKFLOW_SCRIPT     — (optional) URL to a workflow download script
#   CF_TUNNEL_TOKEN     — (optional) Cloudflare tunnel token (fallback if FRP not set)
#   FRP_INDEX           — (optional) FRP subdomain index (self-hosted tunneling)
#   FRP_SERVER_ADDR     — FRP server address (default: 159.195.52.130)
#   FRP_SERVER_PORT     — FRP server port (default: 7000)
#   FRP_TOKEN           — FRP auth token
# =============================================================================
set -e

JUPYTER_TOKEN="${OPEN_BUTTON_TOKEN:-1}"

echo "============================================"
echo "  Provisioning Script — Starting"
echo "============================================"

# ── [1/6] System extras ──────────────────────────────────────────────────────
echo "=== [1/6] System extras ==="
apt-get update && apt-get install -y \
  ffmpeg \
  aria2 \
  tmux \
  zip \
  curl \
  wget

# Install huggingface_hub + hf_transfer for fast authenticated downloads
pip install --quiet "huggingface_hub[cli]" hf_transfer 2>/dev/null || \
  pip install --quiet huggingface_hub hf_transfer 2>/dev/null || true

# Save HF token if provided
if [ -n "$HF_TOKEN" ]; then
  mkdir -p /root/config
  echo "{\"huggingface_token\": \"$HF_TOKEN\"}" > /root/config/token.json
  echo "HF token saved to /root/config/token.json"
  export HF_HUB_ENABLE_HF_TRANSFER=1
fi

# ── [2/6] FRP Tunnel (Self-hosted) ────────────────────────────────────────────
echo "=== [2/6] FRP Tunnel ==="
FRP_COMFY_URL=""
FRP_PORTAL_URL=""
FRP_JUPYTER_URL=""

if [ -n "$FRP_INDEX" ]; then
  echo "FRP_INDEX=$FRP_INDEX — setting up self-hosted FRP tunnel..."
  
  # Build subdomain suffix (empty for 0, number for others)
  if [ "$FRP_INDEX" = "0" ]; then
    SUFFIX=""
  else
    SUFFIX="$FRP_INDEX"
  fi
  
  # Build domains
  FRP_COMFY_URL="https://comfy${SUFFIX}.lxc.muneesraja.com"
  FRP_PORTAL_URL="https://instance${SUFFIX}-comfy.lxc.muneesraja.com"
  FRP_JUPYTER_URL="https://jupyter${SUFFIX}-comfy.lxc.muneesraja.com"
  
  echo "FRP domains: ComfyUI=$FRP_COMFY_URL, Portal=$FRP_PORTAL_URL, Jupyter=$FRP_JUPYTER_URL"
  
  # Download frpc binary
  FRP_VERSION="0.68.1"
  FRP_URL="https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_linux_amd64.tar.gz"
  
  if [ ! -x /usr/local/bin/frpc ]; then
    echo "Downloading frpc v${FRP_VERSION}..."
    curl -sL "$FRP_URL" | tar xz -C /tmp "frp_${FRP_VERSION}_linux_amd64/frpc"
    mv "/tmp/frp_${FRP_VERSION}_linux_amd64/frpc" /usr/local/bin/frpc
    chmod +x /usr/local/bin/frpc
    rm -rf "/tmp/frp_${FRP_VERSION}_linux_amd64"
    echo "frpc installed to /usr/local/bin/frpc"
  fi
  
  # Create frpc config
  mkdir -p /etc/frp
  cat > /etc/frp/frpc.toml << EOF
serverAddr = "${FRP_SERVER_ADDR:-159.195.52.130}"
serverPort = ${FRP_SERVER_PORT:-7000}
auth.method = "token"
auth.token = "${FRP_TOKEN}"

[[proxies]]
name = "comfy${SUFFIX}"
type = "http"
localPort = 18188
customDomains = ["comfy${SUFFIX}.lxc.muneesraja.com"]

[[proxies]]
name = "portal${SUFFIX}"
type = "http"
localPort = 11111
customDomains = ["instance${SUFFIX}-comfy.lxc.muneesraja.com"]

[[proxies]]
name = "jupyter${SUFFIX}"
type = "http"
localPort = 8080
customDomains = ["jupyter${SUFFIX}-comfy.lxc.muneesraja.com"]
EOF
  
  # Start frpc in background
  echo "Starting frpc..."
  /usr/local/bin/frpc -c /etc/frp/frpc.toml > /var/log/frpc.log 2>&1 &
  FRPC_PID=$!
  sleep 3
  
  # Verify frpc started
  if kill -0 $FRPC_PID 2>/dev/null; then
    echo "✅ frpc started (PID $FRPC_PID)"
  else
    echo "❌ frpc failed to start — check /var/log/frpc.log"
    cat /var/log/frpc.log
  fi
  
  # Use FRP URLs as primary
  COMFY_URL="$FRP_COMFY_URL"
  PORTAL_URL="$FRP_PORTAL_URL"
  JUPYTER_URL="$FRP_JUPYTER_URL"
  
else
  echo "No FRP_INDEX set — falling back to Cloudflare tunnels."
fi

# ── [3/6] Cloudflare tunnel (fallback) ──────────────────────────────────────
echo "=== [3/6] Cloudflare tunnel ==="
if [ -z "$FRP_INDEX" ]; then
  if [ -n "$CF_TUNNEL_TOKEN" ]; then
    echo "CF_TUNNEL_TOKEN found — installing Cloudflare tunnel..."
    curl -L --output /tmp/cloudflared.deb \
      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
    dpkg -i /tmp/cloudflared.deb || true
    cloudflared service install "$CF_TUNNEL_TOKEN" || true
    rm -f /tmp/cloudflared.deb
    echo "Cloudflare tunnel installed."
  else
    echo "No CF_TUNNEL_TOKEN set — setting up quick tunnels..."
    CLOUDFLARED_BIN=$(which cloudflared 2>/dev/null || echo "/opt/instance-tools/bin/cloudflared")
    if [ -x "$CLOUDFLARED_BIN" ]; then
      echo "Setting up quick tunnels for ComfyUI and Jupyter..."
      $CLOUDFLARED_BIN tunnel --no-tls-verify --url http://127.0.0.1:18188 > /tmp/comfy_tunnel.log 2>&1 &
      $CLOUDFLARED_BIN tunnel --no-tls-verify --url http://127.0.0.1:8080 > /tmp/jupyter_tunnel.log 2>&1 &
      sleep 15
      COMFY_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/comfy_tunnel.log 2>/dev/null | tail -1 || echo "")
      JUPYTER_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/jupyter_tunnel.log 2>/dev/null | tail -1 || echo "")
      echo "Quick tunnels — ComfyUI: ${COMFY_URL:-NOT READY}, Jupyter: ${JUPYTER_URL:-NOT READY}"
    else
      echo "cloudflared not found at ${CLOUDFLARED_BIN} — quick tunnels skipped."
    fi
  fi
else
  echo "FRP tunnel active — skipping Cloudflare setup."
fi

# ── [4/6] Fix Instance Portal tunnel ──────────────────────────────────────────
echo "=== [4/6] Fix Instance Portal tunnel ==="

# Skip if FRP is active
if [ -z "$FRP_INDEX" ]; then
  # Wait for tunnel_manager to create tunnels
  echo "Waiting for tunnels to initialize..."
  for i in $(seq 1 30); do
    if grep -q 'trycloudflare.com' /var/log/portal/tunnel_manager.log 2>/dev/null; then
      echo "Tunnels detected in logs."
      break
    fi
    sleep 2
  done

  # Save tunnel URLs from portal log
  PORTAL_COMFY_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /var/log/portal/tunnel_manager.log 2>/dev/null | sed -n '2p' || echo "")
  PORTAL_JUPYTER_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /var/log/portal/tunnel_manager.log 2>/dev/null | sed -n '3p' || echo "")
  [ -n "$PORTAL_COMFY_URL" ] && COMFY_URL="$PORTAL_COMFY_URL"
  [ -n "$PORTAL_JUPYTER_URL" ] && JUPYTER_URL="$PORTAL_JUPYTER_URL"

  # Test if portal is broken  
  PORTAL_STATUS=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:11111/ 2>/dev/null || echo "000")
  PORTAL_TUNNEL_STATUS=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:1111/ 2>/dev/null || echo "000")
  echo "Portal app on :11111 = ${PORTAL_STATUS}, tunnel on :1111 = ${PORTAL_TUNNEL_STATUS}"

  if [ "$PORTAL_TUNNEL_STATUS" != "200" ] && ([ "$PORTAL_STATUS" = "200" ] || [ "$PORTAL_STATUS" = "302" ]); then
    echo "Portal app is up on :11111 but tunnel on :1111 is broken. Fixing..."
    pkill -f 'cloudflared.*localhost:1111' 2>/dev/null || true
    sleep 2

    CLOUDFLARED_BIN=$(which cloudflared 2>/dev/null || echo "/opt/portal-aio/tunnel_manager/cloudflared")
    $CLOUDFLARED_BIN tunnel --no-tls-verify --url http://127.0.0.1:11111 > /tmp/portal_tunnel_fix.log 2>&1 &

    echo "Waiting for new portal tunnel URL..."
    for i in $(seq 1 20); do
      PORTAL_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/portal_tunnel_fix.log 2>/dev/null | tail -1 || echo "")
      if [ -n "$PORTAL_URL" ]; then
        echo "New portal tunnel: $PORTAL_URL"
        break
      fi
      sleep 2
    done
  else
    echo "Portal tunnel appears OK."
    PORTAL_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /var/log/portal/tunnel_manager.log 2>/dev/null | head -1 || echo "")
  fi
else
  echo "FRP active — portal tunnel already handled by FRP."
fi

# ── [5/6] Workflow script (optional) ─────────────────────────────────────────
echo "=== [5/6] Workflow script ==="
WORKFLOW_STATUS=""
if [ -n "$WORKFLOW_SCRIPT" ]; then
  echo "WORKFLOW_SCRIPT found: $WORKFLOW_SCRIPT"
  curl --fail -sSL "$WORKFLOW_SCRIPT" -o /workspace/workflow-setup.sh
  chmod +x /workspace/workflow-setup.sh

  # Fetch HF download helper
  WORKFLOW_BASE=$(dirname "$WORKFLOW_SCRIPT")
  HF_HELPER_URL="${WORKFLOW_BASE}/hf_download.sh"
  curl --fail -sSL "$HF_HELPER_URL" -o /workspace/hf_download.sh 2>/dev/null && chmod +x /workspace/hf_download.sh && echo "hf_download.sh helper downloaded" || echo "Warning: could not download hf_download.sh helper"

  # Write workflow-completion webhook
  cat > /workspace/workflow-complete.sh << 'WEBSCRIPT'
#!/bin/bash
_notify_workflow_complete() {
  local webhook_url="$1"
  local timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  local payload="{\"embeds\": [{\"title\": \"✅ Workflow Download Complete!\", \"description\": \"All models have been downloaded. ComfyUI is ready to use.\", \"color\": 5763719, \"footer\": {\"text\": \"Aurora • GrowthLabs\"}, \"timestamp\": \"$timestamp\"}]}"
  local sent=false
  local relay_url="https://relay.lxc.muneesraja.com/hook?url=$(echo -n "$webhook_url" | base64 -w0)"

  for attempt in 1 2 3; do
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -H "Content-Type: application/json" -d "$payload" "$webhook_url" 2>/dev/null) || true
    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
      echo "Workflow notification sent! (direct, attempt $attempt)"
      sent=true
      break
    fi
    [ "$attempt" -lt 3 ] && sleep 2
  done

  if [ "$sent" = false ]; then
    for attempt in 1 2 3; do
      http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 -H "Content-Type: application/json" -d "$payload" "$relay_url" 2>/dev/null) || true
      if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo "Workflow notification sent! (relay, attempt $attempt)"
        sent=true
        break
      fi
      [ "$attempt" -lt 3 ] && sleep 3
    done
  fi
  [ "$sent" = false ] && echo "Workflow notification failed (non-critical)."
}
_notify_workflow_complete "$DISCORD_WEBHOOK_URL"
WEBSCRIPT
  chmod +x /workspace/workflow-complete.sh

  # Run in tmux
  tmux kill-session -t workflow 2>/dev/null || true
  tmux new-session -d -s workflow "bash /workspace/workflow-setup.sh 2>&1 | tee /workspace/workflow.log; bash /workspace/workflow-complete.sh"

  WORKFLOW_STATUS="⏳ Workflow models downloading in background (tmux session: \`workflow\`)"
  echo "Workflow script running in background tmux session 'workflow'."
else
  echo "No WORKFLOW_SCRIPT set — skipping."
fi

# ── [6/6] Discord webhook notification ───────────────────────────────────────
echo "=== [6/6] Discord notification ==="

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

  local portal_line=""
  [ -n "$portal_url" ] && portal_line="[🖥️ Instance Portal]($portal_url)"
  local comfy_line=""
  [ -n "$comfy_url" ] && comfy_line="[🎨 ComfyUI]($comfy_url)"
  local jupyter_line=""
  [ -n "$jupyter_url" ] && jupyter_line="[📓 Jupyter]($jupyter_url)"

  local access_lines="${portal_line}"
  [ -n "$comfy_line" ] && access_lines="${access_lines}\\n${comfy_line}"
  [ -n "$jupyter_line" ] && access_lines="${access_lines}\\n${jupyter_line}"
  [ -z "$access_lines" ] && access_lines="Use Vast.ai dashboard → OPEN button"

  local desc="Instance **${label}** is up and running."
  [ -n "$workflow_status" ] && desc="${desc}\\n\\n${workflow_status}"

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

  local sent=false
  local relay_url="https://relay.lxc.muneesraja.com/hook?url=$(echo -n "$webhook_url" | base64 -w0)"

  for attempt in 1 2 3; do
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -H "Content-Type: application/json" -d "$payload" "$webhook_url" 2>/dev/null) || true
    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
      echo "Discord notification sent! (direct, attempt $attempt)"
      sent=true
      break
    fi
    [ "$attempt" -lt 3 ] && sleep 2
  done

  if [ "$sent" = false ]; then
    for attempt in 1 2 3; do
      http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 -H "Content-Type: application/json" -d "$payload" "$relay_url" 2>/dev/null) || true
      if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo "Discord notification sent! (relay, attempt $attempt)"
        sent=true
        break
      fi
      [ "$attempt" -lt 3 ] && sleep 3
    done
  fi

  [ "$sent" = false ] && echo "Discord notification failed (non-critical)."
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