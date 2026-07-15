import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)


class TestVideoShotPlanSave(unittest.TestCase):
    def test_save_video_shot_plan_writes_file(self):
        from scripts.nodes.save_artifact_nodes import save_video_shot_plan

        with tempfile.TemporaryDirectory() as tmp:
            ctx = MagicMock()
            ctx.state = {
                "output_dir": tmp,
                "story_plan_content": """{
                  "meta": {"story_title": "t", "style": "reel_v2", "aesthetic": "x"},
                  "characters": [{"id": "naila", "name": "Naila", "appearance": "a", "voice_profile": "v"}],
                  "scenes": [{
                    "scene_id": "scene_01", "title": "S1", "environment": "forest", "time_of_day": "day", "lighting": "warm",
                    "duration_budget_seconds": 8,
                    "shots": [
                      {"shot_id": "scene_01_shot_01", "scene_id": "scene_01", "duration_seconds": 1, "description": "a"},
                      {"shot_id": "scene_01_shot_02", "scene_id": "scene_01", "duration_seconds": 1, "description": "b"},
                      {"shot_id": "scene_01_shot_03", "scene_id": "scene_01", "duration_seconds": 1, "description": "c"}
                    ]
                  }]
                }""",
                "video_shot_plan_content": """{
                  "scenes": [{
                    "scene_id": "scene_01",
                    "video_shots": [{
                      "video_shot_id": "scene_01_vshot_01",
                      "scene_id": "scene_01",
                      "panel_ids": ["scene_01_shot_01", "scene_01_shot_02", "scene_01_shot_03"],
                      "anchor_panel_id": "scene_01_shot_01",
                      "duration_seconds": 8,
                      "motion_arc": "Over the first seconds they run; then stop with dust settling.",
                      "pace": "fast"
                    }]
                  }]
                }""",
            }
            import asyncio

            asyncio.run(save_video_shot_plan(ctx))
            out = os.path.join(tmp, "video_shot_plan.json")
            self.assertTrue(os.path.isfile(out))
            data = json.loads(ctx.state["video_shot_plan_content"])
            vshot = data["scenes"][0]["video_shots"][0]
            self.assertEqual(vshot["video_shot_id"], "scene_01_vshot_01")
            self.assertEqual(vshot["duration_seconds"], 8)

    def test_normalize_keeps_optional_non_primary_in_band(self):
        from scripts.nodes.save_artifact_nodes import _normalize_video_shot_plan

        story = {
            "scenes": [{
                "scene_id": "scene_01",
                "duration_budget_seconds": 8,
                "shots": [
                    {"shot_id": "scene_01_shot_01", "duration_seconds": 1},
                    {"shot_id": "scene_01_shot_02", "duration_seconds": 1},
                ],
            }]
        }
        plan = {
            "scenes": [{
                "scene_id": "scene_01",
                "video_shots": [{
                    "video_shot_id": "scene_01_vshot_01",
                    "panel_ids": ["scene_01_shot_01", "scene_01_shot_02"],
                    "anchor_panel_id": "scene_01_shot_01",
                    "duration_seconds": 7,
                    "motion_arc": "Timed arc.",
                    "pace": "fast",
                }],
            }]
        }
        out = _normalize_video_shot_plan(plan, story)
        dur = out["scenes"][0]["video_shots"][0]["duration_seconds"]
        self.assertGreaterEqual(dur, 3)
        self.assertLessEqual(dur, 15)

    def test_normalize_snaps_out_of_band_to_primary(self):
        from scripts.nodes.save_artifact_nodes import _normalize_video_shot_plan

        story = {
            "scenes": [{
                "scene_id": "scene_01",
                "duration_budget_seconds": 8,
                "shots": [{"shot_id": "scene_01_shot_01", "duration_seconds": 1}],
            }]
        }
        plan = {
            "scenes": [{
                "scene_id": "scene_01",
                "video_shots": [{
                    "video_shot_id": "scene_01_vshot_01",
                    "panel_ids": ["scene_01_shot_01"],
                    "anchor_panel_id": "scene_01_shot_01",
                    "duration_seconds": 20,
                    "motion_arc": "Timed arc.",
                    "pace": "fast",
                }],
            }]
        }
        out = _normalize_video_shot_plan(plan, story)
        self.assertIn(out["scenes"][0]["video_shots"][0]["duration_seconds"], (6, 8, 10))

    def test_save_video_shot_plan_rejects_missing_coverage(self):
        from scripts.nodes.save_artifact_nodes import save_video_shot_plan

        with tempfile.TemporaryDirectory() as tmp:
            ctx = MagicMock()
            ctx.state = {
                "output_dir": tmp,
                "story_plan_content": """{
                  "meta": {"story_title": "t", "style": "reel_v2", "aesthetic": "x"},
                  "characters": [{"id": "naila", "name": "Naila", "appearance": "a", "voice_profile": "v"}],
                  "scenes": [{
                    "scene_id": "scene_01", "title": "S1", "environment": "forest", "time_of_day": "day", "lighting": "warm",
                    "shots": [
                      {"shot_id": "scene_01_shot_01", "scene_id": "scene_01", "duration_seconds": 1, "description": "a"},
                      {"shot_id": "scene_01_shot_02", "scene_id": "scene_01", "duration_seconds": 1, "description": "b"}
                    ]
                  }]
                }""",
                "video_shot_plan_content": """{
                  "scenes": [{
                    "scene_id": "scene_01",
                    "video_shots": [{
                      "video_shot_id": "scene_01_vshot_01",
                      "scene_id": "scene_01",
                      "panel_ids": ["scene_01_shot_01"],
                      "anchor_panel_id": "scene_01_shot_01",
                      "duration_seconds": 8,
                      "motion_arc": "Run then stop.",
                      "pace": "fast"
                    }]
                  }]
                }""",
            }
            import asyncio

            with self.assertRaises(ValueError):
                asyncio.run(save_video_shot_plan(ctx))


if __name__ == "__main__":
    unittest.main()
