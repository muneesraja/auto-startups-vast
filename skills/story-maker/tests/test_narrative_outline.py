import unittest

from schemas.plan import NarrativeOutline


class TestNarrativeOutlineSchema(unittest.TestCase):
    def test_parses_minimal_outline(self):
        outline = NarrativeOutline(
            meta={
                "story_title": "Test",
                "target_duration_seconds": 300,
                "duration_tolerance_percent": 15,
                "planned_act_count": 1,
            },
            acts=[
                {
                    "act_id": "act_01",
                    "title": "Act 1",
                    "duration_budget_seconds": 300,
                    "summary": "Opening",
                    "scenes": [
                        {
                            "scene_id": "scene_01",
                            "title": "Beach",
                            "duration_budget_seconds": 300,
                            "beats": ["Baby plays", "Wave forms"],
                        }
                    ],
                }
            ],
        )
        self.assertEqual(outline.meta.target_duration_seconds, 300)
        self.assertEqual(len(outline.acts[0].scenes[0].beats), 2)


if __name__ == "__main__":
    unittest.main()
