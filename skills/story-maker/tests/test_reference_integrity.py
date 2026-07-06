import asyncio
import json
import unittest
from unittest.mock import patch

import config
from scripts.nodes.reference_integrity_node import (
    _truncate_refs,
    reference_integrity,
)


class _Ctx:
    def __init__(self, state):
        self.state = state


def _minimal_story():
    return {
        "scenes": [
            {
                "scene_id": "scene_01",
                "shots": [
                    {
                        "shot_id": "scene_01_shot_01",
                        "scene_id": "scene_01",
                        "characters_present": ["char_01"],
                    }
                ],
            }
        ]
    }


def _scene_assets_style_anchor():
    return {
        "scenes": [
            {
                "scene_id": "scene_01",
                "generate_background": True,
                "background_reference_mode": "style_anchor",
            }
        ]
    }


class TestReferenceIntegrityLogic(unittest.TestCase):
    def test_truncates_to_provider_limit(self):
        limit = config.FAL_GROK_REF_LIMIT
        slots = [
            {"role": "character_sheet", "asset_id": f"char_{i:02d}", "priority": i}
            for i in range(10)
        ]
        refs = [f"{{{{character_sheets.char_{i:02d}.fal_image_url}}}}" for i in range(10)]
        kept, dropped = _truncate_refs(refs, slots, limit=limit, reserve_bg=False)
        self.assertEqual(len(kept), limit)
        self.assertEqual(len(dropped), 10 - limit)

    def test_truncation_reserves_background_slot(self):
        limit = 3
        slots = [
            {"role": "character_sheet", "asset_id": "char_01", "priority": 0},
            {"role": "character_sheet", "asset_id": "char_02", "priority": 1},
            {"role": "scene_background", "asset_id": "scene_01", "priority": 2},
        ]
        refs = [
            "{{character_sheets.char_01.fal_image_url}}",
            "{{character_sheets.char_02.fal_image_url}}",
            "{{character_sheets.char_03.fal_image_url}}",
            "{{backgrounds.scene_01.fal_image_url}}",
        ]
        kept, dropped = _truncate_refs(refs, slots, limit=limit, reserve_bg=True)
        self.assertEqual(len(kept), 3)
        self.assertIn("{{backgrounds.scene_01.fal_image_url}}", kept)
        self.assertEqual(len(dropped), 1)

    def test_strips_background_for_style_anchor(self):
        specs = {
            "shot_images": {
                "scene_01_shot_01": {
                    "shot_id": "scene_01_shot_01",
                    "generation_mode": "grok_edit",
                    "reference_strategy": "char_sheets_and_background",
                    "reference_slots": [
                        {"role": "character_sheet", "asset_id": "char_01", "priority": 0},
                        {"role": "scene_background", "asset_id": "scene_01", "priority": 1},
                    ],
                    "reference_images": [],
                }
            }
        }
        ctx = _Ctx(
            {
                "story_plan_content": json.dumps(_minimal_story()),
                "scene_assets_content": json.dumps(_scene_assets_style_anchor()),
                "generation_specs_content": json.dumps(specs),
            }
        )
        asyncio.run(reference_integrity(ctx))
        entry = json.loads(ctx.state["generation_specs_content"])["shot_images"][
            "scene_01_shot_01"
        ]
        self.assertEqual(entry["reference_strategy"], "char_sheets_only")
        self.assertTrue(
            all("backgrounds." not in r for r in entry["reference_images"])
        )
        self.assertIn("{{character_sheets.char_01.fal_image_url}}", entry["reference_images"])

    def test_multi_character_keeps_all_when_under_limit(self):
        story = {
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "shots": [
                        {
                            "shot_id": "scene_01_shot_01",
                            "characters_present": ["char_01", "char_02", "char_03"],
                        }
                    ],
                }
            ]
        }
        specs = {
            "shot_images": {
                "scene_01_shot_01": {
                    "generation_mode": "grok_edit",
                    "reference_strategy": "char_sheets_only",
                    "reference_slots": [
                        {"role": "character_sheet", "asset_id": "char_01", "priority": 0},
                        {"role": "character_sheet", "asset_id": "char_02", "priority": 1},
                        {"role": "character_sheet", "asset_id": "char_03", "priority": 2},
                    ],
                    "reference_images": [],
                }
            }
        }
        ctx = _Ctx(
            {
                "story_plan_content": json.dumps(story),
                "scene_assets_content": json.dumps(_scene_assets_style_anchor()),
                "generation_specs_content": json.dumps(specs),
            }
        )
        with patch.object(config, "get_image_ref_limit", return_value=13):
            asyncio.run(reference_integrity(ctx))
        entry = json.loads(ctx.state["generation_specs_content"])["shot_images"][
            "scene_01_shot_01"
        ]
        self.assertEqual(len(entry["reference_images"]), 3)


if __name__ == "__main__":
    unittest.main()
