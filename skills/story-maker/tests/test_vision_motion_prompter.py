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
            {
                "shot_id": "scene_01_shot_01",
                "description": "Empty gate",
                "motion_intent": "birds cross",
                "characters_present": [],
            },
        ]
        text = build_video_shot_vision_context(
            video_shot_id="scene_01_vshot_01",
            scene=scene,
            member_shots=member_shots,
            duration_seconds=8,
            pace="fast",
            motion_arc="Light sweeps and birds cross.",
            audio_shots={},
            characters=[
                {"id": "char_01", "name": "Naila", "appearance": "green dress"},
                {"id": "char_03", "name": "Azhagi", "appearance": "dog"},
            ],
            anchor_panel_id="scene_01_shot_01",
            anchor_characters_present=[],
        )
        self.assertIn("video_shot_id: scene_01_vshot_01", text)
        self.assertIn("duration_seconds: 8", text)
        self.assertIn("anchor_characters_present: []", text)
        self.assertIn("EMPTY ANCHOR", text)
        self.assertIn("Forbidden cast", text)
        self.assertIn("char_01: Naila", text)
        self.assertIn("environment-only start frame", text)

    def test_build_video_shot_context_allowed_cast(self):
        text = build_video_shot_vision_context(
            video_shot_id="scene_01_vshot_02",
            scene={"scene_id": "scene_01", "title": "t", "environment": "e", "time_of_day": "d", "lighting": "l"},
            member_shots=[
                {
                    "shot_id": "scene_01_shot_04",
                    "description": "Push gates",
                    "motion_intent": "gates swing",
                    "characters_present": ["char_01", "char_02"],
                }
            ],
            duration_seconds=8,
            pace="fast",
            motion_arc="Gates swing outward.",
            audio_shots={},
            characters=[
                {"id": "char_01", "name": "Naila", "appearance": "a"},
                {"id": "char_02", "name": "Father", "appearance": "b"},
                {"id": "char_03", "name": "Azhagi", "appearance": "dog"},
            ],
            anchor_panel_id="scene_01_shot_04",
            anchor_characters_present=["char_01", "char_02"],
        )
        self.assertIn("anchor_characters_present: ['char_01', 'char_02']", text)
        self.assertIn("char_01: Naila", text)
        self.assertIn("char_03: Azhagi", text)
        self.assertIn("Forbidden cast", text)
        self.assertIn("Only animate roles listed", text)

    def test_vision_prompt_files_include_anti_freeze_density(self):
        root = os.path.join(_SKILL_DIR, "prompts")
        for rel in (
            "vision_motion_prompter.md",
            "reel_v2/vision_motion_prompter.md",
            "reels/vision_motion_prompter.md",
        ):
            path = os.path.join(root, rel)
            with open(path, encoding="utf-8") as f:
                text = f.read().lower()
            self.assertIn("anti-freeze", text)
            self.assertIn("primary", text)
            self.assertRegex(text, r"\b6\b")
            self.assertRegex(text, r"\b8\b")
            self.assertRegex(text, r"\b10\b")
            self.assertIn("never use", text)
            self.assertIn("smooth cinematic motion", text)

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
