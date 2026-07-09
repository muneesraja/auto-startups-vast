import os
import sys
import unittest

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

from scripts.nodes.vision_motion_prompter_node import (
    build_vision_user_context,
    build_video_shot_vision_context,
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
            "staging": "Living room left-to-right: sofa, coffee table, TV wall.",
            "blocking": [
                {
                    "character_id": "char_01",
                    "position": "beside the sofa frame-left",
                    "facing": "screen-right toward char_02",
                }
            ],
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
                    "subject_position": "frame-left",
                    "facing_direction": "screen-right",
                    "eyeline": "toward char_02 off-screen right",
                    "background_region": "sofa and TV wall",
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
        self.assertIn("staging: Living room left-to-right", text)
        self.assertIn("subject_position: frame-left", text)
        self.assertIn("facing_direction: screen-right", text)
        self.assertIn("eyeline: toward char_02 off-screen right", text)

    def test_build_video_shot_context(self):
        scene = {
            "scene_id": "scene_01",
            "title": "Sanctuary",
            "environment": "forest",
            "time_of_day": "morning",
            "lighting": "warm",
            "staging": "path center",
        }
        member_shots = [
            {"shot_id": "scene_01_shot_01", "description": "Naila runs", "motion_intent": "dashes"},
            {"shot_id": "scene_01_shot_02", "description": "Father follows", "motion_intent": "catches up"},
        ]
        text = build_video_shot_vision_context(
            video_shot_id="scene_01_vshot_01",
            scene=scene,
            member_shots=member_shots,
            duration_seconds=4,
            pace="fast",
            motion_arc="Naila runs then father catches up.",
            audio_shots={},
            characters=[{"id": "naila", "name": "Naila", "appearance": "green dress"}],
        )
        self.assertIn("video_shot_id: scene_01_vshot_01", text)
        self.assertIn("duration_seconds: 4", text)
        self.assertIn("scene_01_shot_01", text)
        self.assertIn("motion_arc: Naila runs then father catches up.", text)

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
