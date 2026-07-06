import unittest

from scripts.nodes.story_timeline import enrich_story_timeline, enrich_story_timeline_with_target


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

    def test_preserves_planning_meta(self):
        story = _story_with_durations([8])
        story["_meta"] = {
            "narrative_model": "openai/gpt-5.4-mini",
            "story_plan_model": "openai/gpt-5.4-mini",
        }
        enriched = enrich_story_timeline_with_target(story, target_duration_seconds=300)
        self.assertEqual(enriched["_meta"]["narrative_model"], "openai/gpt-5.4-mini")
        self.assertEqual(enriched["_meta"]["story_plan_model"], "openai/gpt-5.4-mini")
        self.assertEqual(enriched["meta"]["target_duration_seconds"], 300)


if __name__ == "__main__":
    unittest.main()
