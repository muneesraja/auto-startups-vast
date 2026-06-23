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
                "prompt_type": "ideogram_json",
                "prompt": {"text": "A panda sheet"},
                "status": "pending",
                "generated_by": "step_3_character_prompter"
            }
        },
        "ff_shots": {
            "scene_01_shot_01": {
                "prompt_type": "ideogram_json",
                "prompt": {"text": "A panda walking"},
                "status": "pending",
                "generated_by": "step_4_ff_prompter"
            }
        },
        "consistency_patches": {},
        "lf_shots": {},
        "motion_prompts": {}
    }
    
    pf = PromptsFile(**prompts_data)
    assert pf.meta.blueprint_version == 1
    assert pf.character_sheets["char_01"].prompt_type == "ideogram_json"
    assert pf.ff_shots["scene_01_shot_01"].generated_by == "step_4_ff_prompter"
