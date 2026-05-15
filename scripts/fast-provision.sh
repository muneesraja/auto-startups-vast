#!/bin/bash
# =============================================================================
# Fast ComfyUI Provisioning Script
# =============================================================================
# This script bypasses the image's slow provisioner and sets up ComfyUI directly.
# Works with vastai/comfy template images.
#
# CRITICAL: This runs as --onstart-cmd, which means the image's normal
# PROVISIONING_SCRIPT flow is skipped. We must handle:
#   1. Workspace symlink (/opt/workspace-internal/ComfyUI -> /workspace/ComfyUI)
#   2. /.provisioning marker removal (so comfyui.sh doesn't hang)
#   3. Supervisor startup AFTER workspace is ready
# =============================================================================

set -e

echo "============================================"
echo "  Fast Provisioning — Starting"
echo "============================================"

# Environment (passed from vastai-provision.py)
CF_TUNNEL_TOKEN="${CF_TUNNEL_TOKEN:-}"
CF_TUNNEL_HOSTNAME="${CF_TUNNEL_HOSTNAME:-}"
WORKFLOW_SCRIPT="${WORKFLOW_SCRIPT:-}"
HF_TOKEN="${HF_TOKEN:-}"
DISCORD_WEBHOOK_URL="${DISCORD_WEBHOOK_URL:-}"

# =============================================================================
# [1/8] Wait for SSH
# =============================================================================
echo "=== [1/8] Waiting for SSH ==="
for i in {1..30}; do
    if timeout 3 bash -c "echo > /dev/tcp/127.0.0.1/22" 2>/dev/null; then
        echo "✅ SSH ready"
        break
    fi
    echo "Waiting... $i"
    sleep 2
done

# =============================================================================
# [2/8] Workspace Setup (MUST happen before supervisord starts ComfyUI)
# =============================================================================
echo "=== [2/8] Workspace Setup ==="

# Create /workspace if it doesn't exist
mkdir -p /workspace

# Create workspace symlink if needed
# The image stores ComfyUI at /opt/workspace-internal/ComfyUI
# but $WORKSPACE=/workspace, so comfyui.sh looks for /workspace/ComfyUI
if [ ! -e "/workspace/ComfyUI" ] && [ -d "/opt/workspace-internal/ComfyUI" ]; then
    rm -rf /workspace/ComfyUI 2>/dev/null || true
    ln -sf /opt/workspace-internal/ComfyUI /workspace/ComfyUI
    echo "✅ Linked /opt/workspace-internal/ComfyUI -> /workspace/ComfyUI"
elif [ -d "/opt/workspace-internal/ComfyUI" ]; then
    echo "✅ ComfyUI already available at /workspace/ComfyUI"
fi

# Create portal config (indented format for grep compatibility)
# NOTE: Must include "instance portal" (with space) in addition to "instance_portal"
# (with underscore) because the image's exit_portal.sh greps for the PROC_NAME which
# is "instance portal" with a space. Without the space form, the grep check fails and
# the portal process is skipped.
mkdir -p /etc/portal
cat > /etc/portal.yaml << 'EOF'
# Portal configuration
services:
  comfyui:
    enabled: true
    port: 18188
  jupyter:
    enabled: true
    port: 18080
  instance_portal:
    enabled: true
    port: 11111
  instance portal:
    enabled: true
EOF
echo "✅ Created /etc/portal.yaml"

# Remove provisioning marker — this is CRITICAL.
# Without this, comfyui.sh will loop forever waiting for external provisioning.
# The image creates /.provisioning early; we must remove it so supervisord
# can start ComfyUI without hanging on the wait loop in comfyui.sh.
rm -f /.provisioning 2>/dev/null || true
echo "✅ Removed /.provisioning marker"

# =============================================================================
# [3/8] System Packages
# =============================================================================
echo "=== [3/8] System Packages ==="

apt-get update -qq && apt-get install -y -qq ffmpeg aria2 tmux zip curl wget > /dev/null 2>&1 || true
echo "✅ System packages installed"

# =============================================================================
# [4/8] Cloudflared Named Tunnel Setup
# =============================================================================
echo "=== [4/8] Cloudflared Named Tunnel ==="

TUNNEL_STATUS="Vast.ai OPEN button (no tunnel configured)"
TUNNEL_TYPE="None"

