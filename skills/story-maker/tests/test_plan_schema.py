import unittest

from schemas.plan import StoryPlan, StoryPlanDraft


def _minimal_story():
    return {
        "meta": {
            "story_title": "Test Story",
            "style": "Pixar-style animated movie scene",
            "aesthetic": "warm adventure",
            "color_palette": "greens",
            "total_duration_seconds": 8,
            "total_scenes": 1,
            "total_shots": 1,
        },
        "characters": [
            {
                "id": "char_01",
                "name": "Miko",
                "appearance": "brown monkey with yellow cap",
                "voice_profile": "playful chirps",
            }
        ],
        "scenes": [
            {
                "scene_id": "scene_01",
                "title": "Forest",
                "environment": "tropical forest",
                "time_of_day": "morning",
                "lighting": "warm sunlight",
                "shots": [
                    {
                        "shot_id": "scene_01_shot_01",
                        "scene_id": "scene_01",
                        "duration_seconds": 8,
                        "characters_present": ["char_01"],
                        "director_notes": "opening",
                        "description": "Monkey stands on branch looking outward.",
                    }
                ],
            }
        ],
    }


class TestStoryPlanSchema(unittest.TestCase):
    def test_story_plan_parses(self):
        plan = StoryPlan(**_minimal_story())
        self.assertEqual(plan.meta.total_shots, 1)
        self.assertEqual(len(plan.characters), 1)

    def test_rejects_unknown_character(self):
        data = _minimal_story()
        data["scenes"][0]["shots"][0]["characters_present"] = ["char_99"]
        with self.assertRaises(ValueError):
            StoryPlan(**data)

    def test_draft_fills_meta(self):
        data = _minimal_story()
        data["meta"] = {
            "story_title": "T",
            "style": "Pixar-style animated movie scene",
            "aesthetic": "warm",
        }
        plan = StoryPlanDraft(**data).to_plan()
        self.assertEqual(plan.meta.total_shots, 1)


if __name__ == "__main__":
    unittest.main()
