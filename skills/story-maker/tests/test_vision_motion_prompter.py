import unittest

from scripts.nodes.vision_motion_prompter_node import (
    build_vision_user_context,
    _find_shot_context,
    _needs_vision_prompt,
)
from tools.vision_llm import encode_image_base64, _strip_wrapping_quotes


class TestVisionContextAssembly(unittest.TestCase):
    def test_build_context_marks_this_shot(self):
        scene = {
            "scene_id": "scene_01",
            "title": "Morning",
            "environment": "Living room",
            "time_of_day": "morning",
            "lighting": "Warm sun",
            "shots": [
                {
                    "shot_id": "scene_01_shot_01",
                    "description": "Wide on gifts",
                    "duration_seconds": 6,
                    "pace": "slow",
                    "ltx_shot_type": "establishing",
                    "ltx_complexity": "simple",
                    "motion_intent": "Dust drifts",
                    "camera_intent": "slow dolly in",
                    "audio_intent": "gentle hum",
                    "environment_state": "Sun on carpet",
                    "scene_time_offset_seconds": 0,
                    "continuity_from_previous": False,
                    "frame_strategy": "at_rest_then_react",
                    "characters_present": ["char_01"],
                },
                {
                    "shot_id": "scene_01_shot_02",
                    "description": "Close on child",
                },
            ],
        }
        shot = scene["shots"][0]
        text = build_vision_user_context(
            shot,
            scene,
            1,
            {"shot_id": "scene_01_shot_01", "audio": {"dialogue": []}},
            [{"id": "char_01", "name": "Leo", "appearance": "pink onesie"}],
        )
        self.assertIn("THIS SHOT", text)
        self.assertIn("scene_01_shot_01", text)
        self.assertIn("motion_intent: Dust drifts", text)
        self.assertIn("frame_strategy: at_rest_then_react", text)
        self.assertIn("char_01: Leo", text)

    def test_find_shot_context(self):
        story = {
            "scenes": [
                {
                    "scene_id": "scene_02",
                    "shots": [{"shot_id": "scene_02_shot_01"}],
                }
            ]
        }
        found = _find_shot_context(story, "scene_02_shot_01")
        self.assertIsNotNone(found)
        scene, shot, index = found
        self.assertEqual(scene["scene_id"], "scene_02")
        self.assertEqual(index, 1)


class TestVisionIdempotency(unittest.TestCase):
    def test_needs_prompt_when_not_confirmed(self):
        self.assertTrue(_needs_vision_prompt({}, "/tmp/a.png"))

    def test_skips_when_confirmed_same_image(self):
        entry = {
            "vision_confirmed": True,
            "vision_source_image": "/tmp/a.png",
            "motion_prompt": "From the held still...",
        }
        self.assertFalse(_needs_vision_prompt(entry, "/tmp/a.png"))

    def test_reruns_when_image_changed(self):
        entry = {
            "vision_confirmed": True,
            "vision_source_image": "/tmp/old.png",
            "motion_prompt": "text",
        }
        self.assertTrue(_needs_vision_prompt(entry, "/tmp/new.png"))


class TestVisionLlmHelpers(unittest.TestCase):
    def test_strip_wrapping_quotes(self):
        self.assertEqual(_strip_wrapping_quotes('"hello world"'), "hello world")

    def test_encode_image_roundtrip(self):
        import base64
        import tempfile
        import os

        data = b"\x89PNG\r\n\x1a\nfake"
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(data)
            path = f.name
        try:
            self.assertEqual(encode_image_base64(path), base64.b64encode(data).decode())
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
