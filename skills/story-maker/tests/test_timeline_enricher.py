import unittest

from scripts.nodes.timeline_enricher_node import enrich_story_timeline


def _story_with_durations(durations: list[int]) -> dict:
    shots = []
    for i, dur in enumerate(durations, start=1):
        shots.append(
            {
                "shot_id": f"scene_01_shot_{i:02d}",
                "scene_id": "scene_01",
                "duration_seconds": dur,
                "characters_present": ["char_01"],
                "description": f"beat {i}",
            }
        )
    return {"scenes": [{"scene_id": "scene_01", "shots": shots}]}


class TestTimelineEnricher(unittest.TestCase):
    def test_offsets_from_durations(self):
        story = enrich_story_timeline(_story_with_durations([6, 6, 8]))
        shots = story["scenes"][0]["shots"]
        self.assertEqual(shots[0]["scene_time_offset_seconds"], 0)
        self.assertEqual(shots[1]["scene_time_offset_seconds"], 6)
        self.assertEqual(shots[2]["scene_time_offset_seconds"], 12)
        self.assertFalse(shots[0]["continuity_from_previous"])
        self.assertTrue(shots[1]["continuity_from_previous"])
        self.assertTrue(shots[2]["continuity_from_previous"])
        self.assertEqual(story["meta"]["total_duration_seconds"], 20)
        self.assertEqual(story["meta"]["total_shots"], 3)


if __name__ == "__main__":
    unittest.main()
