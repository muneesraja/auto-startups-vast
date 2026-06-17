#!/usr/bin/env python3
"""Regenerate failed shots with refined prompts from OpenRouter evals."""
import json, os, sys, time, subprocess, glob, re

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workflow_builder import build_dynamic_workflow, load_workflow_template

# ── Config ──────────────────────────────────────────────────
BASE_URL = "https://bowl-implications-adaptation-rising.trycloudflare.com"
AUTH = "vastai:55bf912e449867f768bc7dd417b6c10611979218afa94e3413e3120af7e73bbc"
STORY_BASE = "/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video/pluffy-bun"
FEEDBACK_DIR = f"{STORY_BASE}/feedback"
SCENES_DIR = f"{STORY_BASE}/scenes"
CHARACTERS_DIR = f"{STORY_BASE}/characters"
TEMPLATE_NAME = "flux-2-dev-turbo"

# ── Helpers ─────────────────────────────────────────────────
def curl_json(method, endpoint, data=None, timeout=30):
    """ComfyUI API call with Basic Auth."""
    url = f"{BASE_URL.rstrip('/')}{endpoint}"
    cmd = ["curl", "-s", "-X", method, "-u", AUTH, url]
    if data is not None:
        cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(data)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return json.loads(result.stdout) if result.stdout.strip() else {}

def normalize_name(name):
    m = re.match(r'(scene_\d+_shot)(\d+)$', name)
    return f"{m.group(1)}{int(m.group(2)):03d}" if m else name

def find_image(prefix):
    """Find the latest image for a shot prefix."""
    pattern = f"{SCENES_DIR}/{prefix}_*.png"
    matches = glob.glob(pattern)
    if matches:
        matches.sort()
        return matches[-1]
    return None

