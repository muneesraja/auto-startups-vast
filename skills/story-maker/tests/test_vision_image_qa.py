import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from scripts.nodes.image_qa_node import _shot_brief
from tools.vision_llm import _IMAGE_QA_SYSTEM, vision_image_qa


class TestVisionImageQa(unittest.TestCase):
    def test_qa_system_ignores_background_crowd(self):
        self.assertIn("background crowd", _IMAGE_QA_SYSTEM.lower())
        self.assertIn("foreground", _IMAGE_QA_SYSTEM.lower())

    def test_shot_brief_injects_background_population(self):
        story = {
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "background_population": "Twenty classmates at desks behind the leads",
                    "shots": [
                        {
                            "shot_id": "scene_01_shot_01",
                            "characters_present": ["char_01", "char_02"],
                            "description": "Two heroes at the front",
                        }
                    ],
                }
            ]
        }
        brief = _shot_brief(story, "scene_01_shot_01")
        self.assertEqual(
            brief["background_population"],
            "Twenty classmates at desks behind the leads",
        )
        self.assertEqual(brief["characters_present"], ["char_01", "char_02"])

    def test_qa_payload_counts_foreground_only(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"png")
            img_path = tmp.name
        try:
            shot_brief = {
                "description": "Six heroes at the front of class",
                "characters_present": ["char_01", "char_02", "char_03", "char_04", "char_05", "char_06"],
                "background_population": "Twenty classmates at desks behind them",
                "frame_strategy": "at_rest_then_react",
                "environment_state": "Busy classroom",
            }
            captured: dict = {}

            async def _fake_acompletion(**kwargs):
                user_content = kwargs["messages"][1]["content"]
                text_part = next(c for c in user_content if c["type"] == "text")
                captured["payload"] = json.loads(text_part["text"])
                resp = MagicMock()
                resp.choices = [
                    MagicMock(
                        message=MagicMock(
                            content=json.dumps(
                                {
                                    "pass": True,
                                    "reason": "ok",
                                    "has_text": False,
                                    "character_count_ok": True,
                                    "pose_match_ok": True,
                                }
                            )
                        )
                    )
                ]
                return resp

            with patch("litellm.acompletion", new=AsyncMock(side_effect=_fake_acompletion)):
                with patch(
                    "tools.vision_llm.get_vision_api_config",
                    return_value=("openrouter/openai/gpt-5-mini", "k", "https://openrouter.ai/api/v1"),
                ):
                    result = asyncio.run(vision_image_qa(img_path, shot_brief))

            self.assertTrue(result["pass"])
            self.assertEqual(captured["payload"]["foreground_character_count"], 6)
            self.assertEqual(
                captured["payload"]["background_population"],
                "Twenty classmates at desks behind them",
            )
            self.assertEqual(len(captured["payload"]["characters_present"]), 6)
        finally:
            os.unlink(img_path)


if __name__ == "__main__":
    unittest.main()
