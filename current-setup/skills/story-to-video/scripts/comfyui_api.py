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


def curl_json(method, endpoint, base_url, data=None, timeout=30):
    """Make ComfyUI API call via curl (avoids Cloudflare 403 on urllib)."""
    cmd = ["curl", "-s", "-X", method, f"{base_url}{endpoint}"]
    if data is not None:
        cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(data)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def wait_for_prompt(prompt_id, base_url, poll_interval=5, max_wait=600):
    """Poll /history/{prompt_id} until completion or error."""
    start = time.time()
    while time.time() - start < max_wait:
        data = curl_json("GET", f"/history/{prompt_id}", base_url)
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


def download_output(filename, output_path, base_url, subfolder=""):
    """Download an output image from ComfyUI."""
    url = f"{base_url}/view?filename={filename}&subfolder={subfolder}&type=output"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    subprocess.run(["curl", "-s", "-o", output_path, url], timeout=60)
    return os.path.exists(output_path)


def get_available_images(base_url):
    """Query ComfyUI for available input images."""
    data = curl_json("GET", "/object_info/LoadImage", base_url)
    try:
        images = data["LoadImage"]["input"]["required"]["image"][0]
        return set(images)
    except (KeyError, TypeError):
        return set()
