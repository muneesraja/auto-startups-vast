import json
import mimetypes
import os
import socket
import subprocess
import time
from urllib.parse import urlparse

import config
from .workflow_builder import build_ltx_i2v_workflow, load_workflow_template


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


def _resolve_args(url: str) -> list[str]:
    if not url:
        return []
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname or hostname in ("localhost", "127.0.0.1", "::1"):
            return []
        ip = _resolve_hostname(hostname)
        if not ip:
            return []
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return ["--resolve", f"{hostname}:{port}:{ip}"]
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


def wait_for_prompt(prompt_id, base_url=None, poll_interval=5, max_wait=2400, auth=None):
    if not prompt_id:
        raise ValueError("Invalid prompt_id")
    if base_url is None:
        base_url = config.COMFYUI_URL
    if auth is None:
        auth = config.COMFYUI_AUTH

    start = time.time()
    while time.time() - start < max_wait:
        data = curl_json("GET", f"/history/{prompt_id}", base_url, auth=auth)
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
                raise RuntimeError(result.stderr)
            return json.loads(result.stdout)
        except Exception as e:
            if attempt == 2:
                print(f"   upload_image failed: {e}")
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


def generate_ltx_i2v_video(
    image_path: str,
    motion_prompt: str,
    output_path: str,
    duration_seconds: int = 8,
    fps: int = 25,
) -> dict:
    """Generate video+audio with LTX 2.3 I2V via ComfyUI."""
    try:
        upload_res = upload_image(image_path)
        if not upload_res:
            return {"status": "error", "message": f"Failed to upload image: {image_path}"}
        image_server = upload_res.get("name")
        if not image_server:
            return {"status": "error", "message": "Upload returned no server filename"}

        template = load_workflow_template(config.I2V_TEMPLATE_NAME, config.WORKFLOWS_DIR)
        prefix = os.path.splitext(os.path.basename(output_path))[0]
        shot_for_builder = {
            "prompt": motion_prompt,
            "motion_image": image_server,
            "duration": duration_seconds,
            "fps": fps,
            "filename_prefix": prefix,
        }
        global_cfg = {
            "width": 1280,
            "height": 720,
            "seed_base": 42,
            "fps": fps,
            "duration": duration_seconds,
        }
        workflow = build_ltx_i2v_workflow(template, shot_for_builder, global_cfg)

        result = curl_json(
            "POST",
            "/prompt",
            data={"prompt": workflow, "client_id": "story-maker-i2v"},
        )
        if "error" in result:
            return {"status": "error", "message": f"Queue error: {result['error']}"}

        prompt_id = result.get("prompt_id")
        outputs = wait_for_prompt(prompt_id)

        srv_filename = None
        srv_subfolder = ""
        for _nid, out in outputs.items():
            for key in ("videos", "gifs", "images"):
                for item in out.get(key, []):
                    if item.get("type") == "temp":
                        continue
                    srv_filename = item["filename"]
                    srv_subfolder = item.get("subfolder", "")
                    break
                if srv_filename:
                    break
            if srv_filename:
                break

        if not srv_filename:
            return {"status": "error", "message": "No video output in ComfyUI history"}

        ok = download_output(
            srv_filename,
            output_path,
            subfolder=srv_subfolder,
            is_video=True,
        )
        if ok:
            return {"status": "success", "video_path": output_path}
        return {"status": "error", "message": "Failed to download generated video"}
    except Exception as e:
        return {"status": "error", "message": f"LTX I2V failed: {e}"}