if [ -n "$CF_TUNNEL_TOKEN" ] && [ -n "$CF_TUNNEL_HOSTNAME" ]; then
    echo "CF_TUNNEL_TOKEN set — setting up Cloudflare named tunnel..."
    echo "Hostname: $CF_TUNNEL_HOSTNAME"
    
    CLOUDFLARED_BIN="/usr/local/bin/cloudflared"
    
    # Install cloudflared if needed
    if [ ! -x "$CLOUDFLARED_BIN" ]; then
        echo "Downloading cloudflared..."
        curl -sL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" \
          -o "$CLOUDFLARED_BIN"
        chmod +x "$CLOUDFLARED_BIN"
        echo "✅ cloudflared installed"
    fi
    
    # Write credentials from token
    mkdir -p /root/.cloudflared
    echo "$CF_TUNNEL_TOKEN" | base64 -d > /root/.cloudflared/creds.json 2>/dev/null || {
        echo "⚠️ Failed to decode CF_TUNNEL_TOKEN — trying as plain token"
        # For short-lived tokens (not base64), write directly
        echo "$CF_TUNNEL_TOKEN" > /root/.cloudflared/token.txt
    }
    
    # Start tunnel with token
    pkill -f "cloudflared tunnel" 2>/dev/null || true
    
    if [ -f /root/.cloudflared/creds.json ] && [ -s /root/.cloudflared/creds.json ]; then
        # Has credentials JSON — extract tunnel ID and run
        TUNNEL_ID=$(jq -r '.TunnelID // empty' /root/.cloudflared/creds.json 2>/dev/null)
        if [ -n "$TUNNEL_ID" ]; then
            nohup "$CLOUDFLARED_BIN" tunnel run "$TUNNEL_ID" \
              > /var/log/cloudflared.log 2>&1 &
        else
            nohup "$CLOUDFLARED_BIN" tunnel run --token "$CF_TUNNEL_TOKEN" \
              > /var/log/cloudflared.log 2>&1 &
        fi
    else
        # Use token directly
        nohup "$CLOUDFLARED_BIN" tunnel run --token "$CF_TUNNEL_TOKEN" \
          > /var/log/cloudflared.log 2>&1 &
    fi
    
    sleep 5
    
    if pgrep -f "cloudflared tunnel" > /dev/null; then
        echo "✅ cloudflared started (PID $(pgrep -f 'cloudflared tunnel'))"
        TUNNEL_STATUS="🔗 ComfyUI: https://${CF_TUNNEL_HOSTNAME}"
        TUNNEL_TYPE="Cloudflare"
    else
        echo "⚠️ cloudflared failed to start — falling back to quick tunnels"
        cat /var/log/cloudflared.log 2>/dev/null || true
        CF_TUNNEL_TOKEN=""  # Clear so quick tunnel fallback kicks in
    fi
fi

# Cloudflare quick tunnel fallback (when named tunnel is not available)
if [ -z "$CF_TUNNEL_TOKEN" ]; then
    CLOUDFLARED_QT=$(which cloudflared 2>/dev/null || echo "/opt/instance-tools/bin/cloudflared")
    if [ -x "$CLOUDFLARED_QT" ]; then
        echo "Setting up Cloudflare quick tunnels..."
        nohup "$CLOUDFLARED_QT" tunnel --no-tls-verify --url http://127.0.0.1:18188 \
          > /tmp/comfy_tunnel.log 2>&1 &
        nohup "$CLOUDFLARED_QT" tunnel --no-tls-verify --url http://127.0.0.1:18080 \
          > /tmp/jupyter_tunnel.log 2>&1 &
        sleep 15
        CF_COMFY_URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/comfy_tunnel.log 2>/dev/null | tail -1 || echo "")
        CF_JUPYTER_URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/jupyter_tunnel.log 2>/dev/null | tail -1 || echo "")
        TUNNEL_STATUS="ComfyUI: ${CF_COMFY_URL:-NOT READY}\nJupyter: ${CF_JUPYTER_URL:-NOT READY}\n(Cloudflare quick tunnels — URLs change on restart)"
        TUNNEL_TYPE="Cloudflare-Quick"
        echo "✅ Quick tunnels: ComfyUI=${CF_COMFY_URL:-NOT READY}, Jupyter=${CF_JUPYTER_URL:-NOT READY}"
    else
        echo "⚠️ cloudflared not available — use Vast.ai dashboard OPEN button"
        TUNNEL_STATUS="Use Vast.ai dashboard → OPEN button"
        TUNNEL_TYPE="None"
    fi
fi

# =============================================================================
# [5/8] HF Token & Workflow
# =============================================================================
echo "=== [5/8] HF Token & Workflow ==="

# Save HF token if provided
if [ -n "$HF_TOKEN" ]; then
    mkdir -p /root/config
    echo "{\"huggingface_token\": \"$HF_TOKEN\"}" > /root/config/token.json
    export HF_HUB_ENABLE_HF_TRANSFER=1
    echo "✅ HF token saved"
fi

