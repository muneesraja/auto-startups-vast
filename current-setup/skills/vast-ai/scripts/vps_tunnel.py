#!/usr/bin/env python3
"""
vps_tunnel.py — VPS-side Cloudflare tunnel relay via SSH port-forward.
"""

import os
import sys
import time
from typing import Optional

# Ensure sibling modules are importable when loaded standalone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import log, run_cmd

# Process tracking for teardown: VPS_TUNNEL_PIDS[label] = {"cloudflared": pid, "ssh": pid}
VPS_TUNNEL_PIDS: dict = {}


def setup_vps_tunnel(label: str, cloudflare_config: dict, instance_ssh_host: str, instance_ssh_port: str, ssh_key_path: str) -> Optional[tuple]:
    """Setup VPS-side Cloudflare tunnel relay.

    This script runs ON the VPS. It:
    1. Establishes local SSH port-forward: VPS:<unique_port> -> instance:18188
    2. Writes cloudflared config locally
    3. Starts cloudflared locally pointing to localhost:<unique_port>

    Args:
        label: Instance label.
        cloudflare_config: Dict with tunnel_id, hostname, token.
        instance_ssh_host: SSH host of the Vast.ai instance.
        instance_ssh_port: SSH port of the Vast.ai instance.
        ssh_key_path: Path to SSH private key (passed as param, NOT global).

    Returns (cloudflared_pid, ssh_pid) or None on failure.
    """
    tunnel_id = cloudflare_config.get("tunnel_id", "")
    hostname = cloudflare_config.get("hostname", f"comfy-{label}.muneesraja.com")

    if not tunnel_id:
        log("⚠️", "Cannot setup VPS tunnel: missing tunnel_id")
        return None

    # Derive unique local port from label to support concurrent tunnels
    local_port = str(abs(hash(label)) % 1000 + 18000)  # range: 18000-18999

    # Step 1: Kill any existing SSH port-forward on this port (stale from previous run)
    run_cmd(f"fuser -k {local_port}/tcp 2>/dev/null || true", timeout=5)
    time.sleep(1)

    # Step 2: Establish SSH port-forward (local VPS port <local_port> -> instance port 18188)
    key_param = f"-i {ssh_key_path}" if ssh_key_path else ""
    ssh_fwd_cmd = (
        f"ssh {key_param} -fN "
        f"-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o ServerAliveInterval=60 "
        f"-L {local_port}:localhost:18188 "
        f"-p {instance_ssh_port} root@{instance_ssh_host}"
    )
    log("🔌", f"Establishing SSH port forward: localhost:{local_port} -> {instance_ssh_host}:18188")
    result = run_cmd(ssh_fwd_cmd, timeout=30)
    if result["code"] != 0:
        log("❌", f"SSH port forward failed: {result['stderr']}")
        return None

    # Get SSH tunnel PID
    ssh_pid_result = run_cmd(f"pgrep -f 'ssh -fN.*-L {local_port}:localhost:18188' || true", timeout=5)
    ssh_pid = ssh_pid_result["stdout"].strip().split("\n")[-1] if ssh_pid_result["stdout"].strip() else "unknown"
    log("✅", f"SSH port forward established (PID: {ssh_pid})")

    # Step 1b: Kill Vast.ai quick tunnels inside container (Improvement 3)
    # When using VPS-side tunnel, container-side cloudflared is not needed and may conflict
    key_param = f"-i {ssh_key_path}" if ssh_key_path else ""
    ssh_to_instance = f"ssh {key_param} -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p {instance_ssh_port} root@{instance_ssh_host}"
    kill_result = run_cmd(f'{ssh_to_instance} "pkill -f \'cloudflared tunnel\' 2>/dev/null || true; supervisorctl stop tunnel_manager 2>/dev/null || true"', timeout=15)
    if kill_result["code"] == 0:
        log("🧹", "Killed container-side cloudflared processes (using VPS-side tunnel instead)")

    # Step 3: Verify the port-forward works (ComfyUI reachable locally)
    time.sleep(2)
    check = run_cmd(f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{local_port}/system_stats 2>/dev/null", timeout=10)
    if "200" not in check["stdout"]:
        log("⚠️", f"ComfyUI not reachable via port-forward (HTTP {check['stdout']}) — tunnel may still work once cloudflared connects")

    # Step 4: Write cloudflared config locally on this VPS
    config_dir = f"/tmp/cf-config-{label}"
    config_file = f"{config_dir}/config.yml"
    credentials_file = f"/root/.cloudflared/{tunnel_id}.json"

    if not os.path.exists(credentials_file):
        log("⚠️", f"Tunnel credentials not found at {credentials_file} — tunnel will fail")
        return None

    os.makedirs(config_dir, exist_ok=True)
    config_content = f"""tunnel: {tunnel_id}
credentials-file: {credentials_file}

ingress:
  - hostname: {hostname}
    service: http://localhost:{local_port}
    originRequest:
      noTLSVerify: true
  - service: http_status:404
"""
    with open(config_file, "w") as f:
        f.write(config_content)
    log("📝", f"Cloudflared config written to {config_file}")

    # Step 5: Start cloudflared locally on this VPS in background
    log_file = f"/tmp/cf-{label}.log"
    cf_cmd = f"nohup /usr/bin/cloudflared tunnel --no-tls-verify --config {config_file} run {tunnel_id} > {log_file} 2>&1 &"
    log("🌐", "Starting cloudflared on VPS")
    run_cmd(cf_cmd, timeout=10)

    time.sleep(5)  # Wait for cloudflared to connect

    # Get cloudflared PID
    cf_pid_result = run_cmd(f"pgrep -f 'cloudflared tunnel.*--config.*{config_file}' || true", timeout=5)
    cf_pid = cf_pid_result["stdout"].strip().split("\n")[-1] if cf_pid_result["stdout"].strip() else "unknown"

    if cf_pid != "unknown":
        log("✅", f"cloudflared running on VPS (PID: {cf_pid})")
    else:
        # Check log for errors
        log_result = run_cmd(f"tail -5 {log_file} 2>/dev/null || true", timeout=5)
        if log_result["stdout"].strip():
            log("⚠️", f"cloudflared log: {log_result['stdout'][:300]}")
        log("⚠️", "Could not verify cloudflared PID — tunnel may still be functional")

    # Store PIDs for teardown
    VPS_TUNNEL_PIDS[label] = {
        "cloudflared": cf_pid,
        "ssh": ssh_pid,
        "config_dir": config_dir,
        "log_file": log_file,
        "local_port": local_port,
    }

    return (int(cf_pid) if cf_pid != "unknown" else -1, int(ssh_pid) if ssh_pid != "unknown" else -1)


def verify_tunnel(hostname: str, timeout: int = 30) -> bool:
    """Verify Cloudflare tunnel is accessible from the outside.

    Curls the hostname and checks for HTTP 200.
    Returns True if tunnel is working.
    """
    log("🔍", f"Verifying tunnel accessibility: https://{hostname}")
    start = time.time()
    while time.time() - start < timeout:
        result = run_cmd(
            f"curl -s -o /dev/null -w '%{{http_code}}' https://{hostname}/system_stats 2>/dev/null",
            timeout=10
        )
        if "200" in result["stdout"]:
            log("✅", f"Tunnel verified: https://{hostname} is accessible!")
            return True
        time.sleep(5)

    log("⚠️", f"Tunnel not accessible after {timeout}s — may need manual check")
    return False


def teardown_vps_tunnel(label: str) -> None:
    """Clean up VPS-side tunnel processes for a label.

    Kills both cloudflared and SSH tunnel processes, removes config dir.
    """
    if label not in VPS_TUNNEL_PIDS:
        log("ℹ️", f"No VPS tunnel to tear down for label: {label}")
        return

    pids = VPS_TUNNEL_PIDS[label]
    cf_pid = pids.get("cloudflared", "unknown")
    ssh_pid = pids.get("ssh", "unknown")
    config_dir = pids.get("config_dir", "")
    log_file = pids.get("log_file", "")

    log("🧹", f"Cleaning up VPS tunnel for {label}")

    # Kill cloudflared
    if cf_pid and cf_pid != "unknown":
        run_cmd(f"kill {cf_pid} 2>/dev/null || true", timeout=5)
        log("✅", f"Killed cloudflared (PID: {cf_pid})")

    # Kill SSH port-forward
    if ssh_pid and ssh_pid != "unknown":
        run_cmd(f"kill {ssh_pid} 2>/dev/null || true", timeout=5)
        log("✅", f"Killed SSH port forward (PID: {ssh_pid})")

    # Kill any remaining processes on the tunnel's local port
    local_port = pids.get("local_port", "18188")
    run_cmd(f"fuser -k {local_port}/tcp 2>/dev/null || true", timeout=5)

    # Clean up config directory
    if config_dir and os.path.exists(config_dir):
        run_cmd(f"rm -rf {config_dir}", timeout=5)

    # Clean up log file
    if log_file and os.path.exists(log_file):
        run_cmd(f"rm -f {log_file}", timeout=5)

    del VPS_TUNNEL_PIDS[label]
    log("✅", f"VPS tunnel for {label} cleaned up")
