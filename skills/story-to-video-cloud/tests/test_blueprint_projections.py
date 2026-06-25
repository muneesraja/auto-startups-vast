import json
import pytest
from scripts.blueprint_projections import (
    project_for_character_prompter,
    project_for_spatial_mapper,
    project_for_ff_prompter,
    project_for_lf_delta_planner,
    project_for_lf_prompter,
    project_for_motion_prompter
)

@pytest.fixture
def sample_blueprint():
    return {
        "meta": {
            "story_title": "The Panda and the Butterfly",
            "style": "children's book watercolor illustration",
            "aesthetic": "warm, gentle, narrative",
            "total_duration_seconds": 8,
            "total_scenes": 1,
            "total_shots": 1,
            "created_at": "2026-06-17T10:00:00Z",
            "last_updated_at": "2026-06-17T12:00:00Z",
            "version": 1
        },
        "characters": [
            {
                "id": "char_01",
                "name": "Pippin the Panda",
                "appearance": "Chubby baby panda with round ears",
                "character_sheet_status": "pending",
                "character_sheet_path": "/some/path"
            }
        ],
        "scenes": [
            {
                "scene_id": "scene_01",
                "scene_title": "The Forest Path",
                "scene_duration_seconds": 8,
                "environment": "Dense bamboo forest",
                "time_of_day": "late morning",
                "lighting": "warm dappled sunlight",
                "generate_background": True,
                "background_prompt": "Beautiful bamboo forest background",
                "shots": [
                    {
                        "shot_id": "scene_01_shot_01",
                        "shot_index": 0,
                        "duration_seconds": 8,
                        "continuation_from_previous": False,
                        "use_ff_as_lf_reference": True,
                        "wave": 1,
                        "characters_present": ["char_01"],
                        "director_notes": "Opening establishing shot",
                        "ff": {
                            "description": "Medium-wide shot of Pippin",
                            "camera_framing": "medium-wide, eye-level",
                            "character_expressions": {"char_01": "curious"},
                            "generation_status": "pending",
                            "consistent_image_path": "/some/path/consistent.png"
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
                            "generation_status": "pending",
                            "generated_image_path": "/some/path/gen.png"
                        },
                        "motion": {
                            "generation_status": "pending",
                            "video_path": "/some/video.mp4"
                        }
                    }
                ]
            }
        ]
    }

def test_character_prompter_projection(sample_blueprint):
    proj_str = project_for_character_prompter(sample_blueprint)
    proj = json.loads(proj_str)
    
    assert "meta" in proj
    assert proj["meta"]["style"] == "children's book watercolor illustration"
    assert proj["meta"]["aesthetic"] == "warm, gentle, narrative"
    assert "characters" in proj
    assert len(proj["characters"]) == 1
    assert proj["characters"][0]["id"] == "char_01"
    assert proj["characters"][0]["name"] == "Pippin the Panda"
    # Unneeded character sheet fields should be excluded
    assert "character_sheet_path" not in proj["characters"][0]
    assert "scenes" not in proj

def test_spatial_mapper_projection(sample_blueprint):
    proj_str = project_for_spatial_mapper(sample_blueprint)
    proj = json.loads(proj_str)
    
    assert "scenes" in proj
    assert len(proj["scenes"]) == 1
    scene = proj["scenes"][0]
    assert scene["scene_id"] == "scene_01"
    assert len(scene["shots"]) == 1
    shot = scene["shots"][0]
    assert shot["shot_id"] == "scene_01_shot_01"
    assert shot["continuation_from_previous"] is False
    assert shot["characters_present"] == ["char_01"]
    assert shot["ff"]["description"] == "Medium-wide shot of Pippin"
    assert shot["lf"]["description"] == "Same path, Panda walked closer"
    # Exclude other fields
    assert "environment" not in scene
    assert "camera_framing" not in shot["ff"]

def test_ff_prompter_projection(sample_blueprint):
    proj_str = project_for_ff_prompter(sample_blueprint)
    proj = json.loads(proj_str)
    
    assert "characters" in proj
    assert "scenes" in proj
    scene = proj["scenes"][0]
    assert scene["environment"] == "Dense bamboo forest"
    assert scene["time_of_day"] == "late morning"
    assert scene["lighting"] == "warm dappled sunlight"
    shot = scene["shots"][0]
    assert shot["shot_id"] == "scene_01_shot_01"
    assert shot["ff"]["camera_framing"] == "medium-wide, eye-level"
    assert shot["ff"]["character_expressions"] == {"char_01": "curious"}
    # Unneeded fields excluded
    assert "consistent_image_path" not in shot["ff"]
    assert "lf" not in shot

def test_lf_delta_planner_projection(sample_blueprint):
    proj_str = project_for_lf_delta_planner(sample_blueprint)
    proj = json.loads(proj_str)
    
    assert "scenes" in proj
    shot = proj["scenes"][0]["shots"][0]
    assert shot["shot_id"] == "scene_01_shot_01"
    assert shot["duration_seconds"] == 8
    assert shot["ff"]["description"] == "Medium-wide shot of Pippin"
    assert shot["lf"]["description"] == "Same path, Panda walked closer"
    # Delta from FF excluded from here
    assert "delta_from_ff" not in shot["lf"]

def test_lf_prompter_projection(sample_blueprint):
    proj_str = project_for_lf_prompter(sample_blueprint)
    proj = json.loads(proj_str)
    
    assert "characters" in proj
    assert "scenes" in proj
    scene = proj["scenes"][0]
    assert scene["environment"] == "Dense bamboo forest"
    shot = scene["shots"][0]
    assert shot["shot_id"] == "scene_01_shot_01"
    assert shot["use_ff_as_lf_reference"] is True
    assert shot["lf"]["camera_framing"] == "medium, eye-level"
    assert shot["lf"]["character_expressions"] == {"char_01": "surprised"}
    assert shot["lf"]["delta_from_ff"]["camera_change"] == "static camera"
    # Unneeded fields excluded
    assert "generated_image_path" not in shot["lf"]
    assert "ff" not in shot

def test_motion_prompter_projection(sample_blueprint):
    proj_str = project_for_motion_prompter(sample_blueprint)
    proj = json.loads(proj_str)
    
    assert proj["meta"]["style"] == "children's book watercolor illustration"
    assert proj["characters"][0]["name"] == "Pippin the Panda"
    shot = proj["scenes"][0]["shots"][0]
    assert shot["shot_id"] == "scene_01_shot_01"
    assert shot["duration_seconds"] == 8
    assert shot["director_notes"] == "Opening establishing shot"
    assert shot["ff"]["description"] == "Medium-wide shot of Pippin"
    assert shot["lf"]["description"] == "Same path, Panda walked closer"
    # Unneeded video_path and status should be excluded
    assert "video_path" not in shot
