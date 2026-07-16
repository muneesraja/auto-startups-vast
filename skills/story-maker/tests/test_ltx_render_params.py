import os
import sys
import unittest

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

from scripts.nodes.flf_storyboard_planner import normalize_flf_clip_plan
from tools.ltx_render_params import (
    resolve_cfg,
    resolve_clip_render_params,
    resolve_i2v_strength,
    resolve_last_frame_strength,
)
from tools.workflow_builder import (
    build_ltx_flf2v_workflow,
    build_ltx_i2v_workflow,
    load_workflow_template,
)


class TestLtxRenderParams(unittest.TestCase):
    def test_motion_class_strength_table(self):
        self.assertEqual(resolve_i2v_strength("talking"), 0.80)
        self.assertEqual(resolve_i2v_strength("walking"), 0.70)
        self.assertEqual(resolve_i2v_strength("horse_riding"), 0.65)
        self.assertEqual(resolve_i2v_strength("large_reveal"), 0.60)
        self.assertEqual(resolve_i2v_strength("fast_action"), 0.55)
        self.assertEqual(resolve_i2v_strength("emotional"), 0.80)
        self.assertEqual(resolve_i2v_strength("unknown"), 0.70)

    def test_guidance_cfg_table(self):
        self.assertEqual(resolve_cfg("balanced"), 1.0)
        self.assertEqual(resolve_cfg("prompt_follow"), 1.2)
        self.assertEqual(resolve_cfg("strong"), 1.5)
        self.assertEqual(resolve_cfg(None), 1.0)
        self.assertEqual(resolve_cfg("balanced", override=2.0), 1.5)

    def test_last_frame_floor(self):
        self.assertEqual(resolve_last_frame_strength(0.55), 0.85)
        self.assertAlmostEqual(resolve_last_frame_strength(0.80), 0.85)
        self.assertAlmostEqual(resolve_last_frame_strength(0.90), 0.95)

    def test_prefer_stored_vs_recompute(self):
        stored = resolve_clip_render_params(
            {"motion_class": "talking", "i2v_strength": 0.55, "guidance": "strong"},
            prefer_stored=True,
        )
        self.assertEqual(stored["i2v_strength"], 0.55)
        self.assertEqual(stored["cfg"], 1.5)

        fresh = resolve_clip_render_params(
            {"motion_class": "talking", "i2v_strength": 0.55, "guidance": "strong"},
            prefer_stored=False,
        )
        self.assertEqual(fresh["i2v_strength"], 0.80)
        self.assertEqual(fresh["cfg"], 1.5)


class TestNormalizeRenderKnobs(unittest.TestCase):
    def test_normalize_resolves_enums(self):
        scene = {
            "scene_id": "scene_01",
            "shots": [
                {"shot_id": "scene_01_shot_01", "characters_present": []},
                {"shot_id": "scene_01_shot_02", "characters_present": ["char_01"]},
            ],
        }
        raw = {
            "segments": [
                {
                    "segment_id": "scene_01_seg_01",
                    "cut_before": False,
                    "clips": [
                        {
                            "clip_id": "scene_01_seg_01_clip_01",
                            "start_panel_id": "scene_01_shot_01",
                            "end_panel_id": "scene_01_shot_01",
                            "workflow": "i2v",
                            "continuous": False,
                            "duration_seconds": 8,
                            "pace": "slow",
                            "motion_class": "large_reveal",
                            "guidance": "prompt_follow",
                            "motion_prompt": "A cinematic scene of canopy birds. Snappy energetic animation. Quick dynamic motion.",
                        },
                        {
                            "clip_id": "scene_01_seg_01_clip_02",
                            "start_panel_id": "scene_01_shot_02",
                            "end_panel_id": "scene_01_shot_02",
                            "workflow": "i2v",
                            "continuous": False,
                            "duration_seconds": 6,
                            "pace": "medium",
                            "motion_class": "talking",
                            "guidance": "balanced",
                            "motion_prompt": "A cinematic scene of the girl. Natural character animation. Expressive animated motion.",
                        },
                    ],
                }
            ]
        }
        result = normalize_flf_clip_plan(raw, scene, fps=25)
        by_class = {c["motion_class"]: c for c in result["clips"]}
        self.assertIn("large_reveal", by_class)
        self.assertIn("talking", by_class)
        self.assertEqual(by_class["large_reveal"]["i2v_strength"], 0.60)
        self.assertEqual(by_class["large_reveal"]["cfg"], 1.2)
        self.assertEqual(by_class["talking"]["i2v_strength"], 0.80)
        self.assertEqual(by_class["talking"]["cfg"], 1.0)
        self.assertGreaterEqual(by_class["talking"]["last_frame_strength"], 0.85)


class TestWorkflowBuilderOverrides(unittest.TestCase):
    def test_i2v_applies_strength_cfg_resolution(self):
        template = load_workflow_template("ltx-i2v")
        workflow = build_ltx_i2v_workflow(
            template,
            {
                "prompt": "motion",
                "motion_image": "still.png",
                "duration": 8,
                "fps": 25,
                "filename_prefix": "test",
                "i2v_strength": 0.55,
                "cfg": 1.2,
            },
            {"width": 1920, "height": 1088, "seed_base": 7},
        )
        self.assertEqual(workflow["320:312"]["inputs"]["value"], 1920)
        self.assertEqual(workflow["320:299"]["inputs"]["value"], 1088)
        self.assertEqual(workflow["320:296"]["inputs"]["strength"], 0.55)
        self.assertEqual(workflow["320:282"]["inputs"]["cfg"], 1.2)
        self.assertEqual(workflow["320:314"]["inputs"]["cfg"], 1.2)

    def test_flf_applies_first_and_last_strength(self):
        template = load_workflow_template("ltx-flf2v")
        workflow = build_ltx_flf2v_workflow(
            template,
            {
                "prompt": "motion",
                "first_frame_image": "a.png",
                "last_frame_image": "b.png",
                "duration": 6,
                "fps": 25,
                "filename_prefix": "test",
                "i2v_strength": 0.65,
                "last_frame_strength": 0.88,
                "cfg": 1.5,
            },
            {"width": 1920, "height": 1088, "seed_base": 3},
        )
        self.assertEqual(workflow["320:296"]["inputs"]["strength"], 0.65)
        self.assertEqual(workflow["320:330"]["inputs"]["strength"], 0.88)
        self.assertEqual(workflow["320:282"]["inputs"]["cfg"], 1.5)
        self.assertEqual(workflow["320:314"]["inputs"]["cfg"], 1.5)


if __name__ == "__main__":
    unittest.main()
