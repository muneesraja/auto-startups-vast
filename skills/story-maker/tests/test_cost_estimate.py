import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)


class TestCostEstimateNode(unittest.TestCase):
    def test_cost_estimate_storyboard_counts_anchor_only(self):
        from scripts.nodes.cost_estimate_node import cost_estimate

        with tempfile.TemporaryDirectory() as tmp:
            specs = {
                "character_sheets": {"naila": {"status": "pending"}},
                "storyboard_sheets": {"scene_01_sheet_01": {"status": "pending"}},
                "shot_images": {
                    "scene_01_shot_01": {"status": "pending"},
                    "scene_01_shot_02": {"status": "pending"},
                },
                "motion": {},
            }
            vplan = {
                "scenes": [
                    {
                        "scene_id": "scene_01",
                        "video_shots": [
                            {
                                "video_shot_id": "scene_01_vshot_01",
                                "anchor_panel_id": "scene_01_shot_01",
                            }
                        ],
                    }
                ]
            }
            ctx = MagicMock()
            ctx.state = {
                "output_dir": tmp,
                "pipeline_mode": "storyboard",
                "generation_specs_content": json.dumps(specs),
                "video_shot_plan_content": json.dumps(vplan),
            }
            import asyncio

            asyncio.run(cost_estimate(ctx))
            out = os.path.join(tmp, "cost_estimate.json")
            self.assertTrue(os.path.isfile(out))
            data = json.load(open(out, encoding="utf-8"))
            self.assertEqual(data["counts"]["replicate_image_calls_total"], 3)
            self.assertEqual(data["counts"]["vision_motion_calls"], 1)
            self.assertEqual(data["counts"]["ltx_video_calls"], 1)


if __name__ == "__main__":
    unittest.main()
