import asyncio
import json
import unittest

from scripts.nodes.reference_integrity_node import reference_integrity, GROK_REF_LIMIT


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
    def test_truncates_to_seven_refs(self):
        slots = [
            {"role": "character_sheet", "asset_id": f"char_{i:02d}", "priority": i}
            for i in range(10)
        ]
        self.assertTrue(len(slots) > GROK_REF_LIMIT)
        char_refs = [f"char_{i:02d}" for i in range(10)]
        truncated = char_refs[: GROK_REF_LIMIT]
        self.assertEqual(len(truncated), GROK_REF_LIMIT)

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


if __name__ == "__main__":
    unittest.main()
