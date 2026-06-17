#!/usr/bin/env python3
"""
ComfyUI API Interaction Helpers
"""

import json
import os
import subprocess
import time

# Defaults
DEFAULT_BASE_URL = "https://comfy-instance_mandi-qwen.muneesraja.com"
DEFAULT_OUTPUT_DIR = "/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video"


def _auth_args(auth):
    """Convert various auth shapes into curl args.

    Supported forms:
      - None                          → no auth
      - ("user", "pass")              → basic auth (-u user:pass) — LEGACY
      - "TOKEN"                       → bearer header (Authorization: Bearer TOKEN)
      - "user:TOKEN"                  → basic auth (explicit user)

    Bearer is the recommended form for Vast.ai Caddy frontends. On at least
    one Vast instance (Jun 2026, dog-chase-eagle), basic auth returned 401
    even though the bcrypt hash in /etc/Caddyfile matched the env token —
    Caddy's bcrypt comparison appears to mismatch in this version. Use
    bearer (a bare string) or query-string `?token=...` instead.
    Ref: ~/.hermes/skills/vast-ai/references/instance-auth-discovery.md
    """
    if not auth:
        return []
    if isinstance(auth, str):
        if ":" in auth:
            user, _, token = auth.partition(":")
            return ["-u", f"{user}:{token}"]
        return ["-H", "Authorization: Bearer " + auth]
    if isinstance(auth, (tuple, list)) and len(auth) == 2:
        return ["-u", f"{auth[0]}:{auth[1]}"]
    return []


def curl_json(method, endpoint, base_url, data=None, timeout=30, auth=None):
    """Make ComfyUI API call via curl (avoids Cloudflare 403 on urllib).

    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: API endpoint (e.g., /prompt)
        base_url: ComfyUI base URL
        data: Optional JSON data for POST requests
        timeout: Request timeout in seconds
        auth: Optional auth — tuple (user, pass) for basic, bare string for
              bearer token, or "user:TOKEN" for basic. See _auth_args for
              why bearer is preferred on Vast.
    """
    # Strip trailing slash from base_url — otherwise Cloudflare responds to
    # /object_info/... with an HTML 301 "Moved Permanently" body, which
    # json.loads() blows up on. (Caught 2026-06-05, story-to-video t_beb4767d.)
    base_url = base_url.rstrip("/")
    cmd = ["curl", "-s", "-X", method, f"{base_url}{endpoint}"]
    cmd.extend(_auth_args(auth))
    if data is not None:
        cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(data)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def wait_for_prompt(prompt_id, base_url, poll_interval=5, max_wait=2400, auth=None):
    """Poll /history/{prompt_id} until completion or error.

    Default max_wait=2400s (40 min). Long Director multi-keyframe chains
    (e.g. 7-keyframe 30s at 1024×576) routinely take 12-15 min on hosted
    ComfyUI. The 600s default from earlier 5s-single-keyframe tests is
    too short for those.
    """
    start = time.time()
    while time.time() - start < max_wait:
        data = curl_json("GET", f"/history/{prompt_id}", base_url, auth=auth)
        if prompt_id in data:
            info = data[prompt_id]
            status = info.get("status", {}).get("status_str", "unknown")
            if status == "success":
                return info.get("outputs", {})
            elif status == "error":
                msgs = info.get("status", {}).get("messages", [])
                for msg in msgs:
                    if msg[0] == "execution_error":
                        raise RuntimeError(
                            f"Node {msg[1]['node_id']} ({msg[1]['node_type']}): "
                            f"{msg[1]['exception_message']}"
                        )
                raise RuntimeError(f"Execution error: {json.dumps(msgs)[:500]}")
        time.sleep(poll_interval)
    raise TimeoutError(f"Prompt {prompt_id} timed out after {max_wait}s")


def download_output(filename, output_path, base_url, subfolder="", auth=None, is_video=False, file_type="output"):
    """Download an output image or video from ComfyUI.

    Args:
        file_type: ComfyUI storage type — "output" (default, for final videos/frames),
                   "temp" (for Stage 1 preview clips at output/temp/), or "input" (for
                   uploaded reference images). Must match the file's actual location
                   or the request returns 404 and saves a 0-byte file.
    """
    url = f"{base_url}/view?filename={filename}&subfolder={subfolder}&type={file_type}"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    # Use -L to follow the Cloudflare 301 redirect to the actual /view URL.
    # Without -L, the 109-byte "Moved Permanently" HTML body gets saved as the
    # image file.
    cmd = ["curl", "-sSL", "-w", "%{http_code}", "-o", output_path, url]
    cmd.extend(_auth_args(auth))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    saved = os.path.exists(output_path)
    if saved:
        with open(output_path, "rb") as _f:
            magic = _f.read(16)
        
        # Check for HTML/json error page
        is_html_or_json = (
            magic.startswith(b"<!DOC") or
            magic.startswith(b"<html") or
            magic.startswith(b"<html>") or
            magic.startswith(b"{\"")
        )
        if is_html_or_json:
            try:
                os.remove(output_path)
            except OSError:
                pass
            return False

        if not is_video:
            # For images, enforce PNG, JPEG, or GIF magic bytes
            is_valid_image = (
                magic.startswith(b"\x89PNG") or
                magic.startswith(b"\xff\xd8\xff") or
                magic.startswith(b"GIF8")
            )
            if not is_valid_image:
                try:
                    os.remove(output_path)
                except OSError:
                    pass
                return False
    return saved


def get_available_images(base_url, auth=None):
    """Query ComfyUI for available input images."""
    data = curl_json("GET", "/object_info/LoadImage", base_url, auth=auth)
    try:
        images = data["LoadImage"]["input"]["required"]["image"][0]
        return set(images)
    except (KeyError, TypeError):
        return set()


def upload_image(image_path, base_url, auth=None, subfolder="", image_type="input"):
    """Upload an image to ComfyUI's input directory.

    Args:
        image_path: Path to the local image file
        base_url: ComfyUI base URL
        auth: Optional tuple of (username, password) for Basic Auth
        subfolder: Subfolder within the input directory
        image_type: Type of upload (default: "input")

    Returns:
        dict with 'name' (filename on server) and 'subfolder' on success
    """
    import mimetypes
    base_url = base_url.rstrip("/")
    filename = os.path.basename(image_path)
    mime_type = mimetypes.guess_type(image_path)[0] or "image/png"

    # Build curl command for multipart upload
    cmd = ["curl", "-s", "-X", "POST", f"{base_url}/upload/image"]
    cmd.extend(_auth_args(auth))
    cmd.extend([
        "-F", f"image=@{image_path};type={mime_type}",
        "-F", f"subfolder={subfolder}",
        "-F", f"type={image_type}",
        "-F", "overwrite=true"
    ])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