# Run workflow script if provided
WORKFLOW_PID=""
if [ -n "$WORKFLOW_SCRIPT" ]; then
    echo "Downloading workflow script: $WORKFLOW_SCRIPT"
    curl -sSL "$WORKFLOW_SCRIPT" -o /workspace/workflow-setup.sh
    
    # Download the shared HF download helper — workflow scripts need hf_download() function
    HF_HELPER_URL="$(dirname "$WORKFLOW_SCRIPT")/_hf_download.sh"
    echo "Downloading HF helper: $HF_HELPER_URL"
    curl -sSL "$HF_HELPER_URL" -o /workspace/_hf_download.sh
    
    if [ ! -f "/workspace/_hf_download.sh" ]; then
        echo "❌ FATAL: Failed to download _hf_download.sh — workflow cannot run without it"
        echo "   URL attempted: $HF_HELPER_URL"
    elif [ ! -f "/workspace/workflow-setup.sh" ]; then
        echo "❌ Failed to download workflow script"
    else
        chmod +x /workspace/workflow-setup.sh /workspace/_hf_download.sh
        echo "✅ Workflow + helper downloaded"
        
        # Run in background — source helper first so hf_download() is available,
        # then source (not bash) the workflow so it inherits the function
        nohup bash -c '
            source /workspace/_hf_download.sh
            source /workspace/workflow-setup.sh
        ' > /workspace/workflow.log 2>&1 &
        WORKFLOW_PID=$!
        echo "✅ Workflow running in background (PID $WORKFLOW_PID)"
    fi
fi

# =============================================================================
# [6/8] Fix Jupyter & Portal, then Start Supervisor
# =============================================================================

# --- Fix Portal: bind 0.0.0.0 instead of 127.0.0.1 ---
# The image's instance_portal.sh uses --host 127.0.0.1, which makes it unreachable via tunnels.
PORTAL_SCRIPT="/opt/supervisor-scripts/instance_portal.sh"
if [ -f "$PORTAL_SCRIPT" ]; then
    sed -i 's/--host 127.0.0.1/--host 0.0.0.0/g' "$PORTAL_SCRIPT"
    echo "✅ Patched instance_portal.sh to bind 0.0.0.0"
fi

# --- Fix Jupyter: start plain HTTP on port 18080 ---
# The image starts Jupyter with HTTPS (certfile/keyfile) on port 8080.
# Cloudflare/proxy only forwards HTTP, so we need a plain-HTTP one on 18080.
# Also update the supervisor config so it doesn't try to restart the TLS version.
JUPYTER_SCRIPT="/opt/supervisor-scripts/jupyter.sh"
if [ -f "$JUPYTER_SCRIPT" ]; then
    # Patch the supervisor script to remove TLS args and change port to 18080
    sed -i 's/--port 8080/--port 18080/g' "$JUPYTER_SCRIPT"
    sed -i 's/--NotebookApp.certfile=[^ ]*//g' "$JUPYTER_SCRIPT"
    sed -i 's/--NotebookApp.keyfile=[^ ]*//g' "$JUPYTER_SCRIPT"
    sed -i 's/--NotebookApp.ip=[^ ]*/--NotebookApp.ip=0.0.0.0/g' "$JUPYTER_SCRIPT"
    # Remove token requirement for convenience (behind Cloudflare tunnel)
    sed -i 's/--NotebookApp.token=[^ ]*/--NotebookApp.token=/g' "$JUPYTER_SCRIPT"
    sed -i 's/--NotebookApp.password=[^ ]*/--NotebookApp.password=/g' "$JUPYTER_SCRIPT"
    echo "✅ Patched jupyter.sh for plain HTTP on port 18080"
elif [ -f "/etc/supervisor/conf.d/jupyter.conf" ] || [ -f "/etc/supervisor/conf.d/jupyter.ini" ]; then
    # Alternative: patch supervisor config directly
    for f in /etc/supervisor/conf.d/jupyter.*; do
        if [ -f "$f" ]; then
            sed -i 's/--port 8080/--port 18080/g' "$f"
            sed -i 's/--NotebookApp.certfile=[^ ]*//g' "$f"
            sed -i 's/--NotebookApp.keyfile=[^ ]*//g' "$f"
            echo "✅ Patched $f"
        fi
    done
fi
echo "=== [6/8] Starting Supervisor ==="

# supervisord may already be running from image init, or may need starting.
# Only start if not running — never kill it (PID 1 manages it).
if pgrep supervisord > /dev/null; then
    echo "Supervisor already running — restarting ComfyUI with new workspace"
    # Remove provisioning marker again (supervisor may have recreated it)
    rm -f /.provisioning 2>/dev/null || true
    supervisorctl restart comfyui 2>/dev/null || true
    echo "✅ ComfyUI restarted with workspace"
