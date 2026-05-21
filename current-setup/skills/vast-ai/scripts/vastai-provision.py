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
  --ssh-key     Path to SSH private key (default: auto-detect from ~/.ssh)
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

# Ensure sibling modules are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client import init_dotenv, get_client, load_hf_token, load_discord_webhook
from config import GPU_PROFILES
from ssh import detect_ssh_key, setup_ssh_config, SSH_KEY_PATH
from offers import search_offers, rank_offers, load_failed_hosts
from cloudflare import create_cloudflare_tunnel
from provisioning import provision_instance_launch, provision_instance
from monitoring import monitor_instance, health_check_instance, get_instance_info
from vps_tunnel import setup_vps_tunnel, verify_tunnel, teardown_vps_tunnel
from workflow import get_workflow_url, get_workflow_size, wait_for_workflow
from utils import log


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
    parser.add_argument("--vps-tunnel", action="store_true", default=True, help="Run cloudflared from VPS (not container) via SSH port-forward (default: enabled)")
    parser.add_argument("--no-vps-tunnel", action="store_true", help="Run cloudflared from container (old behavior)")
    parser.add_argument("--container-tunnel", action="store_true", help="Alias for --no-vps-tunnel (old behavior)")
    parser.add_argument("--show-failed", action="store_true", help="Display failed hosts history and exit")
    parser.add_argument("--ssh-key", default=None, help="Path to SSH private key (default: auto-detect from ~/.ssh)")
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


def main():
    # Load .env first — sets VAST_API_KEY, DISCORD_WEBHOOK_URL, etc.
    init_dotenv()

    args = parse_args()

    # Detect SSH key early (before any provisioning)
    # Handle --ssh-key override if provided
    if hasattr(args, 'ssh_key') and args.ssh_key:
        ssh_key_path = os.path.expanduser(args.ssh_key)
        log("ℹ️", f"Using user-provided SSH key: {ssh_key_path}")
        if not os.path.exists(ssh_key_path):
            raise FileNotFoundError(f"SSH key file not found: {ssh_key_path}")
        if not os.path.exists(ssh_key_path + ".pub"):
            raise FileNotFoundError(f"SSH public key not found: {ssh_key_path}.pub")
    else:
        # Auto-detect SSH key
        ssh_key_path = detect_ssh_key(get_client())

    # Ensure SSH config for Vast.ai hosts
    setup_ssh_config()

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
                    vast = get_client()
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
    health_ok = health_check_instance(instance_id, ssh_key_path, timeout=120)
    if not health_ok:
        log("⚠️", "Health check failed — instance is running but ComfyUI may need manual setup")
        log("📋", "SSH in and check: ssh_cmd, supervisorctl status, /workspace/ComfyUI")

    info = get_instance_info(instance_id)
    try:
        vast = get_client()
        ssh_url = vast.ssh_url(id=instance_id)
    except Exception:
        ssh_url = "N/A"

    # Parse SSH host/port from instance URL for VPS tunnel
    instance_ssh_host = ""
    instance_ssh_port = ""
    if ssh_url and ssh_url != "N/A":
        ssh_match = re.match(r"ssh://root@([^:]+):(\d+)", ssh_url)
        if ssh_match:
            instance_ssh_host = ssh_match.group(1)
            instance_ssh_port = ssh_match.group(2)

    # === VPS-side Cloudflare tunnel (Improvement 2) ===
    use_vps_tunnel = not getattr(args, "no_vps_tunnel", False) and not getattr(args, "container_tunnel", False)
    tunnel_verified = False

    if use_vps_tunnel and cloudflare_config and instance_ssh_host:
        log("🌐", "VPS-side tunnel mode: running cloudflared on VPS via SSH port-forward")
        tunnel_result = setup_vps_tunnel(
            label=f"instance_{args.label}",
            cloudflare_config=cloudflare_config,
            instance_ssh_host=instance_ssh_host,
            instance_ssh_port=instance_ssh_port,
            ssh_key_path=ssh_key_path,
        )
        if tunnel_result:
            cf_pid, ssh_pid = tunnel_result
            log("✅", f"VPS tunnel established (cloudflared PID: {cf_pid}, SSH PID: {ssh_pid})")
            # Verify tunnel accessibility (Improvement 5)
            cf_hostname = cloudflare_config.get("hostname", "")
            if cf_hostname:
                tunnel_verified = verify_tunnel(cf_hostname, timeout=30)
                if not tunnel_verified:
                    log("⚠️", "Tunnel not verified — ComfyUI URL may not be accessible yet")
        else:
            log("⚠️", "VPS tunnel setup failed — custom domain may not work")
    elif not use_vps_tunnel and cloudflare_config:
        log("ℹ️", "Container-side tunnel mode (deprecated) — cloudflared runs inside instance")
        log("⚠️", "Container-side tunnels are unreliable — use VPS-side tunnel (default) if issues arise")

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
        verified_marker = " ✅ verified" if tunnel_verified else " ⚠️ not yet verified"
        tunnel_mode = "VPS-side" if use_vps_tunnel else "container-side"
        print(f"  🌐 Cloudflare: https://{cloudflare_config['hostname']} ({tunnel_mode}{verified_marker})")
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
        workflow_done = wait_for_workflow(ssh_url, ssh_key_path, timeout=600)
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
