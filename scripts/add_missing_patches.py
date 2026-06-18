import json
import os

def main():
    prompts_path = "/Users/muneesraja/Documents/growthlabs-vault/story-to-video-deterministic/leo_adventure/prompts.json"
    
    if not os.path.exists(prompts_path):
        print("prompts.json not found!")
        return

    with open(prompts_path, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    # 1. Add missing consistency patches
    if "consistency_patches" not in prompts:
        prompts["consistency_patches"] = {}

    # Add scene_03_shot_04 patch
    if "scene_03_shot_04" not in prompts["consistency_patches"]:
        print("Adding consistency patch for scene_03_shot_04...")
        prompts["consistency_patches"]["scene_03_shot_04"] = {
            "prompt_type": "flux_edit",
            "prompt": "Replace Bumblebee in the scene with the character from reference image 1 exactly — same face, body, clothing, and proportions. Keep the background, lighting, composition, and overall scene identical. Maintain the Pixar/Disney 3D animated movie style throughout.",
            "reference_images": [
                "{{character_sheets.char_03.output_path}}",
                "{{ff_shots.scene_03_shot_04.output_path}}"
            ],
            "output_path": None,
            "status": "pending",
            "generated_by": "add_missing_patches_script"
        }

    # Add scene_04_shot_03 patch
    if "scene_04_shot_03" not in prompts["consistency_patches"]:
        print("Adding consistency patch for scene_04_shot_03...")
        prompts["consistency_patches"]["scene_04_shot_03"] = {
            "prompt_type": "flux_edit",
            "prompt": "Replace Blue Toy Spaceship in the scene with the character from reference image 1 exactly — same face, body, clothing, and proportions. Keep the background, lighting, composition, and overall scene identical. Maintain the Pixar/Disney 3D animated movie style throughout.",
            "reference_images": [
                "{{character_sheets.char_04.output_path}}",
                "{{ff_shots.scene_04_shot_03.output_path}}"
            ],
            "output_path": None,
            "status": "pending",
            "generated_by": "add_missing_patches_script"
        }

    # 2. Reset dependent items to 'pending' if they were failed/skipped
    mismatched_shots = ["scene_03_shot_04", "scene_04_shot_03"]
    
    # Also reset scene_01_shot_01_lf because it failed previously but now has our builder fallback fix!
    all_resets_lf = mismatched_shots + ["scene_01_shot_01"]
    
    for shot in all_resets_lf:
        if "lf_shots" in prompts and shot in prompts["lf_shots"]:
            print(f"Resetting lf_shots.{shot} status to pending...")
            prompts["lf_shots"][shot]["status"] = "pending"
            prompts["lf_shots"][shot]["output_path"] = None

    for shot in mismatched_shots:
        if "motion_prompts" in prompts and shot in prompts["motion_prompts"]:
            print(f"Resetting motion_prompts.{shot} status to pending...")
            prompts["motion_prompts"][shot]["status"] = "pending"
            prompts["motion_prompts"][shot]["output_path"] = None

    with open(prompts_path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, indent=2, ensure_ascii=False)
    print("Successfully patched prompts.json!")

if __name__ == "__main__":
    main()
