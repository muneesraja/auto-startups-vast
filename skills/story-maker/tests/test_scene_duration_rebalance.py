import unittest
from unittest.mock import AsyncMock, patch

from scripts.nodes.duration_reconcile import reconcile_scene_durations


class TestSceneDurationRebalance(unittest.TestCase):
    def test_trims_scene_over_budget(self):
        story = {
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "shots": [
                        {"shot_id": "scene_01_shot_01", "duration_seconds": 15},
                        {"shot_id": "scene_01_shot_02", "duration_seconds": 15},
                    ],
                }
            ],
            "meta": {},
        }
        outline = {
            "acts": [
                {
                    "scenes": [
                        {"scene_id": "scene_01", "duration_budget_seconds": 20}
                    ]
                }
            ]
        }
        result = reconcile_scene_durations(story, outline, tolerance_percent=15)
        total = sum(s["duration_seconds"] for s in result["scenes"][0]["shots"])
        self.assertLessEqual(total, 23)

    def test_applies_reels_duration_bounds(self):
        story = {
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "shots": [
                        {"shot_id": "scene_01_shot_01", "duration_seconds": 8},
                        {"shot_id": "scene_01_shot_02", "duration_seconds": 6},
                        {"shot_id": "scene_01_shot_03", "duration_seconds": 5},
                    ],
                }
            ],
            "meta": {},
        }
        outline = {
            "acts": [
                {
                    "scenes": [
                        {"scene_id": "scene_01", "duration_budget_seconds": 9}
                    ]
                }
            ]
        }

        result = reconcile_scene_durations(
            story,
            outline,
            tolerance_percent=15,
            min_shot_seconds=6,
            max_shot_seconds=10,
        )
        durations = [s["duration_seconds"] for s in result["scenes"][0]["shots"]]
        self.assertTrue(all(6 <= d <= 10 for d in durations), durations)


if __name__ == "__main__":
    unittest.main()
