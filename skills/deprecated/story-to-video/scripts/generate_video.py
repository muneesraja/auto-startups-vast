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

    is_director = data.get("workflow_template", "").startswith("ltx-23-director")
    for i, shot in enumerate(data["shots"]):
        required_fields = ["scene", "shot", "motion_prompt", "filename_prefix"]
        if not is_director:
            required_fields.append("motion_image")
        for field in required_fields:
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

def resolve_image_path(image_name, scenes_dir):
    """Resolve local filesystem path of an image name."""
    if not image_name:
        return None
    if os.path.isabs(image_name):
        return image_name if os.path.exists(image_name) else None
    
    # Check current working directory, then scenes directory
    cwd_candidate = os.path.abspath(image_name)
    scenes_candidate = os.path.join(scenes_dir, image_name)
    if os.path.exists(cwd_candidate):
        return cwd_candidate
    elif os.path.exists(scenes_candidate):
        return scenes_candidate
    
    # Try searching without directories
    filename_only = os.path.basename(image_name)
    scenes_file = os.path.join(scenes_dir, filename_only)
    if os.path.exists(scenes_file):
        return scenes_file
    
    return None


def upload_image_if_needed(local_path, base_url, available_images, auth=None):
    """Uploads local image to ComfyUI if it's not already uploaded.
    
    Returns:
        str: Server filename
    """
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


def build_director_timeline(shot_data, global_cfg, scenes_dir, base_url, available_images, auth=None):
    """Build the timeline_data JSON for the LTX Director node."""
    duration = shot_data.get("duration", global_cfg.get("duration", 5))
    
    segments = []
    
    # 1. Process keyframes if present
    keyframes = shot_data.get("keyframes", [])
    if keyframes:
        for kf in keyframes:
            img_name = kf.get("image")
            local_path = resolve_image_path(img_name, scenes_dir)
            server_name = ""
            if local_path:
                server_name = upload_image_if_needed(local_path, base_url, available_images, auth)
            
            start_time = float(kf.get("time", 0.0))
            end_time = float(kf.get("end_time", start_time + 0.5))
            if end_time > duration:
                end_time = duration
                
            seg = {
                "start": start_time,
                "end": end_time,
                "text": kf.get("prompt", kf.get("text", "")),
                "imageFile": server_name,
                "guideStrength": float(kf.get("guide_strength", kf.get("guideStrength", 1.0)))
            }
            segments.append(seg)
    
    # 2. Process text segments if present
    text_segments = shot_data.get("segments", [])
    if text_segments:
        for ts in text_segments:
            start_time = float(ts["start"])
            end_time = float(ts["end"])
            if end_time > duration:
                end_time = duration
                
            seg = {
                "start": start_time,
                "end": end_time,
                "text": ts.get("prompt", ts.get("text", ""))
            }
            if "image" in ts:
                local_path = resolve_image_path(ts["image"], scenes_dir)
                if local_path:
                    seg["imageFile"] = upload_image_if_needed(local_path, base_url, available_images, auth)
                    seg["guideStrength"] = float(ts.get("guide_strength", ts.get("guideStrength", 1.0)))
            segments.append(seg)
            
    # 3. Fallback: if no keyframes and no segments, check motion_image
    if not keyframes and not text_segments:
        motion_image = shot_data.get("motion_image")
        if motion_image:
            local_path = resolve_image_path(motion_image, scenes_dir)
            server_name = ""
            if local_path:
                server_name = upload_image_if_needed(local_path, base_url, available_images, auth)
            
            # Keyframe at 0s guiding start
            segments.append({
                "start": 0.0,
                "end": 0.5,
                "text": shot_data.get("motion_prompt", ""),
                "imageFile": server_name,
                "guideStrength": 1.0
            })
            # Text segment covering full duration
            segments.append({
                "start": 0.0,
                "end": float(duration),
                "text": shot_data.get("motion_prompt", "")
            })
        else:
            # Pure text-to-video
            segments.append({
                "start": 0.0,
                "end": float(duration),
                "text": shot_data.get("motion_prompt", "")
            })
            
    # Sort segments by start time
    segments.sort(key=lambda s: s["start"])
    
    return {"segments": segments, "audioSegments": []}


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
    motion_prompt = shot_data["motion_prompt"]
    seed = shot_data.get("seed", global_cfg.get("seed_base", 42))

    builder_type = workflow_template.get("_builder")
    is_director = (builder_type == "ltx_director")

    print(f"🎬 Scene {scene_num}, Shot {shot_num} (Video)")
    print(f"   Seed: {seed}")
    print(f"   Motion Prompt: {motion_prompt[:120]}...")

    if is_director:
        print("   🤖 Mode: LTX Director Timeline Guided")
        timeline_data = build_director_timeline(
            shot_data, global_cfg, scenes_dir, base_url, available_images, auth
        )
        shot_for_builder = {
            **shot_data,
            "prompt": shot_data.get("motion_prompt", ""),
            "filename_prefix": f"video/{prefix}",
            "references": [],
            "timeline_data": timeline_data
        }
    else:
        motion_image = shot_data["motion_image"]
        print(f"   Input Image: {motion_image}")
        local_img_path = resolve_image_path(motion_image, scenes_dir)
        if not local_img_path or not os.path.exists(local_img_path):
            print(f"   ❌ Input motion image not found locally: {motion_image}")
            print(f"      (Looked in current path and scenes dir: {scenes_dir})")
            return None

        server_filename = upload_image_if_needed(local_img_path, base_url, available_images, auth)
        if not server_filename:
            return None

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
        # Bearer token (recommended for Cloudflare-fronted ComfyUI):
        #   --auth "user:bf3a..."     → string after first colon = bearer
        # Basic auth (legacy):
        #   --auth "user:pass"        → tuple (only if value is short)
        if ":" in args.auth:
            prefix, value = args.auth.split(":", 1)
            # Bearer tokens are long hex strings (≥32 chars), passwords are short.
            # This is the only reliable heuristic since the value can start with
            # anything (e.g. "bf3a..." in the pencil-search case).
            if len(value) >= 32 and " " not in value:
                comfyui_auth = value  # Bearer
            else:
                comfyui_auth = (prefix, value)  # Basic
        else:
            # Raw bearer token (no "user:" prefix)
            comfyui_auth = args.auth

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
        builder_type = workflow_template.get("_builder")
        is_director = (builder_type == "ltx_director")
        for shot in shots:
            prefix = shot["filename_prefix"]
            if is_director:
                timeline_data = build_director_timeline(
                    shot, global_cfg, scenes_dir, base_url, set(), auth=comfyui_auth
                )
                shot_for_builder = {
                    **shot,
                    "prompt": shot.get("motion_prompt", ""),
                    "filename_prefix": f"video/{prefix}",
                    "references": [],
                    "timeline_data": timeline_data
                }
                input_desc = f"{len(timeline_data.get('segments', []))} segments"
            else:
                motion_image = shot["motion_image"]
                shot_for_builder = {
                    **shot,
                    "prompt": shot["motion_prompt"],
                    "references": [motion_image],
                    "filename_prefix": f"video/{prefix}"
                }
                input_desc = f"Input='{motion_image}'"
            workflow = build_dynamic_workflow(workflow_template, shot_for_builder, global_cfg)
            print(f"   ✅ {prefix}: compiled {len(workflow)} nodes. {input_desc}")
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
