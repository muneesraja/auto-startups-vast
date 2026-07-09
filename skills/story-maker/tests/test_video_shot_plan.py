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
                      "duration_seconds": 3,
                      "motion_arc": "Run then stop.",
                      "pace": "fast"
                    }]
                  }]
                }""",
            }
            import asyncio

            asyncio.run(save_video_shot_plan(ctx))
            out = os.path.join(tmp, "video_shot_plan.json")
            self.assertTrue(os.path.isfile(out))
            text = ctx.state["video_shot_plan_content"]
            self.assertIn("scene_01_vshot_01", text)

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
                      "duration_seconds": 3,
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
