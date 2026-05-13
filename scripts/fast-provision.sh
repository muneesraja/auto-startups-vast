#!/bin/bash
# =============================================================================
# Fast ComfyUI Provisioning Script
# =============================================================================
# This script bypasses the image's slow provisioner and sets up ComfyUI directly.
# Works with vastai/comfy template images.
# =============================================================================

set -e

echo "============================================"
echo "  Fast Provisioning — Starting"
echo "============================================"

# Environment (passed from vastai-provision.py)
FRP_INDEX="${FRP_INDEX:-}"
FRP_SERVER_ADDR="${FRP_SERVER_ADDR:-159.195.52.130}"
FRP_SERVER_PORT="${FRP_SERVER_PORT:-7000}"
FRP_TOKEN="${FRP_TOKEN:-growthlabs-frp-2026-Qwerty123}"
WORKFLOW_SCRIPT="${WORKFLOW_SCRIPT:-}"
HF_TOKEN="${HF_TOKEN:-}"
DISCORD_WEBHOOK_URL="${DISCORD_WEBHOOK_URL:-}"

# =============================================================================
# [1/7] Wait for SSH
# =============================================================================
echo "=== [1/7] Waiting for SSH ==="
for i in {1..30}; do
    if timeout 3 bash -c "echo > /dev/tcp/127.0.0.1/22" 2>/dev/null; then
        echo "✅ SSH ready"
        break
    fi
    echo "Waiting... $i"
    sleep 2
done

# =============================================================================
# [2/7] Fast Workspace Setup
# =============================================================================
echo "=== [2/7] Workspace Setup ==="

# Create /workspace if it doesn't exist
mkdir -p /workspace

# Create workspace symlink if needed
if [ ! -e "/workspace/ComfyUI" ] && [ -d "/opt/workspace-internal/ComfyUI" ]; then
    rm -rf /workspace/ComfyUI 2>/dev/null || true
    ln -sf /opt/workspace-internal/ComfyUI /workspace/ComfyUI
    echo "✅ Linked /opt/workspace-internal/ComfyUI -> /workspace/ComfyUI"
elif [ -d "/opt/workspace-internal/ComfyUI" ]; then
    echo "✅ ComfyUI already available at /workspace/ComfyUI"
fi

# Create portal config (indented format for grep compatibility)
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
EOF
echo "✅ Created /etc/portal.yaml"

# Remove provisioning marker if exists
rm -f /.provisioning 2>/dev/null || true

# =============================================================================
# [3/7] FRP Tunnel Setup
# =============================================================================
echo "=== [3/7] FRP Tunnel ==="

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
        echo "❌ frpc failed to start — check /var/log/frpc.log"
        cat /var/log/frpc.log
    fi
else
    echo "No FRP_INDEX set — skipping FRP setup"
fi

# =============================================================================
# [4/7] Start Supervisor
# =============================================================================
echo "=== [4/7] Starting Supervisor ==="

if pgrep supervisord > /dev/null; then
    echo "Supervisor already running"
else
    # Start supervisord if config exists
    if [ -f /etc/supervisor/supervisord.conf ]; then
        supervisord -c /etc/supervisor/supervisord.conf
        echo "✅ Supervisor started"
    else
        echo "⚠️ No supervisor config found"
    fi
fi

# =============================================================================
# [5/7] Install Requirements
# =============================================================================
echo "=== [5/7] Installing Requirements ==="

if [ -f "/venv/main/bin/pip" ] && [ -d "/workspace/ComfyUI" ]; then
    echo "Installing ComfyUI requirements..."
    /venv/main/bin/pip install -q sqlalchemy 2>/dev/null || true
    cd /workspace/ComfyUI
    /venv/main/bin/pip install -q -r requirements.txt 2>/dev/null || echo "⚠️ Some requirements may have failed"
    echo "✅ Requirements installed"
else
    echo "⚠️ No venv found — skipping pip install"
fi

# =============================================================================
# [6/7] Restart Services
# =============================================================================
echo "=== [6/7] Restarting Services ==="

# Wait for portal.yaml to be read
sleep 2

# Restart supervisor services if available
if command -v supervisorctl &> /dev/null; then
    supervisorctl restart comfyui jupyter instance_portal 2>/dev/null || true
    echo "✅ Services restarted"
fi

# =============================================================================
# [7/7] Wait for ComfyUI
# =============================================================================
echo "=== [7/7] Waiting for ComfyUI ==="

for i in {1..60}; do
    if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:18188" 2>/dev/null | grep -q "200\|404"; then
        echo "✅ ComfyUI is responding on port 18188"
        break
    fi
    echo "Waiting... $i"
    sleep 2
done

# =============================================================================
# Discord Notification
# =============================================================================
if [ -n "$DISCORD_WEBHOOK_URL" ]; then
    FRP_STATUS=""
    if [ -n "$FRP_INDEX" ]; then
        SUFFIX="${FRP_INDEX}"
        if [ "$SUFFIX" = "0" ]; then SUFFIX=""; fi
        FRP_STATUS="ComfyUI: https://comfy${SUFFIX}.lxc.muneesraja.com
Portal: https://instance${SUFFIX}-comfy.lxc.muneesraja.com
Jupyter: https://jupyter${SUFFIX}-comfy.lxc.muneesraja.com"
    fi
    
    curl -s -X POST "$DISCORD_WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "{\"content\": \"🚀 **Server Ready**\\n\\nInstance: $(hostname)\\n${FRP_STATUS}\\n\\nFast provisioning complete!\"}" \
        > /dev/null 2>&1 || true
fi

echo "============================================"
echo "  Fast Provisioning Complete!"
echo "============================================"