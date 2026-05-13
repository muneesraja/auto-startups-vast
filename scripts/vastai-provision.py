#!/usr/bin/env python3
"""
vastai-provision.py — Single-command Vast.ai GPU server provisioning
====================================================================
Usage:
  python3 vastai-provision.py --gpu 3090 --workflow prompt_relay_ltx23_test_02 --label mandi
  python3 vastai-provision.py --gpu 4090 --workflow wan22 --label balaji --auto
  python3 vastai-provision.py --gpu 3090 --bare --label mandi  # No workflow, bare ComfyUI

Options:
  --gpu         GPU type: 3090 or 4090 (required)
  --workflow    Workflow script name or alias (optional, omit for bare ComfyUI)
  --label       Instance label, lowercase no spaces (required)
  --auto        Auto-select best offer without prompting
  --dry-run     Search and show offers without provisioning
  --max-price   Override max $/hr (default from GPU profile)
  --monitor     Monitor instance after provisioning (default: true)
  --timeout     Max seconds to wait for instance to become running (default: 600)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

# =============================================================================
# GPU Profiles
# =============================================================================

GPU_PROFILES = {
    "3090": {
        "name": "RTX_3090",
        "num_gpus": 1,
        "min_ram_gb": 24,           # VRAM is bottleneck, not system RAM
        "min_disk_gb": 100,
        "min_inet_down_mbps": 200,  # 200 Mbps sufficient for most workflows
        "min_inet_up_mbps": 200,
        "min_cpu_cores": 2,
        "min_reliability": 0.95,    # 95% — host must be mostly reliable
        "cuda_min": 12.7,           # cuda-12.9 image works on 12.7+ drivers
        "driver_min": "560.0.0",    # NV driver 560+ required for CUDA 12.9 (see references/driver-version-requirements.md)
        "max_price_hr": 0.30,       # Relaxed from 0.25 to show more options
        "max_inet_down_cost_tb": 0.05,
        "docker_image": "vastai/comfy:v0.20.1-cuda-12.9-py312",
        "skip_countries": ["CN"],    # China — slow HF downloads
        "notes": "32GB system RAM is fine for ComfyUI. CUDA 12.9 image works with NV driver 565+",
    },
    "4090": {
        "name": "RTX_4090",
        "num_gpus": 1,
        "min_ram_gb": 24,
        "min_disk_gb": 100,
        "min_inet_down_mbps": 200,
        "min_inet_up_mbps": 200,
        "min_cpu_cores": 2,
        "min_reliability": 0.95,
        "cuda_min": 12.7,
        "driver_min": "560.0.0",    # NV driver 560+ required for CUDA 12.9
        "max_price_hr": 0.50,       # Relaxed from 0.40
        "max_inet_down_cost_tb": 0.05,
        "docker_image": "vastai/comfy:v0.20.1-cuda-12.9-py312",
        "skip_countries": ["CN"],
        "notes": "4090 has 24GB VRAM, better perf/$ than 3090 for many workloads",
    },
}

# =============================================================================
# Workflow Registry — maps aliases to GitHub raw URLs
# =============================================================================

WORKFLOWS_REPO = "muneesraja/auto-startups-vast"
WORKFLOWS_BRANCH = "main"
WORKFLOWS_PATH = "scripts/workflows"

# Populated dynamically from GitHub API or hardcoded for known workflows
WORKFLOW_ALIASES = {
    "wan22": "wan22-download.sh",
    "wan": "wan22-download.sh",
    "wan 2.2": "wan22-download.sh",
    "wan2.2": "wan22-download.sh",
    "wanvideo": "wan22-download.sh",
    "prompt_relay_ltx23_test_02": "prompt_relay_ltx23_test_02.sh",
    "prompt-relay-ltx23-test-02": "prompt_relay_ltx23_test_02.sh",
    "ltx23-prompt-relay": "prompt_relay_ltx23_test_02.sh",
    "ltx23-oldman-redpanda": "prompt_relay_ltx23_test_02.sh",
    "kijai-ltx2.3": "kijai-ltx2.3.sh",
    "ltx-23-prompt-relay": "ltx-23-prompt-relay-download.sh",
    "ltx2-keyframing": "ltx2-keyframing.sh",
    "ltx2.3-img2video": "ltx2.3-img2video.sh",
    "qwen": "qwen-image-download.sh",
    "qwen-image": "qwen-image-download.sh",
}

# =============================================================================
# Config
# =============================================================================

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
HF_TOKEN_PATH = "/root/config/token.json"
FAILED_HOSTS_PATH = "/root/.hermes/skills/vast-ai/scripts/failed_hosts.json"
FRP_ALLOCATE_SCRIPT = "/usr/local/bin/frp-allocate-port"
FRP_SERVER_ADDR = "159.195.52.130"
FRP_SERVER_PORT = 7000
FAST_PROVISION_URL = "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/fast-provision.sh"
# FRP token loaded from VPS config

# =============================================================================
# Helpers
# =============================================================================

def log(emoji: str, msg: str):
    print(f"{emoji} {msg}", flush=True)


def run_cmd(cmd: str, timeout: int = 30) -> dict:
    """Run a shell command and return stdout."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return {"stdout": result.stdout.strip(), "stderr": result.stderr.strip(), "code": result.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Command timed out", "code": -1}


