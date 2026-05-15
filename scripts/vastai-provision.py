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
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Vast.ai Python SDK — pip install vastai>=0.4.0
from vastai import VastAI

# Optional: enable SDK request/response tracing
SDK_EXPLAIN = os.environ.get("VAST_SDK_EXPLAIN", "").lower() in ("1", "true", "yes")


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
# SDK Client — initialized after dotenv so VAST_API_KEY is available
# =============================================================================

VAST_API_KEY = os.environ.get("VAST_API_KEY", "")
# raw=True ensures all methods return plain dicts/lists rather than formatted text
# explain=True (via VAST_SDK_EXPLAIN=1 env var) prints every request/response for debugging
vast = VastAI(
    api_key=VAST_API_KEY if VAST_API_KEY else None,
    raw=True,
    explain=SDK_EXPLAIN,
)

# =============================================================================
# GPU Profiles
# =============================================================================

GPU_PROFILES = {
    "3090": {
        "name": "RTX_3090",
        "num_gpus": 1,
        "min_ram_gb": 24,           # VRAM is bottleneck, not system RAM
        "min_disk_gb": 100,
        "min_inet_down_mbps": 400,  # 400 Mbps min — still good for 25GB+ model downloads
        "min_inet_up_mbps": 300,
        "min_cpu_cores": 2,
        "min_reliability": 0.95,    # 95% — host must be mostly reliable
        "cuda_min": 12.8,           # cuda-12.9 image requires CUDA 12.8+ hardware capability
        "driver_min": "570.0.0",    # NV driver 570+ REQUIRED for CUDA 12.9 (560/565 fail with Error 804)
        "max_price_hr": 0.30,       # Relaxed from 0.25 to show more options
        "max_inet_down_cost_tb": 0.05,
        "docker_image": "vastai/comfy:v0.20.1-cuda-12.9-py312",
        "skip_countries": [],        # No country exclusions
        "notes": "32GB system RAM is fine for ComfyUI. Driver 580.x preferred (native CUDA 13.0). Driver 570.x works but may need compat lib fix.",
    },
    "4090": {
        "name": "RTX_4090",
        "num_gpus": 1,
        "min_ram_gb": 24,
        "min_disk_gb": 100,
        "min_inet_down_mbps": 400,
        "min_inet_up_mbps": 300,
        "min_cpu_cores": 2,
        "min_reliability": 0.95,
        "cuda_min": 12.8,
        "driver_min": "570.0.0",    # NV driver 570+ REQUIRED for CUDA 12.9
        "max_price_hr": 0.50,       # Relaxed from 0.40
        "max_inet_down_cost_tb": 0.05,
        "docker_image": "vastai/comfy:v0.20.1-cuda-12.9-py312",
        "skip_countries": [],
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
    # Qwen Image Edit 2511 4-Step Lightning
    "qwen-image-edit-2511-4steps": "qwen-image-edit-2511-4steps.sh",
    "qwen-2511": "qwen-image-edit-2511-4steps.sh",
    "qwen-image-edit-2511": "qwen-image-edit-2511-4steps.sh",
    "qwen-image-lightning-4steps": "qwen-image-edit-2511-4steps.sh",
}

# =============================================================================
# Config — loaded from .env file or environment variables
# =============================================================================

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
HF_TOKEN_PATH = "/root/config/token.json"
FAILED_HOSTS_PATH = str(Path(__file__).resolve().parent / "failed_hosts.json")
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
    """Load failed hosts tracker.
    Returns dict with host_id -> {timestamp, count, permanent, last_error}.
    Backward-compatible with old {host_id: timestamp} format.
    """
    try:
        with open(FAILED_HOSTS_PATH) as f:
            data = json.load(f)
            # Migrate old flat format to new structured format
            migrated = {}
            for host_id, value in data.items():
                if isinstance(value, (int, float)):
                    migrated[host_id] = {
                        "timestamp": value,
                        "count": 1,
                        "permanent": False,
                        "last_error": "",
                    }
                elif isinstance(value, dict):
                    migrated[host_id] = value
            return migrated
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def classify_host_failure(instance_info: dict) -> tuple[str, bool]:
    """Classify why an instance failed. Returns (reason_code, is_permanent).
    Permanent failures mean the host itself is broken and will never work.
    Transient failures may succeed on a different day/offer.
    """
    status_msg = str(instance_info.get("status_msg", "")).lower()
    actual_status = str(instance_info.get("actual_status", "")).lower()

    # Permanent host failures — these will happen every time on this host
    permanent_patterns = [
        ("cdi device", "CDI GPU injection failure — host NVIDIA runtime broken"),
        ("oci runtime", "OCI runtime failure — container spec invalid"),
        ("failed to start containers", "Docker daemon permanently broken"),
        ("no such container", "Docker daemon failure — container never created"),
        ("kaalia", "Host agent (kaalia) broken"),
        ("nvidia-smi", "NVIDIA driver/CUDA incompatibility"),
        ("cuda error 804", "CUDA Error 804 — driver too old"),
        ("insufficient resources", "Host has insufficient GPU resources"),
    ]

    for pattern, description in permanent_patterns:
        if pattern in status_msg:
            return (description, True)

    # Docker image pull timeout — may succeed later
    if "pull" in status_msg and ("timeout" in status_msg or "deadline" in status_msg):
        return ("Docker image pull timeout — may succeed later", False)

    # Generic loading timeout — may be network congestion
    if actual_status == "loading" and not status_msg:
        return ("Instance stuck loading — possible slow network/host", False)

    # Unknown/uncategorized
    return (f"Unknown failure: {status_msg[:100]}", False)


def save_failed_host(host_id: int, instance_info: dict = None):
    """Record a host as failed. If instance_info provided, classify the failure."""
    failed = load_failed_hosts()
    host_id_str = str(host_id)
    now = time.time()

    # Classify if we have instance info
    reason = "Unknown"
    permanent = False
    if instance_info:
        reason, permanent = classify_host_failure(instance_info)

    if host_id_str in failed:
        # Increment failure count
        failed[host_id_str]["count"] = failed[host_id_str].get("count", 1) + 1
        failed[host_id_str]["timestamp"] = now
        failed[host_id_str]["last_error"] = reason
        # Once marked permanent, always permanent
        if permanent:
            failed[host_id_str]["permanent"] = True
    else:
        failed[host_id_str] = {
            "timestamp": now,
            "count": 1,
            "permanent": permanent,
            "last_error": reason,
        }

    # Clean up transient entries older than 24 hours (keep permanent forever)
    cutoff = now - 86400
    cleaned = {}
    for hid, record in failed.items():
        if record.get("permanent", False):
            cleaned[hid] = record
        elif record.get("timestamp", 0) > cutoff:
            cleaned[hid] = record

    with open(FAILED_HOSTS_PATH, "w") as f:
        json.dump(cleaned, f, indent=2)

    if permanent:
        log("🚫", f"Host {host_id} PERMANENTLY blacklisted: {reason}")
    else:
        log("📝", f"Host {host_id} marked as failed (skipped for 24h): {reason}")


def create_cloudflare_tunnel(label: str) -> dict:
    """Create a Cloudflare named tunnel for a new GPU instance.
    Uses cloudflared CLI with origin certificate (cert.pem) auth.
    Returns dict with tunnel_id, token, hostname.
    """
    tunnel_name = f"comfy-{label}-{int(time.time())}"
    result = run_cmd(f"cloudflared tunnel create '{tunnel_name}'", timeout=30)
    if result["code"] != 0:
        log("⚠️", f"Cloudflare tunnel creation failed: {result['stderr']}")
        return {}
    match = re.search(r'id ([a-f0-9-]+)', result['stdout'])
    if not match:
        log("⚠️", f"Could not extract tunnel ID from: {result['stdout']}")
        return {}
    tunnel_id = match.group(1)
    hostname = f"comfy-{label}.lxc.muneesraja.com"
    route_result = run_cmd(f"cloudflared tunnel route dns '{tunnel_id}' '{hostname}'", timeout=30)
    if route_result["code"] != 0:
        log("⚠️", f"DNS route creation failed: {route_result['stderr']}")
    token_result = run_cmd(f"cloudflared tunnel token '{tunnel_id}'", timeout=10)
    if token_result["code"] != 0:
        log("⚠️", f"Tunnel token retrieval failed: {token_result['stderr']}")
        return {}
    tunnel_token = token_result["stdout"].strip()
    log("🌐", f"Cloudflare tunnel: {hostname} (id={tunnel_id})")
    return {
        "tunnel_id": tunnel_id,
        "token": tunnel_token,
        "hostname": hostname,
        "tunnel_name": tunnel_name,
    }


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

        if self.ram_gb <= profile["min_ram_gb"]:
            issues.append(f"RAM {self.ram_gb:.0f}GB < {profile['min_ram_gb']}GB")
        if self.disk_gb <= profile["min_disk_gb"]:
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
    """Search Vast.ai for offers matching GPU profile using the Python SDK.

    Uses no_default=True to mirror the CLI -n flag behaviour — returns both
    verified and unverified hosts. Ranking then handles preference.
    """
    price = max_price or profile["max_price_hr"]
    failed_hosts = load_failed_hosts()

    # Build query string — the SDK accepts the same syntax as the CLI
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

    log("🔍", f"Searching offers via SDK: {query}")
    try:
        # no_default=True → skip verified=True default (mirrors CLI -n flag)
        # order="dph_total" → cheapest first
        raw_data = vast.search_offers(
            query=query,
            no_default=True,
            order="dph_total",
            limit=30,
        )
    except Exception as e:
        log("❌", f"SDK search_offers failed: {e}")
        return []

    if not isinstance(raw_data, list):
        log("❌", f"Unexpected search result type: {type(raw_data)}")
        return []

    offers = []
    skipped_failed = 0
    now = time.time()
    for o in raw_data:
        try:
            host_id = int(o.get("host_id", 0))
            host_id_str = str(host_id)
            if host_id_str in failed_hosts:
                record = failed_hosts[host_id_str]
                # Permanent blacklists are forever
                if record.get("permanent", False):
                    skipped_failed += 1
                    continue
                # Transient failures expire after 24 hours
                if record.get("timestamp", 0) > (now - 86400):
                    skipped_failed += 1
                    continue

            ram = o.get("cpu_ram", 0)
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
                reliability=float(o.get("reliability", 0)) * 100,  # API returns 0-1
                inet_down_cost_gb=float(o.get("inet_down_cost", 0)),
                inet_up_cost_gb=float(o.get("inet_up_cost", 0)),
                country=o.get("geolocation", "Unknown"),
                host_id=int(o.get("host_id", 0)),
                nv_driver=o.get("driver_version", "Unknown"),
                _is_verified=o.get("verification") in ("verified", "deverified"),
            ))
        except (KeyError, ValueError, TypeError):
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
                           discord_webhook: str, cloudflare_config: Optional[dict] = None) -> dict:
    """Build the env dict for vast.create_instance().

    Returns a plain {KEY: VALUE} dict. The SDK's create_instance() accepts
    this directly as its `env` parameter — no shell escaping needed.
    Note: port mapping (-p 8188:8188) is handled by the Docker image and the
    --direct flag (passed via extra={"direct": True} in provision_instance).
    """
    env = {
        "COMFYUI_ARGS": "--disable-auto-launch --port 18188 --enable-cors-header --listen 0.0.0.0",
        "PROVISIONING_SCRIPT": f"https://raw.githubusercontent.com/{WORKFLOWS_REPO}/{WORKFLOWS_BRANCH}/scripts/comfyui-bootstrap.sh",
        "PORTAL_CONFIG": "localhost:1111:11111:/:Instance Portal|localhost:8188:18188:/:ComfyUI|localhost:8080:18080:/:Jupyter|localhost:8080:8080:/terminals/1:Jupyter Terminal",
        "OPEN_BUTTON_PORT": "1111",
        "JUPYTER_DIR": "/",
        "DATA_DIRECTORY": "/workspace/",
        "OPEN_BUTTON_TOKEN": "1",
    }

    if discord_webhook:
        env["DISCORD_WEBHOOK_URL"] = discord_webhook

    if hf_token:
        env["HF_TOKEN"] = hf_token

    if workflow_url:
        env["WORKFLOW_SCRIPT"] = workflow_url

    # Cloudflare named tunnel — replaces FRP
    if cloudflare_config:
        env["CF_TUNNEL_TOKEN"] = cloudflare_config.get("token", "")
        env["CF_TUNNEL_HOSTNAME"] = cloudflare_config.get("hostname", "")
    else:
        log("ℹ️", "No Cloudflare tunnel — instance will use quick tunnels")

    return env


