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

    def test_save_noop_when_content_missing(self):
        from scripts.nodes.save_artifact_nodes import save_story_sheet_scene

        with tempfile.TemporaryDirectory() as tmp:
            ctx = MagicMock()
            ctx.state = {"output_dir": tmp}
            import asyncio

            asyncio.run(save_story_sheet_scene(ctx))
            self.assertFalse(os.path.exists(os.path.join(tmp, "story_sheet_scene.md")))


class TestStorySheetSceneRouter(unittest.TestCase):
    def test_routes_storyboard_mode_to_storyboard(self):
        from scripts.nodes.resume_router import story_sheet_scene_router

        ctx = MagicMock()
        ctx.state = {"pipeline_mode": "storyboard"}
        import asyncio

        asyncio.run(story_sheet_scene_router(ctx))
        self.assertEqual(ctx.route, "storyboard")

    def test_routes_per_shot_mode_and_clears_text(self):
        from scripts.nodes.resume_router import story_sheet_scene_router

        ctx = MagicMock()
        ctx.state = {"pipeline_mode": "per_shot", "story_sheet_scene_text": "stale"}
        import asyncio

        asyncio.run(story_sheet_scene_router(ctx))
        self.assertEqual(ctx.route, "per_shot")
        self.assertEqual(ctx.state["story_sheet_scene_text"], "")

    def test_defaults_to_per_shot_when_mode_unset(self):
        from scripts.nodes.resume_router import story_sheet_scene_router

        ctx = MagicMock()
        ctx.state = {}
        import asyncio

        asyncio.run(story_sheet_scene_router(ctx))
        self.assertEqual(ctx.route, "per_shot")


class TestResumeRouterStorySheetScene(unittest.TestCase):
    def test_storyboard_mode_missing_sheet_routes_story_sheet_scene(self):
        from scripts.nodes.resume_router import resume_router

        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "scene_paper.md"), "w", encoding="utf-8") as f:
                f.write("# Scene Paper: Test\n")
            ctx = MagicMock()
            ctx.state = {"output_dir": tmp, "fresh": False, "pipeline_mode": "storyboard"}
            import asyncio

            asyncio.run(resume_router(ctx))
            self.assertEqual(ctx.route, "story_sheet_scene")

    def test_storyboard_mode_loads_existing_sheet_and_continues(self):
        from scripts.nodes.resume_router import resume_router

        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "scene_paper.md"), "w", encoding="utf-8") as f:
                f.write("# Scene Paper: Test\n")
            sheet_content = "# Storyboard Sheet Map: Test\n\n**Total sheets:** 1\n"
            with open(os.path.join(tmp, "story_sheet_scene.md"), "w", encoding="utf-8") as f:
                f.write(sheet_content)
            ctx = MagicMock()
            ctx.state = {"output_dir": tmp, "fresh": False, "pipeline_mode": "storyboard"}
            import asyncio

            asyncio.run(resume_router(ctx))
            self.assertEqual(ctx.route, "narrative_outline")
            self.assertEqual(ctx.state["story_sheet_scene_text"], sheet_content)

    def test_per_shot_mode_skips_sheet_check_entirely(self):
        from scripts.nodes.resume_router import resume_router

        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "scene_paper.md"), "w", encoding="utf-8") as f:
                f.write("# Scene Paper: Test\n")
            ctx = MagicMock()
            ctx.state = {"output_dir": tmp, "fresh": False, "pipeline_mode": "per_shot"}
            import asyncio

            asyncio.run(resume_router(ctx))
            # story_sheet_scene.md never checked/required for per_shot profiles
            self.assertEqual(ctx.route, "narrative_outline")
            self.assertNotIn("story_sheet_scene_text", ctx.state)

    def test_fresh_wipes_story_sheet_scene_md(self):
        from scripts.nodes.resume_router import resume_router

        with tempfile.TemporaryDirectory() as tmp:
            sheet_path = os.path.join(tmp, "story_sheet_scene.md")
            with open(sheet_path, "w", encoding="utf-8") as f:
                f.write("# old sheet map\n")
            ctx = MagicMock()
            ctx.state = {"output_dir": tmp, "fresh": True, "pipeline_mode": "storyboard"}
            import asyncio

            asyncio.run(resume_router(ctx))
            self.assertEqual(ctx.route, "scene_paper")
            self.assertFalse(os.path.exists(sheet_path))


class TestStorySheetScenePrompts(unittest.TestCase):
    def test_reel_v2_prompt_resolves_over_base(self):
        old_style = os.environ.get("STORY_STYLE")
        os.environ["STORY_STYLE"] = "reel_v2"
        try:
            from scripts.nodes.storyboard_nodes import _load_prompt_file

            text = _load_prompt_file("story_sheet_scene_author")
            self.assertIn("Storyboard Sheet Scene Splitter (reel_v2", text)
        finally:
            if old_style is None:
                os.environ.pop("STORY_STYLE", None)
            else:
                os.environ["STORY_STYLE"] = old_style

    def test_base_prompt_exists(self):
        path = os.path.join(_SKILL_DIR, "prompts", "story_sheet_scene_author.md")
        self.assertTrue(os.path.isfile(path))


class TestStorySheetSceneAgent(unittest.TestCase):
    def test_agent_module_defines_expected_output_key(self):
        os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
        from agents.story_sheet_scene_author import story_sheet_scene_author_agent

        self.assertEqual(story_sheet_scene_author_agent.output_key, "story_sheet_scene_content")
        self.assertEqual(story_sheet_scene_author_agent.name, "story_sheet_scene_author_agent")


if __name__ == "__main__":
    unittest.main()
