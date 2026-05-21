#!/usr/bin/env python3
"""
cloudflare.py — Cloudflare named tunnel creation and DNS management.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

# Ensure sibling modules are importable when loaded standalone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import log, run_cmd


def _cf_delete_stale_tunnels(label: str) -> None:
    """Delete stale Cloudflare tunnels with matching label prefix.
    Only deletes tunnels with zero active connections (not currently in use).
    Prevents orphaned tunnels from accumulating on re-provisions.
    """
    result = run_cmd("cloudflared tunnel list --output json", timeout=30)
    if result["code"] != 0:
        # Fallback: try text format
        result = run_cmd("cloudflared tunnel list", timeout=30)
        if result["code"] != 0:
            log("ℹ️", "Could not list existing tunnels — skipping stale cleanup")
            return
        # Parse text format: "ID  NAME  CREATED  CONNECTIONS"
        # CONNECTIONS column like "1xbkk03, 1xsin07" = active, empty = stale
        for line in result["stdout"].strip().split("\n")[1:]:  # skip header
            parts = line.split()
            if len(parts) >= 2:
                tid, tname = parts[0], parts[1]
                # Check connections column — if it has content, tunnel is active
                connections = parts[3] if len(parts) > 3 else ""
                if tname.startswith(f"comfy-{label}"):
                    if connections and connections != "0x":
                        log("⏭️", f"Skipping active tunnel: {tname} ({tid}) — has connections")
                        continue
                    log("🧹", f"Deleting stale tunnel: {tname} ({tid})")
                    run_cmd(f"cloudflared tunnel delete '{tid}'", timeout=15)
        return
    try:
        tunnels = json.loads(result["stdout"])
        for t in tunnels:
            if t.get("name", "").startswith(f"comfy-{label}"):
                # Check if tunnel has active connections
                conns = t.get("connections", [])
                if conns and len(conns) > 0:
                    log("⏭️", f"Skipping active tunnel: {t['name']} ({t['id']}) — has {len(conns)} connections")
                    continue
                log("🧹", f"Deleting stale tunnel: {t['name']} ({t['id']})")
                run_cmd(f"cloudflared tunnel delete '{t['id']}'", timeout=15)
    except (json.JSONDecodeError, KeyError):
        log("ℹ️", "Could not parse tunnel list — skipping stale cleanup")


def _cf_delete_stale_dns(label: str, zone_id: str, api_token: str, domain: str) -> None:
    """Delete stale CNAME records for this label prefix from Cloudflare DNS.
    Cleans up old DNS records before creating fresh ones.
    """
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    prefix = f"comfy-{label}"
    try:
        req = urllib.request.Request(f"{url}?name={prefix}.{domain}&type=CNAME", headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        for record in data.get("result", []):
            rec_name = record.get("name", "")
            if rec_name.startswith(prefix):
                rec_id = record["id"]
                log("🧹", f"Deleting stale DNS: {rec_name} (id={rec_id})")
                del_req = urllib.request.Request(
                    f"{url}/{rec_id}", method="DELETE", headers=headers
                )
                urllib.request.urlopen(del_req, timeout=15)
    except Exception as e:
        log("ℹ️", f"DNS cleanup skipped: {e}")


def _cf_create_dns_record(tunnel_id: str, hostname: str, zone_id: str, api_token: str) -> bool:
    """Create a CNAME DNS record via Cloudflare API (proxied=true).
    More reliable than 'cloudflared tunnel route dns' which can misroute.
    Returns True on success.
    """
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    payload = json.dumps({
        "type": "CNAME",
        "name": hostname.split(".")[0],  # subdomain part
        "content": f"{tunnel_id}.cfargotunnel.com",
        "proxied": True,
        "ttl": 1,
    }).encode()
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        if data.get("success"):
            log("✅", f"DNS CNAME created: {hostname} → {tunnel_id}.cfargotunnel.com (proxied)")
            return True
        else:
            errors = data.get("errors", [])
            # If record already exists, that's fine
            err_msgs = [e.get("message", "") for e in errors]
            if any("already exists" in m.lower() or "duplicate" in m.lower() for m in err_msgs):
                log("ℹ️", f"DNS record for {hostname} already exists — continuing")
                return True
            log("⚠️", f"DNS creation failed: {err_msgs}")
            return False
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        log("⚠️", f"DNS API error {e.code}: {body[:200]}")
        return False
    except Exception as e:
        log("⚠️", f"DNS API error: {e}")
        return False


def create_cloudflare_tunnel(label: str) -> dict:
    """Create a Cloudflare named tunnel for a new GPU instance.
    Uses cloudflared CLI with origin certificate (cert.pem) auth.
    Cleans up stale tunnels/DNS before creating new ones.
    Uses Cloudflare API for DNS routing (more reliable than 'cloudflared route dns').
    Returns dict with tunnel_id, token, hostname.
    """
    from config import CF_DOMAIN

    # Load Cloudflare config from .env
    cf_api_token = os.environ.get("CLOUDFLARE_API_KEY", "")
    cf_zone_id = os.environ.get("CF_ZONE_ID", "")
    cf_domain = os.environ.get("CF_DOMAIN", CF_DOMAIN)

    # Step 1: Clean up stale tunnels and DNS for this label
    _cf_delete_stale_tunnels(label)
    if cf_api_token and cf_zone_id:
        _cf_delete_stale_dns(label, cf_zone_id, cf_api_token, cf_domain)

    # Step 2: Create new tunnel
    tunnel_name = f"comfy-{label}"
    result = run_cmd(f"cloudflared tunnel create '{tunnel_name}'", timeout=30)
    if result["code"] != 0:
        log("⚠️", f"Cloudflare tunnel creation failed: {result['stderr']}")
        return {}
    match = re.search(r'id ([a-f0-9-]+)', result['stdout'])
    if not match:
        log("⚠️", f"Could not extract tunnel ID from: {result['stdout']}")
        return {}
    tunnel_id = match.group(1)

    # Step 3: Route DNS — use muneesraja.com (has Universal SSL), NOT lxc.muneesraja.com
    hostname = f"comfy-{label}.{cf_domain}"

    if cf_api_token and cf_zone_id:
        # Use Cloudflare API directly — more reliable than 'cloudflared tunnel route dns'
        # which can misroute to wrong tunnel in some cloudflared versions
        dns_ok = _cf_create_dns_record(tunnel_id, hostname, cf_zone_id, cf_api_token)
        if not dns_ok:
            # Fallback to CLI route
            log("ℹ️", "API DNS route failed — falling back to 'cloudflared tunnel route dns'")
            route_result = run_cmd(f"cloudflared tunnel route dns '{tunnel_id}' '{hostname}'", timeout=30)
            if route_result["code"] != 0:
                log("⚠️", f"DNS route creation failed: {route_result['stderr']}")
    else:
        # No API credentials — use CLI as fallback
        log("ℹ️", "No CF_API_TOKEN/CF_ZONE_ID — using 'cloudflared tunnel route dns' CLI")
        route_result = run_cmd(f"cloudflared tunnel route dns '{tunnel_id}' '{hostname}'", timeout=30)
        if route_result["code"] != 0:
            log("⚠️", f"DNS route creation failed: {route_result['stderr']}")

    # Step 4: Get tunnel token (for instance-side credential-based run)
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
