import os
import json
import re
import argparse
import asyncio
from tools.comfyui_tools import (
    generate_ideogram_image,
    generate_flux_edit,
    generate_ltx_video,
    extract_last_frame
)

def resolve_ref(ref_str, prompts_data):
    """Resolve references like {{character_sheets.char_01.output_path}} dynamically."""
    if not isinstance(ref_str, str):
        return ref_str
    
    match = re.search(r"\{\{+([^}]+)\}\}+", ref_str)
    if not match:
        return ref_str
    
    parts = match.group(1).strip().split(".")
    if len(parts) != 3:
        return ref_str
    
    namespace, key, field = parts
    try:
        val = prompts_data[namespace][key][field]
        if val is None:
            raise ValueError(f"Reference value for {ref_str} is currently null.")
        return val
    except KeyError:
        raise KeyError(f"Could not resolve template reference: {ref_str}")

def update_prompts_file(prompts_path, prompts_data):
    """Write updated prompts back to disk."""
    with open(prompts_path, "w", encoding="utf-8") as f:
        json.dump(prompts_data, f, indent=2, ensure_ascii=False)

async def execute_wave(output_dir: str, wave: int):
    """Executes the specified wave tasks by calling ComfyUI."""
    prompts_path = os.path.join(output_dir, "prompts.json")
    blueprint_path = os.path.join(output_dir, "director_visual_blueprint.json")
    
    with open(prompts_path, "r", encoding="utf-8") as f:
        prompts = json.load(f)
        
    with open(blueprint_path, "r", encoding="utf-8") as f:
        blueprint = json.load(f)

    # Establish directories
    char_sheets_dir = os.path.join(output_dir, "character_sheets")
    images_dir = os.path.join(output_dir, "images")
    videos_dir = os.path.join(output_dir, "videos")
    
    os.makedirs(char_sheets_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(videos_dir, exist_ok=True)

    if wave == 1:
        print(f"\n🌊 Starting Wave 1 Execution in {output_dir}...")
        
        # 1. Generate Character Sheets
        for char_id, entry in list(prompts.get("character_sheets", {}).items()):
            if entry.get("status") == "generated" and entry.get("output_path"):
                print(f"   ⏭️ Character sheet for {char_id} already generated.")
                continue
            
            out_path = os.path.join(char_sheets_dir, f"{char_id}_sheet.png")
            print(f"   🎨 Generating character sheet for {char_id}...")
            res = generate_ideogram_image(entry["prompt"], out_path, aspect_ratio="16:9")
            
            if res.get("status") == "success":
                entry["status"] = "generated"
                entry["output_path"] = res["generated_image_path"]
                print(f"   ✅ Character sheet for {char_id} saved to {res['generated_image_path']}")
            else:
                entry["status"] = "failed"
                print(f"   ❌ Character sheet for {char_id} failed: {res.get('message')}")
            update_prompts_file(prompts_path, prompts)

        # 2. Generate First Frames (FF)
        for shot_id, entry in list(prompts.get("ff_shots", {}).items()):
            if entry["prompt_type"] == "extracted_frame":
                continue  # Handled in Wave 2 setup
            if entry.get("status") == "generated" and entry.get("output_path"):
                print(f"   ⏭️ FF for {shot_id} already generated.")
                continue
                
            out_path = os.path.join(images_dir, f"{shot_id}_ff.png")
            print(f"   🎨 Generating First Frame for {shot_id}...")
            res = generate_ideogram_image(entry["prompt"], out_path, aspect_ratio="16:9")
            
            if res.get("status") == "success":
                entry["status"] = "generated"
                entry["output_path"] = res["generated_image_path"]
                print(f"   ✅ First Frame for {shot_id} saved to {res['generated_image_path']}")
            else:
                entry["status"] = "failed"
                print(f"   ❌ First Frame for {shot_id} failed: {res.get('message')}")
            update_prompts_file(prompts_path, prompts)

        # 3. Generate Consistency Patches (Flux Klein edit)
        for shot_id, entry in list(prompts.get("consistency_patches", {}).items()):
            if entry.get("status") in ("generated", "skipped") and entry.get("output_path"):
                print(f"   ⏭️ Consistency patch for {shot_id} already processed.")
                continue
            
            if entry.get("status") == "skipped":
                continue

            # Resolve reference image paths
            try:
                resolved_refs = [resolve_ref(r, prompts) for r in entry["reference_images"]]
            except Exception as e:
                print(f"   ❌ Skipping consistency patch for {shot_id}: {e}")
                continue
                
            # Last reference is the scene image, preceding are character sheets
            scene_img = resolved_refs[-1]
            char_refs = resolved_refs[:-1]
            
            out_path = os.path.join(images_dir, f"{shot_id}_ff_consistent.png")
            print(f"   🎨 Generating Consistency Patch for {shot_id}...")
            res = generate_flux_edit(entry["prompt"], out_path, scene_img, char_refs)
            
            if res.get("status") == "success":
                entry["status"] = "generated"
                entry["output_path"] = res["generated_image_path"]
                print(f"   ✅ Consistency Patch for {shot_id} saved to {res['generated_image_path']}")
            else:
                entry["status"] = "failed"
                print(f"   ❌ Consistency Patch for {shot_id} failed: {res.get('message')}")
            update_prompts_file(prompts_path, prompts)

        # 4. Generate Last Frames (LF)
        for shot_id, entry in list(prompts.get("lf_shots", {}).items()):
            # Only process Wave 1 shots in Wave 1
            if shot_id not in wave1_shot_ids(blueprint):
                continue
            if entry.get("status") == "generated" and entry.get("output_path"):
                print(f"   ⏭️ LF for {shot_id} already generated.")
                continue

            try:
                resolved_refs = [resolve_ref(r, prompts) for r in entry["reference_images"]]
            except Exception as e:
                print(f"   ❌ Skipping LF for {shot_id}: {e}")
                continue
                
            scene_img = resolved_refs[0]
            char_refs = resolved_refs[1:]
            
            out_path = os.path.join(images_dir, f"{shot_id}_lf.png")
            print(f"   🎨 Generating Last Frame for {shot_id}...")
            res = generate_flux_edit(entry["prompt"], out_path, scene_img, char_refs)
            
            if res.get("status") == "success":
                entry["status"] = "generated"
                entry["output_path"] = res["generated_image_path"]
                print(f"   ✅ Last Frame for {shot_id} saved to {res['generated_image_path']}")
            else:
                entry["status"] = "failed"
                print(f"   ❌ Last Frame for {shot_id} failed: {res.get('message')}")
            update_prompts_file(prompts_path, prompts)

        # 5. Generate Wave 1 Videos (LTX FFLF)
        for shot_id, entry in list(prompts.get("motion_prompts", {}).items()):
            if shot_id not in wave1_shot_ids(blueprint):
                continue
            if entry.get("status") == "generated" and entry.get("output_path"):
                print(f"   ⏭️ Video for {shot_id} already generated.")
                continue

            try:
                ff_img = resolve_ref(entry["ff_image"], prompts)
                lf_img = resolve_ref(entry["lf_image"], prompts)
            except Exception as e:
                print(f"   ❌ Skipping video for {shot_id}: {e}")
                continue
                
            out_path = os.path.join(videos_dir, f"{shot_id}.mp4")
            print(f"   🎬 Generating Video for {shot_id} ({entry['duration_seconds']}s)...")
            res = generate_ltx_video(ff_img, lf_img, entry["prompt"], out_path, duration_seconds=entry["duration_seconds"])
            
            if res.get("status") == "success":
                entry["status"] = "generated"
                entry["output_path"] = res["video_path"]
                print(f"   ✅ Video for {shot_id} saved to {res['video_path']}")
            else:
                entry["status"] = "failed"
                print(f"   ❌ Video for {shot_id} failed: {res.get('message')}")
            update_prompts_file(prompts_path, prompts)

    elif wave == 2:
        print(f"\n🌊 Starting Wave 2 Execution in {output_dir}...")
        
        # 1. Setup Wave 2 First Frames (extract from Wave 1 video outputs)
        for scene in blueprint.get("scenes", []):
            shots = scene.get("shots", [])
            for i, shot in enumerate(shots):
                shot_id = shot["shot_id"]
                if shot.get("continuation_from_previous") is True:
                    # Resolve previous shot ID
                    prev_shot_id = shots[i-1]["shot_id"]
                    prev_video_entry = prompts["motion_prompts"].get(prev_shot_id)
                    
                    if not prev_video_entry or not prev_video_entry.get("output_path"):
                        print(f"   ⚠️ Cannot extract FF for {shot_id}: Preceding video for {prev_shot_id} was not generated.")
                        continue
                        
                    ff_entry = prompts["ff_shots"].get(shot_id)
                    if ff_entry and ff_entry.get("status") == "generated" and ff_entry.get("output_path"):
                        continue
                        
                    prev_video_path = prev_video_entry["output_path"]
                    extracted_path = os.path.join(images_dir, f"{shot_id}_ff.png")
                    
                    print(f"   🎞️ Extracting continuation starting frame for {shot_id} from {prev_shot_id} video...")
                    res = extract_last_frame(prev_video_path, extracted_path)
                    
                    if res.get("status") == "success":
                        if ff_entry:
                            ff_entry["status"] = "generated"
                            ff_entry["output_path"] = res["extracted_frame_path"]
                            update_prompts_file(prompts_path, prompts)
                        print(f"   ✅ Saved continuation starting frame to {res['extracted_frame_path']}")
                    else:
                        print(f"   ❌ Failed to extract starting frame: {res.get('message')}")

        # Re-read prompts file after extraction setup
        with open(prompts_path, "r", encoding="utf-8") as f:
            prompts = json.load(f)

        # 2. Generate Wave 2 Last Frames (LF)
        for shot_id, entry in list(prompts.get("lf_shots", {}).items()):
            if shot_id not in wave2_shot_ids(blueprint):
                continue
            if entry.get("status") == "generated" and entry.get("output_path"):
                print(f"   ⏭️ LF for {shot_id} already generated.")
                continue

            try:
                resolved_refs = [resolve_ref(r, prompts) for r in entry["reference_images"]]
            except Exception as e:
                print(f"   ❌ Skipping LF for {shot_id}: {e}")
                continue
                
            scene_img = resolved_refs[0]
            char_refs = resolved_refs[1:]
            
            out_path = os.path.join(images_dir, f"{shot_id}_lf.png")
            print(f"   🎨 Generating Last Frame for {shot_id}...")
            res = generate_flux_edit(entry["prompt"], out_path, scene_img, char_refs)
            
            if res.get("status") == "success":
                entry["status"] = "generated"
                entry["output_path"] = res["generated_image_path"]
                print(f"   ✅ Last Frame for {shot_id} saved to {res['generated_image_path']}")
            else:
                entry["status"] = "failed"
                print(f"   ❌ Last Frame for {shot_id} failed: {res.get('message')}")
            update_prompts_file(prompts_path, prompts)

        # 3. Generate Wave 2 Videos (LTX FFLF)
        for shot_id, entry in list(prompts.get("motion_prompts", {}).items()):
            if shot_id not in wave2_shot_ids(blueprint):
                continue
            if entry.get("status") == "generated" and entry.get("output_path"):
                print(f"   ⏭️ Video for {shot_id} already generated.")
                continue

            try:
                ff_img = resolve_ref(entry["ff_image"], prompts)
                lf_img = resolve_ref(entry["lf_image"], prompts)
            except Exception as e:
                print(f"   ❌ Skipping video for {shot_id}: {e}")
                continue
                
            out_path = os.path.join(videos_dir, f"{shot_id}.mp4")
            print(f"   🎬 Generating Video for {shot_id} ({entry['duration_seconds']}s)...")
            res = generate_ltx_video(ff_img, lf_img, entry["prompt"], out_path, duration_seconds=entry["duration_seconds"])
            
            if res.get("status") == "success":
                entry["status"] = "generated"
                entry["output_path"] = res["video_path"]
                print(f"   ✅ Video for {shot_id} saved to {res['video_path']}")
            else:
                entry["status"] = "failed"
                print(f"   ❌ Video for {shot_id} failed: {res.get('message')}")
            update_prompts_file(prompts_path, prompts)

def wave1_shot_ids(blueprint):
    ids = []
    for scene in blueprint.get("scenes", []):
        for shot in scene.get("shots", []):
            if shot.get("continuation_from_previous") is False:
                ids.append(shot["shot_id"])
    return ids

def wave2_shot_ids(blueprint):
    ids = []
    for scene in blueprint.get("scenes", []):
        for shot in scene.get("shots", []):
            if shot.get("continuation_from_previous") is True:
                ids.append(shot["shot_id"])
    return ids

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deterministic Story-to-Video Wave Executor")
    parser.add_argument("--dir", required=True, help="Absolute path to output directory")
    parser.add_argument("--wave", type=int, required=True, choices=[1, 2], help="Wave index to execute (1 or 2)")
    args = parser.parse_args()
    asyncio.run(execute_wave(args.dir, args.wave))
