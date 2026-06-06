#!/usr/bin/env python3
"""
Story-to-Video: Video Generator (Phase 3)
=========================================
Generates scene videos from still images via ComfyUI using motion_prompt.json
and the ltx-23-i2v-dev workflow template.

Usage:
    python3 generate_video.py --prompts motion_prompt.json
    python3 generate_video.py --prompts motion_prompt.json --shot video_001_shot001
    python3 generate_video.py --prompts motion_prompt.json --url https://my-comfyui.example.com

Requires: curl (Cloudflare blocks Python urllib)
"""
import argparse
import json
import os
import sys

from comfyui_api import (
    curl_json,
    wait_for_prompt,
    download_output,
    get_available_images,
    upload_image,
    DEFAULT_BASE_URL,
    DEFAULT_OUTPUT_DIR,
)
from workflow_builder import build_dynamic_workflow, load_workflow_template


# ── motion_prompt.json Loader ───────────────────────────────────

def load_motion_prompts(prompts_path):
    """Load motion_prompt.json and return parsed data.

    Returns:
        dict with keys: version, model, workflow_template, global, shots
    """
    if not os.path.exists(prompts_path):
        raise FileNotFoundError(f"Motion prompts file not found: {prompts_path}")

    with open(prompts_path) as f:
        data = json.load(f)

    # Validate required fields
    required = ["version", "model", "workflow_template", "global", "shots"]
    for field in required:
        if field not in data:
            raise ValueError(f"motion_prompt.json missing required field: '{field}'")

    global_cfg = data["global"]
    for field in ["width", "height", "duration", "fps"]:
        if field not in global_cfg:
            raise ValueError(f"motion_prompt.json global section missing required field: '{field}'")

    for i, shot in enumerate(data["shots"]):
        for field in ["scene", "shot", "motion_prompt", "motion_image", "filename_prefix"]:
            if field not in shot:
                raise ValueError(f"motion_prompt.json shot[{i}] missing required field: '{field}'")

    print(f"📋 Loaded motion_prompt.json (v{data['version']})")
    print(f"   Model: {data['model']}")
    print(f"   Template: {data['workflow_template']}")
    print(f"   Shots: {len(data['shots'])}")
    print(f"   Default Resolution: {global_cfg['width']}×{global_cfg['height']}")
    print(f"   Default Length: {global_cfg['duration']}s @ {global_cfg['fps']} FPS")

    return data


# ── Video Generation ─────────────────────────────────────────

