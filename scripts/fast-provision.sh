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
FRP_INDEX="${FRP_INDEX:-}"
FRP_SERVER_ADDR="${FRP_SERVER_ADDR:-159.195.52.130}"
FRP_SERVER_PORT="${FRP_SERVER_PORT:-7000}"
FRP_TOKEN="${FRP_TOKEN:-}"  # Loaded from env var (set by vastai-provision.py from .env)
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
# [4/8] FRP Tunnel Setup
# =============================================================================
echo "=== [4/8] FRP Tunnel ==="

if [ -n "$FRP_INDEX" ]; then
    echo "FRP_INDEX=$FRP_INDEX — setting up self-hosted FRP tunnel..."
    
    # Calculate domain suffix
    if [ "$FRP_INDEX" = "0" ]; then
        SUFFIX=""
    else
        SUFFIX="$FRP_INDEX"
    fi
    
    COMFY_DOMAIN="comfy${SUFFIX}.lxc.muneesraja.com"
    PORTAL_DOMAIN="instance${SUFFIX}-comfy.lxc.muneesraja.com"
    JUPYTER_DOMAIN="jupyter${SUFFIX}-comfy.lxc.muneesraja.com"
    
    echo "FRP domains: ComfyUI=https://$COMFY_DOMAIN, Portal=https://$PORTAL_DOMAIN, Jupyter=https://$JUPYTER_DOMAIN"
    
    # Install frpc if needed
    if [ ! -x "/usr/local/bin/frpc" ]; then
        echo "Downloading frpc v0.68.1..."
        ARCH=$(uname -m)
        case $ARCH in
            x86_64|amd64) ARCH="amd64" ;;
            aarch64|arm64) ARCH="arm64" ;;
            *) echo "Unsupported arch: $ARCH"; exit 1 ;;
        esac
        curl -sL "https://github.com/fatedier/frp/releases/download/v0.68.1/frp_0.68.1_linux_${ARCH}.tar.gz" | tar xzf - -C /tmp
        mv "/tmp/frp_0.68.1_linux_${ARCH}/frpc" /usr/local/bin/frpc
        chmod +x /usr/local/bin/frpc
        rm -rf "/tmp/frp_0.68.1_linux_${ARCH}"
        echo "✅ frpc installed"
    fi
    
    # Create frpc config
    mkdir -p /etc/frp
    cat > /etc/frp/frpc.toml << EOF
serverAddr = "${FRP_SERVER_ADDR}"
serverPort = ${FRP_SERVER_PORT:-7000}
auth.method = "token"
auth.token = "${FRP_TOKEN}"

[[proxies]]
name = "comfy${SUFFIX}"
type = "http"
localPort = 18188
customDomains = ["${COMFY_DOMAIN}"]

[[proxies]]
name = "portal${SUFFIX}"
type = "http"
localPort = 11111
customDomains = ["${PORTAL_DOMAIN}"]

[[proxies]]
name = "jupyter${SUFFIX}"
type = "http"
localPort = 18080
customDomains = ["${JUPYTER_DOMAIN}"]
EOF
    
    # Start frpc
    pkill frpc 2>/dev/null || true
    /usr/local/bin/frpc -c /etc/frp/frpc.toml > /var/log/frpc.log 2>&1 &
    sleep 2
    
    if pgrep frpc > /dev/null; then
        echo "✅ frpc started (PID $(pgrep frpc))"
    else
        echo "⚠️ FRP client failed to start — falling back to Cloudflare quick tunnels"
        cat /var/log/frpc.log
        FRP_INDEX=""  # Clear so Cloudflare fallback kicks in below
    fi
else
    echo "ℹ️ No FRP_INDEX set — will use Cloudflare quick tunnels."
fi

# Cloudflare quick tunnel fallback (when FRP is not available)
if [ -z "$FRP_INDEX" ]; then
    CLOUDFLARED_BIN=$(which cloudflared 2>/dev/null || echo "/opt/instance-tools/bin/cloudflared")
    if [ -x "$CLOUDFLARED_BIN" ]; then
        echo "Setting up Cloudflare quick tunnels..."
        $CLOUDFLARED_BIN tunnel --no-tls-verify --url http://127.0.0.1:18188 > /tmp/comfy_tunnel.log 2>&1 &
        $CLOUDFLARED_BIN tunnel --no-tls-verify --url http://127.0.0.1:18080 > /tmp/jupyter_tunnel.log 2>&1 &
        sleep 15
        CF_COMFY_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/comfy_tunnel.log 2>/dev/null | tail -1 || echo "")
        CF_JUPYTER_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/jupyter_tunnel.log 2>/dev/null | tail -1 || echo "")
        FRP_STATUS="ComfyUI: ${CF_COMFY_URL:-NOT READY}\nJupyter: ${CF_JUPYTER_URL:-NOT READY}\n(Cloudflare quick tunnels — URLs change on restart)"
        echo "✅ Cloudflare tunnels: ComfyUI=${CF_COMFY_URL:-NOT READY}, Jupyter=${CF_JUPYTER_URL:-NOT READY}"
    else
        echo "⚠️ Neither FRP nor Cloudflare available — use Vast.ai dashboard OPEN button"
        FRP_STATUS="Use Vast.ai dashboard → OPEN button"
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
    curl -sSL "$WORKFLOW_SCRIPT" -o /tmp/workflow.sh
    # Also download the shared HF download helper — workflow scripts source it
    HF_HELPER_URL="$(dirname "$WORKFLOW_SCRIPT")/_hf_download.sh"
    echo "Downloading HF helper: $HF_HELPER_URL"
    curl -sSL "$HF_HELPER_URL" -o /workspace/_hf_download.sh 2>/dev/null || true
    if [ -f "/tmp/workflow.sh" ]; then
        chmod +x /tmp/workflow.sh
        echo "✅ Workflow script downloaded"
        # Run in background — model downloads can take time
        # Source the _hf_download.sh helper first so it's available to the workflow
        nohup bash -c 'source /workspace/_hf_download.sh 2>/dev/null; bash /tmp/workflow.sh' > /workspace/workflow.log 2>&1 &
        WORKFLOW_PID=$!
        echo "✅ Workflow script running in background (PID $WORKFLOW_PID)"
    else
        echo "⚠️ Failed to download workflow script"
    fi
