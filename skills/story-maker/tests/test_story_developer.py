import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)


class TestResumeRouterDevelopedStory(unittest.TestCase):
    def test_fresh_routes_developed_story_and_wipes(self):
        from scripts.nodes.resume_router import resume_router

        with tempfile.TemporaryDirectory() as tmp:
            developed = os.path.join(tmp, "developed_story.md")
            scene = os.path.join(tmp, "scene_paper.md")
            with open(developed, "w", encoding="utf-8") as f:
                f.write("# old developed\n")
            with open(scene, "w", encoding="utf-8") as f:
                f.write("# old scene\n")
            ctx = MagicMock()
            ctx.state = {"output_dir": tmp, "fresh": True, "story_text": "Naila slept."}
            import asyncio

            asyncio.run(resume_router(ctx))
            self.assertEqual(ctx.route, "developed_story")
            self.assertFalse(os.path.exists(developed))
            self.assertFalse(os.path.exists(scene))

    def test_fresh_skip_writes_through_and_routes_scene_paper(self):
        from scripts.nodes.resume_router import resume_router

        with tempfile.TemporaryDirectory() as tmp:
            ctx = MagicMock()
            ctx.state = {
                "output_dir": tmp,
                "fresh": True,
                "skip_story_developer": True,
                "story_text": "Raw Naila story.",
            }
            import asyncio

            asyncio.run(resume_router(ctx))
            self.assertEqual(ctx.route, "scene_paper")
            path = os.path.join(tmp, "developed_story.md")
            self.assertTrue(os.path.isfile(path))
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), "Raw Naila story.")
            self.assertEqual(ctx.state["developed_story_text"], "Raw Naila story.")

    def test_missing_developed_story_routes_developer(self):
        from scripts.nodes.resume_router import resume_router

        with tempfile.TemporaryDirectory() as tmp:
            ctx = MagicMock()
            ctx.state = {"output_dir": tmp, "fresh": False, "story_text": "x"}
            import asyncio

            asyncio.run(resume_router(ctx))
            self.assertEqual(ctx.route, "developed_story")

    def test_developed_present_missing_scene_paper_routes_scene_paper(self):
        from scripts.nodes.resume_router import resume_router

        with tempfile.TemporaryDirectory() as tmp:
            content = "# Developed Story: Naila\n\n## Scene 01\n"
            with open(os.path.join(tmp, "developed_story.md"), "w", encoding="utf-8") as f:
                f.write(content)
            ctx = MagicMock()
            ctx.state = {"output_dir": tmp, "fresh": False}
            import asyncio

            asyncio.run(resume_router(ctx))
            self.assertEqual(ctx.route, "scene_paper")
            self.assertEqual(ctx.state["developed_story_text"], content)

    def test_skip_missing_developed_writes_through(self):
        from scripts.nodes.resume_router import resume_router, write_through_developed_story

        with tempfile.TemporaryDirectory() as tmp:
            ctx = MagicMock()
            ctx.state = {
                "output_dir": tmp,
                "fresh": False,
                "skip_story_developer": True,
                "story_text": "Hello sanctuary.",
            }
            import asyncio

            asyncio.run(resume_router(ctx))
            self.assertEqual(ctx.route, "scene_paper")
            self.assertEqual(ctx.state["developed_story_text"], "Hello sanctuary.")
            # helper direct
            ctx2 = MagicMock()
            ctx2.state = {"output_dir": tmp, "story_text": "Direct write."}
            out = write_through_developed_story(ctx2)
            self.assertEqual(out, "Direct write.")


class TestSaveDevelopedStory(unittest.TestCase):
    def test_save_developed_story_writes_md_and_sets_state(self):
        from scripts.nodes.save_artifact_nodes import save_developed_story

        with tempfile.TemporaryDirectory() as tmp:
            ctx = MagicMock()
            ctx.state = {
                "output_dir": tmp,
                "developed_story_content": "# Developed Story: Naila\n",
            }
            import asyncio

            asyncio.run(save_developed_story(ctx))
            path = os.path.join(tmp, "developed_story.md")
            self.assertTrue(os.path.isfile(path))
            with open(path, encoding="utf-8") as f:
                self.assertIn("Naila", f.read())
            self.assertEqual(ctx.state["developed_story_text"], "# Developed Story: Naila")


class TestScenePaperUsesDevelopedStory(unittest.TestCase):
    def test_scene_paper_extra_references_developed_story_text(self):
        path = os.path.join(_SKILL_DIR, "agents", "scene_paper_author.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("{developed_story_text}", src)
        self.assertIn("{story_text}", src)


class TestStoryDeveloperPromptExpansion(unittest.TestCase):
    def test_prompt_has_expansion_and_anti_sameness(self):
        path = os.path.join(_SKILL_DIR, "prompts", "story_developer.md")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("sub-scene architect", text.lower())
        self.assertIn("Thin-story expansion playbook", text)
        self.assertIn("Anti-sameness", text)
        self.assertIn("must not look alike", text.lower())
        self.assertIn("Tortoise and rabbit", text)
        self.assertIn("scenes_target", text)
        self.assertIn("**Purpose:**", text)
        self.assertIn("drawable evolution", text)

    def test_agent_extra_requires_distinct_expansion(self):
        path = os.path.join(_SKILL_DIR, "agents", "story_developer.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("distinct", src.lower())
        self.assertIn("non-alike", src)
        self.assertIn("Purpose line", src)


if __name__ == "__main__":
    unittest.main()
