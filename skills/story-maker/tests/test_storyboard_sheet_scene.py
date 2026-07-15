import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)


class TestSaveStorySheetScene(unittest.TestCase):
    def test_save_story_sheet_scene_writes_md_and_sets_state(self):
        from scripts.nodes.save_artifact_nodes import save_story_sheet_scene

        with tempfile.TemporaryDirectory() as tmp:
            ctx = MagicMock()
            ctx.state = {
                "output_dir": tmp,
                "story_sheet_scene_content": "# Storyboard Sheet Map: Naila\n",
            }
            import asyncio

            asyncio.run(save_story_sheet_scene(ctx))
            path = os.path.join(tmp, "story_sheet_scene.md")
            self.assertTrue(os.path.isfile(path))
            with open(path, encoding="utf-8") as f:
                self.assertIn("Naila", f.read())
            self.assertEqual(ctx.state["story_sheet_scene_text"], "# Storyboard Sheet Map: Naila")


class TestResumeRouterThreeArtifacts(unittest.TestCase):
    def test_missing_plan_routes_plan(self):
        from scripts.nodes.resume_router import resume_router

        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "developed_story.md"), "w", encoding="utf-8") as f:
                f.write("# Developed\n")
            with open(os.path.join(tmp, "scene_paper.md"), "w", encoding="utf-8") as f:
                f.write("# Scene Paper: Test\n")
            ctx = MagicMock()
            ctx.state = {"output_dir": tmp, "fresh": False, "pipeline_mode": "storyboard"}
            import asyncio

            asyncio.run(resume_router(ctx))
            self.assertEqual(ctx.route, "plan")

    def test_plan_present_missing_specs_routes_generation_specs(self):
        from scripts.nodes.resume_router import resume_router

        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "developed_story.md"), "w", encoding="utf-8") as f:
                f.write("# Developed\n")
            with open(os.path.join(tmp, "scene_paper.md"), "w", encoding="utf-8") as f:
                f.write("# Scene Paper: Test\n")
            plan = {
                "meta": {
                    "story_title": "T",
                    "style": "s",
                    "aesthetic": "a",
                    "total_duration_seconds": 2,
                    "total_scenes": 1,
                    "total_shots": 1,
                },
                "characters": [
                    {
                        "id": "char_01",
                        "name": "A",
                        "appearance": "x",
                        "voice_profile": "y",
                    }
                ],
                "scenes": [
                    {
                        "scene_id": "scene_01",
                        "title": "Open",
                        "environment": "forest",
                        "time_of_day": "day",
                        "lighting": "sun",
                        "assets": {"generate_background": False},
                        "audio_scene": {},
                        "shots": [
                            {
                                "shot_id": "scene_01_shot_01",
                                "scene_id": "scene_01",
                                "duration_seconds": 2,
                                "characters_present": ["char_01"],
                                "description": "Wide",
                                "audio": {},
                            }
                        ],
                        "video_shots": [],
                    }
                ],
            }
            import json

            with open(os.path.join(tmp, "plan.json"), "w", encoding="utf-8") as f:
                json.dump(plan, f)
            ctx = MagicMock()
            ctx.state = {"output_dir": tmp, "fresh": False, "pipeline_mode": "storyboard"}
            import asyncio

            asyncio.run(resume_router(ctx))
            self.assertEqual(ctx.route, "generation_specs")
            self.assertIn("plan_content", ctx.state)

    def test_fresh_wipes_plan_and_legacy(self):
        from scripts.nodes.resume_router import resume_router

        with tempfile.TemporaryDirectory() as tmp:
            for name in ("plan.json", "story_sheet_scene.md", "story_plan.json"):
                with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
                    f.write("x")
            ctx = MagicMock()
            ctx.state = {"output_dir": tmp, "fresh": True, "pipeline_mode": "storyboard"}
            import asyncio

            asyncio.run(resume_router(ctx))
            self.assertEqual(ctx.route, "developed_story")
            self.assertFalse(os.path.exists(os.path.join(tmp, "plan.json")))


class TestProductionPlanPrompt(unittest.TestCase):
    def test_reel_v2_production_plan_prompt_resolves(self):
        path = os.path.join(_SKILL_DIR, "prompts", "reel_v2", "production_plan_author.md")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("video_shots", text)
        self.assertIn("storyboard", text.lower())


if __name__ == "__main__":
    unittest.main()
