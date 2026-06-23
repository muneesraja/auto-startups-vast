import os
import json
import argparse

def organize_waves(output_dir: str):
    """Reads prompts.json and director_visual_blueprint.json, and organizes them

    into generator_wave_1.json and generator_wave_2.json.

    Flux-only architecture: Wave 1 phases are character_sheets → ff → lf → video
    (no consistency patches). Wave 2 is extract_ff → lf → video.
    """
    blueprint_path = os.path.join(output_dir, "director_visual_blueprint.json")
    prompts_path = os.path.join(output_dir, "prompts.json")

    if not os.path.exists(blueprint_path) or not os.path.exists(prompts_path):
        raise FileNotFoundError("Missing director_visual_blueprint.json or prompts.json in output directory.")

    with open(blueprint_path, "r", encoding="utf-8") as f:
        blueprint = json.load(f)

    with open(prompts_path, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    # 1. Group shots by Wave
    wave1_shot_ids = []
    wave2_shot_ids = []

    for scene in blueprint.get("scenes", []):
        for shot in scene.get("shots", []):
            shot_id = shot.get("shot_id")
            if shot.get("continuation_from_previous") is False:
                wave1_shot_ids.append(shot_id)
            else:
                wave2_shot_ids.append(shot_id)

    # 2. Build Wave 1 Payload (Flux-only: cs → ff → lf → video, no CP/LF_CP)
    wave1_payload = {
        "wave": 1,
        "character_sheets": {},
        "ff_shots": {},
        "lf_shots": {},
        "motion_prompts": {}
    }

    # All character sheets run in Wave 1
    for char_id, entry in prompts.get("character_sheets", {}).items():
        wave1_payload["character_sheets"][char_id] = entry

    # Wave 1 shots generations
    for shot_id in wave1_shot_ids:
        if shot_id in prompts.get("ff_shots", {}):
            wave1_payload["ff_shots"][shot_id] = prompts["ff_shots"][shot_id]
        if shot_id in prompts.get("lf_shots", {}):
            wave1_payload["lf_shots"][shot_id] = prompts["lf_shots"][shot_id]
        if shot_id in prompts.get("motion_prompts", {}):
            wave1_payload["motion_prompts"][shot_id] = prompts["motion_prompts"][shot_id]

    # Write Wave 1 payload
    wave1_path = os.path.join(output_dir, "generator_wave_1.json")
    with open(wave1_path, "w", encoding="utf-8") as f:
        json.dump(wave1_payload, f, indent=2, ensure_ascii=False)
    print(f"Generated Wave 1 payload: {wave1_path}")

    # 3. Build Wave 2 Payload
    wave2_payload = {
        "wave": 2,
        "ff_shots": {},
        "lf_shots": {},
        "motion_prompts": {}
    }

    # Wave 2 shots: FF is extracted from previous video; LF + video generation.
    for shot_id in wave2_shot_ids:
        if shot_id in prompts.get("ff_shots", {}):
            wave2_payload["ff_shots"][shot_id] = prompts["ff_shots"][shot_id]
        if shot_id in prompts.get("lf_shots", {}):
            wave2_payload["lf_shots"][shot_id] = prompts["lf_shots"][shot_id]
        if shot_id in prompts.get("motion_prompts", {}):
            wave2_payload["motion_prompts"][shot_id] = prompts["motion_prompts"][shot_id]

    # Write Wave 2 payload
    wave2_path = os.path.join(output_dir, "generator_wave_2.json")
    with open(wave2_path, "w", encoding="utf-8") as f:
        json.dump(wave2_payload, f, indent=2, ensure_ascii=False)
    print(f"Generated Wave 2 payload: {wave2_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deterministic Story-to-Video Wave Organizer")
    parser.add_argument("--dir", required=True, help="Absolute path to the output story directory")
    args = parser.parse_args()
    organize_waves(args.dir)
