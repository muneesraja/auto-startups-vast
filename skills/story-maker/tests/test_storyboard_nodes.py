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
    _grid_bbox_row_major,
    _normalize_panels,
    _panel_line,
    build_panel_regen_prompt,
    build_storyboard_sheet_prompt,
    detect_album_panel_bboxes,
    resolve_panel_bboxes,
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
        self.assertIn("Storyboard Sheet 01 includes these shots", prompt)
        self.assertIn("5 rows × 2 columns", prompt)
        self.assertIn("photo album", prompt.lower())

    def test_grid_bbox_row_major_5x2(self):
        first = _grid_bbox_row_major(0)
        self.assertAlmostEqual(first["x"], 0.0)
        self.assertAlmostEqual(first["y"], 0.0)
        self.assertAlmostEqual(first["w"], 0.5)
        self.assertAlmostEqual(first["h"], 0.2)
        third = _grid_bbox_row_major(2)  # second row, left
        self.assertAlmostEqual(third["x"], 0.0)
        self.assertAlmostEqual(third["y"], 0.2)
        self.assertAlmostEqual(third["w"], 0.5)
        self.assertAlmostEqual(third["h"], 0.2)
        right = _grid_bbox_row_major(1)
        self.assertAlmostEqual(right["x"], 0.5)

    def test_detect_album_panel_bboxes_synthetic(self):
        from PIL import Image, ImageDraw

        width, height = 200, 500
        cols, rows = 2, 5
        gutter = 4
        cell_w = (width - gutter) // cols
        cell_h = (height - (rows - 1) * gutter) // rows
        img = Image.new("RGB", (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        colors = [
            (40, 40, 200),
            (40, 180, 40),
            (200, 40, 40),
            (200, 160, 40),
            (160, 40, 200),
            (40, 160, 200),
            (120, 80, 40),
            (80, 120, 160),
            (200, 80, 120),
            (80, 200, 120),
        ]
        for idx, color in enumerate(colors):
            col = idx % cols
            row = idx // cols
            x0 = col * (cell_w + gutter)
            y0 = row * (cell_h + gutter)
            draw.rectangle([x0, y0, x0 + cell_w - 1, y0 + cell_h - 1], fill=color)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sheet.png")
            img.save(path)
            bboxes = detect_album_panel_bboxes(path, 10, inset_px=1)
            self.assertIsNotNone(bboxes)
            self.assertEqual(len(bboxes), 10)
            # First panel should be top-left and roughly half width / fifth height
            self.assertLess(bboxes[0]["x"], 0.05)
            self.assertLess(bboxes[0]["y"], 0.05)
            self.assertAlmostEqual(bboxes[0]["w"], 0.5, delta=0.08)
            self.assertAlmostEqual(bboxes[0]["h"], 0.2, delta=0.08)
            # Second panel starts near vertical gutter
            self.assertGreater(bboxes[1]["x"], 0.45)
            # Partial expected count
            four = detect_album_panel_bboxes(path, 4, inset_px=1)
            self.assertEqual(len(four), 4)

            boxes, method = resolve_panel_bboxes(path, 10, mode="python")
            self.assertEqual(method, "gutter")
            self.assertEqual(len(boxes), 10)

    def test_detect_album_panel_bboxes_no_gutters_returns_none(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "flat.png")
            Image.new("RGB", (200, 500), (30, 80, 120)).save(path)
            self.assertIsNone(detect_album_panel_bboxes(path, 10))
            boxes, method = resolve_panel_bboxes(path, 10, mode="python")
            self.assertEqual(method, "grid")
            self.assertEqual(len(boxes), 10)
            self.assertAlmostEqual(boxes[0]["w"], 0.5)
            self.assertAlmostEqual(boxes[0]["h"], 0.2)

    def test_detect_album_panel_bboxes_smoke_sheet_if_present(self):
        repo_root = os.path.dirname(os.path.dirname(_SKILL_DIR))
        sheet = os.path.join(
            repo_root,
            "outputs",
            "story-maker",
            "smoke_album_5x2",
            "storyboard_sheets",
            "scene_01_sheet_01.png",
        )
        if not os.path.isfile(sheet):
            self.skipTest("smoke_album_5x2 sheet not present")
        boxes, method = resolve_panel_bboxes(sheet, 10, mode="python")
        self.assertEqual(method, "gutter")
        self.assertEqual(len(boxes), 10)
        self.assertLess(boxes[0]["x"], 0.02)
        self.assertGreater(boxes[1]["x"], 0.4)

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
        prompt = build_panel_regen_prompt(
            shot,
            render_style="Pixar CGI",
            character_labels={"char_01": "Naila"},
        )
        self.assertIn("char_01", prompt)
        self.assertIn("Naila", prompt)
        self.assertIn("Image 2", prompt)
        self.assertIn("Wave hello", prompt)
        self.assertNotIn("raises hand", prompt)  # motion_arc omitted from still regen
        self.assertIn("do not add", prompt.lower())
        self.assertIn("expression", prompt.lower())
        self.assertIn("footwear", prompt.lower())
        self.assertIn("REPLACE", prompt)
        self.assertIn("Pixar CGI", prompt)

    def test_build_panel_regen_prompt_empty_stage(self):
        shot = {
            "characters_present": [],
            "description": "Lush clearing with a swing",
            "camera_intent": "wide",
            "video_motion_arc": "Naila sleeps while dog and parrot watch.",
        }
        prompt = build_panel_regen_prompt(shot, render_style="Pixar CGI")
        self.assertIn("empty-stage", prompt.lower())
        self.assertNotIn("Naila sleeps", prompt)
        self.assertIn("do not invent", prompt.lower())
        self.assertNotIn("Image 2", prompt)

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
        self.assertIn("footwear", prompt.lower())
        self.assertIn("sheet identity wins", prompt.lower())
        self.assertIn("expression", prompt.lower())


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
