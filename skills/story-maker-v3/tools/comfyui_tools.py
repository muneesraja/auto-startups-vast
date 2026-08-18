import ipaddress
import json
import mimetypes
import os
import socket
import subprocess
import time
from urllib.parse import urlparse

import config

# NOTE: story-maker-v3 renders video via the Minimax H3 R2V workflow
# (tools/minimax_workflow.py). This module exposes only the generic ComfyUI
# HTTP helpers that renderer needs (queue, poll, upload, download).


def _resolve_hostname(hostname: str) -> str | None:
    try:
        return socket.gethostbyname(hostname)
    except Exception:
        pass
    try:
        res = subprocess.run(
            ["nslookup", hostname], capture_output=True, text=True, timeout=5
        )
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith("Address:") and not line.endswith("#53"):
                return line.split("Address:")[1].strip()
    except Exception:
        pass
    return None


def _is_ip_literal(host: str) -> bool:
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _resolve_args(url: str) -> list[str]:
    """Pin DNS only when the URL points at a bare IP literal.

    For hostnames (especially Cloudflare-fronted proxies like RunPod), anycast
    edges can serve mismatched TLS certs when pinned via `--resolve`. Letting
    curl resolve normally is correct for hostname URLs.
    """
    if not url:
        return []
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname or hostname in ("localhost", "127.0.0.1", "::1"):
            return []
        # Only pin DNS for IP-literal hosts (rare direct-IP setups).
        if not _is_ip_literal(hostname):
            return []
        # IP literal — pass through as-is; no DNS resolution needed.
        return []
    except Exception:
        return []


def _auth_args(auth) -> list[str]:
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


def curl_json(method, endpoint, base_url=None, data=None, timeout=60, auth=None):
    if base_url is None:
        base_url = config.COMFYUI_URL
    if auth is None:
        auth = config.COMFYUI_AUTH

    base_url = base_url.rstrip("/")
    cmd = ["curl", "-s", "-X", method, f"{base_url}{endpoint}"]
    cmd.extend(_resolve_args(base_url))
    cmd.extend(_auth_args(auth))
    if data is not None:
        cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(data)])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"curl failed ({result.returncode}): {result.stderr}")
    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(f"curl_json({method} {endpoint}) returned empty body")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Non-JSON response from {endpoint}: {stdout[:200]!r}") from e


def interrupt_and_clear_queue(base_url=None, auth=None) -> dict:
    """Best-effort stop of active Comfy execution + pending queue."""
    if base_url is None:
        base_url = config.COMFYUI_URL
    if auth is None:
        auth = config.COMFYUI_AUTH

    results: dict[str, object] = {"base_url": base_url, "interrupt": None, "queue": None}
    base = base_url.rstrip("/")
    def _post_maybe_empty(endpoint: str, payload: dict | None = None) -> dict:
        cmd = ["curl", "-s", "-X", "POST", f"{base}{endpoint}"]
        cmd.extend(_resolve_args(base))
        cmd.extend(_auth_args(auth))
        if payload is not None:
            cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(payload)])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"curl failed ({result.returncode}): {result.stderr.strip()}")
        body = (result.stdout or "").strip()
        if not body:
            return {"ok": True, "empty_body": True}
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"ok": True, "raw": body[:300]}

    try:
        results["interrupt"] = _post_maybe_empty("/interrupt")
    except Exception as e:  # pragma: no cover - network/runtime dependent
        results["interrupt"] = {"error": str(e)}

    # Comfy queue payload shape differs by build; try common variants.
    for payload in ({"clear": True}, {"clear_pending": True}, {"delete_queue": True}):
        try:
            results["queue"] = {"payload": payload, "response": _post_maybe_empty("/queue", payload)}
            break
        except Exception as e:  # pragma: no cover - network/runtime dependent
            results["queue"] = {"payload": payload, "error": str(e)}
    return results


def wait_for_prompt(prompt_id, base_url=None, poll_interval=5, max_wait=2400, auth=None):
    if not prompt_id:
        raise ValueError("Invalid prompt_id")
    if base_url is None:
        base_url = config.COMFYUI_URL
    if auth is None:
        auth = config.COMFYUI_AUTH

    start = time.time()
    while time.time() - start < max_wait:
        try:
            data = curl_json("GET", f"/history/{prompt_id}", base_url, auth=auth)
        except (subprocess.TimeoutExpired, RuntimeError, OSError) as e:
            print(f"  poll for {prompt_id} failed: {e}; retrying")
            time.sleep(poll_interval)
            continue
        except Exception as e:
            print(f"  poll for {prompt_id} unexpected error: {e}; retrying")
            time.sleep(poll_interval)
            continue
        if prompt_id in data:
            info = data[prompt_id]
            status = info.get("status", {}).get("status_str", "unknown")
            if status == "success":
                return info.get("outputs", {})
            if status == "error":
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


