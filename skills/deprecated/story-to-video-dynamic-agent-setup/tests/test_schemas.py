import sys
import os
import pytest
from pydantic import ValidationError
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schemas.blueprint import Blueprint
from schemas.prompts import PromptsFile

def test_blueprint_schema_validation():
    # Valid minimal blueprint dict
    blueprint_data = {
        "meta": {
            "story_title": "The Panda and the Butterfly",
            "style": "children's book watercolor illustration",
            "aesthetic": "warm, gentle, narrative",
            "total_duration_seconds": 7,
            "total_scenes": 1,
            "total_shots": 2,
            "created_at": "2026-06-17T10:00:00Z",
            "last_updated_at": "2026-06-17T12:00:00Z",
            "version": 1
        },
        "characters": [
            {
                "id": "char_01",
                "name": "Pippin the Panda",
                "appearance": "Chubby baby panda with round ears",
                "character_sheet_status": "pending"
            }
        ],
        "scenes": [
            {
                "scene_id": "scene_01",
                "scene_title": "The Forest Path",
                "scene_duration_seconds": 7,
                "environment": "Dense bamboo forest",
                "time_of_day": "late morning",
                "lighting": "warm dappled sunlight",
                "shots": [
                    {
                        "shot_id": "scene_01_shot_01",
                        "shot_index": 0,
                        "duration_seconds": 4,
                        "continuation_from_previous": False,
                        "wave": 1,
                        "characters_present": ["char_01"],
                        "director_notes": "Opening establishing shot",
                        "ff": {
                            "description": "Medium-wide shot of Pippin",
                            "camera_framing": "medium-wide, eye-level",
                            "character_expressions": {"char_01": "curious"},
                            "generation_status": "pending"
                        },
                        "lf": {
                            "description": "Same path, Panda walked closer",
                            "camera_framing": "medium, eye-level",
                            "character_expressions": {"char_01": "surprised"},
                            "delta_from_ff": {
                                "camera_change": "static camera",
                                "subject_changes": "panda is closer",
                                "environment_changes": "sunlight shifted",
                                "particle_effects": "dust motes"
                            },
                            "generation_status": "pending"
                        },
                        "motion": {
                            "generation_status": "pending"
                        }
                    },
                    {
                        "shot_id": "scene_01_shot_02",
                        "shot_index": 1,
                        "duration_seconds": 3,
                        "continuation_from_previous": True,
                        "wave": 2,
                        "characters_present": ["char_01"],
                        "director_notes": "Continuation shot",
                        "ff": {
                            "description": "INHERITED from scene_01_shot_01 last frame",
                            "camera_framing": "medium, eye-level",
                            "source": "extracted_from_previous_video",
                            "generation_status": "pending_wave_1"
                        },
                        "lf": {
                            "description": "Panda cups butterfly",
                            "camera_framing": "medium close-up",
                            "delta_from_ff": {
                                "camera_change": "subtle zoom",
                                "subject_changes": "arms raised",
                                "environment_changes": "blurred background",
                                "particle_effects": "shimmer"
                            },
                            "generation_status": "pending"
                        },
                        "motion": {
                            "generation_status": "pending"
                        }
                    }
                ]
            }
        ]
    }

    # Verify instantiation succeeds
    bp = Blueprint(**blueprint_data)
    assert bp.meta.story_title == "The Panda and the Butterfly"
    assert bp.scenes[0].shots[0].duration_seconds == 4
    assert bp.scenes[0].shots[1].continuation_from_previous is True

    # Verify duration constraint (must be between 2 and 5)
    blueprint_data["scenes"][0]["shots"][0]["duration_seconds"] = 6
    with pytest.raises(ValidationError):
        Blueprint(**blueprint_data)

