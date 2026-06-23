import os
import json
import time
import subprocess
import mimetypes
import socket
from urllib.parse import urlparse
import config
from .workflow_builder import build_dynamic_workflow, load_workflow_template

def _resolve_hostname(hostname):
    """Resolve hostname using socket or fallback to nslookup."""
    try:
        return socket.gethostbyname(hostname)
    except Exception:
        pass
    try:
        res = subprocess.run(["nslookup", hostname], capture_output=True, text=True, timeout=5)
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith("Address:") and not line.endswith("#53"):
                return line.split("Address:")[1].strip()
    except Exception:
        pass
    return None

def _resolve_args(url):
    """Resolve the hostname of URL and return curl --resolve args if resolved."""
    if not url:
        return []
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return []
        if hostname in ("localhost", "127.0.0.1", "::1"):
            return []
        ip = _resolve_hostname(hostname)
        if not ip:
            return []
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return ["--resolve", f"{hostname}:{port}:{ip}"]
    except Exception:
        return []

def _auth_args(auth):
    """Convert various auth shapes into curl args."""
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
    """Make ComfyUI API call via curl. Raises on empty/non-JSON response (ISSUE-005 fix).

    NOTE: The hand-rolled retry loop has been removed. Callers running inside a
    Workflow FunctionNode should attach a `RetryConfig` to declare retry intent;
    ad-hoc callers should wrap calls in their own try/except.
    """
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
        raise RuntimeError(
            f"curl command failed with exit code {result.returncode}: {result.stderr}"
        )
    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(
            f"curl_json({method} {endpoint}) got empty stdout body "
            "(likely a ComfyUI tunnel outage — 5xx HTML or dropped connection)."
        )
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        # Cloudflare trycloudflare intermittently returns an HTML error page with HTTP 200
        # and zero Content-Length; raise a clear error so Workflow RetryConfig can retry.
        raise RuntimeError(
            f"curl_json({method} {endpoint}) got non-JSON response: "
            f"{stdout[:200]!r}. JSONDecodeError: {e}"
        ) from e

def wait_for_prompt(prompt_id, base_url=None, poll_interval=5, max_wait=2400, auth=None):
    """Poll /history/{prompt_id} until completion or error."""
    if not prompt_id:
        raise ValueError("Invalid prompt_id. The prompt was not successfully queued in ComfyUI.")
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

def download_output(filename, output_path, base_url=None, subfolder="", auth=None, is_video=False, file_type="output"):
    """Download output image or video from ComfyUI."""
    if base_url is None:
        base_url = config.COMFYUI_URL
    if auth is None:
        auth = config.COMFYUI_AUTH

    base_url = base_url.rstrip("/")
    url = f"{base_url}/view?filename={filename}&subfolder={subfolder}&type={file_type}"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    cmd = ["curl", "-sSL", "-w", "%{http_code}", "-o", output_path, url]
    cmd.extend(_resolve_args(base_url))
    cmd.extend(_auth_args(auth))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    saved = os.path.exists(output_path)
    if saved:
        with open(output_path, "rb") as f:
            magic = f.read(16)

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

def upload_image(image_path, base_url=None, auth=None, subfolder="", image_type="input"):
    """Upload an image to ComfyUI with retries."""
    if base_url is None:
        base_url = config.COMFYUI_URL
    if auth is None:
        auth = config.COMFYUI_AUTH

    base_url = base_url.rstrip("/")
    filename = os.path.basename(image_path)
    mime_type = mimetypes.guess_type(image_path)[0] or "image/png"

    cmd = ["curl", "-s", "-X", "POST", f"{base_url}/upload/image"]
    cmd.extend(_resolve_args(base_url))
    cmd.extend(_auth_args(auth))
    cmd.extend([
        "-F", f"image=@{image_path};type={mime_type}",
        "-F", f"subfolder={subfolder}",
        "-F", f"type={image_type}",
        "-F", "overwrite=true"
    ])

    max_retries = 3
    for attempt in range(max_retries):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                raise RuntimeError(f"curl upload failed with code {result.returncode}: {result.stderr}")
            return json.loads(result.stdout)
        except (json.JSONDecodeError, Exception) as e:
            if attempt == max_retries - 1:
                print(f"   ❌ upload_image failed after {max_retries} attempts: {e}")
                return None
            print(f"   ⚠️ upload_image attempt {attempt + 1} failed: {e}. Retrying in 3s...")
            time.sleep(3)

