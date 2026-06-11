#!/usr/bin/env python3
"""
Story-to-Video-Filmmaking: Smart Frame Generator (Phase 2)
=========================================================
Generates the First Frame (FF) and Last Frame (LF) still images required by
the FFLF Seed Hunter video generation pipeline.

Smart Optimization:
- chain_start / independent: generates both FF + LF (2 images)
- continuation / bridge: generates only LF (1 image; FF comes from prev video tail)

Coherence Check:
- Calls Gemini Vision to evaluate visual continuity and trajectory between FF and LF.
"""
import argparse
import json
import os
import shutil
import sys
import copy

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
from gemini_eval import (
    call_gemini_vision,
    call_openrouter_vision,
    resolve_provider,
    parse_eval_response,
    build_eval_prompt as build_eval_prompt_base,
    GEMINI_MODEL,
    OPENROUTER_MODEL,
    PASS_THRESHOLD,
)

DEFAULT_FILMMAKING_OUTPUT_DIR = "/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video-filmmaking"

COHERENCE_EVAL_PROMPT = """
You are evaluating two keyframes (First Frame and Last Frame) for an AI video generation pipeline.
The video model will interpolate motion between these two frames.

Motion description: {motion_prompt}

Evaluate whether these two frames form a plausible start→end pair:

1. **Spatial Continuity** (0-10): Is it the same environment/setting in both frames?
2. **Character Continuity** (0-10): Are the same characters present, and do they look recognizable across both frames?
3. **Logical Trajectory** (0-10): Could natural motion connect frame A to frame B?
4. **Difficulty Rating** (easy/medium/hard/impossible): How challenging will this interpolation be for the video model?

If difficulty is "impossible", explain what needs to change.

Reply ONLY JSON:
{{
  "spatial_continuity": N,
  "character_continuity": N,
  "logical_trajectory": N, 
  "overall": N,
  "difficulty": "easy|medium|hard|impossible",
  "issues": ["..."],
  "suggestions": ["..."]
}}
"""




# ── Single Frame Generator ─────────────────────────────────────

def generate_single_frame(prompt_text, references, filename, workflow_template,
                          global_cfg, base_url, available_images, auth=None):
    """Generate a single still frame image via ComfyUI."""
    print(f"   🎨 Generating still frame: {filename}")
    print(f"      References: {references}")
    print(f"      Prompt: {prompt_text[:120]}...")

    # Upload references to ComfyUI input folder if needed
    for ref in references:
        # Resolve path
        pass # The caller resolves path
        
    shot_for_builder = {
        "prompt": prompt_text,
        "references": references,
        "filename_prefix": filename.replace(".png", "")
    }

    # Build workflow using builder
    workflow = build_dynamic_workflow(workflow_template, shot_for_builder, global_cfg)

    # Queue workflow
    result = curl_json("POST", "/prompt", base_url,
                       data={"prompt": workflow, "client_id": "story-to-video-filmmaking-still"},
                       auth=auth)

    if "error" in result:
        err = result["error"]
        print(f"      ❌ Queue error: {err.get('type')}: {err.get('message')}")
        return None

    prompt_id = result.get("prompt_id")
    try:
        outputs = wait_for_prompt(prompt_id, base_url, auth=auth)
    except (RuntimeError, TimeoutError) as e:
        print(f"      ❌ {e}")
        return None

    # Download output image
    for nid, out in outputs.items():
        for item in out.get("images", []):
            srv_filename = item["filename"]
            # Save directly with target filename in output scenes dir
            return srv_filename

    return None


# ── Frame Quality Evaluation ───────────────────────────────────

