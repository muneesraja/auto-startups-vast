#!/usr/bin/env python3
"""
monitoring.py — Instance status monitoring and health checks.
"""

import os
import re
import sys
import time
from typing import Optional

# Ensure sibling modules are importable when loaded standalone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import log, run_cmd
from client import get_client
from offers import _detect_permanent_failure, save_failed_host


def monitor_instance(instance_id: int, timeout: int = 600, host_id: int = 0) -> bool:
    """Monitor instance until it's running. Returns True if successful.

    Proactively checks status_msg on every poll — not just when loading.
    This catches CDI/OCI runtime errors that appear even in "created" status.
    """
    vast = get_client()

    log("⏳", f"Monitoring instance {instance_id} (timeout: {timeout}s)...")

    start_time = time.time()
    last_status = ""
    last_status_time = start_time  # Track when we entered current status

    while time.time() - start_time < timeout:
        try:
            data = vast.show_instance(id=instance_id)
        except Exception as e:
            log("⚠️", f"Failed to check status: {e}")
            time.sleep(10)
            continue

        if not isinstance(data, dict):
            time.sleep(10)
            continue

        actual_status = data.get("actual_status", "unknown")
        duration = data.get("duration", 0)
        status_msg = str(data.get("status_msg", "")).strip()

        # Log status transitions
        if actual_status != last_status:
            elapsed = int(time.time() - start_time)
            log("📊", f"Status: {actual_status} (duration: {duration}s, elapsed: {elapsed}s)")
            if status_msg and status_msg != "Error: failed to start containers: C." + str(instance_id):
                log("📝", f"Status message: {status_msg[:200]}")
            last_status = actual_status
            last_status_time = time.time()

        # SUCCESS: instance is running
        if actual_status == "running":
            log("✅", "Instance is running!")
            return True

        # === PROACTIVE FAILURE DETECTION (every poll, every status) ===
        is_permanent, failure_reason = _detect_permanent_failure(data)
        if is_permanent:
            log("❌", failure_reason)
            if status_msg:
                log("📋", f"Full error: {status_msg[:300]}")
            if host_id:
                save_failed_host(host_id, data)
            return False

        # === STUCK STATUS DETECTION ===
        time_in_status = time.time() - last_status_time

        # "created" with no progress after 90s = host agent is dead or Docker is failing
        if actual_status == "created" and time_in_status > 90:
            log("❌", f"Instance stuck in 'created' for {int(time_in_status)}s — host agent not responding, destroying and retrying")
            if host_id:
                save_failed_host(host_id, data)
            return False

        # "loading" with no Docker progress after 120s — check daemon logs
        if actual_status == "loading" and time_in_status > 120:
            # Check daemon logs for Docker failure via SDK
            try:
                log_output = vast.logs(instance_id=instance_id, daemon_logs=True) or ""
            except Exception:
                log_output = ""

            failure_reason = None
            if "No such container" in log_output:
                failure_reason = "Docker daemon failure — container never created"
            elif "instance_extra_logs/C." in log_output and "No such file" in log_output:
                failure_reason = "Host agent (kaalia) broken — can't create instance data"
            elif "image" in log_output.lower() and ("pull" in log_output.lower() or "not found" in log_output.lower()):
                failure_reason = "Docker image pull failed"

            if failure_reason:
                log("❌", f"{failure_reason}")
                log("📋", f"Host agent logs: {log_output[:300]}")
                if host_id:
                    save_failed_host(host_id)
                return False

        # "loading" for 300s+ with no progress = host is dead
        if actual_status == "loading" and time_in_status > 300:
            log("❌", f"Instance stuck loading for {int(time_in_status)}s — host agent likely broken")
            if host_id:
                save_failed_host(host_id)
            return False

        time.sleep(15)

    log("❌", f"Timeout after {timeout}s")
    if host_id:
        try:
            final_data = vast.show_instance(id=instance_id)
            if isinstance(final_data, dict):
                save_failed_host(host_id, final_data)
        except Exception:
            save_failed_host(host_id)
    return False


def get_instance_info(instance_id: int) -> dict:
    """Get instance details after it's running via SDK."""
    vast = get_client()
    try:
        data = vast.show_instance(id=instance_id)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        log("⚠️", f"get_instance_info failed: {e}")
        return {}


def health_check_instance(instance_id: int, ssh_key_path: str, timeout: int = 120) -> bool:
    """Post-provision health check: verify ComfyUI is responding via SSH.

    Checks that:
    1. /workspace/ComfyUI exists (workspace symlink)
    2. ComfyUI is responding on port 8188 or 18188
    3. If not, attempt manual fix and retry

    Args:
        instance_id: Vast.ai instance ID.
        ssh_key_path: Path to SSH private key (passed as param, NOT global).
        timeout: Max seconds to wait for ComfyUI to respond.
    """
    vast = get_client()

    log("🏥", f"Running health check on instance {instance_id}...")

    # Get SSH URL via SDK
    try:
        ssh_url = vast.ssh_url(id=instance_id)
    except Exception as e:
        log("⚠️", f"Cannot get SSH URL for health check: {e}")
        return False

    if not ssh_url:
        log("⚠️", "SSH URL is empty — instance may not be ready yet")
        return False

    # Parse ssh://root@host:port returned by vast.ssh_url()
    match = re.match(r"ssh://root@([^:]+):(\d+)", ssh_url)
    if not match:
        log("⚠️", f"Cannot parse SSH URL: {ssh_url}")
        return False

    ssh_host, ssh_port = match.group(1), match.group(2)
    # Use SSH key if available
    key_param = f"-i {ssh_key_path}" if ssh_key_path else ""
    ssh_cmd = f"ssh {key_param} -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p {ssh_port} root@{ssh_host}"

    # Check 1: Workspace symlink
    log("🔍", "Checking /workspace/ComfyUI...")
    result = run_cmd(f'{ssh_cmd} "ls -la /workspace/ComfyUI 2>/dev/null || echo MISSING"', timeout=15)
    if "MISSING" in result["stdout"]:
        log("⚠️", "/workspace/ComfyUI missing — attempting fix...")
        run_cmd(f'{ssh_cmd} "mkdir -p /workspace && ln -sf /opt/workspace-internal/ComfyUI /workspace/ComfyUI"', timeout=15)
        log("✅", "Created symlink /opt/workspace-internal/ComfyUI -> /workspace/ComfyUI")
    else:
        log("✅", "/workspace/ComfyUI exists")

    # Check 2: ComfyUI responding
    log("🔍", "Checking if ComfyUI is responding...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        result = run_cmd(f'{ssh_cmd} "curl -s -o /dev/null -w \'%{{http_code}}\' http://localhost:8188/system_stats 2>/dev/null || curl -s -o /dev/null -w \'%{{http_code}}\' http://localhost:18188/system_stats 2>/dev/null"', timeout=15)
        if "200" in result["stdout"]:
            log("✅", "ComfyUI is responding!")
            return True
        time.sleep(10)

    # Auto-fix: restart ComfyUI via supervisor
    log("⚠️", f"ComfyUI not responding after {timeout}s — attempting restart...")
    run_cmd(f'{ssh_cmd} "supervisorctl restart comfyui 2>/dev/null || true"', timeout=15)
    time.sleep(15)

    result = run_cmd(f'{ssh_cmd} "curl -s -o /dev/null -w \'%{{http_code}}\' http://localhost:8188/system_stats 2>/dev/null"', timeout=15)
    if "200" in result["stdout"]:
        log("✅", "ComfyUI responding after restart!")
        return True

    log("❌", "Health check failed — ComfyUI not responding")
    return False