fi

# =============================================================================
# [6/8] Fix Jupyter & Portal, then Start Supervisor
# =============================================================================

# --- Fix Portal: bind 0.0.0.0 instead of 127.0.0.1 ---
# The image's instance_portal.sh uses --host 127.0.0.1, which makes it unreachable via FRP.
PORTAL_SCRIPT="/opt/supervisor-scripts/instance_portal.sh"
if [ -f "$PORTAL_SCRIPT" ]; then
    sed -i 's/--host 127.0.0.1/--host 0.0.0.0/g' "$PORTAL_SCRIPT"
    echo "✅ Patched instance_portal.sh to bind 0.0.0.0"
fi

# --- Fix Jupyter: start plain HTTP on port 18080 ---
# The image starts Jupyter with HTTPS (certfile/keyfile) on port 8080.
# FRP only proxies HTTP, so we need to kill the TLS Jupyter and start a plain-HTTP one on 18080.
# Also update the supervisor config so it doesn't try to restart the TLS version.
JUPYTER_SCRIPT="/opt/supervisor-scripts/jupyter.sh"
if [ -f "$JUPYTER_SCRIPT" ]; then
    # Patch the supervisor script to remove TLS args and change port to 18080
    sed -i 's/--port 8080/--port 18080/g' "$JUPYTER_SCRIPT"
    sed -i 's/--NotebookApp.certfile=[^ ]*//g' "$JUPYTER_SCRIPT"
    sed -i 's/--NotebookApp.keyfile=[^ ]*//g' "$JUPYTER_SCRIPT"
    sed -i 's/--NotebookApp.ip=[^ ]*/--NotebookApp.ip=0.0.0.0/g' "$JUPYTER_SCRIPT"
    # Remove token requirement for convenience (behind FRP tunnel)
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

# FRP_STATUS may already be set by the Cloudflare fallback block above.
# Only override if FRP_INDEX is still set (meaning FRP is active).
if [ -n "$FRP_INDEX" ]; then
    SUFFIX="${FRP_INDEX}"
    if [ "$SUFFIX" = "0" ]; then SUFFIX=""; fi
    FRP_STATUS="ComfyUI: https://comfy${SUFFIX}.lxc.muneesraja.com
Portal: https://instance${SUFFIX}-comfy.lxc.muneesraja.com
Jupyter: https://jupyter${SUFFIX}-comfy.lxc.muneesraja.com"
    TUNNEL_TYPE="FRP"
else
    # FRP_STATUS was set by Cloudflare fallback (or default message)
    FRP_STATUS="${FRP_STATUS:-Use Vast.ai dashboard → OPEN button}"
    TUNNEL_TYPE="Cloudflare"
fi

# --- Notification 1: Server Ready (ComfyUI up, SSH/FRP available) ---
echo "=== [8/8] Notification 1: Server Ready ==="
if [ -n "$DISCORD_WEBHOOK_URL" ]; then
    curl -s -X POST "$DISCORD_WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -H "User-Agent: HermesBot/1.0" \
        -d "{\"content\": \"🟢 **Server Ready**\\n\\n${INSTANCE_INFO}\\n\\n${FRP_STATUS}\\n\\n⏳ Models downloading in background...\"}" \
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
            -d "{\"content\": \"📦 **Models Ready**\\n\\n${INSTANCE_INFO}\\nAll models downloaded ${WORKFLOW_RESULT}\\n\\n${FRP_STATUS}\"}" \
            > /dev/null 2>&1 || true
        echo "✅ Discord notification sent (Models Ready)"
    else
        curl -s -X POST "$DISCORD_WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -H "User-Agent: HermesBot/1.0" \
            -d "{\"content\": \"⚠️ **Models Download Issue**\\n\\n${INSTANCE_INFO}\\nWorkflow exited with issues — check /workspace/workflow.log\\n\\n${FRP_STATUS}\"}" \
            > /dev/null 2>&1 || true
        echo "✅ Discord notification sent (Models Issue)"
    fi
fi

echo "============================================"
echo "  Fast Provisioning Complete!"
echo "============================================"
echo "  ComfyUI port: ${COMFY_PORT:-unknown}"
echo "  Workspace: /workspace/ComfyUI"
echo "  Tunnels: ${TUNNEL_TYPE}"
echo "  Logs: /workspace/workflow.log (if workflow set)"
echo "============================================"