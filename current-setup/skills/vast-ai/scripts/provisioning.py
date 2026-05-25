#!/usr/bin/env python3
"""
provisioning.py — Instance creation (atomic launch and manual create).
"""

import os
import sys
from typing import Optional

# Ensure sibling modules are importable when loaded standalone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import log, run_cmd
from client import get_client
from config import GPU_PROFILES, FAST_PROVISION_URL, WORKFLOWS_REPO, WORKFLOWS_BRANCH
from offers import Offer


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
        env["CF_TUNNEL_ID"] = cloudflare_config.get("tunnel_id", "")
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
) -> tuple:
    """Atomic search-and-provision using launch_instance API.

    Uses the /launch_instance/ endpoint which searches and creates in a single
    API call, eliminating the race condition between search and create that
    causes 400 Bad Request (offer no longer available).

    Returns (instance_id, offer_used) or (None, None).
    """
    vast = get_client()

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

    # Build geolocation exclusion for launch_instance (it doesn't support skip_countries natively)
    skip_countries = [c.upper() for c in profile.get("skip_countries", [])]

    log("🚀", f"Atomic launch via SDK: {profile['name']} ≤ ${price:.2f}/hr")

    try:
        launch_kwargs = dict(
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

        # Add geolocation filter to exclude skipped countries from atomic launch
        if skip_countries:
            # Build a query dict that excludes specific countries
            # The SDK's query format uses {"field": {"op": value}} syntax
            from vastai.api.query import parse_query, offers_fields, offers_alias, offers_mult
            base_args = (
                f"num_gpus={profile['num_gpus']} gpu_name={profile['name']} "
                f"disk_space>={disk} dph<={price + 0.10} "
                f"cuda_max_good>={profile['cuda_min'] - 0.5} "
                f"driver_version>={profile.get('driver_min', '570.0.0')} "
                f"inet_down>={profile.get('min_inet_down_mbps', 400)} "
                f"inet_up>={profile.get('min_inet_up_mbps', 300)}"
            )
            # Add exclusion for each skipped country
            for cc in skip_countries:
                base_args += f" geolocation != {cc}"
            base_query = {"verified": {"eq": True}, "external": {"eq": False},
                          "rentable": {"eq": True}, "rented": {"eq": False}}
            query_dict = parse_query(base_args, base_query, offers_fields, offers_alias, offers_mult)
            launch_kwargs["query"] = query_dict
            log("🚫", f"Excluding countries: {skip_countries} from atomic launch")

        data = vast.launch_instance(**launch_kwargs)
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
    vast = get_client()

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
            from offers import save_failed_host
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
