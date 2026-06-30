import unittest
from unittest.mock import patch

from scripts.nodes.story_timeline import enrich_story_timeline
from tools.workflow_builder import snap_duration_seconds


class TestTimelineDurationSnap(unittest.TestCase):
    def test_enricher_snaps_durations(self):
        story = {
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "shots": [
                        {
                            "shot_id": "scene_01_shot_01",
                            "scene_id": "scene_01",
                            "duration_seconds": 7,
                        }
                    ],
                }
            ]
        }
        enriched = enrich_story_timeline(story)
        snapped = enriched["scenes"][0]["shots"][0]["duration_seconds"]
        self.assertEqual(snapped, snap_duration_seconds(7))

    def test_offsets_use_snapped_durations(self):
        story = {
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "shots": [
                        {"shot_id": "scene_01_shot_01", "duration_seconds": 4},
                        {"shot_id": "scene_01_shot_02", "duration_seconds": 7},
                    ],
                }
            ]
        }
        enriched = enrich_story_timeline(story)
        shots = enriched["scenes"][0]["shots"]
        self.assertEqual(shots[1]["scene_time_offset_seconds"], shots[0]["duration_seconds"])


if __name__ == "__main__":
    unittest.main()
