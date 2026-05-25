#!/usr/bin/env python3
"""
offers.py — Offer search, ranking, and failed host tracking.
"""

import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

# Ensure sibling modules are importable when loaded standalone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import log, run_cmd
from client import get_client
from config import FAILED_HOSTS_PATH


# =============================================================================
# Offer dataclass
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

    def meets_specs(self, profile: dict) -> tuple:
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
        if self.inet_down_cost_tb > profile.get("max_inet_down_cost_tb", 0.05):
            issues.append(f"Internet cost ${self.inet_down_cost_tb:.2f}/TB > ${profile['max_inet_down_cost_tb']:.2f}/TB")

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


# =============================================================================
# Failed host tracking
# =============================================================================

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


def classify_host_failure(instance_info: dict) -> tuple:
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


def _detect_permanent_failure(data: dict) -> tuple:
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


# =============================================================================
# Offer search & ranking
# =============================================================================

def search_offers(profile: dict, max_price: Optional[float] = None) -> list:
    """Search Vast.ai for offers matching GPU profile using the Python SDK.

    Uses no_default=True to mirror the CLI -n flag behaviour — returns both
    verified and unverified hosts. Ranking then handles preference.
    """
    vast = get_client()

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


def rank_offers(offers: list, profile: dict, workflow_size_gb: float = 0, verified_only: bool = False) -> list:
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
