#!/usr/bin/env python3
"""
workflow.py — Workflow URL resolution, size estimation, and download monitoring.
"""

import re
import sys
import time

# Ensure sibling modules are importable when loaded standalone
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))

from utils import log, run_cmd
from config import WORKFLOW_ALIASES, WORKFLOWS_REPO, WORKFLOWS_BRANCH, WORKFLOWS_PATH


def get_workflow_url(workflow_name: str) -> str:
    """Resolve workflow name/alias to GitHub raw URL."""
    # Check aliases first
    filename = WORKFLOW_ALIASES.get(workflow_name.lower())
    if not filename:
        # Try exact filename match
        if workflow_name.endswith(".sh"):
            filename = workflow_name
        else:
            # Try adding .sh
            filename = f"{workflow_name}.sh"

    return f"https://raw.githubusercontent.com/{WORKFLOWS_REPO}/{WORKFLOWS_BRANCH}/{WORKFLOWS_PATH}/{filename}"


def get_workflow_size(workflow_name: str) -> float:
    """Get workflow download size in GB from frontmatter. Returns 0 if unknown."""
    filename = WORKFLOW_ALIASES.get(workflow_name.lower(), workflow_name)
    if not filename.endswith(".sh"):
        filename += ".sh"

    url = f"https://raw.githubusercontent.com/{WORKFLOWS_REPO}/{WORKFLOWS_BRANCH}/{WORKFLOWS_PATH}/{filename}"
    result = run_cmd(f"curl -sL '{url}' | head -20", timeout=10)
    if result["code"] == 0:
        match = re.search(r"#\s*size:\s*~?([\d.]+)\s*GB", result["stdout"], re.IGNORECASE)
        if match:
            return float(match.group(1))
    return 0


def wait_for_workflow(ssh_url: str, ssh_key_path: str, timeout: int = 600) -> bool:
    """Wait for the onstart workflow script to finish downloading models via SSH.

    Polls /workspace/workflow.log every 30s until it sees 'All downloads completed'
    or 'Done!', or until timeout. Returns True if workflow completed successfully.

    Args:
        ssh_url: SSH URL in ssh://root@host:port format.
        ssh_key_path: Path to SSH private key (passed as param, NOT global).
        timeout: Max seconds to wait.
    """
    if not ssh_url or ssh_url == "N/A":
        log("⚠️", "No SSH URL — skipping workflow wait")
        return False

    log("⏳", f"Waiting for workflow downloads to complete (timeout: {timeout}s)...")

    # Parse SSH URL: ssh://root@host:port
    match = re.match(r'ssh://root@([^:]+):(\d+)', ssh_url)
    if not match:
        log("⚠️", f"Cannot parse SSH URL: {ssh_url}")
        return False

    host, port = match.group(1), match.group(2)
    # Use SSH key if available
    key_param = f"-i {ssh_key_path}" if ssh_key_path else ""
    ssh_cmd = f"ssh {key_param} -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p {port} root@{host}"

    elapsed = 0
    interval = 30
    while elapsed < timeout:
        # Check if workflow process is still running
        result = run_cmd(
            f'{ssh_cmd} "ps aux | grep -v grep | grep \\\\\"workflow.sh\\\\\" | head -1"',
            timeout=15
        )
        output = result.get("stdout", "").strip()

        # Check the log for completion
        log_result = run_cmd(
            f'{ssh_cmd} "tail -5 /workspace/workflow.log 2>/dev/null"',
            timeout=15
        )
        log_output = log_result.get("stdout", "").strip()

        if "All downloads completed" in log_output or "Done!" in log_output:
            log("✅", "Workflow downloads completed successfully")
            return True

        # Show progress
        if log_output:
            last_line = [l for l in log_output.split("\n") if l.strip()][-1]
            log("📥", f"Workflow progress: {last_line}")
        else:
            log("📥", "Workflow log not yet available...")

        # If no workflow process running, check log one more time
        if not output:
            log_result2 = run_cmd(
                f'{ssh_cmd} "tail -5 /workspace/workflow.log 2>/dev/null"',
                timeout=15
            )
            final_log = log_result2.get("stdout", "").strip()
            if "All downloads completed" in final_log or "Done!" in final_log:
                log("✅", "Workflow downloads completed successfully")
                return True
            if "error" in final_log.lower() or "failed" in final_log.lower():
                log("⚠️", f"Workflow may have failed: {final_log[-200:]}")
                return False
            # No process and no completion marker — likely no workflow
            log("ℹ️", "No workflow process running and no completion marker — assuming no workflow")
            return True

        time.sleep(interval)
        elapsed += interval

    log("⚠️", f"Workflow wait timed out after {timeout}s")
    return False
