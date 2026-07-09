import os
import sys
import unittest

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

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
                "staging": "Forest left-to-right: branch cluster, fallen log, stream edge.",
                "blocking": [
                    {
                        "character_id": "char_01",
                        "position": "upper branch frame-left",
                        "facing": "screen-right toward the clearing",
                    }
                ],
                "shots": [
                    {
                        "shot_id": "scene_01_shot_01",
                        "scene_id": "scene_01",
                        "duration_seconds": 8,
                        "characters_present": ["char_01"],
                        "director_notes": "opening",
                        "description": "Monkey stands on branch looking outward.",
                        "subject_position": "frame-left",
                        "facing_direction": "screen-right",
                        "eyeline": "toward the clearing off-screen right",
                        "background_region": "branch cluster and stream edge",
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

    def test_legacy_plan_without_spatial_fields_still_validates(self):
        data = _minimal_story()
        scene = data["scenes"][0]
        shot = scene["shots"][0]
        scene.pop("staging", None)
        scene.pop("blocking", None)
        shot.pop("subject_position", None)
        shot.pop("facing_direction", None)
        shot.pop("eyeline", None)
        shot.pop("background_region", None)
        plan = StoryPlan(**data)
        self.assertEqual(plan.scenes[0].staging, "")
        self.assertEqual(plan.scenes[0].blocking, [])
        self.assertEqual(plan.scenes[0].shots[0].subject_position, "")


if __name__ == "__main__":
    unittest.main()
