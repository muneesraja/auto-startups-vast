import os
import sys
import json
import subprocess
from dotenv import load_dotenv

workspace_root = "/Users/muneesraja/projects/brainstorm/aurora"
sys.path.insert(0, os.path.join(workspace_root, "skills/story-to-video-deterministic"))

from tools.workflow_builder import build_dynamic_workflow, load_workflow_template
import config

load_dotenv(os.path.join(workspace_root, ".env"))

def test_video_prompt():
    prompt_str = "Leo walks forward through the garden"
    ff_image = "scene_01_shot_01_ff.png"
    lf_image = "scene_01_shot_01_lf.png"
    output_path = "test_video.mp4"
    
    config.WORKFLOWS_DIR = os.path.join(workspace_root, "workflows/comfyui")
    print(f"Loading template ltx-23-fflf-seed-hunter from {config.WORKFLOWS_DIR}...")
    workflow_template = load_workflow_template("ltx-23-fflf-seed-hunter", config.WORKFLOWS_DIR)
    
    shot_for_builder = {
        "prompt": prompt_str,
        "first_frame_image": ff_image,
        "last_frame_image": lf_image,
        "references": [ff_image, lf_image],
        "segment_duration": 3,
        "_finish_mode": True,
        "_selected_gen_index": 1,
        "filename_prefix": "video/test_video"
    }

    global_cfg = {
        "width": 1920,
        "height": 1088,
        "resolution_preset": "1080p",
        "seed_base": 42,
        "fps": 25,
        "segment_duration": 3
    }

    workflow = build_dynamic_workflow(workflow_template, shot_for_builder, global_cfg)
    
    url = f"{os.getenv('COMFYUI_URL').rstrip('/')}/prompt"
    auth = os.getenv('COMFYUI_AUTH')
    
    data = {"prompt": workflow, "client_id": "test-ltx-video"}
    
    cmd = ["curl", "-s", "-X", "POST", url, "-H", "Content-Type: application/json", "-d", json.dumps(data)]
    if auth:
        cmd.extend(["-H", f"Authorization: Bearer {auth}"])
        
    print(f"Sending prompt to {url}...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    print("Return code:", res.returncode)
    try:
        parsed = json.loads(res.stdout)
        print("Response:")
        print(json.dumps(parsed, indent=2))
    except Exception as e:
        print("Failed to parse response as JSON:", e)
        print("Raw response:", res.stdout)

if __name__ == "__main__":
    test_video_prompt()
