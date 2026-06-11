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


def upload_image_if_needed(local_path, base_url, available_images, auth=None):
    """Uploads local image to ComfyUI input folder if not present."""
    if not local_path or not os.path.exists(local_path):
        return None
    server_filename = os.path.basename(local_path)
    if server_filename not in available_images:
        print(f"   📤 Uploading to ComfyUI: {server_filename}")
        upload_result = upload_image(local_path, base_url, auth=auth)
        if not upload_result or "name" not in upload_result:
            print(f"   ❌ Failed to upload image: {local_path}")
            return None
        server_name = upload_result["name"]
        print(f"   ✅ Uploaded successfully as '{server_name}'")
        available_images.add(server_name)
        return server_name
    else:
        print(f"   📷 Image already exists on server: {server_filename}")
        return server_filename
