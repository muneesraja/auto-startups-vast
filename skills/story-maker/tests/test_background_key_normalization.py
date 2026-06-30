import asyncio
import json
import unittest

from scripts.nodes.reference_integrity_node import reference_integrity


class _Ctx:
    def __init__(self, state):
        self.state = state


class TestBackgroundKeyNormalization(unittest.TestCase):
    def test_maps_custom_bg_asset_id_to_scene_id(self):
        specs = {
            "backgrounds": {
                "scene_01": {
                    "scene_id": "scene_01",
                    "fal_image_url": "http://example/bg.png",
                }
            },
            "shot_images": {
                "scene_01_shot_01": {
                    "shot_id": "scene_01_shot_01",
                    "generation_mode": "grok_edit",
                    "reference_strategy": "char_sheets_and_background",
                    "reference_slots": [
                        {
                            "role": "scene_background",
                            "asset_id": "bg_scene_01_plate",
                            "priority": 0,
                        },
                        {"role": "character_sheet", "asset_id": "char_01", "priority": 1},
                    ],
                    "reference_images": [],
                }
            },
        }
        story = {
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "shots": [
                        {
                            "shot_id": "scene_01_shot_01",
                            "characters_present": ["char_01"],
                        }
                    ],
                }
            ]
        }
        scene_assets = {
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "background_reference_mode": "full_plate",
                }
            ]
        }
        ctx = _Ctx(
            {
                "story_plan_content": json.dumps(story),
                "scene_assets_content": json.dumps(scene_assets),
                "generation_specs_content": json.dumps(specs),
            }
        )
        asyncio.run(reference_integrity(ctx))
        entry = json.loads(ctx.state["generation_specs_content"])["shot_images"][
            "scene_01_shot_01"
        ]
        self.assertIn("{{backgrounds.scene_01.fal_image_url}}", entry["reference_images"])


if __name__ == "__main__":
    unittest.main()
