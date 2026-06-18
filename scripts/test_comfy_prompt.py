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

def test_prompt():
    prompt_str = "A cute little boy named Leo wearing a yellow cape"
    output_path = "test_leo.png"
    aspect_ratio = "16:9"
    
    # Load template
    config.WORKFLOWS_DIR = os.path.join(workspace_root, "workflows/comfyui")
    print(f"Loading template from {config.WORKFLOWS_DIR}...")
    workflow_template = load_workflow_template("ideogram-4-t2i", config.WORKFLOWS_DIR)
    
    shot_for_builder = {
        "prompt": prompt_str,
        "references": [],
        "filename_prefix": "test_leo",
        "overrides": {
            "aspect_ratio": "16:9 (Widescreen)" if aspect_ratio == "16:9" else aspect_ratio
        }
    }

    workflow = build_dynamic_workflow(workflow_template, shot_for_builder, {"width": 1280, "height": 720})
    
    # Let's perform the post manually
    url = f"{os.getenv('COMFYUI_URL').rstrip('/')}/prompt"
    auth = os.getenv('COMFYUI_AUTH')
    
    data = {"prompt": workflow, "client_id": "test-ideogram"}
    
    cmd = ["curl", "-s", "-X", "POST", url, "-H", "Content-Type: application/json", "-d", json.dumps(data)]
    if auth:
        cmd.extend(["-H", f"Authorization: Bearer {auth}"])
        
    print(f"Sending prompt to {url}...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    print("Return code:", res.returncode)
    print("Response Status Code:", res.stdout[:500])
    try:
        parsed = json.loads(res.stdout)
        print("Parsed JSON response:")
        print(json.dumps(parsed, indent=2))
    except Exception as e:
        print("Failed to parse response as JSON:", e)
        print("Raw response:", res.stdout)

if __name__ == "__main__":
    test_prompt()
