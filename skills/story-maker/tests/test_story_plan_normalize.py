import unittest

from scripts.nodes.story_plan_normalize import normalize_story_plan
from scripts.nodes.story_timeline import enrich_story_timeline_with_target


class TestStoryPlanNormalize(unittest.TestCase):
    def test_renames_shot_ids_and_fills_scene_fields(self):
        story = {
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "title": "Beach morning",
                    "shots": [
                        {
                            "shot_id": "shot_001",
                            "scene_id": "scene_01",
                            "duration_seconds": 6,
                            "environment_state": "Morning sun on calm beach",
                        },
                        {
                            "shot_id": "shot_002",
                            "scene_id": "scene_01",
                            "duration_seconds": 8,
                            "environment_state": "Ripples spreading",
                        },
                    ],
                }
            ]
        }
        normalized = normalize_story_plan(story)
        scene = normalized["scenes"][0]
        self.assertEqual(scene["shots"][0]["shot_id"], "scene_01_shot_01")
        self.assertEqual(scene["shots"][1]["shot_id"], "scene_01_shot_02")
        self.assertIn("environment", scene)
        self.assertIn("time_of_day", scene)
        self.assertIn("lighting", scene)

    def test_enricher_applies_normalize_first(self):
        story = {
            "scenes": [
                {
                    "scene_id": "scene_02",
                    "title": "Night jungle",
                    "shots": [
                        {
                            "shot_id": "bad_id",
                            "scene_id": "scene_02",
                            "duration_seconds": 5,
                            "environment_state": "Neon jungle at night",
                        }
                    ],
                }
            ]
        }
        enriched = enrich_story_timeline_with_target(story, 60)
        shot = enriched["scenes"][0]["shots"][0]
        self.assertEqual(shot["shot_id"], "scene_02_shot_01")


if __name__ == "__main__":
    unittest.main()