def generate_video_shot(shot_data, global_cfg, workflow_template, base_url, videos_dir,
                        scenes_dir, available_images, auth=None):
    """Generate a single shot video using motion_prompt.json data.

    Args:
        shot_data: Single shot object from motion_prompt.json
        global_cfg: Global config from motion_prompt.json
        workflow_template: Loaded workflow template dict
        base_url: ComfyUI instance URL
        videos_dir: Directory to save output videos
        scenes_dir: Directory containing input scene still images
        available_images: Set of available image filenames on ComfyUI
        auth: Optional tuple of (username, password) for Basic Auth

    Returns:
        str: Path to generated video, or None on failure
    """
    scene_num = shot_data["scene"]
    shot_num = shot_data["shot"]
    prefix = shot_data["filename_prefix"]
    motion_image = shot_data["motion_image"]
    motion_prompt = shot_data["motion_prompt"]
    seed = shot_data.get("seed", global_cfg.get("seed_base", 42))

    print(f"🎬 Scene {scene_num}, Shot {shot_num} (Video)")
    print(f"   Input Image: {motion_image}")
    print(f"   Seed: {seed}")
    print(f"   Motion Prompt: {motion_prompt[:120]}...")

    # 1. Resolve local path of motion_image and upload it
    local_img_path = None
    if os.path.isabs(motion_image):
        local_img_path = motion_image
    else:
        # Check current working directory, then scenes directory
        cwd_candidate = os.path.abspath(motion_image)
        scenes_candidate = os.path.join(scenes_dir, motion_image)
        if os.path.exists(cwd_candidate):
            local_img_path = cwd_candidate
        elif os.path.exists(scenes_candidate):
            local_img_path = scenes_candidate
        else:
            # Try searching without directories
            filename_only = os.path.basename(motion_image)
            scenes_file = os.path.join(scenes_dir, filename_only)
            if os.path.exists(scenes_file):
                local_img_path = scenes_file

    if not local_img_path or not os.path.exists(local_img_path):
        print(f"   ❌ Input motion image not found locally: {motion_image}")
        print(f"      (Looked in current path and scenes dir: {scenes_dir})")
        return None

    # Check if the filename is already on the ComfyUI instance
    server_filename = os.path.basename(local_img_path)
    if server_filename not in available_images:
        print(f"   📤 Uploading input image to ComfyUI: {server_filename}")
        upload_result = upload_image(local_img_path, base_url, auth=auth)
        if not upload_result or "name" not in upload_result:
            print(f"   ❌ Failed to upload input image to ComfyUI: {local_img_path}")
            return None
        server_filename = upload_result["name"]
        print(f"   ✅ Uploaded successfully as '{server_filename}'")
        # Add to available images to avoid re-uploading
        available_images.add(server_filename)
    else:
        print(f"   📷 Input image already exists on server: {server_filename}")

    # Build shot data copy with updated prompt, filename_prefix, references, overrides
    # Wait, the template expects:
    # __PROMPT__ -> shot_data["prompt"]
    # __MOTION_IMAGE__ -> shot_data["motion_image"] or references[0]
    # __FILENAME_PREFIX__ -> shot_data["filename_prefix"]
    # __SEED__ -> shot_data["seed"]
    # __WIDTH__, __HEIGHT__ -> global_cfg or shot_overrides
    # __DURATION__, __FPS__ -> shot_data or global_cfg
    shot_for_builder = {
        **shot_data,
        "prompt": motion_prompt,
        "motion_image": server_filename,
        "references": [server_filename],
        "filename_prefix": f"video/{prefix}"
    }

    # Build the workflow from template
    workflow = build_dynamic_workflow(workflow_template, shot_for_builder, global_cfg)

    # Queue the workflow
    result = curl_json("POST", "/prompt", base_url,
                       data={"prompt": workflow, "client_id": "story-to-video-video"},
                       auth=auth)

    if "error" in result:
        err = result["error"]
        node_errors = result.get("node_errors", {})
        print(f"   ❌ Queue error: {err.get('type')}: {err.get('message')}")
        for nid, errs in node_errors.items():
            for e in errs.get("errors", []):
                print(f"      Node {nid}: {e.get('details', e.get('message', ''))}")
        return None

    prompt_id = result.get("prompt_id")
    print(f"   ⏳ Queued video task: {prompt_id}")

    try:
        outputs = wait_for_prompt(prompt_id, base_url, auth=auth)
    except (RuntimeError, TimeoutError) as e:
        print(f"   ❌ {e}")
        return None

    # Download output video files
    for nid, out in outputs.items():
        # Look for video outputs (CreateVideo / SaveVideo node outputs are under gifs/videos/images)
        video_items = out.get("gifs", []) + out.get("videos", []) + out.get("images", [])
        for item in video_items:
            filename = item["filename"]
            # Use base filename to avoid nested dirs in output path
            base_fname = os.path.basename(filename)
            out_path = os.path.join(videos_dir, base_fname)
            print(f"   📥 Downloading {base_fname}...")
            if download_output(filename, out_path, base_url, item.get("subfolder", ""), auth=auth, is_video=True):
                size = os.path.getsize(out_path)
                print(f"   ✅ Saved video: {out_path} ({size/1024/1024:.2f} MB)")
                return out_path

    print(f"   ⚠️ No video file found in ComfyUI history outputs")
    return None