def _build_onstart_cmd(fast_mode: bool) -> str:
    """Return the onstart command string."""
    if fast_mode:
        return f"curl -sSL '{FAST_PROVISION_URL}' | bash"
    return "entrypoint.sh"


def provision_instance_launch(
    profile: dict,
    label: str,
    workflow_url: Optional[str],
    hf_token: str,
    discord_webhook: str,
    cloudflare_config: Optional[dict] = None,
    fast_mode: bool = True,
    max_price: Optional[float] = None,
) -> tuple[Optional[int], Optional[Offer]]:
    """Atomic search-and-provision using launch_instance API.

    Uses the /launch_instance/ endpoint which searches and creates in a single
    API call, eliminating the race condition between search and create that
    causes 400 Bad Request (offer no longer available).

    Returns (instance_id, offer_used) or (None, None).
    """
    env_dict = build_provisioning_env(profile, workflow_url, hf_token, discord_webhook, cloudflare_config)
    disk = profile["min_disk_gb"]
    onstart_cmd = _build_onstart_cmd(fast_mode)

    if fast_mode:
        log("⚡", "Using FAST provisioning mode (atomic launch)")
    else:
        log("🐢", "Using SLOW image provisioner (atomic launch)")

    # Build a query dict matching our search filters so launch_instance
    # internally finds the same quality hosts we would have picked manually.
    price = max_price or profile["max_price_hr"]
    driver_min = profile.get("driver_min", "570.0.0")
    min_inet = profile.get("min_inet_down_mbps", 400)
    query_str = (
        f"gpu_name={profile['name']} "
        f"num_gpus={profile['num_gpus']} "
        f"rented=False "
        f"dph<={price + 0.10} "
        f"cuda_max_good>={profile['cuda_min'] - 0.5} "
        f"driver_version>={driver_min} "
        f"inet_down>={min_inet} "
        f"inet_up>={min_inet}"
    )

    log("🚀", f"Atomic launch via SDK: {profile['name']} ≤ ${price:.2f}/hr")

    try:
        data = vast.launch_instance(
            gpu_name=profile["name"],
            num_gpus=str(profile["num_gpus"]),
            image=profile["docker_image"],
            disk=disk,
            env=env_dict,
            label=label,
            onstart_cmd=onstart_cmd,
            cancel_unavail=True,
            runtype="ssh",
            jupyter_lab=True,
            jupyter_dir="/",
            extra="-p 8188:8188",
            order="dph_total",
            limit=5,
        )
    except Exception as e:
        error_text = str(e)
        api_error = ""
        if hasattr(e, "response") and e.response is not None:
            try:
                resp_json = e.response.json()
                api_error = resp_json.get("msg", resp_json.get("error", ""))
            except Exception:
                api_error = e.response.text[:200]

        if "no_such_ask" in error_text.lower() or "not available" in (api_error or "").lower():
            log("⚠️", f"Atomic launch: no offers available — falling back to manual search")
        elif "insufficient" in (api_error or "").lower():
            log("🚫", f"Atomic launch: insufficient resources — {api_error[:100]}")
        else:
            log("❌", f"Atomic launch failed: {error_text}")
            if api_error:
                log("📋", f"API detail: {api_error[:200]}")
        return None, None

    if not isinstance(data, dict):
        log("❌", f"Unexpected launch_instance response type: {type(data)}")
        return None, None

    instance_id = data.get("new_contract")
    if instance_id:
        if not data.get("success"):
            log("⚠️", "API returned success=False but instance was created (known API quirk)")
        log("✅", f"Instance created via atomic launch: {instance_id}")

        # Reconstruct an Offer from the launch response if available
        offer = None
        offer_data = data.get("offer") or {}
        if offer_data:
            try:
                ram = offer_data.get("cpu_ram", 0)
                if isinstance(ram, (int, float)) and ram > 1000:
                    ram = ram / 1024
                offer = Offer(
                    id=offer_data.get("id", 0),
                    gpu_name=offer_data.get("gpu_name", profile["name"]),
                    cuda_max_good=float(offer_data.get("cuda_max_good", 0)),
                    cpu_ghz=float(offer_data.get("cpu_ghz", 0)),
                    vcpus=float(offer_data.get("num_cpus", 0)),
                    ram_gb=ram,
                    disk_gb=float(offer_data.get("disk_space", 0)),
                    dph_total=float(offer_data.get("dph_total", 0)),
                    inet_down_mbps=float(offer_data.get("inet_down", 0)),
                    inet_up_mbps=float(offer_data.get("inet_up", 0)),
                    reliability=float(offer_data.get("reliability", 0)) * 100,
                    inet_down_cost_gb=float(offer_data.get("inet_down_cost", 0)),
                    inet_up_cost_gb=float(offer_data.get("inet_up_cost", 0)),
                    country=offer_data.get("geolocation", "Unknown"),
                    host_id=int(offer_data.get("host_id", 0)),
                    nv_driver=offer_data.get("driver_version", "Unknown"),
                    _is_verified=offer_data.get("verification") in ("verified", "deverified"),
                )
            except (KeyError, ValueError, TypeError):
                pass
        return instance_id, offer

    error_msg = str(data.get("error", "")) or str(data.get("msg", ""))
    if "no_such_ask" in str(data) or "not available" in error_msg:
        log("⚠️", "Atomic launch: no offers available")
    else:
        log("❌", f"Atomic launch failed: {data}")
    return None, None


