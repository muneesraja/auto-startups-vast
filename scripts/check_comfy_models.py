import os
import json
import ssl
import urllib.request
from dotenv import load_dotenv

workspace_root = "/Users/muneesraja/projects/brainstorm/aurora"
dotenv_path = os.path.join(workspace_root, ".env")
load_dotenv(dotenv_path)

COMFYUI_URL = os.getenv("COMFYUI_URL")
COMFYUI_AUTH = os.getenv("COMFYUI_AUTH")

def check_models():
    url = f"{COMFYUI_URL.rstrip('/')}/object_info"
    headers = {
        "Authorization": f"Bearer {COMFYUI_AUTH}"
    }
    
    req = urllib.request.Request(url, headers=headers)
    context = ssl._create_unverified_context()
    
    try:
        with urllib.request.urlopen(req, timeout=30, context=context) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
            
            loaders = ["UNETLoader", "VAELoader", "CLIPLoader", "CheckpointLoader", "CheckpointLoaderSimple", "LoraLoader"]
            for loader in loaders:
                if loader in data:
                    print(f"\n=== {loader} ===")
                    inputs = data[loader].get("input", {})
                    required = inputs.get("required", {})
                    for input_name, input_def in required.items():
                        if isinstance(input_def, list) and len(input_def) > 0 and isinstance(input_def[0], list):
                            print(f"  Input: {input_name}")
                            for opt in input_def[0]:
                                print(f"    - {opt}")
                else:
                    print(f"\n=== {loader} is NOT present on server ===")
                    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_models()
