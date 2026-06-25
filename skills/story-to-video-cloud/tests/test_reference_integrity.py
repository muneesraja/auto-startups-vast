import sys
import os
import json
import asyncio
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.nodes.reference_integrity_node import run_reference_integrity

class MockContext:
    def __init__(self, state):
        self.state = state

def test_reference_integrity_ff_continuation():
    async def run():
        blueprint = {
            "scenes": [{
                "shots": [{
                    "shot_id": "shot_1",
                    "continuation_from_previous": True,
                    "characters_present": ["char_1"]
                }]
            }]
        }
        ff_prompts = {
            "ff_shots": {
                "shot_1": {
                    "prompt_type": "grok_edit",
                    "prompt": "some prompt",
                    "reference_images": ["some_ref"],
                    "status": "pending"
                }
            }
        }
        ctx = MockContext({
            "blueprint_json_content": json.dumps(blueprint),
            "ff_prompts_content": json.dumps(ff_prompts),
            "lf_prompts_content": json.dumps({"lf_shots": {}})
        })
        
        await run_reference_integrity(ctx)
        
        updated_ff = json.loads(ctx.state["ff_prompts_content"])
        shot = updated_ff["ff_shots"]["shot_1"]
        assert shot["prompt_type"] == "extracted_frame"
        assert shot["prompt"] is None
        assert shot["reference_images"] == []
        assert shot["status"] == "pending_wave_1"

    asyncio.run(run())

def test_reference_integrity_ff_normal_shot():
    async def run():
        blueprint = {
            "scenes": [{
                "shots": [{
                    "shot_id": "shot_1",
                    "continuation_from_previous": False,
                    "characters_present": ["char_1", "char_2"]
                }]
            }]
        }
        # One valid but out-of-order, one invalid reference
        ff_prompts = {
            "ff_shots": {
                "shot_1": {
                    "prompt_type": "grok_edit",
                    "prompt": "some prompt",
                    "reference_images": [
                        "{{character_sheets.char_2.fal_image_url}}",
                        "{{character_sheets.char_3.fal_image_url}}"  # invalid, char_3 not present
                    ],
                    "status": "pending"
                }
            }
        }
        ctx = MockContext({
            "blueprint_json_content": json.dumps(blueprint),
            "ff_prompts_content": json.dumps(ff_prompts),
            "lf_prompts_content": json.dumps({"lf_shots": {}})
        })
        
        await run_reference_integrity(ctx)
        
        updated_ff = json.loads(ctx.state["ff_prompts_content"])
        shot = updated_ff["ff_shots"]["shot_1"]
        assert shot["prompt_type"] == "grok_edit"
        # char_2 remains, char_3 is filtered out, char_1 is auto-injected
        assert "{{character_sheets.char_2.fal_image_url}}" in shot["reference_images"]
        assert "{{character_sheets.char_1.fal_image_url}}" in shot["reference_images"]
        assert "{{character_sheets.char_3.fal_image_url}}" not in shot["reference_images"]
        assert len(shot["reference_images"]) == 2

    asyncio.run(run())

def test_reference_integrity_lf_normal_shot():
    async def run():
        blueprint = {
            "scenes": [{
                "shots": [{
                    "shot_id": "shot_1",
                    "continuation_from_previous": False,
                    "use_ff_as_lf_reference": False,
                    "characters_present": ["char_1"]
                }]
            }]
        }
        lf_prompts = {
            "lf_shots": {
                "shot_1": {
                    "prompt_type": "grok_edit",
                    "prompt": "some prompt",
                    "reference_images": [],
                    "status": "pending"
                }
            }
        }
        ctx = MockContext({
            "blueprint_json_content": json.dumps(blueprint),
            "ff_prompts_content": json.dumps({"ff_shots": {}}),
            "lf_prompts_content": json.dumps(lf_prompts)
        })
        
        await run_reference_integrity(ctx)
        
        updated_lf = json.loads(ctx.state["lf_prompts_content"])
        shot = updated_lf["lf_shots"]["shot_1"]
        assert shot["prompt_type"] == "grok_edit"
        # Should prepend FF image, and inject char_1
        assert shot["reference_images"] == [
            "{{ff_shots.shot_1.fal_image_url}}",
            "{{character_sheets.char_1.fal_image_url}}"
        ]

    asyncio.run(run())

