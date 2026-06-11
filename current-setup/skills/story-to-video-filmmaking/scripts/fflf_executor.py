#!/usr/bin/env python3
"""
Story-to-Video-Filmmaking: FFLF Executor (Phase 3)
===================================================
Orchestrates the multi-stage LTX 2.3 FFLF Seed Hunter workflow.

Execution modes:
1. Default: Stage 1 preview -> auto motion evaluator selection -> Stage 2+3 upscale/render.
2. Fast (--fast): Stage 1+2+3 in one pass using seed 0, skipping seed hunt.
3. Interactive (--interactive): Stage 1 preview -> blocks on user CLI input for selection -> Stage 2+3.

Usage:
    python3 fflf_executor.py --prompts filmmaking_prompt.json
    python3 fflf_executor.py --prompts filmmaking_prompt.json --fast
    python3 fflf_executor.py --prompts filmmaking_prompt.json --interactive
"""
import argparse
import json
import os
import sys
import copy
import time

from comfyui_api import (
    curl_json,
    wait_for_prompt,
    download_output,
    get_available_images,
    upload_image,
    DEFAULT_BASE_URL,
)
from workflow_builder import build_dynamic_workflow, load_workflow_template
from filmmaking_utils import load_filmmaking_prompts, upload_image_if_needed
from continuation_pipeline import extract_continuation_frame

# Defaults
DEFAULT_FILMMAKING_OUTPUT_DIR = "/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video-filmmaking"





# ── Path Resolution & Upload Helpers ───────────────────────────

