#!/usr/bin/env python3
"""
Story-to-Video-Cinematic: Recursive Cinematic Orchestrator
=========================================================
Orchestrates the 3-stage model pipeline:
  1. Ideogram 4 T2I -> Character sheets + raw scene stills
  2. Flux Klein 9B Edit -> Character consistency refinement
  3. LTX 2.3 FFLF -> Consistent video generation

Optimization:
- Batch executes Ideogram passes first to avoid model swapping.
- Batch executes Flux Klein edit passes next.
- Sequentially executes LTX 2.3 FFLF video generation and tail frame extraction.
"""

import argparse
import json
import os
import shutil
import sys
import time
import copy

# Resolve and append story-to-video-filmmaking scripts path
script_dir = os.path.dirname(os.path.abspath(__file__))
filmmaking_scripts = os.path.abspath(os.path.join(
    script_dir, "..", "..", "story-to-video-filmmaking", "scripts"
))
sys.path.append(filmmaking_scripts)

# Import ComfyUI and filmmaking helper modules
from comfyui_api import (
    curl_json,
    wait_for_prompt,
    download_output,
    get_available_images,
    upload_image,
    DEFAULT_BASE_URL,
)
from workflow_builder import build_dynamic_workflow, load_workflow_template
from filmmaking_utils import upload_image_if_needed
from continuation_pipeline import extract_continuation_frame
from fflf_executor import execute_fflf_shot

# Import our new cinematic generators
import ideogram_generator
import flux_edit_pass


# ── Cinematic Prompts Loader & Validator ──────────────────────

def load_cinematic_prompts(prompts_path):
    """Load and validate cinematic_prompt.json."""
    if not os.path.exists(prompts_path):
        raise FileNotFoundError(f"Cinematic prompts file not found: {prompts_path}")

    with open(prompts_path) as f:
        data = json.load(f)

    # Validate required top-level fields
    required = ["version", "pipeline", "models", "global", "shots"]
    for field in required:
        if field not in data:
            raise ValueError(f"cinematic_prompt.json missing required field: '{field}'")

    if data["pipeline"] != "cinematic":
        raise ValueError(f"cinematic_prompt.json pipeline field must be 'cinematic'")

    global_cfg = data["global"]
    for field in ["resolution_preset", "fps", "segment_duration"]:
        if field not in global_cfg:
            raise ValueError(f"cinematic_prompt.json global section missing required field: '{field}'")

    for i, shot in enumerate(data["shots"]):
        required_fields = ["scene", "shot", "shot_type", "filename_prefix", "motion_prompt"]
        for field in required_fields:
            if field not in shot:
                raise ValueError(f"cinematic_prompt.json shot[{i}] missing required field: '{field}'")
        
        # Check first_frame_prompt/last_frame_prompt based on type
        if shot["shot_type"] in ("chain_start", "independent") and "first_frame_prompt" not in shot:
            raise ValueError(f"cinematic_prompt.json shot[{i}] ({shot['filename_prefix']}) is a root shot but missing 'first_frame_prompt'")
        if "last_frame_prompt" not in shot:
            raise ValueError(f"cinematic_prompt.json shot[{i}] ({shot['filename_prefix']}) missing 'last_frame_prompt'")

    print(f"📋 Loaded cinematic_prompt.json (v{data['version']})")
    print(f"   Pipeline: {data['pipeline']}")
    print(f"   Models: {data['models']}")
    print(f"   Shots: {len(data['shots'])}")
    print(f"   Default Style: {global_cfg.get('style', 'Not Specified')}")

    return data


# ── Chain Topology Resolver ────────────────────────────────────

