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
import ast
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from vastai import VastAI
except ImportError:
    print("❌ ERROR: 'vastai' python package is required. Install with: pip install vastai")
    sys.exit(1)


def _load_dotenv():
    """Load .env file from project root (walks up from this script's location)."""
    search = Path(__file__).resolve().parent
    for _ in range(6):  # Walk up max 6 levels
        env_file = search / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key, value = key.strip(), value.strip()
                    if value and key not in os.environ:  # Don't override existing env
                        os.environ[key] = value
            return
        search = search.parent

_load_dotenv()

# =============================================================================
# GPU Profiles
# =============================================================================

GPU_PROFILES = {
    "3090": {
        "name": "RTX_3090",
        "num_gpus": 1,
        "min_ram_gb": 24,           # VRAM is bottleneck, not system RAM
        "min_disk_gb": 100,
        "min_inet_down_mbps": 500,  # 500 Mbps min — critical for 25GB+ model downloads
        "min_inet_up_mbps": 500,
        "min_cpu_cores": 2,
        "min_reliability": 0.95,    # 95% — host must be mostly reliable
        "cuda_min": 12.8,           # cuda-12.9 image requires CUDA 12.8+ hardware capability
        "driver_min": "570.0.0",    # NV driver 570+ REQUIRED for CUDA 12.9 (560/565 fail with Error 804)
        "max_price_hr": 0.30,       # Relaxed from 0.25 to show more options
        "max_inet_down_cost_tb": 0.05,
        "docker_image": "vastai/comfy:v0.20.1-cuda-12.9-py312",
        "skip_countries": ["CN"],    # China — slow HF downloads
        "notes": "32GB system RAM is fine for ComfyUI. Driver 580.x preferred (native CUDA 13.0). Driver 570.x works but may need compat lib fix.",
    },
    "4090": {
        "name": "RTX_4090",
        "num_gpus": 1,
        "min_ram_gb": 24,
        "min_disk_gb": 100,
        "min_inet_down_mbps": 500,
        "min_inet_up_mbps": 500,
        "min_cpu_cores": 2,
        "min_reliability": 0.95,
        "cuda_min": 12.8,
        "driver_min": "570.0.0",    # NV driver 570+ REQUIRED for CUDA 12.9
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

# Maps friendly names/aliases → actual filenames in scripts/workflows/
# IMPORTANT: These MUST match real files. See .agents/rules/workflow-alias-maintenance.md
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
    "prompt-relay": "ltx-23-prompt-relay.sh",
    # LTX 2.3 — I2V Keyframe
    "ltx-23-i2v-keyframe": "ltx-23-i2v-keyframe.sh",
    "ltx23-keyframe": "ltx-23-i2v-keyframe.sh",
    # LTX 2.3 — I2V Distilled
    "ltx-23-i2v-distilled": "ltx-23-i2v-distilled.sh",
    "ltx23-distilled": "ltx-23-i2v-distilled.sh",
    # Qwen Image Edit
    "qwen": "qwen-image-edit.sh",
    "qwen-image": "qwen-image-edit.sh",
    "qwen-image-edit": "qwen-image-edit.sh",
}

# =============================================================================
# Config — loaded from .env file or environment variables
# =============================================================================

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
HF_TOKEN_PATH = "/root/config/token.json"
FAILED_HOSTS_PATH = str(Path(__file__).resolve().parent / "failed_hosts.json")
FRP_ALLOCATE_SCRIPT = "/usr/local/bin/frp-allocate-port"
FRP_SERVER_ADDR = os.environ.get("FRP_SERVER_ADDR", "159.195.52.130")
FRP_SERVER_PORT = int(os.environ.get("FRP_SERVER_PORT", "7000"))
FRP_TOKEN = os.environ.get("FRP_TOKEN", "")  # Loaded from .env — NEVER hardcode
VAST_API_KEY = os.environ.get("VAST_API_KEY", "") # Automatically loaded by SDK if set, or via ~/.vast_api_key

# Initialize SDK globally
# If VAST_API_KEY is empty, VastAI() will fallback to ~/.vast_api_key
try:
    vast_client = VastAI(api_key=VAST_API_KEY) if VAST_API_KEY else VastAI()
except Exception as e:
    print(f"❌ Failed to initialize Vast.ai SDK: {e}")
    sys.exit(1)
FAST_PROVISION_URL = "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/fast-provision.sh"

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
    """Load HF token from env var (set by .env) or JSON config file."""
    # Check env var first (loaded by _load_dotenv from .env)
    token = os.environ.get("HF_TOKEN", "")
    if token:
        return token
    # Fall back to JSON config file
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

        # Driver version check (570.0.0+ required for CUDA 12.9)
        driver_min = profile.get("driver_min", "570.0.0")
        if self.nv_driver and self.nv_driver != "Unknown":
            # Parse driver version (e.g., "580.126.09" -> [580, 126, 9])
            try:
                parts = [int(x) for x in self.nv_driver.split(".")]
                min_parts = [int(x) for x in driver_min.split(".")]
                # Compare major version
                if parts[0] < min_parts[0]:
                    issues.append(f"Driver {self.nv_driver} < {driver_min} (CUDA 12.9 incompatible)")
            except (ValueError, IndexError):
                pass  # Unknown format, skip check

        # Country skip
        for skip in profile.get("skip_countries", []):
            if skip.lower() in (self.country or "").lower():
                issues.append(f"Country {self.country} in skip list")
                break

        return (len(issues) == 0, issues)


def search_offers(profile: dict, max_price: Optional[float] = None) -> list[Offer]:
    """Search Vast.ai for offers matching GPU profile.
    
    Always searches both verified and unverified hosts (via -n flag).
    Ranking handles preference (unverified preferred by default).
    """
    price = max_price or profile["max_price_hr"]
    failed_hosts = load_failed_hosts()

    # Build search query — filter at API level to avoid fetching unsuitable hosts
    # -n flag disables default 'verified=true', so we get both verified + unverified
    driver_min = profile.get("driver_min", "570.0.0")
    min_inet = profile.get("min_inet_down_mbps", 500)
    query = (
        f"gpu_name={profile['name']} "
        f"num_gpus={profile['num_gpus']} "
        f"rented=False "
        f"dph<={price + 0.10} "
        f"cuda_max_good>={profile['cuda_min'] - 0.5} "
        f"driver_version>={driver_min} "
        f"inet_down>={min_inet} "
        f"inet_up>={min_inet}"
    )

    log("🔍", f"Searching offers: {query}")
    try:
        raw_data = vast_client.search_offers(query=query, limit=30, order='dph+')
    except Exception as e:
        log("❌", f"Search failed: {e}")
        return []

    if not isinstance(raw_data, list):
        log("❌", f"Failed to parse search results. Expected list, got {type(raw_data)}")
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


def rank_offers(offers: list[Offer], profile: dict, workflow_size_gb: float = 0, verified_only: bool = False) -> list[Offer]:
    """Filter and rank offers. Best = meets specs + lowest total cost.
    
    Default: unverified hosts preferred (cheaper). The reliability filter
    already ensures minimum quality, so verification status is secondary.
    Pass verified_only=True to prefer verified hosts instead.
    """
    valid = []
    for o in offers:
        ok, _ = o.meets_specs(profile)
        if ok:
            if verified_only and not o._is_verified:
                continue  # Skip unverified when --verified-only
            valid.append(o)

    if not valid:
        log("⚠️", "No offers meet all specs — showing all available sorted by price")
        return sorted(offers, key=lambda o: o.dph_total)[:5]

    # Score: dph + estimated inet cost for workflow
    # Unverified hosts are preferred by default (they're 30-50% cheaper)
    for o in valid:
        estimated_inet_cost = workflow_size_gb * o.inet_down_cost_gb if workflow_size_gb > 0 else 0
        o._total_cost = o.dph_total + (estimated_inet_cost / 10)
        if not verified_only and o._is_verified:
            o._total_cost += 0.01  # Small penalty so cheaper unverified hosts rank first

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

    # FRP tunneling configuration — OPTIONAL
    # Falls back to Cloudflare quick tunnels if FRP is not available
    if frp_config:
        env_parts.append(f'-e FRP_INDEX="{frp_config.get("index", 0)}"')
        env_parts.append(f'-e FRP_SERVER_ADDR="{FRP_SERVER_ADDR}"')
        env_parts.append(f'-e FRP_SERVER_PORT="{FRP_SERVER_PORT}"')
        frp_token = _load_frp_token()
        if frp_token:
            env_parts.append(f'-e FRP_TOKEN="{frp_token}"')
    else:
        log("⚠️", "No FRP config — instance will use Cloudflare quick tunnels")

    env_parts.extend([
        '-e PORTAL_CONFIG="localhost:1111:11111:/:Instance Portal|localhost:8188:18188:/:ComfyUI|localhost:8080:18080:/:Jupyter|localhost:8080:8080:/terminals/1:Jupyter Terminal"',
        '-e OPEN_BUTTON_PORT="1111"',
        '-e JUPYTER_DIR="/"',
        '-e DATA_DIRECTORY="/workspace/"',
        '-e OPEN_BUTTON_TOKEN="1"',
    ])

    return " ".join(env_parts)


def _load_frp_token() -> str:
    """Load FRP token from .env (via FRP_TOKEN env var) or VPS config."""
    # 1. From .env / environment variable (preferred)
    if FRP_TOKEN:
        return FRP_TOKEN
    # 2. Fallback: VPS server config (when running on the FRP server itself)
    try:
        with open("/etc/frp/frps.toml") as f:
            for line in f:
                if 'auth.token' in line:
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

    log("🚀", f"Provisioning instance on host {offer.host_id} (${offer.dph_total:.4f}/hr)...")

    try:
        # Pass parameters as expected by the vastai SDK
        # Some SDK versions expect kwarg names matching CLI parameters exactly
        data = vast_client.create_instance(
            id=str(offer.id),
            image=profile['docker_image'],
            env=env_str,
            disk=disk,
            label=label,
            direct=True,
            ssh=True,
            jupyter=True,
            cancel_unavail=True,
            onstart_cmd=onstart_cmd
        )
    except Exception as e:
        log("❌", f"Provisioning failed: {e}")
        return None

    if isinstance(data, dict):
        instance_id = data.get("new_contract")
        if instance_id:
            # Vast.ai API often returns success=False even when the instance
            # IS created. Trust new_contract as the real indicator.
            if not data.get("success"):
                log("⚠️", f"API returned success=False but instance was created (known API quirk)")
            log("✅", f"Instance created: {instance_id}")
            return instance_id
        # No new_contract — genuinely failed
        error_msg = str(data.get("error", "")) or str(data.get("message", ""))
        if "no_such_ask" in str(data) or "not available" in error_msg:
            log("⚠️", "Offer no longer available — will try next offer")
        else:
            log("❌", f"Instance creation failed: {data}")
        return None
    elif hasattr(data, 'new_contract') and data.new_contract:
        # Just in case SDK returns an object
        instance_id = data.new_contract
        log("✅", f"Instance created: {instance_id}")
        return instance_id

    log("❌", f"Failed to parse provisioning response: {data}")
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
        try:
            instances = vast_client.show_instances()
        except Exception as e:
            log("⚠️", f"Failed to check status: {e}")
            time.sleep(10)
            continue

        data = None
        for inst in instances:
            # Handle both dicts and object models
            inst_id = inst.get("id") if isinstance(inst, dict) else getattr(inst, "id", None)
            if str(inst_id) == str(instance_id):
                data = inst if isinstance(inst, dict) else inst.__dict__
                break
                
        if not data:
            log("⚠️", f"Instance {instance_id} not found in instances list. Waiting...")
            time.sleep(10)
            continue

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


        time.sleep(15)

    log("❌", f"Timeout after {timeout}s")
    return False


def get_instance_info(instance_id: int) -> dict:
    """Get instance details after it's running."""
    try:
        instances = vast_client.show_instances()
        for inst in instances:
            inst_id = inst.get("id") if isinstance(inst, dict) else getattr(inst, "id", None)
            if str(inst_id) == str(instance_id):
                return inst if isinstance(inst, dict) else inst.__dict__
    except Exception as e:
        log("⚠️", f"Failed to get instance info: {e}")
    return {}


def health_check_instance(instance_id: int, timeout: int = 120) -> bool:
    """Post-provision health check: verify ComfyUI is responding via SSH.
    
    Checks that:
    1. /workspace/ComfyUI exists (workspace symlink)
    2. ComfyUI is responding on port 8188 or 18188
    3. If not, attempt manual fix and retry
    """
    log("🏥", f"Running health check on instance {instance_id}...")
    
    # Get SSH Info
    info = get_instance_info(instance_id)
    ssh_host = info.get("ssh_host")
    ssh_port = info.get("ssh_port")
    
    if not ssh_host or not ssh_port:
        log("⚠️", f"Cannot get SSH info for health check. Info: {info}")
        return False
    
    ssh_url = f"ssh://root@{ssh_host}:{ssh_port}"
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
    parser.add_argument("--verified-only", action="store_true", help="Only show verified hosts (default: prefer unverified/cheaper)")
    parser.add_argument("--no-frp", action="store_true", help="Skip FRP tunnel setup (use Cloudflare quick tunnels)")
    return parser.parse_args()


def send_discord_notification(webhook_url: str, instance_id: int, gpu_name: str, cost: str,
                               location: str, ssh_url: str, frp_domains: dict = None,
                               workflow_status: str = "", emoji: str = "🖥️", title: str = "Vast.ai Server Ready") -> bool:
    """Send a notification to Discord."""
    if not webhook_url:
        return False

    lines = [
        f"{emoji} **{title}**",
        f"**Instance:** {instance_id} | **GPU:** {gpu_name} | **Cost:** {cost}",
        f"📍 {location}",
        f"🔑 SSH: `{ssh_url}`",
    ]
    if frp_domains:
        for service, url in frp_domains.items():
            lines.append(f"🔗 {service.capitalize()}: {url}")
    if workflow_status:
        lines.append(f"📦 Workflow: {workflow_status}")

    payload = {"content": "\n".join(lines)}

    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "HermesBot/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 204
    except Exception as e:
        log("⚠️", f"Discord notification failed: {e}")
        return False


def wait_for_workflow(ssh_url: str, timeout: int = 600) -> bool:
    """Wait for the onstart workflow script to finish downloading models via SSH.

    Polls /workspace/workflow.log every 30s until it sees 'All downloads completed'
    or 'Done!', or until timeout. Returns True if workflow completed successfully.
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
    ssh_cmd = f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p {port} root@{host}"

    elapsed = 0
    interval = 30
    while elapsed < timeout:
        # Check if workflow process is still running
        result = run_cmd(
            f'{ssh_cmd} "ps aux | grep -v grep | grep \\"workflow.sh\\" | head -1"',
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

    # Allocate FRP tunnel subdomain index (optional)
    frp_config = None
    if not args.no_frp:
        frp_config = allocate_frp_index(f"instance_{args.label}")
        if frp_config:
            log("🌐", f"FRP allocated: index={frp_config.get('index')}, domains={frp_config.get('custom_domains', {})}")
        else:
            log("⚠️", "FRP allocation failed — will use Cloudflare quick tunnels instead")
    else:
        log("🌐", "FRP disabled (--no-frp) — will use Cloudflare quick tunnels")

    # Search offers
    offers = search_offers(profile, args.max_price)
    if not offers:
        log("❌", "No offers found. Try relaxing constraints or checking later.")
        sys.exit(1)

    log("📊", f"Found {len(offers)} raw offers")

    # Rank offers
    ranked = rank_offers(offers, profile, workflow_size_gb, verified_only=args.verified_only)
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
                ssh_host = info.get("ssh_host", "N/A")
                ssh_port = info.get("ssh_port", "N/A")
                ssh_url = f"ssh://root@{ssh_host}:{ssh_port}" if ssh_host != "N/A" else "N/A"
                # === Notification 1: Server Ready (immediate) ===
                print("\n" + "=" * 80)
                log("🎉", "SERVER READY!")
                print("=" * 80)
                print(f"  Instance ID:  {instance_id}")
                print(f"  GPU:          {best.gpu_name}")
                print(f"  Cost:         ${best.dph_total:.4f}/hr")
                print(f"  Location:     {best.country}")
                print(f"  SSH:          {ssh_url}")
                print(f"  Portal:       https://cloud.vast.ai/instances/{instance_id}")
                if frp_config.get("custom_domains"):
                    print("  FRP Tunnels:")
                    for service, url in frp_config["custom_domains"].items():
                        print(f"    {service}: {url}")
                if workflow_url:
                    print(f"  Workflow:     {args.workflow} (downloading in background)")
                print("=" * 80)

                if discord_webhook:
                    frp_domains = frp_config.get("custom_domains")
                    workflow_note = f"{args.workflow} — models downloading in background" if workflow_url else ""
                    sent = send_discord_notification(
                        discord_webhook, instance_id, best.gpu_name,
                        f"${best.dph_total:.4f}/hr", best.country, ssh_url, frp_domains,
                        workflow_status=workflow_note,
                        emoji="🟢", title="Server Ready"
                    )
                    if sent:
                        log("📬", "Discord notification sent (Server Ready)")
                    else:
                        log("⚠️", "Discord notification failed (Server Ready)")

                # === Wait for workflow downloads, then Notification 2: Models Ready ===
                if workflow_url and health_ok:
                    workflow_done = wait_for_workflow(ssh_url, timeout=600)
                    if workflow_done:
                        workflow_status = f"{args.workflow} ✅ models downloaded"
                    else:
                        workflow_status = f"{args.workflow} ⚠️ still downloading"
                else:
                    workflow_status = ""

                if workflow_url and discord_webhook and workflow_status:
                    sent2 = send_discord_notification(
                        discord_webhook, instance_id, best.gpu_name,
                        f"${best.dph_total:.4f}/hr", best.country, ssh_url, frp_domains,
                        workflow_status=workflow_status,
                        emoji="📦", title="Models Ready"
                    )
                    if sent2:
                        log("📬", "Discord notification sent (Models Ready)")
                    else:
                        log("⚠️", "Discord notification failed (Models Ready)")

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
