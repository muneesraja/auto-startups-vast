import os
import asyncio
import tempfile
import unittest
import sys

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

from scripts.nodes.sequential_shot_image_node import (
    _needs_sequential_prompt,
    _should_skip_existing,
    build_shot_image_user_context,
    image_generation_router,
)


class TestSequentialShotImageHelpers(unittest.TestCase):
    def test_image_generation_router_switches_modes(self):
        class _Ctx:
            def __init__(self, sequential):
                self.state = {"sequential_shots": sequential}
                self.route = None

        ctx = _Ctx(True)
        asyncio.run(image_generation_router(ctx))
        self.assertEqual(ctx.route, "sequential")

        ctx = _Ctx(False)
        asyncio.run(image_generation_router(ctx))
        self.assertEqual(ctx.route, "parallel")

    def test_build_context_includes_spatial_fields(self):
        scene = {
            "scene_id": "scene_01",
            "title": "Kitchen chat",
            "environment": "Kitchen",
            "time_of_day": "day",
            "lighting": "Warm window light",
            "staging": "Kitchen left-to-right: stove wall, island, sink window.",
            "blocking": [
                {
                    "character_id": "char_01",
                    "position": "by the stove",
                    "facing": "screen-right toward char_02",
                }
            ],
            "shots": [{"shot_id": "scene_01_shot_01"}, {"shot_id": "scene_01_shot_02"}],
        }
        previous_shot = {
            "shot_id": "scene_01_shot_01",
            "description": "Parent at stove.",
            "subject_position": "frame-left",
            "facing_direction": "screen-right",
            "eyeline": "toward child off-screen right",
            "background_region": "stove wall",
        }
        shot = {
            "shot_id": "scene_01_shot_02",
            "description": "Child replies.",
            "duration_seconds": 6,
            "pace": "medium",
            "ltx_shot_type": "dialogue",
            "ltx_complexity": "moderate",
            "frame_strategy": "at_rest_then_react",
            "characters_present": ["char_02"],
            "environment_state": "Counter clutter catches sunlight.",
            "motion_intent": "The child answers softly.",
            "camera_intent": "static medium reverse",
            "audio_intent": "\"Okay.\"",
            "subject_position": "frame-right",
            "facing_direction": "screen-left",
            "eyeline": "toward parent off-screen left",
            "background_region": "sink window side",
        }
        text = build_shot_image_user_context(
            shot,
            scene,
            2,
            previous_shot,
            "Child frame-right, reverse angle in kitchen.",
        )
        self.assertIn("staging: Kitchen left-to-right", text)
        self.assertIn("previous_shot_id: scene_01_shot_01", text)
        self.assertIn("subject_position: frame-right", text)
        self.assertIn("background_region: sink window side", text)

    def test_needs_sequential_prompt_when_source_changes(self):
        entry = {"image_prompt": "existing", "sequential_prompt_source_image": "/tmp/a.png"}
        self.assertTrue(_needs_sequential_prompt(entry, "/tmp/b.png"))
        self.assertFalse(_needs_sequential_prompt(entry, "/tmp/a.png"))

    def test_should_skip_existing_only_when_source_matches(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            entry = {
                "output_path": path,
                "image_qa_status": "passed",
                "sequential_prompt_source_image": "/tmp/a.png",
            }
            self.assertFalse(_should_skip_existing(entry, "/tmp/b.png"))
            self.assertTrue(_should_skip_existing(entry, "/tmp/a.png"))
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