def upload_image(image_path, filename=None):
    """Upload an image to ComfyUI input directory."""
    if filename is None:
        filename = os.path.basename(image_path)
    url = f"{BASE_URL.rstrip('/')}/upload/image"
    cmd = [
        "curl", "-s", "-X", "POST", "-u", AUTH,
        "-F", f"image=@{image_path}",
        "-F", f"name={filename}",
        "-F", "overwrite=true",
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return json.loads(result.stdout) if result.stdout.strip() else {}

def wait_for_prompt(prompt_id, poll_interval=5, max_wait=300):
    """Poll /history/{prompt_id} until completion."""
    start = time.time()
    while time.time() - start < max_wait:
        data = curl_json("GET", f"/history/{prompt_id}")
        if prompt_id in data:
            info = data[prompt_id]
            status = info.get("status", {}).get("status_str", "unknown")
            if status == "success":
                return info.get("outputs", {})
            elif status == "error":
                msgs = info.get("status", {}).get("messages", [])
                raise RuntimeError(f"Execution error: {json.dumps(msgs)[:300]}")
        time.sleep(poll_interval)
    raise TimeoutError(f"Prompt {prompt_id} timed out after {max_wait}s")

def download_output(filename, output_path, subfolder=""):
    """Download an output image from ComfyUI."""
    url = f"{BASE_URL.rstrip('/')}/view?filename={filename}&subfolder={subfolder}&type=output"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cmd = ["curl", "-s", "-o", output_path, "-u", AUTH, url]
    subprocess.run(cmd, capture_output=True, text=True, timeout=30)


# ── Main ────────────────────────────────────────────────────
def patch_resize_node(workflow):
    """Replace missing comfyui-kjnodes with built-in alternatives.
    
    Missing nodes: ImageResizeKJv2, GetImageSizeAndCount, ColorMatchV2, GrowMaskWithBlur
    """
    replacements = {}
    
    for nid, node in list(workflow.items()):
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type", "")
        inputs = node.get("inputs", {})
        
        if ct == "ImageResizeKJv2":
            # Replace with built-in ImageScale
            node["class_type"] = "ImageScale"
            if "crop" not in inputs:
                inputs["crop"] = "disabled"
            # Remove mask output references downstream
            
        elif ct == "GetImageSizeAndCount":
            # Replace with PrimitiveInt nodes for width/height
            # This node outputs width, height, count — we'll hardcode to 1000x1000
            # Find what consumes its outputs and replace with constants
            replacements[nid] = node  # Mark for downstream patching
            # Convert to a no-op by making it output fixed values
            # Actually, just remove it and fix downstream connections
            node["class_type"] = "EmptyImage"
            node["inputs"] = {"width": 1000, "height": 1000, "batch_size": 1, "color": 0}
            
        elif ct == "ColorMatchV2":
            # This is a color matching node — replace with passthrough
            # It takes reference_image and target_image, outputs matched
            # Just pass through the target image
            node["class_type"] = "ImageScale"
            inputs_copy = dict(inputs)
            # Keep image input, remove reference
            if "reference_image" in inputs_copy:
                del inputs_copy["reference_image"]
            if "image" in inputs_copy:
                inputs_copy["image"] = inputs_copy["image"]
            inputs_copy["upscale_method"] = "lanczos"
            inputs_copy["width"] = 1000
            inputs_copy["height"] = 1000
            inputs_copy["crop"] = "disabled"
            node["inputs"] = inputs_copy
            
        elif ct == "GrowMaskWithBlur":
            # Replace with a simple mask blur using built-in nodes
            # Actually, just pass through the mask input
            node["class_type"] = "InvertMask"  # Simple passthrough
            if "mask" in inputs:
                pass  # Keep mask input
            # Remove extra params
            for k in ["expand", "incremental_expandrate", "tapered_corners", 
                       "flip_input", "blur_radius", "lerp_alpha", "decay_factor", 
                       "fill_holes"]:
                inputs.pop(k, None)
    
    return workflow

def main():
    # Load prompt.json and template
    with open(f"{STORY_BASE}/prompt.json") as f:
        prompt_data = json.load(f)
    
    template = load_workflow_template(TEMPLATE_NAME)
    global_cfg = prompt_data["global"]
    
    # Build shot lookup
    shot_lookup = {}
    for s in prompt_data["shots"]:
        shot_lookup[normalize_name(s["filename_prefix"])] = s
    
    # Get refined prompts from OpenRouter evals
    failed_norms = [
        "scene_006_shot005", "scene_004_shot004", "scene_006_shot004", "scene_006_shot006",
        "scene_001_shot002", "scene_004_shot005", "scene_005_shot002", "scene_003_shot004",
        "scene_004_shot003", "scene_007_shot002",
    ]
    
    jobs = []
    for name in failed_norms:
        norm = normalize_name(name)
        # Find eval
        for f in os.listdir(FEEDBACK_DIR):
            if not f.endswith("_iter1.json"):
                continue
            with open(f"{FEEDBACK_DIR}/{f}") as fh:
                data = json.load(fh)
            if data.get("provider") != "openrouter":
                continue
            f_norm = normalize_name(data.get("prefix", f.replace("_iter1.json", "")))
            if f_norm == norm:
                rp = data.get("refined_prompt", "")
                shot_data = shot_lookup.get(norm)
                if shot_data and rp:
                    jobs.append({"name": norm, "shot_data": shot_data, "refined_prompt": rp, "score": data.get("score", "?")})
                elif not rp:
                    print(f"⚠️ {norm}: no refined prompt, skipping")
                else:
                    print(f"⚠️ {norm}: not found in prompt.json, skipping")
                break
    
    print(f"\n🚀 Regenerating {len(jobs)} shots with refined prompts")
    print(f"   ComfyUI: {BASE_URL}")
    print(f"   Template: {TEMPLATE_NAME}")
    print(f"{'='*60}")
    
    # Upload character references first
    ref_files = {}
    for f in os.listdir(CHARACTERS_DIR):
        if f.endswith(".png"):
            local = f"{CHARACTERS_DIR}/{f}"
            print(f"📤 Uploading ref: {f}")
            upload_image(local, f)
            ref_files[f] = True
    
    queued = []
    for i, job in enumerate(jobs, 1):
        name = job["name"]
        shot = job["shot_data"]
        rp = job["refined_prompt"]
        
        print(f"\n[{i}/{len(jobs)}] 🎨 {name} (was {job['score']}/10)")
        print(f"   Refined: {rp[:120]}...")
        
        # Build shot copy with refined prompt
        shot_copy = {**shot, "prompt": rp}
        
        # Build workflow
        try:
            workflow = build_dynamic_workflow(template, shot_copy, global_cfg)
        except Exception as e:
            print(f"   ❌ Workflow build failed: {e}")
            continue
        
        # Queue
        try:
            result = curl_json("POST", "/prompt", {"prompt": workflow})
            prompt_id = result.get("prompt_id")
            if not prompt_id:
                print(f"   ❌ Queue failed: {json.dumps(result)[:200]}")
                continue
            print(f"   📤 Queued: {prompt_id}")
            queued.append({"name": name, "prompt_id": prompt_id, "shot_data": shot_copy})
        except Exception as e:
            print(f"   ❌ Queue error: {e}")
            continue
    
    if not queued:
        print("\n❌ No jobs queued")
        return
    
    # Poll for completion
    print(f"\n⏳ Polling {len(queued)} jobs...")
    completed = []
    failed = []
    
    while queued:
        time.sleep(5)
        remaining = []
        for job in queued:
            try:
                data = curl_json("GET", f"/history/{job['prompt_id']}")
                if job["prompt_id"] in data:
                    info = data[job["prompt_id"]]
                    status = info.get("status", {}).get("status_str", "unknown")
                    if status == "success":
                        # Download output
                        outputs = info.get("outputs", {})
                        for node_id, node_out in outputs.items():
                            for img in node_out.get("images", []):
                                fname = img["filename"]
                                prefix = job["shot_data"]["filename_prefix"]
                                # Save as v2 refinement
                                out_name = f"{prefix}_v2_00001_.png"
                                out_path = f"{SCENES_DIR}/{out_name}"
                                download_output(fname, out_path, img.get("subfolder", ""))
                                print(f"   ✅ {job['name']}: downloaded {out_name}")
                                completed.append({**job, "output_path": out_path})
                        continue
                    elif status == "error":
                        print(f"   ❌ {job['name']}: execution error")
                        failed.append(job)
                        continue
                remaining.append(job)
            except Exception as e:
                print(f"   ⚠️ {job['name']}: poll error: {e}")
                remaining.append(job)
        queued = remaining
    
    print(f"\n{'='*60}")
    print(f"✅ Regeneration complete: {len(completed)} success, {len(failed)} failed")
    
    # Output the completed shot names for re-evaluation
    if completed:
        print(f"\n📋 Shots to re-evaluate:")
        for c in completed:
            print(f"   {c['name']} → {c['output_path']}")

if __name__ == "__main__":
    main()
