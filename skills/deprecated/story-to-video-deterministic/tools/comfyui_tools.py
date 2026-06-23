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

def generate_ideogram_image(json_prompt: str, output_path: str, aspect_ratio: str = "16:9") -> dict:
    """Generates an image using Ideogram 4 via ComfyUI workflow.
    
    Args:
        json_prompt (str): Ideogram 4 JSON prompt string or dictionary.
        output_path (str): Path to save the generated image.
        aspect_ratio (str): Aspect ratio (default 16:9 for cinematic).
    """
    try:
        # Resolve json_prompt string to dict if needed
        if isinstance(json_prompt, str):
            try:
                json_prompt_dict = json.loads(json_prompt)
                prompt_str = json.dumps(json_prompt_dict)
            except json.JSONDecodeError:
                prompt_str = json_prompt
        else:
            prompt_str = json.dumps(json_prompt)

        workflow_template = load_workflow_template("ideogram-4-t2i", config.WORKFLOWS_DIR)
        
        shot_for_builder = {
            "prompt": prompt_str,
            "references": [],
            "filename_prefix": os.path.splitext(os.path.basename(output_path))[0],
            "overrides": {
                "aspect_ratio": "16:9 (Widescreen)" if aspect_ratio == "16:9" else aspect_ratio
            }
        }

        workflow = build_dynamic_workflow(workflow_template, shot_for_builder, {"width": 1280, "height": 720})

        result = curl_json("POST", "/prompt", data={"prompt": workflow, "client_id": "deterministic-ideogram"})
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

        # Download
        success = download_output(srv_filename, output_path)
        if success:
            return {
                "status": "success",
                "message": f"Generated Ideogram image successfully: {output_path}",
                "generated_image_path": output_path
            }
        else:
            return {"status": "error", "message": "Failed to download generated image from ComfyUI."}

    except Exception as e:
        return {"status": "error", "message": f"Ideogram generation failed: {str(e)}"}

def generate_flux_edit(prompt: str, output_path: str, scene_image_path: str, character_ref_paths: list[str]) -> dict:
    """Generates an edited image using Flux Klein 9B via ComfyUI workflow.
    
    Args:
        prompt (str): Edit instruction prompt following Flux edit style.
        output_path (str): Path to save the generated image.
        scene_image_path (str): Local path to the scene image to edit.
        character_ref_paths (list[str]): Local paths to reference images (max 4).
    """
    try:
        # 1. Upload files
        scene_res = upload_image(scene_image_path)
        if not scene_res:
            return {"status": "error", "message": f"Failed to upload scene image: {scene_image_path}"}
        scene_server = scene_res.get("name")

        char_servers = []
        for path in character_ref_paths[:4]:  # Flux Klein 9B limit is 4 refs
            res = upload_image(path)
            if not res:
                return {"status": "error", "message": f"Failed to upload character reference: {path}"}
            char_servers.append(res.get("name"))

        # 2. Load template
        workflow_template = load_workflow_template("flux-2-klein-image-edit", config.WORKFLOWS_DIR)

        # 3. Build workflow
        shot_for_builder = {
            "prompt": prompt,
            "scene_image": scene_server,
            "character_refs": char_servers,
            "filename_prefix": os.path.splitext(os.path.basename(output_path))[0],
            "_builder_mode": "flux_klein_edit_dynamic"
        }

        workflow = build_dynamic_workflow(workflow_template, shot_for_builder, {"width": 1344, "height": 768})

        # 4. Run ComfyUI
        result = curl_json("POST", "/prompt", data={"prompt": workflow, "client_id": "deterministic-flux-edit"})
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

        # 5. Download
        success = download_output(srv_filename, output_path)
        if success:
            return {
                "status": "success",
                "message": f"Generated Flux Klein edited image successfully: {output_path}",
                "generated_image_path": output_path
            }
        else:
            return {"status": "error", "message": "Failed to download edited image from ComfyUI."}

    except Exception as e:
        return {"status": "error", "message": f"Flux edit generation failed: {str(e)}"}

def generate_ltx_video(ff_image_path: str, lf_image_path: str, motion_prompt: str, output_path: str, duration_seconds: int = 3) -> dict:
    """Generates video using LTX 2.3 FFLF workflow via ComfyUI.
    
    Args:
        ff_image_path (str): Path to first frame image.
        lf_image_path (str): Path to last frame image.
        motion_prompt (str): Motion description prompt for LTX.
        output_path (str): Path to save generated video.
        duration_seconds (int): Duration in seconds (2-5, default 3).
    """
    try:
        # 1. Upload files
        ff_res = upload_image(ff_image_path) if ff_image_path else None
        lf_res = upload_image(lf_image_path)
        
        ff_server = ff_res.get("name") if ff_res else ""
        lf_server = lf_res.get("name")
        
        if not lf_server:
            return {"status": "error", "message": f"Failed to upload last frame image: {lf_image_path}"}
        if ff_image_path and not ff_server:
            return {"status": "error", "message": f"Failed to upload first frame image: {ff_image_path}"}

        # 2. Load template
        workflow_template = load_workflow_template("ltx-23-fflf-seed-hunter", config.WORKFLOWS_DIR)

        # 3. Build workflow
        shot_for_builder = {
            "prompt": motion_prompt,
            "first_frame_image": ff_server,
            "last_frame_image": lf_server,
            "references": [lf_server],
            "segment_duration": duration_seconds,
            "_finish_mode": True,
            "_selected_gen_index": 1,  # 1-indexed for ImpactSwitch (defaults to seed choice 1)
            "filename_prefix": "video/" + os.path.splitext(os.path.basename(output_path))[0]
        }
        if ff_server:
            shot_for_builder["references"].insert(0, ff_server)

        # Generate custom config mapping
        global_cfg = {
            "width": 1920,
            "height": 1088,
            "resolution_preset": "1080p",
            "seed_base": 42,
            "fps": 25,
            "segment_duration": duration_seconds
        }

        workflow = build_dynamic_workflow(workflow_template, shot_for_builder, global_cfg)

        # 4. Run ComfyUI
        result = curl_json("POST", "/prompt", data={"prompt": workflow, "client_id": "deterministic-ltx"})
        if "error" in result:
            return {"status": "error", "message": f"Queue error: {result['error']}"}

        prompt_id = result.get("prompt_id")
        outputs = wait_for_prompt(prompt_id)

        srv_filename = None
        srv_subfolder = "video"
        
        for nid, out in outputs.items():
            video_items = out.get("gifs", []) + out.get("videos", []) + out.get("images", [])
            for item in video_items:
                # Skip temp preview files
                if item.get("type") == "temp" or item.get("subfolder") == "temp":
                    continue
                srv_filename = item["filename"]
                srv_subfolder = item.get("subfolder", "video")
                break
            if srv_filename:
                break

        if not srv_filename:
            return {"status": "error", "message": "No output video file found in ComfyUI execution history."}

        # 5. Download
        success = download_output(srv_filename, output_path, subfolder=srv_subfolder, is_video=True)
        if success:
            return {
                "status": "success",
                "message": f"Generated video successfully: {output_path}",
                "video_path": output_path
            }
        else:
            return {"status": "error", "message": "Failed to download generated video from ComfyUI."}

    except Exception as e:
        return {"status": "error", "message": f"LTX Video generation failed: {str(e)}"}