def resolve_chains(shots):
    """Group shots into chains and identify independent shots."""
    # Build lookup by filename_prefix
    shot_by_prefix = {s["filename_prefix"]: s for s in shots}

    # Determine continuation shots
    has_predecessor = set()
    for shot in shots:
        if shot.get("continues_from"):
            has_predecessor.add(shot["filename_prefix"])

    # Root shots: chain_start or independent
    root_shots = [s for s in shots if s["filename_prefix"] not in has_predecessor]

    # Build chains
    chains = []
    for root in root_shots:
        chain = [root]
        while True:
            last_prefix = chain[-1]["filename_prefix"]
            next_shots = [s for s in shots if s.get("continues_from") == last_prefix]
            if not next_shots:
                break
            if len(next_shots) > 1:
                print(f"   ⚠️  Multiple shots continue from '{last_prefix}' — using the first one: {next_shots[0]['filename_prefix']}")
            chain.append(next_shots[0])
        chains.append(chain)

    return chains


def print_execution_plan(chains, mode):
    """Print execution plan details."""
    total_shots = sum(len(c) for c in chains)
    total_chains = len(chains)
    print(f"\n📋 Execution Plan ({total_chains} chain(s), {total_shots} shot(s) total, mode={mode.upper()})")
    print("=" * 80)
    for chain_idx, chain in enumerate(chains):
        root = chain[0]
        root_type = root["shot_type"]
        print(f"\n  Chain {chain_idx + 1}: [{root['filename_prefix']}] (root type={root_type})")
        for shot_idx, shot in enumerate(chain):
            prefix = shot["filename_prefix"]
            shot_type = shot["shot_type"]
            primary_char = shot.get("primary_character", "None")
            print(f"    [{shot_idx + 1}] {prefix} (type={shot_type}, primary_char={primary_char})")
    print("=" * 80)


def _extract_tail(video_path, shot, global_cfg, scenes_dir, prefix):
    """Extract the tail frame from a video for use as the next shot's FF."""
    if not video_path or not os.path.exists(video_path):
        return None
    overlap_seconds = shot.get("overrides", {}).get("overlap_seconds") or global_cfg.get("overlap_seconds", 1.0)
    fps = shot.get("overrides", {}).get("fps") or global_cfg.get("fps", 25)
    target_image_name = f"{prefix}_tail_frame.png"
    target_image_path = os.path.join(scenes_dir, target_image_name)
    try:
        extracted = extract_continuation_frame(
            video_path=video_path,
            overlap_seconds=overlap_seconds,
            fps=fps,
            output_path=target_image_path
        )
        return extracted if extracted and os.path.exists(extracted) else None
    except Exception as e:
        print(f"  ⚠️  Tail frame extraction error: {e}")
        return None