def test_prompts_schema_validation():
    prompts_data = {
        "meta": {
            "blueprint_version": 1,
            "last_updated_by": "step_7_motion_prompter",
            "last_updated_at": "2026-06-17T12:00:00Z"
        },
        "character_sheets": {
            "char_01": {
                "prompt_type": "flux_klein_t2i",
                "prompt": "A character reference sheet for a chubby baby panda with round ears. Front view, three-quarter view, side view, back view, face portrait, and gear detail on a clean white background with flat studio lighting.",
                "status": "pending",
                "generated_by": "step_3_character_prompter"
            }
        },
        "ff_shots": {
            "scene_01_shot_01": {
                "prompt_type": "flux_klein_t2i",
                "prompt": "Use image 1 as the character reference. A medium-wide eye-level shot of Pippin the chubby baby panda on a forest path in late morning dappled sunlight. Pippin is curious, head tilted slightly forward, ears perked.",
                "reference_images": [
                    "{{character_sheets.char_01.output_path}}"
                ],
                "status": "pending",
                "generated_by": "step_4_ff_prompter"
            }
        },
        "lf_shots": {
            "scene_01_shot_01": {
                "prompt_type": "flux_klein_t2i",
                "prompt": "Use image 1 as the character reference and image 2 for the established scene context. Pippin the panda is closer to camera on the same forest path, eyes wide with surprise, late-morning sunlight slightly shifted, dust motes drifting. End state: panda is in closer medium shot, surprised expression.",
                "reference_images": [
                    "{{character_sheets.char_01.output_path}}",
                    "{{ff_shots.scene_01_shot_01.output_path}}"
                ],
                "status": "pending",
                "generated_by": "step_6_lf_prompter"
            }
        },
        "lf_delta_plan": {
            "scene_01_shot_01": "pose-change"
        },
        "character_spatial_map": {
            "scene_01_shot_01": [
                {
                    "character_id": "char_01",
                    "reference_index": 1,
                    "screen_position": "center midground",
                    "visual_identifier": "chubby baby panda with round ears",
                    "action": "curious head tilt, walking"
                }
            ]
        },
        "motion_prompts": {
            "scene_01_shot_01": {
                "prompt": "Pippin walks forward toward the camera, his ears perking up. Dust motes drift through the late-morning sunlight. The camera holds steady.",
                "duration_seconds": 4,
                "ff_image": "{{ff_shots.scene_01_shot_01.output_path}}",
                "lf_image": "{{lf_shots.scene_01_shot_01.output_path}}",
                "status": "pending",
                "generated_by": "step_7_motion_prompter"
            }
        }
    }

    pf = PromptsFile(**prompts_data)
    assert pf.meta.blueprint_version == 1
    assert pf.character_sheets["char_01"].prompt_type == "flux_klein_t2i"
    assert isinstance(pf.character_sheets["char_01"].prompt, str)
    assert pf.ff_shots["scene_01_shot_01"].generated_by == "step_4_ff_prompter"
    assert len(pf.ff_shots["scene_01_shot_01"].reference_images) == 1
    assert pf.lf_shots["scene_01_shot_01"].prompt_type == "flux_klein_t2i"
    assert len(pf.lf_shots["scene_01_shot_01"].reference_images) == 2
    assert pf.motion_prompts["scene_01_shot_01"].duration_seconds == 4

def test_prompts_schema_lf_continuation():
    """Wave-2 continuation shot: FF is extracted from previous video (no generation)."""
    prompts_data = {
        "meta": {
            "blueprint_version": 1,
            "last_updated_by": "step_4_ff_prompter",
            "last_updated_at": "2026-06-17T12:00:00Z"
        },
        "ff_shots": {
            "scene_01_shot_02": {
                "prompt_type": "extracted_frame",
                "prompt": None,
                "reference_images": [],
                "status": "pending_wave_1",
                "generated_by": "system"
            }
        }
    }
    pf = PromptsFile(**prompts_data)
    assert pf.ff_shots["scene_01_shot_02"].prompt_type == "extracted_frame"
    assert pf.ff_shots["scene_01_shot_02"].prompt is None