else
    if [ -f /etc/supervisor/supervisord.conf ]; then
        supervisord -c /etc/supervisor/supervisord.conf
        echo "✅ Supervisor started"
    else
        echo "⚠️ No supervisor config found — will try manual start"
    fi
fi

# =============================================================================
# [7/8] Wait for ComfyUI
# =============================================================================
echo "=== [7/8] Waiting for ComfyUI ==="

# Try port 18188 (image default) first, then 8188 (fallback)
COMFY_PORT=""
for i in {1..60}; do
    for port in 18188 8188; do
        if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${port}" 2>/dev/null | grep -q "200\|404"; then
            COMFY_PORT=$port
            break 2
        fi
    done
    echo "Waiting... $i"
    sleep 2
done

if [ -n "$COMFY_PORT" ]; then
    echo "✅ ComfyUI is responding on port $COMFY_PORT"
else
    echo "⚠️ ComfyUI did not respond within 120s — manual check required"
fi

# =============================================================================
# [8/8] Notifications — Server Ready + Models Ready
# =============================================================================

INSTANCE_INFO="Instance: $(hostname)"

# TUNNEL_STATUS may already be set by the cloudflared block above.
TUNNEL_STATUS="${TUNNEL_STATUS:-Use Vast.ai dashboard → OPEN button}"
TUNNEL_TYPE="${TUNNEL_TYPE:-None}"

# --- Notification 1: Server Ready (ComfyUI up, SSH / tunnel available) ---
echo "=== [8/8] Notification 1: Server Ready ==="
if [ -n "$DISCORD_WEBHOOK_URL" ]; then
    curl -s -X POST "$DISCORD_WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -H "User-Agent: HermesBot/1.0" \
        -d "{\"content\": \"🟢 **Server Ready**\\n\\n${INSTANCE_INFO}\\n\\n${TUNNEL_STATUS}\\n\\n⏳ Models downloading in background...\"}" \
        > /dev/null 2>&1 || true
    echo "✅ Discord notification sent (Server Ready)"
fi

# --- Wait for workflow downloads, then notify Models Ready ---
if [ -n "$WORKFLOW_PID" ] && kill -0 "$WORKFLOW_PID" 2>/dev/null; then
    echo "⏳ Waiting for workflow download to complete (PID $WORKFLOW_PID)..."
    # Poll every 10s, show progress from log
    LAST_LINE=""
    while kill -0 "$WORKFLOW_PID" 2>/dev/null; do
        CURRENT_LINE="$(tail -1 /workspace/workflow.log 2>/dev/null)"
        if [ "$CURRENT_LINE" != "$LAST_LINE" ]; then
            echo "  $CURRENT_LINE"
            LAST_LINE="$CURRENT_LINE"
        fi
        sleep 10
    done
    # Wait a moment for the process to fully exit and flush output
    wait "$WORKFLOW_PID" 2>/dev/null || true
    EXIT_CODE=$?
    if [ "$EXIT_CODE" -eq 0 ]; then
        echo "✅ Workflow download completed successfully"
        WORKFLOW_RESULT="✅"
    else
        echo "⚠️ Workflow download exited with code $EXIT_CODE — check /workspace/workflow.log"
        WORKFLOW_RESULT="⚠️"
    fi
else
    WORKFLOW_RESULT=""
fi

# --- Notification 2: Models Ready ---
if [ -n "$DISCORD_WEBHOOK_URL" ] && [ -n "$WORKFLOW_PID" ]; then
    if [ "$WORKFLOW_RESULT" = "✅" ]; then
        curl -s -X POST "$DISCORD_WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -H "User-Agent: HermesBot/1.0" \
            -d "{\"content\": \"📦 **Models Ready**\\n\\n${INSTANCE_INFO}\\nAll models downloaded ${WORKFLOW_RESULT}\\n\\n${TUNNEL_STATUS}\"}" \
            > /dev/null 2>&1 || true
        echo "✅ Discord notification sent (Models Ready)"
    else
        curl -s -X POST "$DISCORD_WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -H "User-Agent: HermesBot/1.0" \
            -d "{\"content\": \"⚠️ **Models Download Issue**\\n\\n${INSTANCE_INFO}\\nWorkflow exited with issues — check /workspace/workflow.log\\n\\n${TUNNEL_STATUS}\"}" \
            > /dev/null 2>&1 || true
        echo "✅ Discord notification sent (Models Issue)"
    fi
fi

echo "============================================"
echo "  Fast Provisioning Complete!"
echo "============================================"
echo "  ComfyUI port: ${COMFY_PORT:-unknown}"
echo "  Workspace: /workspace/ComfyUI"
echo "  Tunnels: ${TUNNEL_TYPE:-None}"
echo "  Logs: /workspace/workflow.log (if workflow set)"
echo "============================================"