def resolve_image_path(image_name, scenes_dir):
    """Resolve local path of first frame / last frame images."""
    if not image_name:
        return None
    if os.path.isabs(image_name):
        return image_name if os.path.exists(image_name) else None
    
    # Try directly, then inside scenes directory
    candidates = [
        os.path.abspath(image_name),
        os.path.join(scenes_dir, image_name),
        os.path.join(scenes_dir, os.path.basename(image_name))
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
            
    return None




# ── FFLF Video Generation Pipeline ─────────────────────────────

def execute_fflf_shot(shot_data, global_cfg, workflow_template, base_url, videos_dir,
                      scenes_dir, motion_eval_dir, available_images, mode="auto", auth=None):
    """Execute the FFLF Seed Hunter workflow for a single shot.
    
    Args:
        shot_data: Shot dict
        global_cfg: Global configuration
        workflow_template: Workflow template dictionary
        base_url: ComfyUI base URL
        videos_dir: Video outputs folder
        scenes_dir: Image assets folder
        motion_eval_dir: Preview clips folder
        available_images: Set of images already on ComfyUI
        mode: "auto" (evaluator-selected), "interactive" (CLI-prompted), or "fast"
        auth: Optional Basic Auth tuple
    """
    scene_num = shot_data["scene"]
    shot_num = shot_data["shot"]
    shot_type = shot_data["shot_type"]
    prefix = shot_data["filename_prefix"]
    motion_prompt = shot_data["motion_prompt"]
    
    print(f"\n🎬 [Scene {scene_num}, Shot {shot_num}] Type: {shot_type}")
    print(f"   Motion Prompt: {motion_prompt}")
    
    # 1. Resolve first frame and last frame local paths
    ff_image_name = shot_data.get("first_frame_image")
    lf_image_name = shot_data.get("last_frame_image")
    
    # For continuation shots, check if the first frame was extracted locally
    if shot_type in ("continuation", "bridge") and not ff_image_name:
        ff_image_name = f"{prefix}_ff_extracted.png"
        
    ff_local = resolve_image_path(ff_image_name, scenes_dir)
    lf_local = resolve_image_path(lf_image_name, scenes_dir)
    
    if shot_type in ("chain_start", "independent") and not ff_local:
        print(f"   ❌ First frame image not found locally: {ff_image_name}")
        return None
    if not lf_local:
        print(f"   ❌ Last frame image not found locally: {lf_image_name}")
        return None
        
    # 2. Upload images to ComfyUI
    ff_server = upload_image_if_needed(ff_local, base_url, available_images, auth) if ff_local else None
    lf_server = upload_image_if_needed(lf_local, base_url, available_images, auth)
    
    # 3. Formulate builder input
    shot_for_builder = copy.deepcopy(shot_data)
    shot_for_builder["prompt"] = motion_prompt
    shot_for_builder["first_frame_image"] = ff_server or ""
    shot_for_builder["last_frame_image"] = lf_server
    shot_for_builder["references"] = [lf_server]
    if ff_server:
        shot_for_builder["references"].insert(0, ff_server)
        
    # Set default seed base and secondary seeds
    seed_base = shot_data.get("seed", global_cfg.get("seed_base", 42))
    shot_for_builder["seed_base"] = seed_base
    shot_for_builder["seed_stage2"] = seed_base + 1000
    shot_for_builder["seed_stage3"] = seed_base + 2000

    # 4. Multi-Stage Execution
    if mode == "fast":
        print("   ⚡ Mode: FAST (Direct upscale, seed hunt skipped)")
        shot_for_builder["_finish_mode"] = True
        shot_for_builder["_selected_gen_index"] = 0
        shot_for_builder["filename_prefix"] = f"video/{prefix}"
        
        workflow = build_dynamic_workflow(workflow_template, shot_for_builder, global_cfg)
        return queue_and_wait_video(workflow, base_url, videos_dir, auth)
        
    # Mode is either "auto" or "interactive" -> runs Stage 1 previews first
    print("   🔭 Phase 1: Running 3× parallel Stage 1 Seed Hunting previews...")
    shot_for_builder["_finish_mode"] = False
    shot_for_builder["_selected_gen_index"] = 0  # Ignored in seed hunt mode
    shot_for_builder["filename_prefix"] = f"motion_eval/{prefix}_stage1"
    
    workflow_stage1 = build_dynamic_workflow(workflow_template, shot_for_builder, global_cfg)
    
    # Queue Stage 1 and download previews
    preview_paths = queue_and_download_previews(workflow_stage1, base_url, motion_eval_dir, auth)
    if not preview_paths or len(preview_paths) < 3:
        print("   ❌ Failed to generate or download 3 low-res previews.")
        return None
        
    print(f"   ✅ Stage 1 Previews generated:")
    for idx, path in enumerate(preview_paths):
        print(f"      [{idx}] Preview: {path} ({os.path.getsize(path)/1024:.1f} KB)")
        
    # 5. Seed Selection Decision Point
    selected_index = 0
    if mode == "interactive":
        print("\n   👇 INTERACTIVE SELECTION REQUIRED:")
        while True:
            try:
                choice = input("      Enter the index of the best motion (0, 1, or 2): ").strip()
                if choice in ("0", "1", "2"):
                    selected_index = int(choice)
                    break
                else:
                    print("      ⚠️ Invalid choice. Please enter 0, 1, or 2.")
            except KeyboardInterrupt:
                print("\n   ❌ Generation cancelled by user.")
                sys.exit(0)
    else:
        print("\n   🤖 Auto Mode: Invoking Gemini Motion Evaluator...")
        try:
            from motion_evaluator import evaluate_motion_previews
            eval_result = evaluate_motion_previews(
                preview_paths=preview_paths,
                first_frame_path=ff_local,
                last_frame_path=lf_local,
                motion_prompt=motion_prompt
            )
            selected_index = eval_result["selected_index"]
            print(f"      Selected index: [{selected_index}] (Motion score: {eval_result['scores'][selected_index]['overall']:.2f})")
            print(f"      Reason: {eval_result['reasoning']}")
            
            # Save evaluation report
            report_path = os.path.join(motion_eval_dir, f"{prefix}_motion_eval.json")
            with open(report_path, "w") as f:
                json.dump(eval_result, f, indent=2)
            print(f"      📄 Evaluation report saved to: {report_path}")
        except Exception as e:
            print(f"      ⚠️ Auto-evaluation failed: {e}. Falling back to default index [0]")
            selected_index = 0

    # 6. Execute Stage 2+3 Upscale & Render
    print(f"\n   🎬 Phase 2: Upscaling selected motion path [{selected_index}] to full-resolution...")
    shot_for_builder["_finish_mode"] = True
    shot_for_builder["_selected_gen_index"] = selected_index
    shot_for_builder["filename_prefix"] = f"video/{prefix}"
    
    workflow_final = build_dynamic_workflow(workflow_template, shot_for_builder, global_cfg)
    return queue_and_wait_video(workflow_final, base_url, videos_dir, auth)


def queue_and_wait_video(workflow, base_url, target_dir, auth=None):
    """Queue workflow and wait for final video output."""
    result = curl_json("POST", "/prompt", base_url,
                       data={"prompt": workflow, "client_id": "story-to-video-filmmaking-video"},
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
    print(f"   ⏳ Queued full render: {prompt_id}")

    try:
        outputs = wait_for_prompt(prompt_id, base_url, auth=auth)
    except (RuntimeError, TimeoutError) as e:
        print(f"   ❌ {e}")
        return None

    for nid, out in outputs.items():
        video_items = out.get("gifs", []) + out.get("videos", []) + out.get("images", [])
        for item in video_items:
            filename = item["filename"]
            base_fname = os.path.basename(filename)
            out_path = os.path.join(target_dir, base_fname)
            print(f"   📥 Downloading {base_fname}...")
            if download_output(filename, out_path, base_url, item.get("subfolder", ""), auth=auth, is_video=True):
                size = os.path.getsize(out_path)
                print(f"   ✅ Saved final video: {out_path} ({size/1024/1024:.2f} MB)")
                return out_path
                
    print("   ⚠️ No video file found in final execution outputs")
    return None


def queue_and_download_previews(workflow, base_url, target_dir, auth=None):
    """Queue workflow and download the 3 low-res preview videos."""
    result = curl_json("POST", "/prompt", base_url,
                       data={"prompt": workflow, "client_id": "story-to-video-filmmaking-previews"},
                       auth=auth)

    if "error" in result:
        err = result["error"]
        print(f"   ❌ Queue error: {err.get('type')}: {err.get('message')}")
        return []

    prompt_id = result.get("prompt_id")
    print(f"   ⏳ Queued Stage 1 task: {prompt_id}")

    try:
        outputs = wait_for_prompt(prompt_id, base_url, auth=auth)
    except (RuntimeError, TimeoutError) as e:
        print(f"   ❌ {e}")
        return []

    downloaded_paths = []
    # Collect all video outputs.
    # Previews are written by nodes: 5062, 5186, 5202
    preview_nodes = ["5062", "5186", "5202"]
    
    # We want them in order corresponding to node 5062 (index 0), 5186 (index 1), 5202 (index 2)
    node_to_idx = {"5062": 0, "5186": 1, "5202": 2}
    previews = [None, None, None]
    
    for nid in preview_nodes:
        if nid in outputs:
            out = outputs[nid]
            video_items = out.get("gifs", []) + out.get("videos", []) + out.get("images", [])
            if video_items:
                item = video_items[0]
                filename = item["filename"]
                base_fname = os.path.basename(filename)
                out_path = os.path.join(target_dir, base_fname)
                print(f"   📥 Downloading preview: {base_fname}...")
                if download_output(filename, out_path, base_url, item.get("subfolder", ""), auth=auth, is_video=True):
                    previews[node_to_idx[nid]] = out_path
                    
    return [p for p in previews if p is not None]


# ── Main CLI ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Story-to-Video-Filmmaking: FFLF Executor",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--prompts", default="filmmaking_prompt.json",
                        help="Path to filmmaking_prompt.json (default: filmmaking_prompt.json)")
    parser.add_argument("--url", default=os.environ.get("COMFYUI_URL", DEFAULT_BASE_URL),
                        help=f"ComfyUI base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--output-dir", default=DEFAULT_FILMMAKING_OUTPUT_DIR,
                        help=f"Output base directory (default: {DEFAULT_FILMMAKING_OUTPUT_DIR})")
    parser.add_argument("--shot", type=str, default=None,
                        help="Filter and run only a specific shot (matches filename_prefix)")
    parser.add_argument("--fast", action="store_true",
                        help="Skip Stage 1 seed hunting and executeStage 2+3 directly using index 0")
    parser.add_argument("--interactive", action="store_true",
                        help="Prompt user in terminal to select index from Stage 1 preview videos")
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
    motion_eval_dir = os.path.join(output_dir, "motion_eval")

    os.makedirs(videos_dir, exist_ok=True)
    os.makedirs(motion_eval_dir, exist_ok=True)

    # Parse auth
    comfyui_auth = None
    if args.auth:
        parts = args.auth.split(":", 1)
        if len(parts) == 2:
            comfyui_auth = (parts[0], parts[1])
        else:
            print("❌ Invalid auth format. Use username:password")
            sys.exit(1)

    # Load prompts
    try:
        prompts_data = load_filmmaking_prompts(args.prompts)
    except Exception as e:
        print(f"❌ Error loading prompts: {e}")
        sys.exit(1)

    global_cfg = prompts_data["global"]
    shots = prompts_data["shots"]

    # Filter shots
    if args.shot:
        shots = [s for s in shots if s["filename_prefix"] == args.shot]
        if not shots:
            print(f"❌ Shot '{args.shot}' not found in filmmaking_prompt.json")
            sys.exit(1)

    # Load workflow template
    template_name = prompts_data["workflow_template"]
    try:
        workflow_template = load_workflow_template(template_name)
        print(f"🔧 Loaded workflow template: {template_name}")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Dry-run mode
    if args.dry_run:
        print(f"\n🔍 Dry-run: compiling workflows for {len(shots)} filmmaking shots...")
        # Compile resolution preset values
        preset = global_cfg.get("resolution_preset", "1080p")
        presets = workflow_template.get("_resolution_presets", {})
        width = presets.get(preset, {}).get("width", 1920)
        height = presets.get(preset, {}).get("height", 1088)
        
        for shot in shots:
            prefix = shot["filename_prefix"]
            shot_for_builder = copy.deepcopy(shot)
            shot_for_builder["prompt"] = shot["motion_prompt"]
            shot_for_builder["first_frame_image"] = shot.get("first_frame_image") or "ff_placeholder.png"
            shot_for_builder["last_frame_image"] = shot["last_frame_image"]
            shot_for_builder["references"] = [shot_for_builder["last_frame_image"]]
            shot_for_builder["_finish_mode"] = True
            shot_for_builder["_selected_gen_index"] = 0
            
            workflow = build_dynamic_workflow(workflow_template, shot_for_builder, global_cfg)
            print(f"   ✅ {prefix}: compiled {len(workflow)} nodes. Output target: {width}x{height} (preset {preset})")
            
        print(f"\n✅ Dry-run complete. All {len(shots)} workflow specs compiled successfully.")
        return

    # Discover available images on ComfyUI
    try:
        available = get_available_images(base_url, auth=comfyui_auth)
        print(f"📷 Found {len(available)} available files in ComfyUI input directory")
    except Exception as e:
        print(f"⚠️  Could not fetch available images from ComfyUI: {e}")
        available = set()

    # Determine execution mode
    mode = "auto"
    if args.fast:
        mode = "fast"
    elif args.interactive:
        mode = "interactive"

    print(f"\n🎥 Generating {len(shots)} filmmaking shots")
    print(f"   Execution Mode: {mode.upper()}")
    print(f"   Save path: {videos_dir}/")

    results = {}
    for shot in shots:
        prefix = shot["filename_prefix"]

        # Skip existing check
        if args.skip_existing:
            existing = sorted(
                f for f in os.listdir(videos_dir)
                if f.startswith(prefix) and f.endswith(('.mp4', '.webm', '.gif'))
                and os.path.getsize(os.path.join(videos_dir, f)) > 1024
            )
            if existing:
                existing_path = os.path.join(videos_dir, existing[-1])
                print(f"\n🎬 {prefix}: ⏭️  Skipping ({existing[-1]} exists)")
                results[prefix] = {"path": existing_path, "skipped": True}
                continue

        # Handle continuation shot first frame extraction from previous shot's video path
        shot_type = shot.get("shot_type")
        continues_from = shot.get("continues_from")
        if shot_type in ("continuation", "bridge") and not shot.get("first_frame_image"):
            prev_video_path = None
            if continues_from and continues_from in results and results[continues_from]:
                prev_video_path = results[continues_from].get("path")
            
            if prev_video_path and os.path.exists(prev_video_path):
                target_image_name = f"{prefix}_ff_extracted.png"
                target_image_path = os.path.join(scenes_dir, target_image_name)
                
                # Retrieve overrides or globals for overlap_seconds and fps
                overlap_seconds = shot.get("overrides", {}).get("overlap_seconds") or global_cfg.get("overlap_seconds", 1.0)
                fps = shot.get("overrides", {}).get("fps") or global_cfg.get("fps", 25)
                
                print(f"   🎞️  Continuation: Extracting first frame from preceding video {prev_video_path}")
                try:
                    extracted_path = extract_continuation_frame(
                        video_path=prev_video_path,
                        overlap_seconds=overlap_seconds,
                        fps=fps,
                        output_path=target_image_path
                    )
                    if extracted_path and os.path.exists(extracted_path):
                        shot["first_frame_image"] = target_image_name
                except Exception as e:
                    print(f"   ⚠️  Failed to extract continuation frame: {e}")
            else:
                print(f"   ⚠️  Continuation source shot '{continues_from}' video path not found or does not exist.")

        path = execute_fflf_shot(
            shot_data=shot,
            global_cfg=global_cfg,
            workflow_template=workflow_template,
            base_url=base_url,
            videos_dir=videos_dir,
            scenes_dir=scenes_dir,
            motion_eval_dir=motion_eval_dir,
            available_images=available,
            mode=mode,
            auth=comfyui_auth
        )
        if path:
            results[prefix] = {"path": path, "skipped": False}
        else:
            results[prefix] = None

    # Summary
    print(f"\n{'='*60}")
    print(f"  Filmmaking Video Generation Summary")
    print(f"{'='*60}")
    skipped = 0
    for prefix, result in results.items():
        if result:
            status = "⏭️" if result.get("skipped") else "✅"
            if result.get("skipped"):
                skipped += 1
            print(f"  {prefix}: {status} — {result.get('path')}")
        else:
            print(f"  {prefix}: ❌ Failed")
            
    total = len(results)
    if skipped:
        print(f"\n  ⏭️  {skipped}/{total} skipped (--skip-existing)")


if __name__ == "__main__":
    main()