def provision_instance(offer: Offer, profile: dict, label: str,
                       workflow_url: Optional[str], hf_token: str,
                       discord_webhook: str, cloudflare_config: Optional[dict] = None,
                       fast_mode: bool = True) -> Optional[int]:
    """Provision a Vast.ai instance via the Python SDK using a specific offer ID.
    This is the fallback path when atomic launch_instance is unavailable or
    when the user wants to pick a specific offer in manual mode."""
    env_dict = build_provisioning_env(profile, workflow_url, hf_token, discord_webhook, cloudflare_config)
    disk = max(profile["min_disk_gb"], int(offer.disk_gb * 0.8))
    onstart_cmd = _build_onstart_cmd(fast_mode)

    if fast_mode:
        log("⚡", "Using FAST provisioning mode")
    else:
        log("🐢", "Using SLOW image provisioner")

    log("🚀", f"Provisioning instance on host {offer.host_id} (${offer.dph_total:.4f}/hr) via SDK...")

    try:
        data = vast.create_instance(
            id=offer.id,
            image=profile["docker_image"],
            env=env_dict,
            disk=disk,
            label=label,
            onstart_cmd=onstart_cmd,
            cancel_unavail=True,
            runtype="ssh",
            jupyter_lab=True,
            jupyter_dir="/",
            extra={"direct": True},
        )
    except Exception as e:
        error_text = str(e)
        api_error = ""
        if hasattr(e, "response") and e.response is not None:
            try:
                resp_json = e.response.json()
                api_error = resp_json.get("msg", resp_json.get("error", ""))
            except Exception:
                api_error = e.response.text[:200]

        if "no_such_ask" in error_text.lower() or "not available" in (api_error or "").lower():
            log("⚠️", f"Offer no longer available — will try next offer")
            return None
        elif "insufficient" in (api_error or "").lower():
            log("🚫", f"Host has insufficient GPU resources — permanently blacklisting: {api_error[:100]}")
            save_failed_host(offer.host_id, {"status_msg": api_error, "actual_status": "created"})
            return None
        else:
            log("❌", f"SDK create_instance raised: {error_text}")
            if api_error:
                log("📋", f"API error detail: {api_error[:200]}")
            return None

    if not isinstance(data, dict):
        log("❌", f"Unexpected create_instance response type: {type(data)}")
        return None

    instance_id = data.get("new_contract")
    if instance_id:
        if not data.get("success"):
            log("⚠️", "API returned success=False but instance was created (known API quirk)")
        log("✅", f"Instance created: {instance_id}")
        return instance_id

    error_msg = str(data.get("error", "")) or str(data.get("msg", ""))
    if "no_such_ask" in str(data) or "not available" in error_msg:
        log("⚠️", "Offer no longer available — will try next offer")
    else:
        log("❌", f"Instance creation failed: {data}")
    return None


