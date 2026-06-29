import unittest

from schemas.generation import GenerationSpecs


class TestGenerationSpecs(unittest.TestCase):
    def test_valid_specs(self):
        specs = GenerationSpecs(
            character_sheets={
                "char_01": {
                    "character_id": "char_01",
                    "sheet_prompt": "turnaround sheet...",
                }
            },
            shot_images={
                "scene_01_shot_01": {
                    "shot_id": "scene_01_shot_01",
                    "generation_mode": "grok_edit",
                    "reference_strategy": "char_sheets_only",
                    "reference_slots": [
                        {"role": "character_sheet", "asset_id": "char_01", "priority": 0}
                    ],
                    "image_prompt": "Monkey on branch...",
                }
            },
            motion={
                "scene_01_shot_01": {
                    "shot_id": "scene_01_shot_01",
                    "motion_prompt": "The monkey swings...",
                    "duration_seconds": 8,
                }
            },
        )
        self.assertIn("char_01", specs.character_sheets)

    def test_key_mismatch_raises(self):
        with self.assertRaises(ValueError):
            GenerationSpecs(
                shot_images={
                    "scene_01_shot_01": {
                        "shot_id": "wrong_id",
                        "generation_mode": "grok_edit",
                        "reference_strategy": "char_sheets_only",
                        "image_prompt": "test",
                    }
                }
            )


if __name__ == "__main__":
    unittest.main()
