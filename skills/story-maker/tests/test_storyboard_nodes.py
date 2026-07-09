import os
import sys
import tempfile
import unittest

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

from scripts.nodes.storyboard_nodes import (  # noqa: E402
    _build_safe_panel_regen_prompt,
    _chunk_shots,
    _normalize_panels,
    _panel_line,
    build_panel_regen_prompt,
    build_storyboard_sheet_prompt,
)
from scripts.nodes.sequential_shot_image_node import image_generation_router  # noqa: E402


class TestStoryboardHelpers(unittest.TestCase):
    def test_chunk_shots(self):
        shots = [{"shot_id": f"s{i}"} for i in range(12)]
        chunks = _chunk_shots(shots, 10)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(len(chunks[0]), 10)
        self.assertEqual(len(chunks[1]), 2)

    def test_panel_line_includes_staging(self):
        shot = {
            "camera_intent": "close-up",
            "description": "Naila smiles",
            "motion_intent": "quick smile bloom",
            "duration_seconds": 1,
            "subject_position": "frame left",
            "facing_direction": "camera right",
        }
        line = _panel_line(shot, 1)
        self.assertIn("Panel 1", line)
        self.assertIn("Duration: ~1s", line)
        self.assertIn("CAM: close-up", line)
        self.assertIn("Visual:", line)
        self.assertIn("Motion: quick smile bloom", line)
        self.assertIn("subject_position", line)

    def test_build_storyboard_sheet_prompt(self):
        scene = {
            "scene_id": "scene_01",
            "title": "Kitchen",
            "environment": "home kitchen",
            "time_of_day": "morning",
            "lighting": "warm",
            "staging": "stove left, table right",
        }
        shots = [
            {
                "shot_id": "scene_01_shot_01",
                "camera_intent": "wide",
                "description": "Establish kitchen",
            }
        ]
        template = (
            "Scene: {scene_title}\n"
            "Environment: {environment}\n"
            "Time: {time_of_day}\n"
            "Light: {lighting}\n"
            "Staging: {staging}\n"
            "Panels: {panel_count}\n"
            "{panel_lines}\n"
            "{render_style}"
        )
        prompt = build_storyboard_sheet_prompt(
            scene,
            shots,
            render_style="Pixar CGI",
            template=template,
        )
        self.assertIn("Kitchen", prompt)
        self.assertIn("Panel 1", prompt)
        self.assertIn("Pixar CGI", prompt)

    def test_build_storyboard_sheet_prompt_research_template(self):
        scene = {
            "scene_id": "scene_01",
            "title": "THE SANCTUARY HEART",
            "environment": "forest",
            "time_of_day": "morning",
            "lighting": "warm",
            "staging": "swing center",
        }
        shots = [
            {
                "shot_id": "scene_01_shot_01",
                "camera_intent": "Wide Shot",
                "description": "Establish sanctuary",
                "characters_present": ["naila"],
            }
        ]
        prompt = build_storyboard_sheet_prompt(scene, shots, render_style="Pixar CGI")
        self.assertIn("STORYBOARD SHEET 01", prompt)
        self.assertIn("Storyboard Sheet 01 includes these shots", prompt)

    def test_normalize_panels(self):
        data = {
            "panels": [
                {"x": 0.0, "y": 0.0, "w": 0.2, "h": 0.5},
                {"x": 0.2, "y": 0.0, "w": 0.2, "h": 0.5},
            ]
        }
        panels = _normalize_panels(data, 2)
        self.assertEqual(len(panels), 2)
        self.assertAlmostEqual(panels[0]["w"], 0.2)

    def test_build_panel_regen_prompt(self):
        shot = {
            "characters_present": ["char_01"],
            "description": "Wave hello",
            "camera_intent": "medium shot",
            "video_motion_arc": "Child raises hand then smiles.",
        }
        prompt = build_panel_regen_prompt(shot, render_style="Pixar CGI")
        self.assertIn("char_01", prompt)
        self.assertIn("Wave hello", prompt)
        self.assertIn("raises hand", prompt)
        self.assertIn("Pixar CGI", prompt)

    def test_build_safe_panel_regen_prompt(self):
        shot = {
            "characters_present": ["naila"],
            "description": "Child smiles to camera",
            "camera_intent": "close-up",
        }
        prompt = _build_safe_panel_regen_prompt(shot, render_style="Pixar CGI")
        self.assertIn("family-friendly", prompt.lower())
        self.assertIn("close-up", prompt.lower())
        self.assertIn("Pixar CGI", prompt)


class TestImageGenerationRouter(unittest.IsolatedAsyncioTestCase):
    async def test_storyboard_route(self):
        class Ctx:
            state = {"pipeline_mode": "storyboard", "sequential_shots": True}
            route = None

        ctx = Ctx()
        await image_generation_router(ctx)
        self.assertEqual(ctx.route, "storyboard")


if __name__ == "__main__":
    unittest.main()
