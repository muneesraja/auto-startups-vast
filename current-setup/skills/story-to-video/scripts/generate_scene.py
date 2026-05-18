#!/usr/bin/env python3
"""
Story-to-Video: Generate scene images via ComfyUI Qwen Image Edit 2511 API.

Usage:
    python3 generate_scene.py --manifest story_manifest.json --scene 1 [--seed 42]
    python3 generate_scene.py --manifest story_manifest.json --all
    python3 generate_scene.py --manifest story_manifest.json --all --url https://my-comfyui.example.com

Requires: curl (Cloudflare blocks Python urllib)
Tested: RTX 3090, 6 scenes, ~3 min total
"""

import json
import os
import subprocess
import sys
import time
import argparse

# ── Defaults ──────────────────────────────────────────────────
DEFAULT_BASE_URL = "https://mandi-qwen.muneesraja.com"
DEFAULT_OUTPUT_DIR = "/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video"

# Character → reference image filename mapping (override per story via manifest)
DEFAULT_REF_IMAGES = {
    "hare": "hare_reference_sheet.png",
    "tortoise": "tortoise_reference_sheet.png",
    "squirrel": "squirrel_reference_sheet.png",
    "fox": "fox_reference_sheet.png",
    "forest_animals": "forest_animals_reference_sheet.png",
}

# Fallbacks when a character ref is missing from the instance
DEFAULT_FALLBACKS = {
    "fox": "tortoise_reference_sheet.png",
}


# ── API Helpers ──────────────────────────────────────────────

def curl_json(method, endpoint, base_url, data=None, timeout=30):
    """Make ComfyUI API call via curl (avoids Cloudflare 403 on urllib)."""
    cmd = ["curl", "-s", "-X", method, f"{base_url}{endpoint}"]
    if data is not None:
        cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(data)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def wait_for_prompt(prompt_id, base_url, poll_interval=5, max_wait=180):
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


