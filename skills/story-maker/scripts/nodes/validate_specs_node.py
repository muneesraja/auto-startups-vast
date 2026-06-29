"""Validate generation_specs against story and scene plans."""
import json

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from schemas.generation import GenerationSpecs
from schemas.plan import AudioPlan, SceneAssetsPlan, StoryPlan
from ._json_util import clean_json_str


async def validate_generation_specs(ctx: Context) -> None:
    specs_raw = ctx.state.get("generation_specs_content")
    story_raw = ctx.state.get("story_plan_content")
    audio_raw = ctx.state.get("audio_plan_content")
    scene_raw = ctx.state.get("scene_assets_content")
    if not all([specs_raw, story_raw]):
        raise ValueError("generation_specs_content and story_plan_content required")

    specs_dict = clean_json_str(specs_raw) if isinstance(specs_raw, str) else specs_raw
    story_dict = clean_json_str(story_raw) if isinstance(story_raw, str) else story_raw
    audio_dict = clean_json_str(audio_raw) if audio_raw else {}
    scene_dict = clean_json_str(scene_raw) if scene_raw else {}

    story = StoryPlan(**story_dict)
    GenerationSpecs(**specs_dict)
    if audio_dict:
        audio = AudioPlan(**audio_dict)
        for shot_id, shot_audio in audio.shots.items():
            present = set()
            for scene in story.scenes:
                for shot in scene.shots:
                    if shot.shot_id == shot_id:
                        present = set(shot.characters_present)
            for d in shot_audio.audio.dialogue:
                cid = d.get("character_id")
                if cid and cid not in present:
                    raise ValueError(
                        f"Audio dialogue speaker {cid} not in shot {shot_id} characters_present"
                    )

    if scene_dict:
        SceneAssetsPlan(**scene_dict)

    style_anchor_scenes = {
        s["scene_id"]
        for s in scene_dict.get("scenes", [])
        if s.get("background_reference_mode", "style_anchor") == "style_anchor"
    }
    shot_to_scene = {}
    for scene in story.scenes:
        for shot in scene.shots:
            shot_to_scene[shot.shot_id] = scene.scene_id

    for shot_id, entry in specs_dict.get("shot_images", {}).items():
        scene_id = shot_to_scene.get(shot_id)
        if scene_id in style_anchor_scenes:
            refs = entry.get("reference_images", [])
            if any("backgrounds." in r for r in refs):
                raise ValueError(
                    f"Shot {shot_id} in style_anchor scene {scene_id} "
                    "must not reference backgrounds.*"
                )

    for scene in story.scenes:
        prev_prompt = None
        for shot in scene.shots:
            img = specs_dict.get("shot_images", {}).get(shot.shot_id, {})
            prompt = img.get("image_prompt", "").strip()
            if prev_prompt and prompt and prompt == prev_prompt:
                raise ValueError(
                    f"Consecutive shots {shot.shot_id} shares identical image_prompt "
                    "with prior shot in scene"
                )
            prev_prompt = prompt

    for _scene, shot in story.iter_shots():
        if shot.shot_id not in specs_dict.get("shot_images", {}):
            raise ValueError(f"Missing shot_images entry for {shot.shot_id}")
        if shot.shot_id not in specs_dict.get("motion", {}):
            raise ValueError(f"Missing motion entry for {shot.shot_id}")

    for cid in story.character_map():
        if cid not in specs_dict.get("character_sheets", {}):
            raise ValueError(f"Missing character_sheets entry for {cid}")

    for scene in scene_dict.get("scenes", []):
        if scene.get("generate_background") and scene["scene_id"] not in specs_dict.get(
            "backgrounds", {}
        ):
            raise ValueError(
                f"Scene {scene['scene_id']} requires background but missing in specs"
            )

    print("✅ [validate_generation_specs] Passed")


validate_generation_specs_node = FunctionNode(
    func=validate_generation_specs, name="validate_generation_specs_node"
)