def get_video_frame_count(video_path):
    """Retrieve the number of frames in a video using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=nb_frames", "-of", "default=nokey=1:noprint_wrappers=1",
        video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        val = result.stdout.strip()
        if val and val.isdigit():
            return int(val)
    except Exception:
        pass
    return 75  # Fallback: 3s at 25fps

def extract_last_frame(video_path: str, output_path: str) -> dict:
    """Extracts the last frame from a video file.

    Args:
        video_path (str): Path to the video file.
        output_path (str): Path to save the extracted frame.
    """
    try:
        if not os.path.exists(video_path):
            return {"status": "error", "message": f"Video file not found: {video_path}"}

        num_frames = get_video_frame_count(video_path)
        frame_idx = max(0, num_frames - 1)

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"select=eq(n\\,{frame_idx})",
            "-vframes", "1", output_path
        ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(output_path):
            return {
                "status": "success",
                "message": f"Successfully extracted last frame to {output_path}",
                "extracted_frame_path": output_path
            }
        else:
            return {"status": "error", "message": "ffmpeg completed but output file not found."}
    except Exception as e:
        return {"status": "error", "message": f"Failed to extract last frame: {str(e)}"}


# Flux Klein 9B has a hard 4-reference cap (per docs.bfl.ai Image Editing overview).
_FLUX_KLEIN_MAX_REFS = 4


def generate_flux_image(
    prompt: str,
    output_path: str,
    reference_image_paths: list[str] | None = None,
    width: int = 1344,
    height: int = 768,
) -> dict:
    """Unified entry point for ALL Flux Klein 9B image generation.

    Used by:
      - Character sheet generation (reference_image_paths = [] → pure T2I)
      - FF shot generation  (reference_image_paths = [char_sheet_1, ...])
      - LF shot generation  (reference_image_paths = [char_sheet_1, ..., FF_image])

    Internally:
      - 0 refs → loads `flux-2-klein-t2i` template + `flux_t2i` builder mode
      - ≥1 refs → loads `flux-2-klein-image-edit` template + `flux_klein_edit_dynamic`
        builder mode (uploads all refs; primary ref = refs[0], additional refs chained
        via ReferenceLatent). Flux Klein caps at 4 refs (FLUX_KLEIN_MAX_REFS).

    Args:
        prompt: Natural-language Flux prompt (no JSON, no bbox layout).
        output_path: Local path to save the generated image.
        reference_image_paths: Optional list of local image paths to attach as
            references. Order matters: refs[0] becomes the primary reference.
        width: Output width in pixels (default 1344 — Flux Klein 9B native).
        height: Output height in pixels (default 768).

    Returns:
        dict with keys: status, message, generated_image_path (on success).
    """
    reference_image_paths = reference_image_paths or []
    if len(reference_image_paths) > _FLUX_KLEIN_MAX_REFS:
        print(
            f"   ⚠️ Flux Klein 9B supports max {_FLUX_KLEIN_MAX_REFS} refs; "
            f"truncating from {len(reference_image_paths)} to {_FLUX_KLEIN_MAX_REFS}."
        )
        reference_image_paths = reference_image_paths[:_FLUX_KLEIN_MAX_REFS]

    try:
        filename_prefix = os.path.splitext(os.path.basename(output_path))[0]
        client_id = f"deterministic-flux-{'t2i' if not reference_image_paths else 'edit'}"

        if not reference_image_paths:
            # --- Pure T2I path (character sheets) ---
            workflow_template = load_workflow_template("flux-2-klein-t2i", config.WORKFLOWS_DIR)
            shot_for_builder = {
                "prompt": prompt,
                "filename_prefix": filename_prefix,
            }
            workflow = build_dynamic_workflow(
                workflow_template, shot_for_builder, {"width": width, "height": height}
            )
        else:
            # --- Reference-conditioned path (FF, LF) ---
            char_servers: list[str] = []
            for path in reference_image_paths:
                res = upload_image(path)
                if not res:
                    return {
                        "status": "error",
                        "message": f"Failed to upload reference image: {path}",
                    }
                char_servers.append(res.get("name"))

            workflow_template = load_workflow_template("flux-2-klein-image-edit", config.WORKFLOWS_DIR)
            shot_for_builder = {
                "prompt": prompt,
                "scene_image": char_servers[0],   # primary ref (model treats it as Image 1)
                "character_refs": char_servers,    # full chain (refs[0] is also the primary)
                "filename_prefix": filename_prefix,
                "_builder_mode": "flux_klein_edit_dynamic",
            }
            workflow = build_dynamic_workflow(
                workflow_template, shot_for_builder, {"width": width, "height": height}
            )

        result = curl_json("POST", "/prompt", data={"prompt": workflow, "client_id": client_id})
        if "error" in result:
            return {"status": "error", "message": f"Queue error: {result['error']}"}

        prompt_id = result.get("prompt_id")
        outputs = wait_for_prompt(prompt_id)

        srv_filename = None
        for nid, out in outputs.items():
            for item in out.get("images", []):
                srv_filename = item["filename"]
                break
            if srv_filename:
                break

        if not srv_filename:
            return {"status": "error", "message": "No output filename found in ComfyUI execution history."}

        success = download_output(srv_filename, output_path)
        if success:
            return {
                "status": "success",
                "message": f"Generated Flux Klein image successfully: {output_path}",
                "generated_image_path": output_path,
            }
        return {"status": "error", "message": "Failed to download generated image from ComfyUI."}
    except Exception as e:
        return {"status": "error", "message": f"Flux image generation failed: {str(e)}"}


def generate_ltx_video(
    ff_image_path: str,
    lf_image_path: str,
    motion_prompt: str,
    output_path: str,
    duration_seconds: int = 3,
    width: int = 1280,
    height: int = 720,
    fps: int = 24,
    use_builtin_enhancer: bool = False,
) -> dict:
    """Generates video using LTX 2.3 First-Last-Frame (FLF2V) workflow.

    The motion prompt is fed verbatim when `use_builtin_enhancer=False`; when
    `use_builtin_enhancer=True`, the workflow's built-in `TextGenerateLTX2Prompt`
    node takes the raw prompt and rewrites it using the FF + LF image context
    (controlled by node 2082 — the ENHANCER boolean).

    Args:
        ff_image_path: Local path to first-frame image (required).
        lf_image_path: Local path to last-frame image (required).
        motion_prompt: Motion description (LTX-2 prompting rules apply:
            focus on what MOVES, never restate static visual details).
        output_path: Path to save generated video.
        duration_seconds: 2-5 seconds (default 3).
        width: Output width (default 1280).
        height: Output height (default 720).
        fps: Frame rate (default 24).
        use_builtin_enhancer: If True, let ComfyUI's TextGenerateLTX2Prompt
            node rewrite the prompt. If False (recommended), the motion_prompter
            agent has already produced a vetted prompt and we pass it through.

    Returns:
        dict with keys: status, message, video_path (on success).
    """
    try:
        if not ff_image_path:
            return {"status": "error", "message": "ff_image_path is required for FLF2V."}
        if not lf_image_path:
            return {"status": "error", "message": "lf_image_path is required for FLF2V."}

        # 1. Upload FF + LF
        ff_res = upload_image(ff_image_path)
        if not ff_res:
            return {"status": "error", "message": f"Failed to upload first frame: {ff_image_path}"}
        lf_res = upload_image(lf_image_path)
        if not lf_res:
            return {"status": "error", "message": f"Failed to upload last frame: {lf_image_path}"}

        ff_server = ff_res.get("name")
        lf_server = lf_res.get("name")

        # 2. Load FLF2V template
        workflow_template = load_workflow_template("ltx-2.3-flf2v", config.WORKFLOWS_DIR)

        # 3. Build workflow — pass through builder so the new ltx_flf2v branch
        #    can substitute placeholders. See workflow_builder.build_dynamic_workflow.
        shot_for_builder = {
            "prompt": motion_prompt,
            "filename_prefix": os.path.splitext(os.path.basename(output_path))[0],
            "first_frame_image": ff_server,
            "last_frame_image": lf_server,
            "duration_seconds": duration_seconds,
            "width": width,
            "height": height,
            "fps": fps,
            "use_builtin_enhancer": use_builtin_enhancer,
            "seed": 42,
        }
        global_cfg = {
            "width": width,
            "height": height,
            "fps": fps,
            "duration_seconds": duration_seconds,
            "seed_base": 42,
        }
        workflow = build_dynamic_workflow(workflow_template, shot_for_builder, global_cfg)

        # 4. Run ComfyUI
        result = curl_json("POST", "/prompt", data={"prompt": workflow, "client_id": "deterministic-ltx-flf2v"})
        if "error" in result:
            return {"status": "error", "message": f"Queue error: {result['error']}"}

        prompt_id = result.get("prompt_id")
        outputs = wait_for_prompt(prompt_id)

        # 5. Locate output video file
        srv_filename = None
        srv_subfolder = ""
        for nid, out in outputs.items():
            video_items = out.get("gifs", []) + out.get("videos", []) + out.get("images", [])
            for item in video_items:
                if item.get("type") == "temp" or item.get("subfolder") == "temp":
                    continue
                srv_filename = item["filename"]
                srv_subfolder = item.get("subfolder", "")
                break
            if srv_filename:
                break

        if not srv_filename:
            return {"status": "error", "message": "No output video file found in ComfyUI execution history."}

        success = download_output(srv_filename, output_path, subfolder=srv_subfolder, is_video=True)
        if success:
            return {
                "status": "success",
                "message": f"Generated LTX FLF2V video successfully: {output_path}",
                "video_path": output_path,
            }
        return {"status": "error", "message": "Failed to download generated video from ComfyUI."}
    except Exception as e:
        return {"status": "error", "message": f"LTX FLF2V video generation failed: {str(e)}"}