# ── Orchestrator Main Execution ───────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Story-to-Video-Cinematic: Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--prompts", default="cinematic_prompt.json",
                        help="Path to cinematic_prompt.json (default: cinematic_prompt.json)")
    parser.add_argument("--url", default=os.environ.get("COMFYUI_URL", DEFAULT_BASE_URL),
                        help=f"ComfyUI base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--output-dir", default=None,
                        help="Output directory (defaults to sibling directory of --prompts)")
    parser.add_argument("--shot", type=str, default=None,
                        help="Process only a specific shot (matches filename_prefix)")
    parser.add_argument("--fast", action="store_true",
                        help="Skip LTX seed hunting, use Stage 2+3 directly")
    parser.add_argument("--interactive", action="store_true",
                        help="Prompt user in terminal to select Stage 1 preview index")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip shots whose videos already exist in videos/")
    parser.add_argument("--dry-run", action="store_true",
                        help="Resolve chains and print execution plan without generating anything")
    parser.add_argument("--auth", type=str, default=None,
                        help="ComfyUI Basic Auth in username:password format")
    parser.add_argument("--api-key", default=os.environ.get("GEMINI_API_KEY", ""),
                        help="API key for motion evaluation")
    parser.add_argument("--provider", choices=["openrouter", "gemini"], default=None,
                        help="Vision provider for evaluation")
    parser.add_argument("--references-dir", type=str, default=None,
                        help="Character reference sheets folder")

    args = parser.parse_args()
    base_url = args.url

    # Resolve output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        # derive output directory from prompts path
        prompts_dir = os.path.dirname(os.path.abspath(args.prompts))
        output_dir = prompts_dir

    # Establish subdirectories
    scenes_dir = os.path.join(output_dir, "scenes")
    scenes_edited_dir = os.path.join(output_dir, "scenes_edited")
    videos_dir = os.path.join(output_dir, "videos")
    motion_eval_dir = os.path.join(output_dir, "motion_eval")
    
    if args.references_dir:
        references_dir = args.references_dir
    else:
        references_dir = os.path.join(output_dir, "character_sheets")

    for d in [scenes_dir, scenes_edited_dir, videos_dir, motion_eval_dir, references_dir]:
        os.makedirs(d, exist_ok=True)

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
        prompts_data = load_cinematic_prompts(args.prompts)
    except Exception as e:
        print(f"❌ Error loading prompts: {e}")
        sys.exit(1)

    global_cfg = prompts_data["global"]
    shots = prompts_data["shots"]
    characters = prompts_data.get("characters", {})

    # Filter to single shot if requested
    if args.shot:
        target = next((s for s in shots if s["filename_prefix"] == args.shot), None)
        if not target:
            print(f"❌ Shot '{args.shot}' not found in cinematic_prompt.json")
            sys.exit(1)
        shots = [target]

    # Resolve chain topology
    mode = "fast" if args.fast else ("interactive" if args.interactive else "auto")
    chains = resolve_chains(shots)

    if args.dry_run:
        print_execution_plan(chains, mode)
        print("\n✅ Dry-run complete — no assets or videos generated.")
        return

    print_execution_plan(chains, mode)

    # Resolve workflow template folders
    cinematic_templates_dir = os.path.abspath(os.path.join(script_dir, "..", "assets", "workflow-templates"))
    filmmaking_templates_dir = os.path.abspath(os.path.join(script_dir, "..", "..", "story-to-video-filmmaking", "assets", "workflow-templates"))

    # Load Templates
    try:
        ideogram_template = load_workflow_template("ideogram-4-t2i", templates_dir=cinematic_templates_dir)
        flux_edit_template = load_workflow_template("flux-2-klein-image-edit", templates_dir=cinematic_templates_dir)
        ltx_fflf_template = load_workflow_template("ltx-23-fflf-seed-hunter", templates_dir=filmmaking_templates_dir)
    except FileNotFoundError as e:
        print(f"❌ Workflow template loading failed: {e}")
        sys.exit(1)

    # Discover available images on ComfyUI
    try:
        available = get_available_images(base_url, auth=comfyui_auth)
        print(f"📷 Found {len(available)} files in ComfyUI input directory")
    except Exception as e:
        print(f"⚠️  Could not fetch ComfyUI available images: {e}")
        available = set()

    # ─────────────────────────────────────────────────────────────
    # PHASE 1: GENERATE CHARACTER SHEETS (Ideogram 4 T2I)
    # ─────────────────────────────────────────────────────────────
    print(f"\n\n{'═'*80}\n  PHASE 1: Generating Character Sheets\n{'═'*80}")
    character_sheet_server_paths = {}
    
    for char_name, char_info in characters.items():
        sheet_filename = f"{char_name}_character_sheet.png"
        sheet_local_path = os.path.join(references_dir, sheet_filename)
        
        if os.path.exists(sheet_local_path) and os.path.getsize(sheet_local_path) > 1024:
            print(f"   📷 Character sheet for '{char_name}' already exists locally: {sheet_filename}")
        else:
            print(f"   🎨 Composing character sheet prompt for '{char_name}'...")
            json_prompt = ideogram_generator.compose_character_sheet_prompt(
                character_name=char_name,
                character_desc=char_info["description"],
                style_notes=char_info.get("style_notes", ""),
                global_style=global_cfg.get("style", "")
            )
            srv_file = ideogram_generator.generate_ideogram_image(
                prompt_text=json_prompt,
                filename=sheet_filename,
                workflow_template=ideogram_template,
                global_cfg=global_cfg,
                base_url=base_url,
                auth=comfyui_auth
            )
            if srv_file:
                print(f"      📥 Downloading character sheet still to: {sheet_local_path}")
                download_output(srv_file, sheet_local_path, base_url, auth=comfyui_auth)
            else:
                print(f"      ❌ Character sheet generation failed for: {char_name}")
                sys.exit(1)

        # Upload sheet to ComfyUI and store server-side name
        srv_name = upload_image_if_needed(sheet_local_path, base_url, available, comfyui_auth)
        character_sheet_server_paths[char_name] = srv_name

    # ─────────────────────────────────────────────────────────────
    # PHASE 2: GENERATE RAW SCENE FRAMES (Ideogram 4 T2I)
    # ─────────────────────────────────────────────────────────────
    print(f"\n\n{'═'*80}\n  PHASE 2: Generating Raw Scene stills (Ideogram 4)\n{'═'*80}")
    raw_stills = {} # Mapping local path -> server filename
    
    for shot in shots:
        prefix = shot["filename_prefix"]
        shot_type = shot["shot_type"]
        chars_present = shot.get("characters_present", [])
        
        # 1. FF (Only generated for chain starts and independents)
        if shot_type in ("chain_start", "independent"):
            ff_raw_name = f"{prefix}_ff_raw.png"
            ff_raw_path = os.path.join(scenes_dir, ff_raw_name)
            
            if os.path.exists(ff_raw_path) and os.path.getsize(ff_raw_path) > 1024:
                print(f"   📷 Raw FF already exists locally: {ff_raw_name}")
            else:
                json_prompt = ideogram_generator.compose_scene_prompt(
                    prompt_text=shot["first_frame_prompt"],
                    global_style=global_cfg.get("style", ""),
                    characters_present=chars_present,
                    characters_cfg=characters
                )
                srv_file = ideogram_generator.generate_ideogram_image(
                    prompt_text=json_prompt,
                    filename=ff_raw_name,
                    workflow_template=ideogram_template,
                    global_cfg=global_cfg,
                    base_url=base_url,
                    auth=comfyui_auth
                )
                if srv_file:
                    print(f"      📥 Downloading raw FF still to: {ff_raw_path}")
                    download_output(srv_file, ff_raw_path, base_url, auth=comfyui_auth)
                else:
                    print(f"      ❌ Raw FF generation failed for {prefix}")
                    continue

        # 2. LF (Always generated)
        lf_raw_name = f"{prefix}_lf_raw.png"
        lf_raw_path = os.path.join(scenes_dir, lf_raw_name)
        
        if os.path.exists(lf_raw_path) and os.path.getsize(lf_raw_path) > 1024:
            print(f"   📷 Raw LF already exists locally: {lf_raw_name}")
        else:
            json_prompt = ideogram_generator.compose_scene_prompt(
                prompt_text=shot["last_frame_prompt"],
                global_style=global_cfg.get("style", ""),
                characters_present=chars_present,
                characters_cfg=characters
            )
            srv_file = ideogram_generator.generate_ideogram_image(
                prompt_text=json_prompt,
                filename=lf_raw_name,
                workflow_template=ideogram_template,
                global_cfg=global_cfg,
                base_url=base_url,
                auth=comfyui_auth
            )
            if srv_file:
                print(f"      📥 Downloading raw LF still to: {lf_raw_path}")
                download_output(srv_file, lf_raw_path, base_url, auth=comfyui_auth)
            else:
                print(f"      ❌ Raw LF generation failed for {prefix}")
                continue

    # ─────────────────────────────────────────────────────────────
    # PHASE 3: RUN FLUX KLEIN EDIT PASS (Character Consistency)
    # ─────────────────────────────────────────────────────────────
    print(f"\n\n{'═'*80}\n  PHASE 3: Running Flux Klein Edit Pass\n{'═'*80}")
    
    for shot in shots:
        prefix = shot["filename_prefix"]
        shot_type = shot["shot_type"]
        chars_present = shot.get("characters_present", [])
        primary_char = shot.get("primary_character")
        
        # Determine if we should perform the edit pass
        has_character = len(chars_present) > 0 and primary_char in characters
        
        # Helper function to edit a single raw image
        def process_edit_pass(raw_filename, edited_filename, edit_prompt_key):
            raw_path = os.path.join(scenes_dir, raw_filename)
            edited_path = os.path.join(scenes_edited_dir, edited_filename)
            
            if not os.path.exists(raw_path):
                print(f"   ⚠️  Raw still '{raw_filename}' not found. Skipping edit pass.")
                return False
                
            if os.path.exists(edited_path) and os.path.getsize(edited_path) > 1024:
                print(f"   📷 Edited still '{edited_filename}' already exists locally.")
                return True
                
            if not has_character:
                # No characters present/registered -> copy raw to edited folder directly
                print(f"   ⏭️  No character consistency needed for '{raw_filename}' — copying raw file.")
                shutil.copy(raw_path, edited_path)
                return True
                
            # Upload raw scene image to ComfyUI
            srv_scene = upload_image_if_needed(raw_path, base_url, available, comfyui_auth)
            srv_char_sheet = character_sheet_server_paths[primary_char]
            
            # Resolve edit prompt
            char_info = characters[primary_char]
            edit_prompt = shot.get("edit_pass", {}).get(edit_prompt_key)
            if not edit_prompt:
                edit_descriptor = char_info.get("edit_prompt_descriptor", primary_char)
                edit_prompt = flux_edit_pass.compose_edit_prompt(
                    edit_prompt_descriptor=edit_descriptor,
                    style=global_cfg.get("style", "")
                )
                
            srv_edited = flux_edit_pass.execute_flux_klein_edit(
                scene_image_server_path=srv_scene,
                character_ref_server_path=srv_char_sheet,
                edit_prompt=edit_prompt,
                filename=edited_filename,
                workflow_template=flux_edit_template,
                global_cfg=global_cfg,
                base_url=base_url,
                auth=comfyui_auth
            )
            
            if srv_edited:
                print(f"      📥 Downloading edited still to: {edited_path}")
                download_output(srv_edited, edited_path, base_url, auth=comfyui_auth)
                return True
            else:
                print(f"      ❌ Flux Klein edit failed for: {edited_filename}")
                return False

        # 1. Edit FF (for root shots)
        if shot_type in ("chain_start", "independent"):
            process_edit_pass(f"{prefix}_ff_raw.png", f"{prefix}_ff_edited.png", "ff_edit_prompt")
            
        # 2. Edit LF (all shots)
        process_edit_pass(f"{prefix}_lf_raw.png", f"{prefix}_lf_edited.png", "lf_edit_prompt")

    # ─────────────────────────────────────────────────────────────
    # PHASE 4: EXECUTE FFLF VIDEO PIPELINE (LTX 2.3)
    # ─────────────────────────────────────────────────────────────
    print(f"\n\n{'═'*80}\n  PHASE 4: Executing FFLF Video Pipeline\n{'═'*80}")
    
    all_results = {}
    start_time = time.time()
    
    for chain_idx, chain in enumerate(chains):
        print(f"\n\n{'═'*70}")
        print(f"  🎬 Processing Chain {chain_idx+1}/{len(chains)} — {len(chain)} shot(s)")
        print(f"{'═'*70}")
        
        tail_frame_path = None
        
        for shot_idx, shot in enumerate(chain):
            prefix = shot["filename_prefix"]
            shot_type = shot["shot_type"]
            
            # Skip if we only targeted a specific shot and it's not this one
            if args.shot and prefix != args.shot:
                continue
                
            print(f"\n{'─'*60}")
            print(f"  🎬 Processing video shot [{shot_idx+1}/{len(chain)}]: {prefix}")
            print(f"{'─'*60}")
            
            # Skip existing videos
            if args.skip_existing:
                existing = sorted(
                    f for f in os.listdir(videos_dir)
                    if f.startswith(prefix) and f.endswith(('.mp4', '.webm', '.gif'))
                    and os.path.getsize(os.path.join(videos_dir, f)) > 1024 * 100
                )
                if existing:
                    existing_path = os.path.join(videos_dir, existing[-1])
                    print(f"  ⏭️  Skipping video gen for {prefix} (exists: {existing[-1]})")
                    tail_frame_path = _extract_tail(existing_path, shot, global_cfg, scenes_edited_dir, prefix)
                    all_results[prefix] = {"path": existing_path, "tail_frame": tail_frame_path, "skipped": True}
                    continue

            # Resolve keyframe inputs in scenes_edited folder
            shot_data_for_fflf = copy.deepcopy(shot)
            
            # Assign edited keyframes
            if shot_type in ("chain_start", "independent"):
                shot_data_for_fflf["first_frame_image"] = f"{prefix}_ff_edited.png"
            elif shot_type in ("continuation", "bridge"):
                # Use preceding tail frame
                if tail_frame_path and os.path.exists(tail_frame_path):
                    shot_data_for_fflf["first_frame_image"] = os.path.basename(tail_frame_path)
                    print(f"  🔗 Using tail frame as FF: {os.path.basename(tail_frame_path)}")
                else:
                    print(f"  ⚠️  No tail frame available for continuation shot {prefix}. Video will run without anchor!")
                    
            shot_data_for_fflf["last_frame_image"] = f"{prefix}_lf_edited.png"
            
            # FFLF Video Generation
            print(f"\n  🎥 Running FFLF video generation...")
            video_path = execute_fflf_shot(
                shot_data=shot_data_for_fflf,
                global_cfg=global_cfg,
                workflow_template=ltx_fflf_template,
                base_url=base_url,
                videos_dir=videos_dir,
                scenes_dir=scenes_edited_dir, # pass scenes_edited so fflf resolves images there
                motion_eval_dir=motion_eval_dir,
                available_images=available,
                mode=mode,
                auth=comfyui_auth
            )
            
            if not video_path:
                print(f"  ❌ Video generation failed for {prefix}.")
                all_results[prefix] = None
                break
                
            # Extract tail frame for next shot
            tail_frame_path = None
            if shot_idx < len(chain) - 1:
                print(f"\n  🎞️  Extracting tail frame for next shot...")
                tail_frame_path = _extract_tail(video_path, shot, global_cfg, scenes_edited_dir, prefix)
                if tail_frame_path:
                    print(f"  ✅ Tail frame ready: {os.path.basename(tail_frame_path)}")
                else:
                    print(f"  ⚠️  Tail frame extraction failed.")
                    
            all_results[prefix] = {
                "path": video_path,
                "tail_frame": tail_frame_path,
                "skipped": False
            }

    # Final summary
    elapsed = time.time() - start_time
    print(f"\n\n{'═'*80}\n  Orchestrator — Final Summary ({elapsed/60:.1f}min)\n{'═'*80}")
    total = len(all_results)
    succeeded = sum(1 for r in all_results.values() if r and not r.get("skipped"))
    skipped = sum(1 for r in all_results.values() if r and r.get("skipped"))
    failed = sum(1 for r in all_results.values() if not r)

    for prefix, result in all_results.items():
        if result is None:
            print(f"  ❌ {prefix}: Failed")
        elif result.get("skipped"):
            print(f"  ⏭️  {prefix}: Skipped — {result['path']}")
        else:
            size_mb = os.path.getsize(result["path"]) / 1024 / 1024 if result["path"] and os.path.exists(result["path"]) else 0
            print(f"  ✅ {prefix}: {result['path']} ({size_mb:.1f}MB)")

    print(f"\n  Total: {total} shots — ✅ {succeeded} done, ⏭️ {skipped} skipped, ❌ {failed} failed")


if __name__ == "__main__":
    main()