def _image_mime_type(image_path: str) -> str:
    with open(image_path, "rb") as f:
        magic = f.read(16)
    if magic.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if magic.startswith(b"\x89PNG"):
        return "image/png"
    if magic.startswith(b"GIF8"):
        return "image/gif"
    if magic.startswith(b"RIFF") and magic[8:12] == b"WEBP":
        return "image/webp"
    return mimetypes.guess_type(image_path)[0] or "image/png"


def _video_mime_type(video_path: str) -> str:
    ext = os.path.splitext(video_path)[1].lower()
    mimes = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".mkv": "video/x-matroska"}
    return mimes.get(ext) or mimetypes.guess_type(video_path)[0] or "video/mp4"


def has_node_type(class_type: str, base_url=None, auth=None) -> bool:
    """Check whether a ComfyUI server has a given node type installed."""
    try:
        info = curl_json("GET", "/object_info", base_url=base_url, auth=auth, timeout=30)
        return class_type in info
    except Exception:
        return False


def upload_image(image_path, base_url=None, auth=None, subfolder="", image_type="input"):
    if base_url is None:
        base_url = config.COMFYUI_URL
    if auth is None:
        auth = config.COMFYUI_AUTH

    base_url = base_url.rstrip("/")
    mime_type = _image_mime_type(image_path)
    cmd = ["curl", "-s", "-X", "POST", f"{base_url}/upload/image"]
    cmd.extend(_resolve_args(base_url))
    cmd.extend(_auth_args(auth))
    cmd.extend(
        [
            "-F",
            f"image=@{image_path};type={mime_type}",
            "-F",
            f"subfolder={subfolder}",
            "-F",
            f"type={image_type}",
            "-F",
            "overwrite=true",
        ]
    )

    for attempt in range(3):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                raise RuntimeError(
                    f"curl exit {result.returncode}: stderr={result.stderr.strip()[:200]}"
                )
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError as je:
                raise RuntimeError(
                    f"non-JSON response (first 200 chars): {result.stdout[:200]!r}"
                ) from je
        except Exception as e:
            if attempt == 2:
                print(f"   upload_image failed: {e}")
                return None
            time.sleep(3)


def upload_video(video_path, base_url=None, auth=None, subfolder=""):
    """Upload a video file to ComfyUI's input folder (same /upload/image endpoint).

    ComfyUI's upload endpoint accepts any file type; the ``image`` form field
    name is kept for compatibility. Returns the same dict shape as
    :func:`upload_image` (``{name, subfolder, type}``).
    """
    if base_url is None:
        base_url = config.COMFYUI_URL
    if auth is None:
        auth = config.COMFYUI_AUTH

    base_url = base_url.rstrip("/")
    mime_type = _video_mime_type(video_path)
    cmd = ["curl", "-s", "-X", "POST", f"{base_url}/upload/image"]
    cmd.extend(_resolve_args(base_url))
    cmd.extend(_auth_args(auth))
    cmd.extend(
        [
            "-F",
            f"image=@{video_path};type={mime_type}",
            "-F",
            f"subfolder={subfolder}",
            "-F",
            "type=input",
            "-F",
            "overwrite=true",
        ]
    )

    for attempt in range(3):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                raise RuntimeError(
                    f"curl exit {result.returncode}: stderr={result.stderr.strip()[:200]}"
                )
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError as je:
                raise RuntimeError(
                    f"non-JSON response (first 200 chars): {result.stdout[:200]!r}"
                ) from je
        except Exception as e:
            if attempt == 2:
                print(f"   upload_video failed: {e}")
                return None
            time.sleep(3)


def download_output(
    filename,
    output_path,
    base_url=None,
    subfolder="",
    auth=None,
    is_video=False,
    file_type="output",
):
    if base_url is None:
        base_url = config.COMFYUI_URL
    if auth is None:
        auth = config.COMFYUI_AUTH

    base_url = base_url.rstrip("/")
    url = f"{base_url}/view?filename={filename}&subfolder={subfolder}&type={file_type}"
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    cmd = ["curl", "-sSL", "-o", output_path, url]
    cmd.extend(_resolve_args(base_url))
    cmd.extend(_auth_args(auth))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0 or not os.path.exists(output_path):
        return False

    with open(output_path, "rb") as f:
        magic = f.read(16)
    if magic.startswith((b"<!DOC", b"<html", b'{"')):
        try:
            os.remove(output_path)
        except OSError:
            pass
        return False
    if not is_video:
        is_valid_image = magic.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8"))
        if not is_valid_image:
            try:
                os.remove(output_path)
            except OSError:
                pass
            return False
    return True