def test_reference_integrity_truncation_with_spatial_priority():
    async def run():
        blueprint = {
            "scenes": [{
                "shots": [{
                    "shot_id": "shot_1",
                    "continuation_from_previous": False,
                    "use_ff_as_lf_reference": False,
                    "characters_present": [
                        "char_1", "char_2", "char_3", "char_4",
                        "char_5", "char_6", "char_7", "char_8"
                    ]
                }]
            }]
        }
        # Spatial map prioritizes char_8 and char_7
        spatial_map = {
            "character_spatial_map": {
                "shot_1": [
                    {"character_id": "char_8", "reference_index": 1},
                    {"character_id": "char_7", "reference_index": 2}
                ]
            }
        }
        
        # FF Prompts starts with no reference images (relying on auto-inject)
        ff_prompts = {
            "ff_shots": {
                "shot_1": {
                    "prompt_type": "grok_edit",
                    "prompt": "some prompt",
                    "reference_images": [],
                    "status": "pending"
                }
            }
        }
        
        # LF Prompts starts with no reference images
        lf_prompts = {
            "lf_shots": {
                "shot_1": {
                    "prompt_type": "grok_edit",
                    "prompt": "some prompt",
                    "reference_images": [],
                    "status": "pending"
                }
            }
        }
        
        ctx = MockContext({
            "blueprint_json_content": json.dumps(blueprint),
            "character_spatial_map_content": json.dumps(spatial_map),
            "ff_prompts_content": json.dumps(ff_prompts),
            "lf_prompts_content": json.dumps(lf_prompts)
        })
        
        await run_reference_integrity(ctx)
        
        updated_ff = json.loads(ctx.state["ff_prompts_content"])
        ff_shot = updated_ff["ff_shots"]["shot_1"]
        
        # FF has limit of 7 references.
        # Sorted characters based on spatial map should be: char_8, char_7, then remaining characters.
        # Therefore, the top 7 are: char_8, char_7, char_1, char_2, char_3, char_4, char_5.
        expected_ff_refs = [
            "{{character_sheets.char_8.fal_image_url}}",
            "{{character_sheets.char_7.fal_image_url}}",
            "{{character_sheets.char_1.fal_image_url}}",
            "{{character_sheets.char_2.fal_image_url}}",
            "{{character_sheets.char_3.fal_image_url}}",
            "{{character_sheets.char_4.fal_image_url}}",
            "{{character_sheets.char_5.fal_image_url}}"
        ]
        assert ff_shot["reference_images"] == expected_ff_refs
        
        updated_lf = json.loads(ctx.state["lf_prompts_content"])
        lf_shot = updated_lf["lf_shots"]["shot_1"]
        
        # LF has limit of 7 references total, where the first is ALWAYS ff_shots.shot_1.fal_image_url.
        # Leaving 6 slots for characters.
        # Placements: char_8, char_7, and then remaining: char_1, char_2, char_3, char_4.
        expected_lf_refs = [
            "{{ff_shots.shot_1.fal_image_url}}",
            "{{character_sheets.char_8.fal_image_url}}",
            "{{character_sheets.char_7.fal_image_url}}",
            "{{character_sheets.char_1.fal_image_url}}",
            "{{character_sheets.char_2.fal_image_url}}",
            "{{character_sheets.char_3.fal_image_url}}",
            "{{character_sheets.char_4.fal_image_url}}"
        ]
        assert lf_shot["reference_images"] == expected_lf_refs

    asyncio.run(run())


def test_prompt_text_validation():
    from scripts.nodes.validate_prompts_node import _check_character_in_prompt
    
    spatial_map = {
        "shot_1": [
            {
                "character_id": "char_1",
                "visual_identifier": "chubby giant panda with cream-white face"
            }
        ]
    }
    
    # 1. Matches name
    ok, reason = _check_character_in_prompt(
        "A cute character named Bamboo is walking.",
        "char_1", "Bamboo", "chubby panda", spatial_map, "shot_1"
    )
    assert ok
    
    # 2. Matches visual identifier noun (panda)
    ok, reason = _check_character_in_prompt(
        "A cute giant panda is walking.",
        "char_1", "Bamboo", "chubby panda", spatial_map, "shot_1"
    )
    assert ok
    
    # 3. Missing character completely
    ok, reason = _check_character_in_prompt(
        "A cute little red squirrel jumps on the branch.",
        "char_1", "Bamboo", "chubby panda", spatial_map, "shot_1"
    )
    assert not ok
    assert "not found in prompt text" in reason


