import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.nodes.validate_prompts_node import _validate_motion_prompts

def test_validate_motion_prompts_valid():
    blueprint = {
        "scenes": [
            {
                "shots": [
                    {
                        "shot_id": "scene_01_shot_01",
                        "characters_present": ["char_01", "char_02"]
                    }
                ]
            }
        ]
    }
    
    motion_prompts = {
        "scene_01_shot_01": {
            "prompt": "The baby giggles and the monkey swings.",
            "duration_seconds": 8,
            "character_sounds": {
                "char_01": ["hu", "ahhh"],
                "char_02": ["huhu"]
            }
        }
    }
    
    errors = []
    _validate_motion_prompts(motion_prompts, blueprint, errors)
    assert len(errors) == 0

def test_validate_motion_prompts_invalid_character():
    blueprint = {
        "scenes": [
            {
                "shots": [
                    {
                        "shot_id": "scene_01_shot_01",
                        "characters_present": ["char_01"]
                    }
                ]
            }
        ]
    }
    
    motion_prompts = {
        "scene_01_shot_01": {
            "prompt": "The baby giggles.",
            "duration_seconds": 8,
            "character_sounds": {
                "char_01": ["hu", "ahhh"],
                "char_02": ["huhu"]  # char_02 is not present in shot_01
            }
        }
    }
    
    errors = []
    _validate_motion_prompts(motion_prompts, blueprint, errors)
    assert len(errors) == 1
    assert "character 'char_02' has planned sounds but is not in characters_present" in errors[0]
