import os
import json
from comfyui_api import upload_image

def load_filmmaking_prompts(prompts_path):
    """Load filmmaking_prompt.json and return parsed data with validation."""
    if not os.path.exists(prompts_path):
        raise FileNotFoundError(f"Filmmaking prompts file not found: {prompts_path}")

    with open(prompts_path) as f:
        data = json.load(f)

    # Validate required fields
    required = ["version", "model", "workflow_template", "global", "shots"]
    for field in required:
        if field not in data:
            raise ValueError(f"filmmaking_prompt.json missing required field: '{field}'")

    global_cfg = data["global"]
    for field in ["resolution_preset", "fps", "segment_duration"]:
        if field not in global_cfg:
            raise ValueError(f"filmmaking_prompt.json global section missing required field: '{field}'")

    for i, shot in enumerate(data["shots"]):
        required_fields = ["scene", "shot", "shot_type", "last_frame_prompt", "motion_prompt", "filename_prefix"]
        for field in required_fields:
            if field not in shot:
                raise ValueError(f"filmmaking_prompt.json shot[{i}] missing required field: '{field}'")

    print(f"📋 Loaded filmmaking_prompt.json (v{data['version']})")
    print(f"   Model: {data['model']}")
    print(f"   Template: {data['workflow_template']}")
    print(f"   Shots: {len(data['shots'])}")
    print(f"   Default Resolution Preset: {global_cfg['resolution_preset']}")
    print(f"   Default Segment Duration: {global_cfg['segment_duration']}s @ {global_cfg['fps']} FPS")

    return data


def upload_image_if_needed(local_path, base_url, available_images, auth=None,
                            comfyui_filename=None):
    """Uploads local image to ComfyUI input folder with optional server-name override.

    The default behavior is "skip if same-name already exists on server" (cheap,
    no-op fast path). The orchestrator's story-prefixing pattern means
    cross-story collisions are prevented at the schema level (see tiny-bee
    lesson 2026-06-11), so we don't need to overwrite by default.

    Args:
        local_path: Path to the local image file
        base_url: ComfyUI base URL
        available_images: Set of images already on ComfyUI input server
        auth: Optional Basic Auth tuple
        comfyui_filename: Optional override for the server filename. If None,
            uses basename(local_path). When set, the file is uploaded with this
            name (using overwrite=true at the endpoint) regardless of whether
            it already exists on the server. This is the per-story prefix
            mechanism that prevents cross-story filename collisions.

    Returns:
        Server filename on success, None on failure.
    """
    if not local_path or not os.path.exists(local_path):
        return None
    server_filename = comfyui_filename or os.path.basename(local_path)

    if comfyui_filename is None and server_filename in available_images:
        # Fast path: same name already on server, skip upload.
        print(f"   📷 Image already exists on server: {server_filename}")
        return server_filename

    print(f"   📤 Uploading to ComfyUI as: {server_filename}")
    upload_result = upload_image(
        local_path, base_url, auth=auth,
        subfolder="",
        image_type="input",
    )
    if not upload_result or "name" not in upload_result:
        print(f"   ❌ Failed to upload image: {local_path}")
        return None
    server_name = upload_result["name"]
    print(f"   ✅ Uploaded: {server_name} (local={os.path.basename(local_path)})")
    available_images.add(server_name)
    return server_name