def evaluate_frame_quality(image_path, expected_prompt, character_names, references_base_dir, reference_filenames, api_key, provider):
    """Evaluate a single generated still image against its prompt and reference sheets."""
    provider_name, resolved_key, call_fn = resolve_provider(provider)
    if api_key:
        resolved_key = api_key
        
    # Build details
    expected_desc = f"EXPECTED SCENE DESCRIPTION:\nGeneration prompt: {expected_prompt}\n"
    if character_names:
        expected_desc += f"Characters expected: {', '.join(character_names)}"
    else:
        expected_desc += "Characters expected: None (landscape/environment)"
        
    # Resolve reference image paths
    reference_images = []
    if references_base_dir and reference_filenames:
        for ref_name in reference_filenames:
            ref_path = os.path.join(references_base_dir, ref_name)
            if os.path.exists(ref_path):
                reference_images.append(ref_path)

    eval_prompt = build_eval_prompt_base(expected_desc, version="v2", reference_names=reference_filenames if reference_filenames else None)
    
    response = call_fn(eval_prompt, image_path, resolved_key, reference_images=reference_images if reference_images else None)
    
    reasoning = ""
    if isinstance(response, dict):
        reasoning = response.get("reasoning", "")
        response = response["response"]
        
    result = parse_eval_response(response)
    if result and reasoning:
        result["reasoning"] = reasoning
    return result


# ── FF ↔ LF Coherence Check ────────────────────────────────────

def evaluate_ff_lf_coherence(ff_path, lf_path, motion_prompt, api_key, provider):
    """Check visual coherence and trajectory between First Frame and Last Frame."""
    provider_name, resolved_key, call_fn = resolve_provider(provider)
    if api_key:
        resolved_key = api_key
        
    eval_prompt = COHERENCE_EVAL_PROMPT.format(motion_prompt=motion_prompt)
    
    # We pass ff_path as the primary image and lf_path as reference_images
    response = call_fn(eval_prompt, ff_path, resolved_key, reference_images=[lf_path])
    
    reasoning = ""
    if isinstance(response, dict):
        reasoning = response.get("reasoning", "")
        response = response["response"]
        
    # Parse coherence JSON
    try:
        text = response.strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        if reasoning:
            result["reasoning"] = reasoning
        return result
    except Exception as e:
        print(f"   ❌ Coherence parser error: {e}. Raw response: {response}")
        return {
            "spatial_continuity": 5,
            "character_continuity": 5,
            "logical_trajectory": 5,
            "overall": 5.0,
            "difficulty": "medium",
            "issues": ["Could not parse coherence evaluation response"],
            "suggestions": []
        }


# ── Smart Frame Generation Coordinator ────────────────────────