def upload_image(filepath, base_url, name=None):
    """Upload an image to ComfyUI's input directory."""
    name = name or os.path.basename(filepath)
    cmd = [
        "curl", "-s", "-X", "POST",
        f"{base_url}/upload/image",
        "-F", f"image=@{filepath}",
        "-F", f"name={name}",
        "-F", "overwrite=true",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return json.loads(result.stdout) if result.stdout.strip() else {}


# ── Image Selection ─────────────────────────────────────────

def pick_images(characters, available, ref_images, fallbacks):
    """Select up to 3 reference images. Falls back for missing characters."""
    images = []
    for c in characters:
        ref = ref_images.get(c)
        if ref and ref in available:
            images.append(ref)
        else:
            fallback = fallbacks.get(c, "example.png")
            print(f"   ⚠️ {c} ref not on instance, using {fallback}")
            images.append(fallback)
    # Deduplicate preserving order
    unique = list(dict.fromkeys(images))
    while len(unique) < 3:
        unique.append(unique[0] if unique else "example.png")
    return unique[:3]


# ── Workflow Builder ─────────────────────────────────────────

def build_workflow(image1, image2, image3, prompt_text, seed=42, filename_prefix="scene"):
    """Build the complete Qwen Image Edit 2511 API workflow."""
    return {
        "197": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "qwen_image_edit_2511_fp8_e4m3fn.safetensors", "weight_dtype": "default"}},
        "209": {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": ["197", 0], "lora_name": "Qwen-Image-Lightning-4steps-V2.0.safetensors", "strength_model": 1}},
        "149": {"class_type": "TorchCompileModelQwenImage", "inputs": {
            "model": ["209", 0], "backend": "inductor", "fullgraph": False,
            "mode": "default", "dynamic": False, "creduce": True, "compile_shape": 64}},
        "145": {"class_type": "ModelSamplingAuraFlow", "inputs": {
            "model": ["149", 0], "shift": 3.1}},
        "75": {"class_type": "CFGNorm", "inputs": {
            "model": ["145", 0], "strength": 1.0}},
        "38": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
            "type": "qwen_image", "device": "default"}},
        "39": {"class_type": "VAELoader", "inputs": {
            "vae_name": "split_files/vae/qwen_image_vae.safetensors"}},
        "213": {"class_type": "LoadImage", "inputs": {"image": image1}},
        "175": {"class_type": "LoadImage", "inputs": {"image": image2}},
        "182": {"class_type": "LoadImage", "inputs": {"image": image3}},
        "200": {"class_type": "ImageResizeKJv2", "inputs": {
            "image": ["213", 0], "mask": ["213", 1], "width": 1024, "height": 1024,
            "upscale_method": "lanczos", "keep_proportion": "total_pixels",
            "pad_color": "0, 0, 0", "crop_position": "center", "divisible_by": 32, "device": "cpu"}},
        "201": {"class_type": "ImageResizeKJv2", "inputs": {
            "image": ["175", 0], "width": 1024, "height": 1024,
            "upscale_method": "lanczos", "keep_proportion": "total_pixels",
            "pad_color": "0, 0, 0", "crop_position": "center", "divisible_by": 32, "device": "cpu"}},
        "202": {"class_type": "ImageResizeKJv2", "inputs": {
            "image": ["182", 0], "width": 1024, "height": 1024,
            "upscale_method": "lanczos", "keep_proportion": "total_pixels",
            "pad_color": "0, 0, 0", "crop_position": "center", "divisible_by": 32, "device": "cpu"}},
        "176": {"class_type": "EmptySD3LatentImage", "inputs": {
            "width": 1024, "height": 1024, "batch_size": 1}},
        "154": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {
            "clip": ["38", 0], "prompt": prompt_text,
            "image1": ["200", 0], "image2": ["201", 0], "image3": ["202", 0]}},
        "153": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {
            "clip": ["38", 0], "prompt": prompt_text,
            "image1": ["200", 0], "image2": ["201", 0], "image3": ["202", 0]}},
        "163": {"class_type": "ConditioningZeroOut", "inputs": {
            "conditioning": ["154", 0]}},
        "88": {"class_type": "VAEEncode", "inputs": {
            "pixels": ["200", 0], "vae": ["39", 0]}},
        "172": {"class_type": "VAEEncode", "inputs": {
            "pixels": ["201", 0], "vae": ["39", 0]}},
        "180": {"class_type": "VAEEncode", "inputs": {
            "pixels": ["202", 0], "vae": ["39", 0]}},
        "162": {"class_type": "ReferenceLatent", "inputs": {
            "conditioning": ["153", 0], "latent": ["88", 0]}},
        "171": {"class_type": "ReferenceLatent", "inputs": {
            "conditioning": ["162", 0], "latent": ["172", 0]}},
        "179": {"class_type": "ReferenceLatent", "inputs": {
            "conditioning": ["171", 0], "latent": ["180", 0]}},
        "184": {"class_type": "Any Switch (rgthree)", "inputs": {
            "any_01": ["179", 0], "any_02": ["171", 0], "any_03": ["162", 0]}},
        "205": {"class_type": "Any Switch (rgthree)", "inputs": {
            "any_01": ["176", 0], "any_02": ["88", 0]}},
        "196": {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {
            "conditioning": ["184", 0], "reference_latents_method": "index_timestep_zero"}},
        "195": {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {
            "conditioning": ["163", 0], "reference_latents_method": "index_timestep_zero"}},
        "3": {"class_type": "KSampler", "inputs": {
            "model": ["75", 0], "positive": ["196", 0], "negative": ["195", 0],
            "latent_image": ["205", 0], "seed": seed, "control_after_generate": "fixed",
            "steps": 4, "cfg": 1, "sampler_name": "euler", "scheduler": "simple", "denoise": 1}},
        "8": {"class_type": "VAEDecode", "inputs": {
            "samples": ["3", 0], "vae": ["39", 0]}},
        "214": {"class_type": "SaveImage", "inputs": {
            "images": ["8", 0], "filename_prefix": filename_prefix}},
    }


# ── Manifest Loader ─────────────────────────────────────────

def load_manifest(manifest_path):
    """Load story manifest JSON and build scene data."""
    with open(manifest_path) as f:
        manifest = json.load(f)

    style = manifest.get("style", "")
    char_map = {c["id"]: c["identity_spec"] for c in manifest.get("characters", [])}
    char_names = {c["id"]: c["name"] for c in manifest.get("characters", [])}

    scenes = {}
    for scene in manifest.get("scenes", []):
        num = scene["scene_number"]
        characters = scene.get("characters_present", [])
        setting = scene.get("setting", "")
        action = scene.get("action", "")
        emotion = scene.get("emotion", "")
        camera = scene.get("camera", "")

        # Build prompt
        char_descriptions = []
        for cid in characters:
            name = char_names.get(cid, cid)
            spec = char_map.get(cid, "")
            # Abbreviate for 3+ characters
            if len(characters) >= 3:
                # Use key features only (first sentence or ~100 chars)
                short = spec.split(",")[0] + ", " + ", ".join(spec.split(",")[1:3])
                char_descriptions.append(f"- {name}: {short}")
            else:
                char_descriptions.append(f"- {name}: {spec}")

        prompt_parts = []
        prompt_parts.append("Characters in this scene must match the provided reference images exactly:")
        prompt_parts.extend(char_descriptions)
        prompt_parts.append(f"Scene setting: {setting}.")
        prompt_parts.append(f"Action: {action}.")
        prompt_parts.append(f"Mood: {emotion}.")
        prompt_parts.append(f"Camera: {camera}.")
        prompt_parts.append(f"Style: {style}.")

        scenes[num] = {
            "title": scene.get("title", f"Scene {num}"),
            "characters": characters,
            "prompt": "\n".join(prompt_parts),
        }

    return manifest.get("title", "story"), scenes