# =============================================================================
# Monitoring
# =============================================================================

def _detect_permanent_failure(data: dict) -> tuple[bool, str]:
    """Check if the instance data indicates a permanent host failure.
    Returns (is_permanent, reason) — always checks status_msg regardless of actual_status.
    """
    status_msg = str(data.get("status_msg", "")).lower()
    actual_status = str(data.get("actual_status", "")).lower()

    # Permanent GPU/CDI/OCI runtime errors — these appear even in "created" status
    permanent_patterns = [
        ("cdi device", "CDI GPU injection failure — host NVIDIA runtime broken"),
        ("oci runtime", "OCI runtime failure — container spec invalid"),
        ("failed to start containers", "Docker daemon permanently broken"),
        ("no such container", "Docker daemon failure — container never created"),
        ("nvidia-smi", "NVIDIA driver/CUDA incompatibility"),
        ("cuda error 804", "CUDA Error 804 — driver too old"),
        ("insufficient resources", "Host has insufficient GPU resources"),
    ]

    for pattern, description in permanent_patterns:
        if pattern in status_msg:
            return (True, description)

    # If status is "created" and there's ANY error message, it's likely a permanent failure
    if actual_status == "created" and status_msg and any(x in status_msg for x in ["error", "failed", "unknown", "unresolvable"]):
        return (True, f"Host container creation failed: {data.get('status_msg', '')[:120]}")

    return (False, "")


