import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from scripts.nodes.image_qa_node import image_qa


class _Ctx:
    def __init__(self, state):
        self.state = state


class TestImageQaNode(unittest.TestCase):
    def test_skips_qa_passed_shots(self):
        with tempfile.TemporaryDirectory() as tmp:
            img_path = os.path.join(tmp, "images", "scene_01_shot_01.png")
            os.makedirs(os.path.dirname(img_path), exist_ok=True)
            with open(img_path, "wb") as f:
                f.write(b"png")
            specs = {
                "shot_images": {
                    "scene_01_shot_01": {
                        "shot_id": "scene_01_shot_01",
                        "output_path": img_path,
                        "image_qa_status": "passed",
                    }
                }
            }
            story = {
                "scenes": [
                    {
                        "scene_id": "scene_01",
                        "shots": [
                            {
                                "shot_id": "scene_01_shot_01",
                                "description": "test",
                                "characters_present": [],
                            }
                        ],
                    }
                ]
            }
            ctx = _Ctx(
                {
                    "output_dir": tmp,
                    "generation_specs_content": json.dumps(specs),
                    "story_plan_content": json.dumps(story),
                }
            )
            with patch(
                "scripts.nodes.image_qa_node.vision_image_qa",
                new_callable=AsyncMock,
            ) as mock_qa:
                asyncio.run(image_qa(ctx))
                mock_qa.assert_not_called()


if __name__ == "__main__":
    unittest.main()