def generate_frames_for_shot(shot_data, global_cfg, workflow_template, base_url,
                              scenes_dir, references_base_dir, available_images,
                              api_key=None, provider=None, evaluate=False, auth=None):
    """Determine frame generation needs and execute still generations."""
    shot_type = shot_data["shot_type"]
    prefix = shot_data["filename_prefix"]
    character_names = shot_data.get("characters_present", [])
    reference_filenames = shot_data.get("references", [])
    
    print(f"\n🎬 Smart Frame Gen: [Shot {prefix}] type={shot_type}")
    
    ff_image_name = shot_data.get("first_frame_image")
    lf_image_name = shot_data.get("last_frame_image")
    
    result = {
        "first_frame_path": None,
        "last_frame_path": None,
        "first_frame_source": "skipped",
        "last_frame_source": "skipped",
        "evaluations": {}
    }
    
    # Resolve local target paths
    ff_path = os.path.join(scenes_dir, ff_image_name) if ff_image_name else None
    lf_path = os.path.join(scenes_dir, lf_image_name)
    
    # Upload reference sheets to ComfyUI if they exist in references_base_dir
    ref_srv_names = []
    if references_base_dir and reference_filenames:
        for ref_name in reference_filenames:
            ref_local_path = os.path.join(references_base_dir, ref_name)
            if os.path.exists(ref_local_path):
                srv_name = upload_image_if_needed(ref_local_path, base_url, available_images, auth)
                if srv_name:
                    ref_srv_names.append(srv_name)
            else:
                print(f"   ⚠️ Reference sheet not found locally: {ref_local_path}")
                
    # --- Generate First Frame (FF) ---
    if shot_type in ("chain_start", "independent"):
        print(f"   👉 Generating First Frame...")
        # Check if already exists and skip
        if ff_path and os.path.exists(ff_path) and os.path.getsize(ff_path) > 1024:
            print(f"      📷 First Frame image exists: {ff_image_name}")
            result["first_frame_path"] = ff_path
            result["first_frame_source"] = "existing"
        else:
            srv_ff = generate_single_frame(
                prompt_text=shot_data["first_frame_prompt"],
                references=ref_srv_names,
                filename=ff_image_name,
                workflow_template=workflow_template,
                global_cfg=global_cfg,
                base_url=base_url,
                available_images=available_images,
                auth=auth
            )
            if srv_ff:
                # Download to scenes directory
                local_dest = os.path.join(scenes_dir, ff_image_name)
                print(f"      📥 Downloading FF still to: {local_dest}")
                if download_output(srv_ff, local_dest, base_url, auth=auth):
                    result["first_frame_path"] = local_dest
                    result["first_frame_source"] = "generated"
                    
        # Single image evaluation for FF
        if evaluate and result["first_frame_path"]:
            ff_eval = evaluate_frame_quality(
                image_path=result["first_frame_path"],
                expected_prompt=shot_data["first_frame_prompt"],
                character_names=character_names,
                references_base_dir=references_base_dir,
                reference_filenames=reference_filenames,
                api_key=api_key,
                provider=provider
            )
            result["evaluations"]["ff"] = ff_eval
            
    elif shot_type in ("continuation", "bridge"):
        print(f"   ⏭️  Skipping First Frame (extracted dynamically from previous video during execution)")
        result["first_frame_source"] = "continuation_extracted"
        
    # --- Generate Last Frame (LF) ---
    print(f"   👉 Generating Last Frame...")
    if os.path.exists(lf_path) and os.path.getsize(lf_path) > 1024:
        print(f"      📷 Last Frame image exists: {lf_image_name}")
        result["last_frame_path"] = lf_path
        result["last_frame_source"] = "existing"
    else:
        srv_lf = generate_single_frame(
            prompt_text=shot_data["last_frame_prompt"],
            references=ref_srv_names,
            filename=lf_image_name,
            workflow_template=workflow_template,
            global_cfg=global_cfg,
            base_url=base_url,
            available_images=available_images,
            auth=auth
        )
        if srv_lf:
            # Download to scenes directory
            local_dest = os.path.join(scenes_dir, lf_image_name)
            print(f"      📥 Downloading LF still to: {local_dest}")
            if download_output(srv_lf, local_dest, base_url, auth=auth):
                result["last_frame_path"] = local_dest
                result["last_frame_source"] = "generated"
                
    # Single image evaluation for LF
    if evaluate and result["last_frame_path"]:
        lf_eval = evaluate_frame_quality(
            image_path=result["last_frame_path"],
            expected_prompt=shot_data["last_frame_prompt"],
            character_names=character_names,
            references_base_dir=references_base_dir,
            reference_filenames=reference_filenames,
            api_key=api_key,
            provider=provider
        )
        result["evaluations"]["lf"] = lf_eval
        
    # --- Coherence Check between FF and LF ---
    # Can only run if we generated/have BOTH images locally (i.e. chain_start or independent)
    if evaluate and result["first_frame_path"] and result["last_frame_path"]:
        print(f"   📊 Running FF ↔ LF Coherence Check...")
        coherence = evaluate_ff_lf_coherence(
            ff_path=result["first_frame_path"],
            lf_path=result["last_frame_path"],
            motion_prompt=shot_data["motion_prompt"],
            api_key=api_key,
            provider=provider
        )
        result["evaluations"]["coherence"] = coherence
        print(f"      Coherence Score: {coherence.get('overall', 0)}/10 (Difficulty: {coherence.get('difficulty')})")
        if coherence.get("issues"):
            print(f"      ⚠️ Coherence Issues: {'; '.join(coherence['issues'])}")
            
    return result




