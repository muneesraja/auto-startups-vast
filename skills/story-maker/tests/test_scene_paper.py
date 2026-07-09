import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)


class TestResumeRouterScenePaper(unittest.TestCase):
    def test_fresh_routes_scene_paper_and_wipes_scene_paper_md(self):
        from scripts.nodes.resume_router import resume_router

        with tempfile.TemporaryDirectory() as tmp:
            scene_path = os.path.join(tmp, "scene_paper.md")
            with open(scene_path, "w", encoding="utf-8") as f:
                f.write("# old scene paper\n")
            ctx = MagicMock()
            ctx.state = {"output_dir": tmp, "fresh": True}
            import asyncio

            asyncio.run(resume_router(ctx))
            self.assertEqual(ctx.route, "scene_paper")
            self.assertFalse(os.path.exists(scene_path))

    def test_missing_scene_paper_routes_scene_paper(self):
        from scripts.nodes.resume_router import resume_router

        with tempfile.TemporaryDirectory() as tmp:
            ctx = MagicMock()
            ctx.state = {"output_dir": tmp, "fresh": False}
            import asyncio

            asyncio.run(resume_router(ctx))
            self.assertEqual(ctx.route, "scene_paper")

    def test_loads_scene_paper_into_state(self):
        from scripts.nodes.resume_router import resume_router

        with tempfile.TemporaryDirectory() as tmp:
            content = "# Scene Paper: Test\n\n## Scene 01\n"
            with open(os.path.join(tmp, "scene_paper.md"), "w", encoding="utf-8") as f:
                f.write(content)
            ctx = MagicMock()
            ctx.state = {"output_dir": tmp, "fresh": False}
            import asyncio

            asyncio.run(resume_router(ctx))
            self.assertEqual(ctx.route, "narrative_outline")
            self.assertEqual(ctx.state["scene_paper_text"], content)
            self.assertEqual(ctx.state["scene_paper_content"], content)


class TestSaveScenePaper(unittest.TestCase):
    def test_save_scene_paper_writes_md_and_sets_state(self):
        from scripts.nodes.save_artifact_nodes import save_scene_paper

        with tempfile.TemporaryDirectory() as tmp:
            ctx = MagicMock()
            ctx.state = {
                "output_dir": tmp,
                "scene_paper_content": "# Scene Paper: Naila\n",
            }
            import asyncio

            asyncio.run(save_scene_paper(ctx))
            path = os.path.join(tmp, "scene_paper.md")
            self.assertTrue(os.path.isfile(path))
            with open(path, encoding="utf-8") as f:
                self.assertIn("Naila", f.read())
            self.assertEqual(ctx.state["scene_paper_text"], "# Scene Paper: Naila")


if __name__ == "__main__":
    unittest.main()
