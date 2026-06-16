#!/usr/bin/env python3
"""
runpod-provision.py - RunPod Community Cloud GPU pod provisioning.

Usage:
  python3 runpod-provision.py --gpu 3090 --label mandi
  python3 runpod-provision.py --gpu 3090 --workflow prompt_relay_ltx23_test_02 --label mandi --auto
  python3 runpod-provision.py --gpu 3090 --workflow wan22 --label balaji --dry-run

This script uses only Python stdlib and runpodctl.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


DEFAULT_IMAGE = "runpod/comfyui:latest"
DEFAULT_TEMPLATE_ID = "cw3nka7d08"  # ComfyUI template
DEFAULT_PORTS = "8188/http,22/tcp,8080/http"
DEFAULT_CONTAINER_DISK_GB = 150
DEFAULT_VOLUME_GB = 0
HF_TOKEN_PATH = "/root/config/token.json"
SSH_KEY_PATH = "/root/.runpod/ssh/RunPod-Key-Go"
WORKFLOWS_REPO = "muneesraja/auto-startups-vast"
WORKFLOWS_BRANCH = "main"
WORKFLOWS_PATH = "workflows/setup"
BOOTSTRAP_URL = (
    f"https://raw.githubusercontent.com/{WORKFLOWS_REPO}/"
    f"{WORKFLOWS_BRANCH}/scripts/comfyui-bootstrap.sh"
)

# HF download helper script to upload to pods
HF_DOWNLOAD_HELPER = r'''#!/bin/bash
# HuggingFace download helper — uses hf CLI (fastest) with aria2c fallback
hf_download() {
  local repo="$1"
  local filename="$2"
  local dest_dir="$3"
  echo "  Downloading: $repo/$filename -> $dest_dir"
  mkdir -p "$dest_dir"
  if command -v hf &>/dev/null; then
    hf download "$repo" "$filename" --local-dir "$dest_dir" 2>&1
    return $?
  elif command -v huggingface-cli &>/dev/null; then
    huggingface-cli download "$repo" "$filename" --local-dir "$dest_dir" 2>&1
    return $?
  else
    local url="https://huggingface.co/$repo/resolve/main/$filename"
    command -v aria2c &>/dev/null || (apt-get update -qq && apt-get install -y -qq aria2)
    aria2c -x 16 -s 16 -k 1M -d "$dest_dir" -o "$(basename "$filename")" "$url"
  fi
}
'''

GPU_PROFILES = {
    "3090": {
        "display_name": "RTX 3090",
        "gpu_id": "NVIDIA GeForce RTX 3090",
        "memory_gb": 24,
        "estimated_price_hr": 0.30,
        "max_price_hr": 0.30,
        "notes": "Community Cloud 24GB VRAM budget profile.",
    },
    "4090": {
        "display_name": "RTX 4090",
        "gpu_id": "NVIDIA GeForce RTX 4090",
        "memory_gb": 24,
        "estimated_price_hr": 0.44,
        "max_price_hr": 0.60,
        "notes": "Optional fallback; this skill is optimized for 3090.",
    },
}

WORKFLOW_ALIASES = {
    # Wan 2.2
    "wan22": "wan-22-i2v-keyframe.sh",
    "wan": "wan-22-i2v-keyframe.sh",
    "wan 2.2": "wan-22-i2v-keyframe.sh",
    "wan2.2": "wan-22-i2v-keyframe.sh",
    "wanvideo": "wan-22-i2v-keyframe.sh",
    "wan-22-i2v-keyframe": "wan-22-i2v-keyframe.sh",
    # LTX 2.3 — Prompt Relay
    "ltx-23-prompt-relay": "ltx-23-prompt-relay.sh",
    "ltx23-prompt-relay": "ltx-23-prompt-relay.sh",
    "ltx23-pr": "ltx-23-prompt-relay.sh",
    # LTX 2.3 — I2V Keyframe
    "ltx-23-i2v-keyframe": "ltx-23-i2v-keyframe.sh",
    "ltx-keyframe": "ltx-23-i2v-keyframe.sh",
    # LTX 2.3 — I2V Distilled
    "ltx-23-i2v-distilled": "ltx-23-i2v-distilled.sh",
    "ltx-distilled": "ltx-23-i2v-distilled.sh",
    # LTX 2.3 — I2V Official (Lightricks)
    "ltx-23-i2v-official": "ltx-23-i2v-official.sh",
    "ltx-official": "ltx-23-i2v-official.sh",
    # Qwen Image Edit
    "qwen": "qwen-image-edit.sh",
    "qwen-image": "qwen-image-edit.sh",
    "qwen-image-edit": "qwen-image-edit.sh",
    # Qwen Image Edit 2511 4-Step Lightning
    "qwen-2511": "qwen-image-edit-2511-4steps.sh",
    "qwen-image-edit-2511-4steps": "qwen-image-edit-2511-4steps.sh",
    "qwen-image-edit-2511": "qwen-image-edit-2511-4steps.sh",
    "qwen-image-lightning-4steps": "qwen-image-edit-2511-4steps.sh",
    # HiDream O1 Image Dev I2I
    "hidream-o1": "hidream-o1-dev-i2i.sh",
    "hidream-o1-dev-i2i": "hidream-o1-dev-i2i.sh",
    "hidream": "hidream-o1-dev-i2i.sh",
    "hidream-o1-dev": "hidream-o1-dev-i2i.sh",
    "hidream-gemma4": "hidream-o1-dev-i2i.sh",
    # Flux.2 Klein 9B Image Edit
    "flux-2-klein": "flux-2-klein-image-edit.sh",
    "flux-klein": "flux-2-klein-image-edit.sh",
    "flux2-klein": "flux-2-klein-image-edit.sh",
}


@dataclass
class Candidate:
    id: str
    name: str
    location: str
    stock_status: str
    estimated_price_hr: float

    @property
    def stock_rank(self) -> int:
        value = (self.stock_status or "").lower()
        if value == "high":
            return 0
        if value == "medium":
            return 1
        if value == "low":
            return 2
        return 3


def log(prefix: str, msg: str) -> None:
    print(f"{prefix} {msg}", flush=True)


def run_cmd(args: list[str], timeout: int = 30) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "code": result.returncode,
        }
    except FileNotFoundError:
        return {"stdout": "", "stderr": "runpodctl not found in PATH", "code": 127}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Command timed out", "code": -1}


def load_json_command(args: list[str], timeout: int = 30) -> Any:
    result = run_cmd(args + ["-o", "json"], timeout=timeout)
    if result["code"] != 0:
        raise RuntimeError(result["stderr"] or result["stdout"] or "command failed")
    try:
        return json.loads(result["stdout"] or "null")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"failed to parse JSON from {' '.join(args)}: {exc}") from exc


def pod_create_help() -> str:
    result = run_cmd(["runpodctl", "pod", "create", "--help"], timeout=10)
    return f"{result['stdout']}\n{result['stderr']}"


def supports_create_flag(flag: str, help_text: str) -> bool:
    return flag in help_text


def load_hf_token() -> str:
    try:
        with open(HF_TOKEN_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return ""

    for key in ("huggingface_token", "HF_TOKEN", "hf_token", "token"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def load_discord_webhook() -> str:
    # Try env var first
    value = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if value.strip():
        return value.strip()
    # Fall back to config file
    try:
        with open(HF_TOKEN_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in ("discord_webhook_url", "DISCORD_WEBHOOK_URL", "webhook_url"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return ""


def validate_hf_token(token: str) -> bool:
    """Validate HF token by checking length and prefix."""
    if not token:
        return False
    if not token.startswith("hf_"):
        log("WARN", f"HF token doesn't start with 'hf_' — may be invalid")
        return True  # Don't block, just warn
    if len(token) < 20:
        log("ERROR", f"HF token too short ({len(token)} chars) — likely corrupted")
        return False
    return True


def workflow_filename(workflow_name: str) -> str:
    filename = WORKFLOW_ALIASES.get(workflow_name.lower())
    if filename:
        return filename
    if workflow_name.endswith(".sh"):
        return workflow_name
    return f"{workflow_name}.sh"


def workflow_url(workflow_name: str) -> str:
    filename = workflow_filename(workflow_name)
    return (
        f"https://raw.githubusercontent.com/{WORKFLOWS_REPO}/"
        f"{WORKFLOWS_BRANCH}/{WORKFLOWS_PATH}/{filename}"
    )


def workflow_size_gb(workflow_name: str) -> float:
    url = workflow_url(workflow_name)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "runpod-provision/1.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read(8192).decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0.0
    first_lines = "\n".join(body.splitlines()[:25])
    match = re.search(r"#\s*size:\s*~?([\d.]+)\s*GB", first_lines, re.IGNORECASE)
    if not match:
        return 0.0
    try:
        return float(match.group(1))
    except ValueError:
        return 0.0


def normalize_status(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def extract_pod_id(data: Any) -> Optional[str]:
    if isinstance(data, str):
        return data.strip() or None
    if not isinstance(data, dict):
        return None

    for key in ("id", "podId", "pod_id"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value

    for key in ("pod", "data"):
        nested = data.get(key)
        if isinstance(nested, dict):
            pod_id = extract_pod_id(nested)
            if pod_id:
                return pod_id

    return None


def extract_status(data: Any) -> str:
    if not isinstance(data, dict):
        return "UNKNOWN"

    keys = (
        "desiredStatus",
        "desired_status",
        "status",
        "podStatus",
        "runtimeStatus",
        "containerStatus",
        "machineStatus",
    )
    for key in keys:
        value = normalize_status(data.get(key))
        if value:
            return value

    runtime = data.get("runtime")
    if isinstance(runtime, dict):
        for key in keys:
            value = normalize_status(runtime.get(key))
            if value:
                return value

    return "UNKNOWN"


def find_gpu(profile: dict[str, Any]) -> dict[str, Any]:
    gpu_data = load_json_command(["runpodctl", "gpu", "list"], timeout=20)
    if not isinstance(gpu_data, list):
        raise RuntimeError("unexpected runpodctl gpu list response")

    for gpu in gpu_data:
        if not isinstance(gpu, dict):
            continue
        if gpu.get("gpuId") == profile["gpu_id"]:
            return gpu

    raise RuntimeError(f"GPU not found by runpodctl: {profile['gpu_id']}")


def search_candidates(profile: dict[str, Any]) -> list[Candidate]:
    data = load_json_command(["runpodctl", "datacenter", "list"], timeout=30)
    if not isinstance(data, list):
        raise RuntimeError("unexpected runpodctl datacenter list response")

    candidates: list[Candidate] = []
    for dc in data:
        if not isinstance(dc, dict):
            continue
        availability = dc.get("gpuAvailability") or []
        if not isinstance(availability, list):
            continue
        for gpu in availability:
            if not isinstance(gpu, dict):
                continue
            if gpu.get("gpuId") != profile["gpu_id"]:
                continue
            candidates.append(
                Candidate(
                    id=str(dc.get("id") or dc.get("name") or ""),
                    name=str(dc.get("name") or dc.get("id") or ""),
                    location=str(dc.get("location") or "Unknown"),
                    stock_status=str(gpu.get("stockStatus") or "Available"),
                    estimated_price_hr=float(profile["estimated_price_hr"]),
                )
            )
            break

    candidates = [c for c in candidates if c.id]
    candidates.sort(key=lambda c: (c.estimated_price_hr, c.stock_rank, c.location, c.id))
    return candidates


def frp_allocate_index(label: str) -> str:
    """Allocate a unique FRP subdomain index for this instance."""
    import subprocess
    result = subprocess.run(
        ["/usr/local/bin/frp-allocate-port", "allocate", label],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            return str(data.get("index", ""))
        except json.JSONDecodeError:
            log("WARN", f"Failed to parse frp-allocate-port output: {result.stdout[:100]}")
    else:
        log("WARN", f"frp-allocate-port failed: {result.stderr[:100]}")
    return ""


def build_env(workflow: Optional[str], hf_token: str, discord_webhook: str, frp_index: str = "") -> str:
    env: dict[str, str] = {
        "COMFYUI_ARGS": "--disable-auto-launch --port 8188 --enable-cors-header",
        "DATA_DIRECTORY": "/workspace/",
        "JUPYTER_DIR": "/workspace",
        "OPEN_BUTTON_PORT": "8188",
        "OPEN_BUTTON_TOKEN": "1",
    }
    if hf_token:
        env["HF_TOKEN"] = hf_token
    if discord_webhook:
        env["DISCORD_WEBHOOK_URL"] = discord_webhook
    if frp_index:
        env["FRP_INDEX"] = frp_index
        env["FRP_SERVER_ADDR"] = "159.195.52.130"
        env["FRP_SERVER_PORT"] = "7000"
        # FRP_TOKEN loaded from VPS config
        frp_token = _load_frp_token()
        if frp_token:
            env["FRP_TOKEN"] = frp_token
    if workflow:
        env["WORKFLOW_SCRIPT"] = workflow_url(workflow)
    return json.dumps(env, separators=(",", ":"))


def _load_frp_token() -> str:
    """Load FRP token from VPS config."""
    try:
        with open("/etc/frp/frps.toml", "r", encoding="utf-8") as f:
            for line in f:
                if "auth.token" in line:
                    match = re.search(r'auth\.token\s*=\s*["\']?([^"\'\s]+)', line)
                    if match:
                        return match.group(1)
    except (FileNotFoundError, IOError):
        pass
    return ""


def build_create_command(
    profile: dict[str, Any],
    label: str,
    env_json: str,
    candidate: Optional[Candidate],
    args: argparse.Namespace,
    help_text: str,
) -> list[str]:
    cmd = [
        "runpodctl",
        "pod",
        "create",
        "--name",
        label,
        "--template-id",
        DEFAULT_TEMPLATE_ID,
        "--gpu-id",
        profile["gpu_id"],
        "--gpu-count",
        "1",
        "--cloud-type",
        "COMMUNITY",
        "--public-ip",
        "--container-disk-in-gb",
        str(DEFAULT_CONTAINER_DISK_GB),
        "--volume-in-gb",
        str(DEFAULT_VOLUME_GB),
        "--ports",
        DEFAULT_PORTS,
        "--env",
        env_json,
    ]

    if candidate:
        cmd.extend(["--data-center-ids", candidate.id])

    if args.stop_after:
        if supports_create_flag("--stop-after", help_text):
            cmd.extend(["--stop-after", args.stop_after])
        else:
            log("WARN", "--stop-after requested but this runpodctl does not list that flag; omitting it")

    if args.terminate_after:
        if supports_create_flag("--terminate-after", help_text):
            cmd.extend(["--terminate-after", args.terminate_after])
        else:
            log("WARN", "--terminate-after requested but this runpodctl does not list that flag; omitting it")

    cmd.extend(["-o", "json"])
    return cmd


def create_pod(cmd: list[str]) -> Optional[str]:
    result = run_cmd(cmd, timeout=90)
    if result["code"] != 0:
        log("ERROR", result["stderr"] or result["stdout"] or "pod create failed")
        return None
    try:
        data = json.loads(result["stdout"] or "{}")
    except json.JSONDecodeError:
        log("ERROR", f"failed to parse pod create response: {result['stdout'][:300]}")
        return None

    pod_id = extract_pod_id(data)
    if not pod_id:
        log("ERROR", f"pod create response did not include an id: {json.dumps(data)[:500]}")
        return None
    return pod_id


def get_pod(pod_id: str) -> dict[str, Any]:
    data = load_json_command(["runpodctl", "pod", "get", pod_id], timeout=20)
    if isinstance(data, dict):
        return data
    return {}


def monitor_pod(pod_id: str, timeout: int) -> bool:
    log("WAIT", f"Monitoring pod {pod_id} for up to {timeout}s")
    start = time.time()
    last_status = ""

    while time.time() - start < timeout:
        try:
            data = get_pod(pod_id)
        except RuntimeError as exc:
            log("WARN", f"status check failed: {exc}")
            time.sleep(10)
            continue

        status = extract_status(data)
        if status != last_status:
            elapsed = int(time.time() - start)
            log("STATUS", f"{status} after {elapsed}s")
            last_status = status

        if status in ("RUNNING", "READY"):
            return True
        if status in ("FAILED", "TERMINATED", "EXITED", "DEAD"):
            return False

        time.sleep(15)

    log("ERROR", f"timeout waiting for pod {pod_id}")
    return False


def get_ssh_info(pod_id: str) -> Optional[dict[str, str]]:
    """Get SSH connection details from runpodctl."""
    for attempt in range(5):
        result = run_cmd(["runpodctl", "ssh", "info", pod_id], timeout=20)
        if result["code"] == 0 and result["stdout"]:
            try:
                data = json.loads(result["stdout"])
                if data.get("ssh_command"):
                    return data
            except json.JSONDecodeError:
                pass
        time.sleep(10)
    return None


def ssh_exec(host: str, port: str, command: str, timeout: int = 60) -> dict[str, Any]:
    """Execute a command on a remote host via SSH."""
    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-o", "BatchMode=yes",
        "-i", SSH_KEY_PATH,
        "-p", port,
        f"root@{host}",
        command,
    ]
    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "code": result.returncode,
        }
    except FileNotFoundError:
        return {"stdout": "", "stderr": "ssh not found in PATH", "code": 127}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "SSH command timed out", "code": -1}


def ssh_upload_file(host: str, port: str, remote_path: str, content: str) -> bool:
    """Upload a file to remote host via SSH stdin."""
    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-o", "BatchMode=yes",
        "-i", SSH_KEY_PATH,
        "-p", port,
        f"root@{host}",
        f"cat > {remote_path}",
    ]
    try:
        result = subprocess.run(
            ssh_cmd,
            input=content,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def bootstrap_pod(
    pod_id: str,
    ssh_info: dict[str, str],
    hf_token: str,
    discord_webhook: str,
    workflow: Optional[str],
    frp_index: str = "",
) -> bool:
    """Post-provisioning SSH bootstrap: set env vars, install deps, run workflow."""
    host = ssh_info["ip"]
    port = str(ssh_info["port"])

    log("BOOTSTRAP", "Setting up environment on pod...")

    # 1. Set env vars in SSH environment
    env_lines = []
    if hf_token:
        env_lines.append(f'export HF_TOKEN="{hf_token}"')
    env_lines.append("export HF_HUB_ENABLE_HF_TRANSFER=1")
    if workflow:
        env_lines.append(f'export WORKFLOW_SCRIPT="{workflow_url(workflow)}"')
    if discord_webhook:
        env_lines.append(f'export DISCORD_WEBHOOK_URL="{discord_webhook}"')
    if frp_index:
        env_lines.append(f"export FRP_INDEX={frp_index}")
        env_lines.append('export FRP_SERVER_ADDR="159.195.52.130"')
        env_lines.append("export FRP_SERVER_PORT=7000")
        frp_token = _load_frp_token()
        if frp_token:
            env_lines.append(f'export FRP_TOKEN="{frp_token}"')

    env_content = "\n".join(env_lines) + "\n"
    if not ssh_upload_file(host, port, "/root/.ssh/environment", env_content):
        log("WARN", "Failed to upload env vars — continuing anyway")

    # 2. Upload hf_download.sh helper
    if not ssh_upload_file(host, port, "/workspace/hf_download.sh", HF_DOWNLOAD_HELPER):
        log("WARN", "Failed to upload hf_download.sh")
    else:
        ssh_exec(host, port, "chmod +x /workspace/hf_download.sh")

    # 3. Install hf CLI + authenticate
    if hf_token:
        log("BOOTSTRAP", "Installing hf CLI and authenticating...")
        install_result = ssh_exec(
            host, port,
            "pip install --quiet 'huggingface_hub[cli]' hf_transfer 2>&1 | tail -3",
            timeout=120,
        )
        if install_result["code"] != 0:
            log("WARN", f"pip install returned code {install_result['code']}")

        # Authenticate with HF
        auth_cmd = f'echo "{hf_token}" | hf auth login --token - 2>&1 | tail -3'
        auth_result = ssh_exec(host, port, auth_command:=auth_cmd, timeout=30)
        if "Logged in" in auth_result.get("stdout", ""):
            log("BOOTSTRAP", "HF authentication successful")
        else:
            log("WARN", f"HF auth: {auth_result.get('stdout', '')[:100]}")

    # 4. Download and run workflow script
    if workflow:
        log("BOOTSTRAP", f"Downloading workflow: {workflow}...")
        wf_url = workflow_url(workflow)
        download_cmd = f'curl -sSL "{wf_url}" -o /workspace/workflow-setup.sh && chmod +x /workspace/workflow-setup.sh'
        dl_result = ssh_exec(host, port, download_cmd, timeout=30)
        if dl_result["code"] != 0:
            log("ERROR", f"Failed to download workflow: {dl_result.get('stderr', '')[:200]}")
            return False

        # Run workflow in tmux
        log("BOOTSTRAP", "Starting workflow download in tmux session 'workflow'...")
        tmux_cmd = (
            "tmux kill-session -t workflow 2>/dev/null || true; "
            f"tmux new-session -d -s workflow '"
            f"export HF_TOKEN=\"{hf_token}\" && "
            f"export HF_HUB_ENABLE_HF_TRANSFER=1 && "
            f"bash /workspace/workflow-setup.sh 2>&1 | tee /workspace/workflow.log'"
        )
        tmux_result = ssh_exec(host, port, tmux_cmd, timeout=15)
        if tmux_result["code"] == 0:
            log("BOOTSTRAP", "Workflow started in tmux session 'workflow'")
        else:
            log("WARN", f"tmux start returned code {tmux_result['code']}")

    log("BOOTSTRAP", "Bootstrap complete")
    return True


def print_candidates(candidates: list[Candidate], profile: dict[str, Any], workflow_gb: float) -> None:
    print("\n" + "=" * 80)
    print(f"Community Cloud candidates for {profile['gpu_id']}")
    print("=" * 80)
    if not candidates:
        print("No datacenter candidates found.")
    for idx, candidate in enumerate(candidates[:10], start=1):
        workflow_cost = 0.0
        if workflow_gb:
            workflow_cost = 0.0
        print(
            f"  #{idx} | {candidate.id:10s} | {candidate.location:14s} | "
            f"stock: {candidate.stock_status:9s} | est: ${candidate.estimated_price_hr:.4f}/hr"
        )
        if workflow_gb and workflow_cost:
            print(f"       estimated workflow transfer cost: ${workflow_cost:.2f}")
    print("=" * 80)


def print_ready(pod_id: str, profile: dict[str, Any], price_hr: float, workflow: Optional[str], ssh_data: Optional[dict] = None) -> None:
    print("\n" + "=" * 80)
    print("SERVER READY")
    print("=" * 80)
    print(f"  Pod ID:   {pod_id}")
    print(f"  GPU:      {profile['gpu_id']}")
    print(f"  Cost:     estimated ${price_hr:.4f}/hr")
    if ssh_data:
        print(f"  SSH:      ssh -i {SSH_KEY_PATH} root@{ssh_data['ip']} -p {ssh_data['port']}")
    else:
        print(f"  SSH:      runpodctl ssh info {pod_id}")
    print(f"  ComfyUI:  https://{pod_id}-8188.runpod.app")
    print(f"  Jupyter:  https://{pod_id}-8080.runpod.app")
    if workflow:
        print(f"  Workflow: {workflow} ({workflow_url(workflow)})")
    print("=" * 80)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RunPod Community Cloud pod provisioning")
    parser.add_argument("--gpu", default="3090", choices=sorted(GPU_PROFILES), help="GPU type")
    parser.add_argument("--workflow", default=None, help="Workflow script name or alias")
    parser.add_argument("--label", required=True, help="Pod label/name")
    parser.add_argument("--auto", action="store_true", help="Auto-select cheapest candidate")
    parser.add_argument("--dry-run", action="store_true", help="Show candidates without provisioning")
    parser.add_argument("--max-price", type=float, default=None, help="Maximum estimated $/hr")
    parser.add_argument("--no-monitor", action="store_true", help="Skip post-create monitoring")
    parser.add_argument("--no-bootstrap", action="store_true", help="Skip SSH bootstrap (env setup + workflow)")
    parser.add_argument("--timeout", type=int, default=600, help="Seconds to wait for RUNNING")
    parser.add_argument("--stop-after", default=None, help="Auto-stop duration, e.g. 4h, if CLI supports it")
    parser.add_argument("--terminate-after", default=None, help="Auto-terminate duration, e.g. 8h, if CLI supports it")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = GPU_PROFILES[args.gpu]
    price_cap = args.max_price if args.max_price is not None else profile["max_price_hr"]

    log("INFO", f"GPU profile: {profile['display_name']} ({profile['gpu_id']})")
    log("INFO", f"Label: {args.label}")
    log("INFO", "Cloud: COMMUNITY with public IP")

    if profile["estimated_price_hr"] > price_cap:
        log(
            "ERROR",
            f"estimated price ${profile['estimated_price_hr']:.4f}/hr exceeds cap ${price_cap:.4f}/hr",
        )
        return 1

    workflow_gb = 0.0
    if args.workflow:
        workflow_gb = workflow_size_gb(args.workflow)
        log("INFO", f"Workflow: {args.workflow} ({workflow_url(args.workflow)})")
        if workflow_gb:
            log("INFO", f"Workflow declared size: ~{workflow_gb:.1f}GB")
    else:
        log("INFO", "No workflow selected")

    hf_token = load_hf_token()
    discord_webhook = load_discord_webhook()
    log("INFO", f"HF_TOKEN: {'SET' if hf_token else 'MISSING'}")
    log("INFO", f"Discord webhook: {'SET' if discord_webhook else 'MISSING'}")

    # Validate HF token before provisioning
    if hf_token and not validate_hf_token(hf_token):
        log("ERROR", "HF token validation failed — check /root/config/token.json")
        return 1

    try:
        gpu = find_gpu(profile)
    except RuntimeError as exc:
        log("ERROR", str(exc))
        return 1

    if not gpu.get("communityCloud"):
        log("ERROR", f"{profile['gpu_id']} is not marked available on Community Cloud")
        return 1
    if not gpu.get("available"):
        log("ERROR", f"{profile['gpu_id']} is not currently available")
        return 1

    try:
        candidates = search_candidates(profile)
    except RuntimeError as exc:
        log("ERROR", str(exc))
        return 1

    if not candidates:
        log("ERROR", "No Community Cloud datacenter candidates found for this GPU")
        return 1

    print_candidates(candidates, profile, workflow_gb)
    log("COST", f"Estimated compute cost: ${profile['estimated_price_hr']:.4f}/hr")
    log("COST", f"Price cap: ${price_cap:.4f}/hr")

    if args.dry_run:
        log("INFO", "Dry run; exiting without provisioning")
        return 0

    if not args.auto:
        answer = input(
            f"\nProvision {profile['gpu_id']} on {candidates[0].id} "
            f"for estimated ${profile['estimated_price_hr']:.4f}/hr? (y/N): "
        ).strip().lower()
        if answer != "y":
            log("INFO", "Aborted")
            return 1

    help_text = pod_create_help()
    frp_index = frp_allocate_index(args.label)
    if frp_index:
        log("FRP", f"Allocated FRP index {frp_index}")
    env_json = build_env(args.workflow, hf_token, discord_webhook, frp_index)
    attempts = candidates[:3]

    for index, candidate in enumerate(attempts, start=1):
        log(
            "TRY",
            f"{index}/{len(attempts)} datacenter {candidate.id} "
            f"({candidate.location}, stock {candidate.stock_status})",
        )
        cmd = build_create_command(profile, args.label, env_json, candidate, args, help_text)
        log("CMD", " ".join(cmd[:20]) + " ...")
        pod_id = create_pod(cmd)
        if not pod_id:
            continue

        log("OK", f"Pod created: {pod_id}")
        if args.no_monitor:
            print_ready(pod_id, profile, profile["estimated_price_hr"], args.workflow)
            return 0

        if monitor_pod(pod_id, args.timeout):
            # Wait for SSH to be ready
            log("WAIT", "Waiting for SSH to be ready...")
            time.sleep(15)
            ssh_data = get_ssh_info(pod_id)

            # Bootstrap the pod (env vars, hf auth, workflow)
            if not args.no_bootstrap and ssh_data:
                bootstrap_pod(pod_id, ssh_data, hf_token, discord_webhook, args.workflow, frp_index)

            print_ready(pod_id, profile, profile["estimated_price_hr"], args.workflow, ssh_data)
            return 0

        log("WARN", f"Pod {pod_id} did not become ready; trying next candidate if available")

    log("ERROR", f"All {len(attempts)} provisioning attempts failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