def test_validate_prompts_node_integration(tmp_path, capsys):
    import json
    from scripts.nodes.validate_prompts_node import validate_prompts
    
    blueprint = {
        "characters": [
            {"id": "char_1", "name": "Bamboo", "appearance": "chubby giant panda"}
        ],
        "scenes": [
            {
                "shots": [
                    {
                        "shot_id": "shot_1",
                        "characters_present": ["char_1"],
                        "continuation_from_previous": False
                    }
                ]
            }
        ]
    }
    
    prompts_valid = {
        "ff_shots": {
            "shot_1": {
                "prompt_type": "grok_edit",
                "prompt": "A chubby giant panda on the path.",
                "reference_images": ["{{character_sheets.char_1.fal_image_url}}"]
            }
        },
        "lf_shots": {
            "shot_1": {
                "prompt_type": "grok_edit",
                "prompt": "I've attached the first frame. The chubby giant panda stands up on the path.",
                "reference_images": [
                    "{{ff_shots.shot_1.fal_image_url}}",
                    "{{character_sheets.char_1.fal_image_url}}"
                ]
            }
        },
        "character_sheets": {},
        "motion_prompts": {},
        "character_spatial_map": {
            "shot_1": [
                {
                    "character_id": "char_1",
                    "reference_index": 1,
                    "screen_position": "center",
                    "visual_identifier": "chubby giant panda",
                    "action": "walking"
                }
            ]
        }
    }
    
    out_dir = str(tmp_path)
    with open(os.path.join(out_dir, "director_visual_blueprint.json"), "w") as f:
        json.dump(blueprint, f)
    with open(os.path.join(out_dir, "prompts.json"), "w") as f:
        json.dump(prompts_valid, f)
        
    class MockCtx:
        def __init__(self, state):
            self.state = state
            
    ctx = MockCtx({"output_dir": out_dir})
    
    async def run():
        await validate_prompts(ctx)
    asyncio.run(run())

    captured = capsys.readouterr()
    assert "All cross-checks passed" in captured.out
    assert "validation issue" not in captured.out

    prompts_invalid = {
        "ff_shots": {
            "shot_1": {
                "prompt_type": "grok_edit",
                "prompt": "A beautiful landscape with tall trees.",
                "reference_images": ["{{character_sheets.char_1.fal_image_url}}"]
            }
        },
        "lf_shots": {
            "shot_1": {
                "prompt_type": "grok_edit",
                "prompt": "I've attached the first frame. The chubby giant panda stands up on the path.",
                "reference_images": [
                    "{{character_sheets.char_1.fal_image_url}}"
                ]
            }
        },
        "character_sheets": {},
        "motion_prompts": {},
        "character_spatial_map": {
            "shot_1": [
                {
                    "character_id": "char_1",
                    "reference_index": 1,
                    "screen_position": "center",
                    "visual_identifier": "chubby giant panda",
                    "action": "walking"
                }
            ]
        }
    }
    
    with open(os.path.join(out_dir, "prompts.json"), "w") as f:
        json.dump(prompts_invalid, f)
        
    async def run2():
        await validate_prompts(ctx)
    asyncio.run(run2())

    captured2 = capsys.readouterr()
    assert "3 validation issue(s):" in captured2.out
    assert "[Prompt-Text-cov] shot_1: Character 'Bamboo' (char_1) not found in prompt text." in captured2.out
    assert "[LF-ref1] shot_1: first reference image must point to ff_shots.shot_1.fal_image_url" in captured2.out
    assert "[LF-cov] shot_1: characters_present has ['char_1'] but reference_images only cover []." in captured2.out


def test_character_ref_validator(tmp_path):
    from scripts.nodes.character_ref_validator_node import run_character_ref_validator
    
    blueprint = {
        "characters": [
            {"id": "char_1", "name": "Dolphin", "appearance": "A friendly gray dolphin"}
        ],
        "scenes": [{
            "shots": [
                {
                    "shot_id": "scene_01_shot_01",
                    "continuation_from_previous": False,
                    "characters_present": []
                }
            ]
        }]
    }

    prompts = {
        "ff_shots": {
            "scene_01_shot_01": {
                "prompt_type": "grok_edit",
                "prompt": "A gray dolphin jumping out of the water.",
                "reference_images": [],
                "status": "pending"
            }
        },
        "lf_shots": {}
    }

    out_dir = str(tmp_path)
    blueprint_path = os.path.join(out_dir, "director_visual_blueprint.json")
    prompts_path = os.path.join(out_dir, "prompts.json")

    with open(blueprint_path, "w", encoding="utf-8") as f:
        json.dump(blueprint, f)
    with open(prompts_path, "w", encoding="utf-8") as f:
        json.dump(prompts, f)

    class MockCtx:
        def __init__(self, state):
            self.state = state

    ctx = MockCtx({"output_dir": out_dir})

    # Mock llm_validate_presence to return True
    import scripts.nodes.character_ref_validator_node as validator_module
    original_llm = validator_module.llm_validate_presence
    
    async def mock_presence(prompt_text, char_name, char_appearance):
        return True
    
    validator_module.llm_validate_presence = mock_presence

    try:
        async def run():
            await run_character_ref_validator(ctx)
        asyncio.run(run())

        with open(blueprint_path, "r", encoding="utf-8") as f:
            bp_updated = json.load(f)
        with open(prompts_path, "r", encoding="utf-8") as f:
            pr_updated = json.load(f)

        # The dolphin should be automatically added to characters_present and reference_images
        shot = bp_updated["scenes"][0]["shots"][0]
        assert "char_1" in shot["characters_present"]
        
        ff_shot = pr_updated["ff_shots"]["scene_01_shot_01"]
        assert "{{character_sheets.char_1.fal_image_url}}" in ff_shot["reference_images"]
    finally:
        validator_module.llm_validate_presence = original_llm