# ── CLI Main ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Story-to-Video-Filmmaking: Smart Frame Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--prompts", required=True,
                        help="Path to filmmaking_prompt.json")
    parser.add_argument("--shot", type=str,
                        help="Filter and run only a specific shot (matches filename_prefix)")
    parser.add_argument("--evaluate", action="store_true",
                        help="Evaluate generated images and run visual coherence checks")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse filmmaking_prompt.json and print execution steps without queueing")
    parser.add_argument("--url", default=DEFAULT_BASE_URL,
                        help=f"ComfyUI base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--output-dir", default=DEFAULT_FILMMAKING_OUTPUT_DIR,
                        help=f"Output base directory (default: {DEFAULT_FILMMAKING_OUTPUT_DIR})")
    parser.add_argument("--api-key", default=os.environ.get("GEMINI_API_KEY", ""),
                        help="Gemini API Key override")
    parser.add_argument("--provider", choices=["openrouter", "gemini"], default=None,
                        help="Vision API provider")
    parser.add_argument("--references-dir", type=str, default=None,
                        help="Character reference sheets folder (defaults to sibling 'characters/')")
    parser.add_argument("--auth", type=str, default=None,
                        help="ComfyUI Basic Auth in username:password format")

    args = parser.parse_args()
    base_url = args.url
    output_dir = args.output_dir
    scenes_dir = os.path.join(output_dir, "scenes")
    
    # Establish subdirectories
    os.makedirs(scenes_dir, exist_ok=True)

    # Basic Auth
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

    # Resolve references directory
    if args.references_dir:
        references_base_dir = args.references_dir
    else:
        prompts_dir = os.path.dirname(os.path.abspath(args.prompts))
        references_base_dir = os.path.join(prompts_dir, "characters")
        
    print(f"📂 Reference Sheets Dir: {references_base_dir}")

    # Load workflow template (image generation model, e.g. flux-2-dev-turbo)
    template_name = prompts_data.get("image_workflow_template") or prompts_data.get("global", {}).get("image_workflow_template", "flux-2-dev-turbo")
    try:
        workflow_template = load_workflow_template(template_name)
        print(f"🔧 Loaded image generation workflow template: {template_name}")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Dry-run
    if args.dry_run:
        print(f"\n🔍 Dry-run: compiling frame generation workflows for {len(shots)} shots...")
        for shot in shots:
            prefix = shot["filename_prefix"]
            shot_type = shot["shot_type"]
            if shot_type in ("chain_start", "independent"):
                print(f"   ✅ {prefix} (type={shot_type}): will generate FF ({shot.get('first_frame_image')}) and LF ({shot.get('last_frame_image')})")
            else:
                print(f"   ✅ {prefix} (type={shot_type}): will generate LF ({shot.get('last_frame_image')}) only")
        print("\n✅ Dry-run complete.")
        return

    # Discover available images on ComfyUI
    try:
        available = get_available_images(base_url, auth=comfyui_auth)
    except Exception as e:
        print(f"⚠️  Could not fetch available images from ComfyUI: {e}")
        available = set()

    # Generate
    print(f"\n📖 Generating stills for {len(shots)} filmmaking shots...")
    for shot in shots:
        result = generate_frames_for_shot(
            shot_data=shot,
            global_cfg=global_cfg,
            workflow_template=workflow_template,
            base_url=base_url,
            scenes_dir=scenes_dir,
            references_base_dir=references_base_dir,
            available_images=available,
            api_key=args.api_key,
            provider=args.provider,
            evaluate=args.evaluate,
            auth=comfyui_auth
        )
        
        # Save frame generation feedback JSON
        if args.evaluate and (result["first_frame_path"] or result["last_frame_path"]):
            feedback_dir = os.path.join(output_dir, "feedback")
            os.makedirs(feedback_dir, exist_ok=True)
            feedback_path = os.path.join(feedback_dir, f"{shot['filename_prefix']}_still_eval.json")
            with open(feedback_path, "w") as f:
                json.dump(result["evaluations"], f, indent=2)
            print(f"   📄 Stills evaluation feedback saved to: {feedback_path}")

    print("\n✅ Phase 2 Frame Generation Completed.")


if __name__ == "__main__":
    main()