def monitor_instance(instance_id: int, timeout: int = 600, host_id: int = 0) -> bool:
    """Monitor instance until it's running. Returns True if successful.

    Proactively checks status_msg on every poll — not just when loading.
    This catches CDI/OCI runtime errors that appear even in "created" status.
    """
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
    try:
        data = vast.show_instance(id=instance_id)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        log("⚠️", f"get_instance_info failed: {e}")
        return {}


def health_check_instance(instance_id: int, timeout: int = 120) -> bool:
    """Post-provision health check: verify ComfyUI is responding via SSH.
    
    Checks that:
    1. /workspace/ComfyUI exists (workspace symlink)
    2. ComfyUI is responding on port 8188 or 18188
    3. If not, attempt manual fix and retry
    """
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
    parser.add_argument("--no-tunnel", action="store_true", help="Skip Cloudflare named tunnel setup (use quick tunnels only)")
    parser.add_argument("--show-failed", action="store_true", help="Display failed hosts history and exit")
    return parser.parse_args()


def send_discord_notification(webhook_url: str, instance_id: int, gpu_name: str, cost: str,
                               location: str, ssh_url: str, cf_hostname: str = None,
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
    if cf_hostname:
        lines.append(f"🔗 ComfyUI: https://{cf_hostname}")
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

    # Handle --show-failed flag
    if hasattr(args, 'show_failed') and args.show_failed:
        failed = load_failed_hosts()
        if not failed:
            log("ℹ️", "No failed hosts recorded")
            sys.exit(0)
        print("\n" + "=" * 80)
        log("📋", f"Failed Hosts History ({len(failed)} entries)")
        print("=" * 80)
        for host_id, record in sorted(failed.items(), key=lambda x: x[1].get("timestamp", 0), reverse=True):
            ts = record.get("timestamp", 0)
            age = "permanent" if record.get("permanent") else f"{int((time.time() - ts) / 3600)}h ago"
            count = record.get("count", 1)
            error = record.get("last_error", "Unknown")[:60]
            print(f"  Host {host_id}: {age} | {count}x failures | {error}")
        print("=" * 80)
        sys.exit(0)

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

    # Create Cloudflare named tunnel (optional)
    cloudflare_config = None
    if not args.no_tunnel:
        cloudflare_config = create_cloudflare_tunnel(f"instance_{args.label}")
        if cloudflare_config:
            log("🌐", f"Cloudflare tunnel: {cloudflare_config.get('hostname')} (id={cloudflare_config.get('tunnel_id')})")
        else:
            log("⚠️", "Cloudflare tunnel creation failed — will use quick tunnels instead")
    else:
        log("🌐", "Cloudflare tunnel disabled (--no-tunnel) — will use quick tunnels")

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

    # =================================================================
    # PROVISION + MONITOR retry loop
    # Handles both create failures and monitoring failures in one loop.
    # When monitoring fails, the instance is destroyed and the next offer is tried.
    # Auto mode uses atomic launch_instance on the first attempt (search+create
    # in a single API call, eliminating the race condition).
    # =================================================================
    MAX_RETRIES = 5 if args.auto else 3
    attempt = 0
    final_success = False

    while attempt < MAX_RETRIES and not final_success:
        instance_id = None
        chosen_offer = None

        # --- Attempt: atomic launch OR manual pick ---
        if args.auto and attempt == 0:
            # Only try atomic launch on the first attempt
            log("⚡", "Auto mode — using atomic launch_instance to avoid stale offers")
            instance_id, chosen_offer = provision_instance_launch(
                profile=profile,
                label=args.label,
                workflow_url=workflow_url,
                hf_token=hf_token,
                discord_webhook=discord_webhook,
                cloudflare_config=cloudflare_config,
                fast_mode=not args.slow,
                max_price=args.max_price,
            )
            if instance_id:
                log("✅", f"Atomic launch succeeded with instance {instance_id}")
                if chosen_offer:
                    log("📊", f"Host: {chosen_offer.host_id} | ${chosen_offer.dph_total:.4f}/hr | {chosen_offer.country}")
            else:
                log("⚠️", "Atomic launch failed — falling back to manual search+create path")

        # --- Fallback: manual search+create ---
        if not instance_id:
            if attempt >= len(ranked):
                log("❌", f"No more offers to try (attempted {attempt})")
                break

            best = ranked[attempt]
            ok, issues = best.meets_specs(profile)

            if not ok:
                log("⚠️", f"Offer #{attempt+1} has issues: {', '.join(issues)}")
                attempt += 1
                continue

            # In manual mode: ask for confirmation on first offer only.
            if not args.auto and attempt == 0:
                print(f"\n🏗️  Provision on offer {best.id} (${best.dph_total:.4f}/hr, {best.country})? (y/N): ", end="", flush=True)
                if input().strip().lower() != "y":
                    log("🛑", "Aborted by user")
                    sys.exit(1)

            log("🔄" if attempt > 0 else "🚀", f"Attempt {attempt+1}/{MAX_RETRIES}: {best.id} (${best.dph_total:.4f}/hr, {best.country})")

            instance_id = provision_instance(
                offer=best,
                profile=profile,
                label=args.label,
                workflow_url=workflow_url,
                hf_token=hf_token,
                discord_webhook=discord_webhook,
                cloudflare_config=cloudflare_config,
                fast_mode=not args.slow,
            )

            if not instance_id:
                log("❌", f"Provisioning failed on host {best.host_id}")
                attempt += 1
                continue

            chosen_offer = best

        # --- Monitor the instance ---
        if args.monitor and not args.no_monitor:
            host_id = chosen_offer.host_id if chosen_offer else 0
            success = monitor_instance(instance_id, timeout=args.timeout, host_id=host_id)

            if not success:
                log("❌", f"Instance {instance_id} failed monitoring — destroying and retrying next offer")
                # Destroy to stop billing immediately
                try:
                    vast.destroy_instance(id=instance_id)
                    log("💥", f"Instance {instance_id} destroyed")
                except Exception as e:
                    log("⚠️", f"Could not destroy instance {instance_id}: {e}")
                attempt += 1
                continue  # Try next offer
        
        # --- Success path ---
        final_success = True
        break

    # =================================================================
    # FINAL REPORTING (only reached on success)
    # =================================================================
    if not final_success or not instance_id:
        log("❌", "All provisioning attempts failed")
        sys.exit(1)

    # Post-provision health check
    health_ok = health_check_instance(instance_id, timeout=120)
    if not health_ok:
        log("⚠️", "Health check failed — instance is running but ComfyUI may need manual setup")
        log("📋", "SSH in and check: ssh_cmd, supervisorctl status, /workspace/ComfyUI")

    info = get_instance_info(instance_id)
    try:
        ssh_url = vast.ssh_url(id=instance_id)
    except Exception:
        ssh_url = "N/A"

    # === Notification 1: Server Ready (immediate) ===
    print("\n" + "=" * 80)
    log("🎉", "SERVER READY!")
    print("=" * 80)
    print(f"  Instance ID:  {instance_id}")
    if chosen_offer:
        print(f"  GPU:          {chosen_offer.gpu_name}")
        print(f"  Cost:         ${chosen_offer.dph_total:.4f}/hr")
        print(f"  Location:     {chosen_offer.country}")
    print(f"  SSH:          {ssh_url}")
    print(f"  Portal:       https://cloud.vast.ai/instances/{instance_id}")
    if cloudflare_config and cloudflare_config.get("hostname"):
        print(f"  🌐 Cloudflare: https://{cloudflare_config['hostname']}")
    if workflow_url:
        print(f"  Workflow:     {args.workflow} (downloading in background)")
    print("=" * 80)

    if discord_webhook:
        cf_hostname = cloudflare_config.get("hostname") if cloudflare_config else None
        workflow_note = f"{args.workflow} — models downloading in background" if workflow_url else ""
        cost_str = f"${chosen_offer.dph_total:.4f}/hr" if chosen_offer else "N/A"
        country_str = chosen_offer.country if chosen_offer else "Unknown"
        sent = send_discord_notification(
            discord_webhook, instance_id,
            chosen_offer.gpu_name if chosen_offer else "Unknown",
            cost_str, country_str, ssh_url, cf_hostname,
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
            discord_webhook, instance_id,
            chosen_offer.gpu_name if chosen_offer else "Unknown",
            cost_str, country_str, ssh_url, cf_hostname,
            workflow_status=workflow_status,
            emoji="📦", title="Models Ready"
        )
        if sent2:
            log("📬", "Discord notification sent (Models Ready)")
        else:
            log("⚠️", "Discord notification failed (Models Ready)")

    sys.exit(0)


if __name__ == "__main__":
    main()