# ── Scene Generation ─────────────────────────────────────────

def generate_scene(scene_num, scene_data, base_url, output_dir,
                   available_images, ref_images, fallbacks, seed=42):
    """Generate a single scene image."""
    images = pick_images(scene_data["characters"], available_images, ref_images, fallbacks)
    prefix = f"scene_{scene_num:03d}"

    print(f"🎬 Scene {scene_num}: {scene_data['title']}")
    print(f"   Characters: {', '.join(scene_data['characters'])}")
    print(f"   Input images: {images}")
    print(f"   Seed: {seed}")

    workflow = build_workflow(
        image1=images[0], image2=images[1], image3=images[2],
        prompt_text=scene_data["prompt"], seed=seed, filename_prefix=prefix
    )

    result = curl_json("POST", "/prompt", base_url, data={"prompt": workflow, "client_id": "story-to-video"})
    if "error" in result:
        err = result["error"]
        node_errors = result.get("node_errors", {})
        print(f"   ❌ Queue error: {err.get('type')}: {err.get('message')}")
        for nid, errs in node_errors.items():
            for e in errs.get("errors", []):
                print(f"      Node {nid}: {e.get('details', e.get('message', ''))}")
        return None

    prompt_id = result.get("prompt_id")
    print(f"   ⏳ Queued: {prompt_id}")

    try:
        outputs = wait_for_prompt(prompt_id, base_url)
    except (RuntimeError, TimeoutError) as e:
        print(f"   ❌ {e}")
        return None

    for nid, out in outputs.items():
        for item in out.get("images", []):
            filename = item["filename"]
            out_path = os.path.join(output_dir, filename)
            if download_output(filename, out_path, base_url, item.get("subfolder", "")):
                size = os.path.getsize(out_path)
                print(f"   ✅ Saved: {out_path} ({size/1024:.0f} KB)")
                return out_path

    print(f"   ⚠️ No images in output")
    return None


# ── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Story-to-Video scene generator")
    parser.add_argument("--manifest", required=True, help="Path to story_manifest.json")
    parser.add_argument("--scene", type=int, help="Generate a specific scene (1-6)")
    parser.add_argument("--all", action="store_true", help="Generate all scenes")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--url", default=DEFAULT_BASE_URL, help="ComfyUI base URL")
    parser.add_argument("--output-dir", default=None,
                        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR}/<story-title>/scenes)")
    args = parser.parse_args()

    # Load manifest
    story_title, scenes = load_manifest(args.manifest)

    # Determine output directory
    output_dir = args.output_dir or os.path.join(DEFAULT_OUTPUT_DIR, story_title, "scenes")
    os.makedirs(output_dir, exist_ok=True)

    # Auto-detect available images on instance
    base_url = args.url
    print(f"🔍 Checking available images on {base_url}...")
    available_images = get_available_images(base_url)
    print(f"   Found {len(available_images)} images: {', '.join(sorted(available_images))}")

    # Build ref image map from manifest character IDs
    ref_images = DEFAULT_REF_IMAGES.copy()

    if args.all:
        print(f"\n📖 Story: {story_title} ({len(scenes)} scenes)")
        print(f"📁 Output: {output_dir}\n")
        for num in sorted(scenes.keys()):
            generate_scene(num, scenes[num], base_url, output_dir,
                         available_images, ref_images, DEFAULT_FALLBACKS, seed=args.seed)
            print()
    elif args.scene:
        if args.scene not in scenes:
            print(f"❌ Scene {args.scene} not found in manifest")
            sys.exit(1)
        generate_scene(args.scene, scenes[args.scene], base_url, output_dir,
                      available_images, ref_images, DEFAULT_FALLBACKS, seed=args.seed)
    else:
        parser.print_help()