def load_hf_token() -> str:
    """Load HF token from shared config."""
    try:
        with open(HF_TOKEN_PATH) as f:
            data = json.load(f)
            return data.get("huggingface_token", "")
    except (FileNotFoundError, json.JSONDecodeError):
        return ""


def load_discord_webhook() -> str:
    """Load Discord webhook URL from env or config."""
    if DISCORD_WEBHOOK_URL:
        return DISCORD_WEBHOOK_URL
    # Try loading from token.json (JSON format)
    try:
        with open(HF_TOKEN_PATH) as f:
            data = json.load(f)
            url = data.get("discord_webhook_url", "")
            if url:
                return url
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return ""


def load_failed_hosts() -> dict:
    """Load failed hosts tracker. Returns {host_id: last_failure_timestamp}."""
    try:
        with open(FAILED_HOSTS_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def allocate_frp_index(label: str) -> dict:
    """Allocate an FRP subdomain index for a new GPU instance.
    Returns dict with index, domains, and frpc config template.
    """
    result = run_cmd(f"{FRP_ALLOCATE_SCRIPT} allocate '{label}'", timeout=10)
    if result["code"] != 0:
        log("⚠️", f"FRP allocation failed: {result['stderr']}")
        return {}
    try:
        return json.loads(result["stdout"])
    except json.JSONDecodeError:
        log("⚠️", f"Failed to parse FRP allocation response: {result['stdout']}")
        return {}


def save_failed_host(host_id: int):
    """Record a host as failed."""
    failed = load_failed_hosts()
    failed[str(host_id)] = time.time()
    # Clean up entries older than 24 hours
    cutoff = time.time() - 86400
    failed = {k: v for k, v in failed.items() if v > cutoff}
    with open(FAILED_HOSTS_PATH, "w") as f:
        json.dump(failed, f, indent=2)
    log("📝", f"Host {host_id} marked as failed (will be skipped for 24h)")


# =============================================================================
# Offer Search & Filtering
# =============================================================================

@dataclass
class Offer:
    id: int
    gpu_name: str
    cuda_max_good: float
    cpu_ghz: float
    vcpus: float
    ram_gb: float
    disk_gb: float
    dph_total: float
    inet_down_mbps: float
    inet_up_mbps: float
    reliability: float
    inet_down_cost_gb: float  # $/GB
    inet_up_cost_gb: float
    country: str
    host_id: int
    nv_driver: str
    direct_port_count: int = 0
    _is_verified: bool = False  # Verified or deverified host

    @property
    def inet_down_cost_tb(self) -> float:
        return self.inet_down_cost_gb * 1024

    def meets_specs(self, profile: dict) -> tuple[bool, list[str]]:
        """Check if offer meets GPU profile requirements. Returns (ok, reasons)."""
        issues = []

        if self.ram_gb < profile["min_ram_gb"]:
            issues.append(f"RAM {self.ram_gb:.0f}GB < {profile['min_ram_gb']}GB")
        if self.disk_gb < profile["min_disk_gb"]:
            issues.append(f"Disk {self.disk_gb:.0f}GB < {profile['min_disk_gb']}GB")
        if self.inet_down_mbps < profile["min_inet_down_mbps"]:
            issues.append(f"Download {self.inet_down_mbps:.0f}Mbps < {profile['min_inet_down_mbps']}Mbps")
        if self.inet_up_mbps < profile["min_inet_up_mbps"]:
            issues.append(f"Upload {self.inet_up_mbps:.0f}Mbps < {profile['min_inet_up_mbps']}Mbps")
        if self.reliability < profile["min_reliability"] * 100:
            issues.append(f"Reliability {self.reliability:.1f}% < {profile['min_reliability']*100:.0f}%")
        if self.dph_total > profile["max_price_hr"]:
            issues.append(f"Price ${self.dph_total:.4f} > ${profile['max_price_hr']:.2f}")
        if self.cuda_max_good < profile["cuda_min"]:
            issues.append(f"CUDA {self.cuda_max_good} < {profile['cuda_min']}")

        # Country skip
        for skip in profile.get("skip_countries", []):
            if skip.lower() in (self.country or "").lower():
                issues.append(f"Country {self.country} in skip list")
                break

        return (len(issues) == 0, issues)


def search_offers(profile: dict, max_price: Optional[float] = None) -> list[Offer]:
    """Search Vast.ai for offers matching GPU profile."""
    price = max_price or profile["max_price_hr"]
    failed_hosts = load_failed_hosts()

    # Build search query — start broad, we filter in Python
    # Include driver_version filter to avoid hosts with outdated CUDA drivers
    driver_min = profile.get("driver_min", "560.0.0")  # Default: CUDA 12.9 compatible
    query = (
        f"gpu_name={profile['name']} "
        f"num_gpus={profile['num_gpus']} "
        f"rented=False "
        f"dph<={price + 0.10} "  # Slightly above max to catch borderline offers
        f"cuda_max_good>={profile['cuda_min'] - 0.5} "  # Slightly below to catch borderline
        f"driver_version>={driver_min}"  # Filter out hosts with old drivers
    )

    log("🔍", f"Searching offers: {query}")
    result = run_cmd(f"vastai search offers -n '{query}' --raw -o 'dph+' --limit 30", timeout=30)

    if result["code"] != 0:
        log("❌", f"Search failed: {result['stderr']}")
        return []

    try:
        raw_data = json.loads(result["stdout"])
    except json.JSONDecodeError:
        log("❌", f"Failed to parse search results")
        return []

    offers = []
    skipped_failed = 0
    for o in raw_data:
        try:
            # Skip failed hosts
            host_id = int(o.get("host_id", 0))
            if str(host_id) in failed_hosts:
                skipped_failed += 1
                continue

            ram = o.get("gpu_ram", 0)
            if isinstance(ram, (int, float)) and ram > 1000:
                ram = ram / 1024  # MB to GB

            offers.append(Offer(
                id=o["id"],
                gpu_name=o.get("gpu_name", ""),
                cuda_max_good=float(o.get("cuda_max_good", 0)),
                cpu_ghz=float(o.get("cpu_ghz", 0)),
                vcpus=float(o.get("num_cpus", 0)),
                ram_gb=ram,
                disk_gb=float(o.get("disk_space", 0)),
                dph_total=float(o.get("dph_total", 0)),
                inet_down_mbps=float(o.get("inet_down", 0)),
                inet_up_mbps=float(o.get("inet_up", 0)),
                reliability=float(o.get("reliability", 0)) * 100,  # API returns 0-1, convert to 0-100%
                inet_down_cost_gb=float(o.get("inet_down_cost", 0)),
                inet_up_cost_gb=float(o.get("inet_up_cost", 0)),
                country=o.get("geolocation", "Unknown"),
                host_id=int(o.get("host_id", 0)),
                nv_driver=o.get("driver_version", "Unknown"),
                _is_verified=o.get("verification") in ("verified", "deverified"),
            ))
        except (KeyError, ValueError, TypeError) as e:
            continue  # Skip malformed offers

    if skipped_failed > 0:
        log("🚫", f"Skipped {skipped_failed} previously failed hosts")

    return offers


def rank_offers(offers: list[Offer], profile: dict, workflow_size_gb: float = 0) -> list[Offer]:
    """Filter and rank offers. Best = meets specs + lowest total cost."""
    valid = []
    for o in offers:
        ok, _ = o.meets_specs(profile)
        if ok:
            valid.append(o)

    if not valid:
        # If nothing meets specs, return all offers sorted by price (for manual review)
        log("⚠️", "No offers meet all specs — showing all available sorted by price")
        return sorted(offers, key=lambda o: o.dph_total)[:5]

    # Score: dph + estimated inet cost for workflow
    # Bonus: verified/deverified hosts are more reliable for Docker
    for o in valid:
        estimated_inet_cost = workflow_size_gb * o.inet_down_cost_gb if workflow_size_gb > 0 else 0
        o._total_cost = o.dph_total + (estimated_inet_cost / 10)  # Normalize inet cost (amortize over 10 hours)
        # Penalty for unverified hosts (more likely to have Docker issues)
        if not o._is_verified:
            o._total_cost += 0.02  # $0.02/hr penalty — makes verified hosts preferred when close in price

    valid.sort(key=lambda o: o._total_cost)
    return valid


# =============================================================================
# Provisioning
# =============================================================================

def get_workflow_url(workflow_name: str) -> Optional[str]:
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


def build_provisioning_env(profile: dict, workflow_url: Optional[str], hf_token: str, 
                           discord_webhook: str, frp_config: Optional[dict] = None) -> str:
    """Build the --env string for vastai create instance."""
    docker_image = profile["docker_image"]

    env_parts = [
        "-p 8188:8188",
        '-e COMFYUI_ARGS="--disable-auto-launch --port 18188 --enable-cors-header --listen 0.0.0.0"',
        f'-e PROVISIONING_SCRIPT="https://raw.githubusercontent.com/{WORKFLOWS_REPO}/{WORKFLOWS_BRANCH}/scripts/comfyui-bootstrap.sh"',
    ]

    if discord_webhook:
        env_parts.append(f'-e DISCORD_WEBHOOK_URL="{discord_webhook}"')

    if hf_token:
        env_parts.append(f'-e HF_TOKEN="{hf_token}"')

    if workflow_url:
        env_parts.append(f'-e WORKFLOW_SCRIPT="{workflow_url}"')

    # FRP tunneling configuration (self-hosted alternative to Cloudflare)
    if frp_config:
        env_parts.append(f'-e FRP_INDEX="{frp_config.get("index", 0)}"')
        env_parts.append(f'-e FRP_SERVER_ADDR="{FRP_SERVER_ADDR}"')
        env_parts.append(f'-e FRP_SERVER_PORT="{FRP_SERVER_PORT}"')
        # Read FRP token from VPS config
        frp_token = _load_frp_token()
        if frp_token:
            env_parts.append(f'-e FRP_TOKEN="{frp_token}"')

    env_parts.extend([
        '-e PORTAL_CONFIG="localhost:1111:11111:/:Instance Portal|localhost:8188:18188:/:ComfyUI|localhost:8080:18080:/:Jupyter|localhost:8080:8080:/terminals/1:Jupyter Terminal"',
        '-e OPEN_BUTTON_PORT="1111"',
        '-e JUPYTER_DIR="/"',
        '-e DATA_DIRECTORY="/workspace/"',
        '-e OPEN_BUTTON_TOKEN="1"',
    ])

    return " ".join(env_parts)


def _load_frp_token() -> str:
    """Load FRP token from VPS config."""
    try:
        with open("/etc/frp/frps.toml") as f:
            for line in f:
                if 'auth.token' in line:
                    # Parse: auth.token = "value" or auth.token = 'value'
                    match = re.search(r'auth\.token\s*=\s*["\']?([^"\'\s]+)', line)
                    if match:
                        return match.group(1)
    except (FileNotFoundError, IOError):
        pass
    return ""


def provision_instance(offer: Offer, profile: dict, label: str,
                       workflow_url: Optional[str], hf_token: str,
                       discord_webhook: str, frp_config: Optional[dict] = None,
                       fast_mode: bool = True) -> Optional[int]:
    """Provision a Vast.ai instance. Returns instance ID or None."""
    env_str = build_provisioning_env(profile, workflow_url, hf_token, discord_webhook, frp_config)

    disk = max(profile["min_disk_gb"], int(offer.disk_gb * 0.8))  # Use 80% of available disk
    
    # Fast mode: use fast-provision.sh (default)
    # Slow mode: let image's internal provisioner run
    if fast_mode:
        onstart_cmd = f"curl -sSL '{FAST_PROVISION_URL}' | bash"
        log("⚡", "Using FAST provisioning mode")
    else:
        onstart_cmd = "entrypoint.sh"
        log("🐢", "Using SLOW image provisioner")

    cmd = (
        f"vastai create instance {offer.id} "
        f"--image {profile['docker_image']} "
        f"--env '{env_str}' "
        f"--disk {disk} "
        f"--label \"{label}\" "
        f"--direct --ssh --jupyter "
        f"--cancel-unavail "
        f"--onstart-cmd '{onstart_cmd}'"
    )

    log("🚀", f"Provisioning instance on host {offer.host_id} (${offer.dph_total:.4f}/hr)...")
    log("📋", f"Command: {cmd[:200]}...")

    result = run_cmd(cmd, timeout=60)

    if result["code"] != 0:
        log("❌", f"Provisioning failed: {result['stderr']}")
        return None

    # Vast.ai API sometimes returns "Started. {json}" — strip non-JSON prefix
    raw_output = result["stdout"].strip()
    # Find the first '{' and parse from there
    json_start = raw_output.find("{")
    if json_start == -1:
        log("❌", f"No JSON in provisioning response: {raw_output[:200]}")
        return None

    json_str = raw_output[json_start:]

    try:
        data = json.loads(json_str)
        if data.get("success"):
            instance_id = data.get("new_contract")
            log("✅", f"Instance created: {instance_id}")
            return instance_id
        else:
            log("❌", f"Instance creation returned success=false: {data}")
            # Check for error codes
            error_msg = data.get("error", "") or data.get("message", "")
            if "no_such_ask" in str(data) or "not available" in error_msg:
                log("⚠️", "Offer no longer available — will try next offer")
            return None
    except json.JSONDecodeError:
        log("❌", f"Failed to parse provisioning response: {json_str[:200]}")
        return None


# =============================================================================
# Monitoring
# =============================================================================

def monitor_instance(instance_id: int, timeout: int = 600, host_id: int = 0) -> bool:
    """Monitor instance until it's running. Returns True if successful."""
    log("⏳", f"Monitoring instance {instance_id} (timeout: {timeout}s)...")

    start_time = time.time()
    last_status = ""

    while time.time() - start_time < timeout:
        result = run_cmd(f"vastai show instance {instance_id} --raw", timeout=15)

        if result["code"] != 0:
            log("⚠️", f"Failed to check status: {result['stderr']}")
            time.sleep(10)
            continue

        try:
            data = json.loads(result["stdout"])
            actual_status = data.get("actual_status", "unknown")
            duration = data.get("duration", 0)

            if actual_status != last_status:
                elapsed = int(time.time() - start_time)
                log("📊", f"Status: {actual_status} (duration: {duration}s, elapsed: {elapsed}s)")
                last_status = actual_status

            if actual_status == "running":
                log("✅", "Instance is running!")
                return True

            if actual_status == "loading" and duration > 120:
                # Check daemon logs for Docker failure
                logs = run_cmd(f"vastai logs {instance_id} --daemon-logs", timeout=10)
                log_output = logs.get("stdout", "") + logs.get("stderr", "")

                # Detect host agent (kaalia) failures
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

            # If still loading after 300s with null image, host agent is dead
            if actual_status == "loading" and duration > 300:
                log("❌", f"Instance stuck loading for {duration}s (no image pulled) — host agent likely broken")
                if host_id:
                    save_failed_host(host_id)
                return False

        except json.JSONDecodeError:
            pass

        time.sleep(15)

    log("❌", f"Timeout after {timeout}s")
    return False


def get_instance_info(instance_id: int) -> dict:
    """Get instance details after it's running."""
    result = run_cmd(f"vastai show instance {instance_id} --raw", timeout=15)
    if result["code"] != 0:
        return {}

    try:
        return json.loads(result["stdout"])
    except json.JSONDecodeError:
        return {}


def health_check_instance(instance_id: int, timeout: int = 120) -> bool:
    """Post-provision health check: verify ComfyUI is responding via SSH.
    
    Checks that:
    1. /workspace/ComfyUI exists (workspace symlink)
    2. ComfyUI is responding on port 8188 or 18188
    3. If not, attempt manual fix and retry
    """
    log("🏥", f"Running health check on instance {instance_id}...")
    
    # Get SSH URL
    ssh_result = run_cmd(f"vastai ssh-url {instance_id}", timeout=10)
    if ssh_result["code"] != 0:
        log("⚠️", f"Cannot get SSH URL for health check: {ssh_result['stderr']}")
        return False
    
    ssh_url = ssh_result["stdout"].strip()
    # Parse ssh://root@host:port
    import re
    match = re.match(r"ssh://root@([^:]+):(\d+)", ssh_url)
    if not match:
        log("⚠️", f"Cannot parse SSH URL: {ssh_url}")
        return False
    
    ssh_host, ssh_port = match.group(1), match.group(2)
    ssh_cmd = f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p {ssh_port} root@{ssh_host}"
    
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


# =============================================================================
# Main
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(description="Vast.ai GPU server provisioning")
    parser.add_argument("--gpu", required=True, choices=["3090", "4090"], help="GPU type")
    parser.add_argument("--workflow", default=None, help="Workflow script name or alias")
    parser.add_argument("--label", required=True, help="Instance label (lowercase, no spaces)")
    parser.add_argument("--auto", action="store_true", help="Auto-select best offer without prompting")
    parser.add_argument("--dry-run", action="store_true", help="Search and show offers without provisioning")
    parser.add_argument("--max-price", type=float, default=None, help="Override max $/hr")
    parser.add_argument("--monitor", action="store_true", default=True, help="Monitor after provisioning")
    parser.add_argument("--no-monitor", action="store_true", help="Skip monitoring")
    parser.add_argument("--slow", action="store_true", help="Use slow image provisioner (default: fast)")
    parser.add_argument("--timeout", type=int, default=600, help="Max seconds to wait for running status")
    return parser.parse_args()


def main():
    args = parse_args()
    profile = GPU_PROFILES[args.gpu]

    log("🔧", f"GPU Profile: {profile['name']}")
    log("🏷️", f"Label: {args.label}")

    # Resolve workflow
    workflow_url = None
    workflow_size_gb = 0
    if args.workflow:
        workflow_url = get_workflow_url(args.workflow)
        workflow_size_gb = get_workflow_size(args.workflow)
        log("📦", f"Workflow: {args.workflow} (~{workflow_size_gb}GB)")
        log("🔗", f"URL: {workflow_url}")
    else:
        log("🖥️", "Bare ComfyUI (no workflow)")

    # Load secrets
    hf_token = load_hf_token()
    discord_webhook = load_discord_webhook()
    log("🔑", f"HF Token: {'SET' if hf_token else 'MISSING'}")
    log("📬", f"Discord Webhook: {'SET' if discord_webhook else 'MISSING'}")

    # Allocate FRP tunnel subdomain index
    frp_config = allocate_frp_index(f"instance_{args.label}")
    if frp_config:
        log("🌐", f"FRP allocated: index={frp_config.get('index')}, domains={list(frp_config.get('custom_domains', {}).values())}")
    else:
        log("⚠️", "FRP allocation failed — will fall back to Cloudflare quick tunnels")

    # Search offers
    offers = search_offers(profile, args.max_price)
    if not offers:
        log("❌", "No offers found. Try relaxing constraints or checking later.")
        sys.exit(1)

    log("📊", f"Found {len(offers)} raw offers")

    # Rank offers
    ranked = rank_offers(offers, profile, workflow_size_gb)
    if not ranked:
        log("❌", "No valid offers after filtering")
        sys.exit(1)

    # Show top 5
    print("\n" + "=" * 80)
    log("🏆", f"Top offers for {profile['name']}:")
    print("=" * 80)
    for i, o in enumerate(ranked[:5]):
        ok, issues = o.meets_specs(profile)
        status = "✅" if ok else "⚠️"
        inet_tb = o.inet_down_cost_tb
        print(
            f"  {status} #{i+1} | ID: {o.id} | ${o.dph_total:.4f}/hr | "
            f"RAM: {o.ram_gb:.0f}GB | Disk: {o.disk_gb:.0f}GB | "
            f"CUDA: {o.cuda_max_good} | Net: {o.inet_down_mbps:.0f}/{o.inet_up_mbps:.0f} Mbps | "
            f"Inet: ${inet_tb:.2f}/TB | {o.country}"
        )
        if issues:
            print(f"       ⚠️  Issues: {', '.join(issues)}")
    print("=" * 80)

    if args.dry_run:
        log("🔍", "Dry run — exiting without provisioning")
        sys.exit(0)

    # Auto-retry: try up to 5 offers if Docker fails (competitive market needs more retries)
    MAX_RETRIES = 5 if args.auto else 3
    for attempt in range(MAX_RETRIES):
        if attempt >= len(ranked):
            log("❌", f"No more offers to try (attempted {attempt})")
            sys.exit(1)

        best = ranked[attempt]
        ok, issues = best.meets_specs(profile)

        if not ok:
            log("⚠️", f"Offer #{attempt+1} has issues: {', '.join(issues)}")
            if attempt < MAX_RETRIES - 1:
                log("🔄", "Trying next offer...")
                continue
            if not args.auto:
                print("\nProceed anyway? (y/N): ", end="", flush=True)
                if input().strip().lower() != "y":
                    log("🛑", "Aborted by user")
                    sys.exit(1)

        # In auto mode: no confirmation needed — provision immediately.
        # In manual mode: ask for confirmation on first offer only.
        if not args.auto and attempt == 0:
            print(f"\n🏗️  Provision on offer {best.id} (${best.dph_total:.4f}/hr, {best.country})? (y/N): ", end="", flush=True)
            if input().strip().lower() != "y":
                log("🛑", "Aborted by user")
                sys.exit(1)

        log("🔄" if attempt > 0 else "🚀", f"Attempt {attempt+1}/{MAX_RETRIES}: {best.id} (${best.dph_total:.4f}/hr, {best.country})")

        # Provision
        instance_id = provision_instance(
            offer=best,
            profile=profile,
            label=args.label,
            workflow_url=workflow_url,
            hf_token=hf_token,
            discord_webhook=discord_webhook,
            frp_config=frp_config,
            fast_mode=not args.slow,
        )

        if not instance_id:
            log("❌", f"Provisioning failed on host {best.host_id}")
            save_failed_host(best.host_id)
            if attempt < MAX_RETRIES - 1:
                log("🔄", "Trying next offer...")
                continue
            sys.exit(1)

        # Monitor
        if args.monitor and not args.no_monitor:
            success = monitor_instance(instance_id, timeout=args.timeout, host_id=best.host_id)
            if success:
                # Post-provision health check
                health_ok = health_check_instance(instance_id, timeout=120)
                if not health_ok:
                    log("⚠️", "Health check failed — instance is running but ComfyUI may need manual setup")
                    log("📋", "SSH in and check: ssh_cmd, supervisorctl status, /workspace/ComfyUI")

                info = get_instance_info(instance_id)
                ssh_url_result = run_cmd(f"vastai ssh-url {instance_id}", timeout=10)
                ssh_url = ssh_url_result.get("stdout", "N/A")

                print("\n" + "=" * 80)
                log("🎉", "SERVER READY!")
                print("=" * 80)
                print(f"  Instance ID:  {instance_id}")
                print(f"  GPU:          {best.gpu_name}")
                print(f"  Cost:         ${best.dph_total:.4f}/hr")
                print(f"  Location:     {best.country}")
                print(f"  SSH:          {ssh_url}")
                print(f"  Portal:       https://cloud.vast.ai/instances/{instance_id}")
                if frp_config and frp_config.get("custom_domains"):
                    print("  FRP Tunnels:")
                    for service, url in frp_config["custom_domains"].items():
                        print(f"    {service}: {url}")
                if workflow_url:
                    print(f"  Workflow:     {args.workflow} (downloading in background)")
                print("=" * 80)
                sys.exit(0)
            else:
                log("❌", f"Instance {instance_id} did not reach running status")
                save_failed_host(best.host_id)
                if attempt < MAX_RETRIES - 1:
                    log("🔄", "Trying next offer...")
                    continue
                log("📋", f"Check: https://cloud.vast.ai/instances/{instance_id}")
                sys.exit(1)
        else:
            log("✅", f"Instance {instance_id} created — monitoring skipped")
            log("📋", f"https://cloud.vast.ai/instances/{instance_id}")
            sys.exit(0)

    log("❌", f"All {MAX_RETRIES} attempts failed")
    sys.exit(1)


if __name__ == "__main__":
    main()