# ── Main ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Story-to-Video: Phase 3 Video Generator (LTX 2.3 I2V)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--prompts", default="motion_prompt.json",
                        help="Path to motion_prompt.json file (default: motion_prompt.json)")
    parser.add_argument("--url", default=os.environ.get("COMFYUI_URL", DEFAULT_BASE_URL),
                        help=f"ComfyUI base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                        help=f"Output base directory (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--shot", type=str, default=None,
                        help="Filter and run only a specific shot (matches filename_prefix)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip generation if the video file already exists in output-dir/videos/")
    parser.add_argument("--auth", type=str, default=None,
                        help="ComfyUI Basic Auth in username:password format")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build workflow configurations and print parameters without queueing execution")

    args = parser.parse_args()
    base_url = args.url
    output_dir = args.output_dir
    
    # Establish subdirectories
    scenes_dir = os.path.join(output_dir, "scenes")
    videos_dir = os.path.join(output_dir, "videos")

    # Parse auth
    comfyui_auth = None
    if args.auth:
        parts = args.auth.split(":", 1)
        if len(parts) == 2:
            comfyui_auth = (parts[0], parts[1])
        else:
            print("❌ Invalid auth format. Use username:password")
            sys.exit(1)

    os.makedirs(videos_dir, exist_ok=True)

    # ── Load motion_prompt.json ──
    try:
        prompts_data = load_motion_prompts(args.prompts)
    except Exception as e:
        print(f"❌ Error loading prompts: {e}")
        sys.exit(1)

    global_cfg = prompts_data["global"]
    shots = prompts_data["shots"]

    # ── Filter shots ──
    if args.shot:
        shots = [s for s in shots if s["filename_prefix"] == args.shot]
        if not shots:
            print(f"❌ Shot '{args.shot}' not found in motion_prompt.json")
            print(f"   Available: {[s['filename_prefix'] for s in prompts_data['shots']]}")
            sys.exit(1)

    # ── Load workflow template ──
    template_name = prompts_data["workflow_template"]
    try:
        workflow_template = load_workflow_template(template_name)
        print(f"🔧 Loaded workflow template: {template_name}")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # ── Dry-run mode ──
    if args.dry_run:
        print(f"\n🔍 Dry-run: compiling workflows for {len(shots)} video shots...")
        for shot in shots:
            prefix = shot["filename_prefix"]
            # Mock build shot
            shot_for_builder = {
                **shot,
                "prompt": shot["motion_prompt"],
                "references": [shot["motion_image"]],
                "filename_prefix": f"video/{prefix}"
            }
            workflow = build_dynamic_workflow(workflow_template, shot_for_builder, global_cfg)
            print(f"   ✅ {prefix}: compiled {len(workflow)} nodes. Input='{shot['motion_image']}'")
        print(f"\n✅ Dry-run complete. All {len(shots)} workflow specs compiled successfully.")
        return

    # ── Discover available images on ComfyUI ──
    try:
        available = get_available_images(base_url, auth=comfyui_auth)
        print(f"📷 Found {len(available)} available files in ComfyUI input directory")
    except Exception as e:
        print(f"⚠️  Could not fetch available images from ComfyUI: {e}")
        available = set()

    # ── Generation mode ──
    print(f"\n🎥 Generating {len(shots)} videos")
    print(f"   Model: {prompts_data['model']}")
    print(f"   Save path: {videos_dir}/")

    results = {}
    for shot in shots:
        prefix = shot["filename_prefix"]

        # Skip existing check
        if args.skip_existing:
            # Check for existing video files in output dir (MP4, WEBM, GIF)
            existing = sorted(
                f for f in os.listdir(videos_dir)
                if f.startswith(prefix) and f.endswith(('.mp4', '.webm', '.gif'))
                and os.path.getsize(os.path.join(videos_dir, f)) > 1024
            )
            if existing:
                existing_path = os.path.join(videos_dir, existing[-1])
                print(f"\n🎬 {prefix}: ⏭️  Skipping ({existing[-1]} exists, "
                      f"{os.path.getsize(existing_path)/1024/1024:.2f} MB)")
                results[prefix] = {"path": existing_path, "skipped": True}
                continue

        path = generate_video_shot(
            shot, global_cfg, workflow_template, base_url,
            videos_dir, scenes_dir, available, auth=comfyui_auth
        )
        if path:
            results[prefix] = {"path": path, "skipped": False}
        else:
            results[prefix] = None

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"  Video Generation Summary ({prompts_data['model']})")
    print(f"{'='*60}")
    skipped = 0
    for prefix, result in results.items():
        if result:
            if result.get("skipped"):
                status = "⏭️"
                skipped += 1
            else:
                status = "✅"
            print(f"  {prefix}: {status} — {result.get('path', 'N/A')}")
        else:
            print(f"  {prefix}: ❌ Failed")
            
    total = len(results)
    if skipped:
        print(f"\n  ⏭️  {skipped}/{total} skipped (--skip-existing)")


if __name__ == "__main__":
    main()
