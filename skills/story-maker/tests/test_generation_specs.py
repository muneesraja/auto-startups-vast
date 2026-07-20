import unittest

from schemas.generation import (
    DirectorGuideFrame,
    DirectorRenderUnit,
    GenerationSpecs,
    StoryboardVideoScenePlan,
)


class TestGenerationSpecs(unittest.TestCase):
    def test_valid_specs(self):
        specs = GenerationSpecs(
            character_sheets={
                "char_01": {
                    "character_id": "char_01",
                    "sheet_prompt": "turnaround sheet...",
                }
            },
            shot_images={
                "scene_01_shot_01": {
                    "shot_id": "scene_01_shot_01",
                    "generation_mode": "grok_edit",
                    "reference_strategy": "char_sheets_only",
                    "reference_slots": [
                        {"role": "character_sheet", "asset_id": "char_01", "priority": 0}
                    ],
                    "image_prompt": "Monkey on branch...",
                }
            },
            motion={
                "scene_01_shot_01": {
                    "shot_id": "scene_01_shot_01",
                    "motion_prompt": "The monkey swings...",
                    "duration_seconds": 8,
                }
            },
        )
        self.assertIn("char_01", specs.character_sheets)

    def test_key_mismatch_raises(self):
        with self.assertRaises(ValueError):
            GenerationSpecs(
                shot_images={
                    "scene_01_shot_01": {
                        "shot_id": "wrong_id",
                        "generation_mode": "grok_edit",
                        "reference_strategy": "char_sheets_only",
                        "image_prompt": "test",
                    }
                }
            )


class TestDirectorSceneSchema(unittest.TestCase):
    def test_guide_frame_placement_resolves(self):
        start = DirectorGuideFrame(panel_id="p1", placement="start")
        mid = DirectorGuideFrame(panel_id="p2", placement="middle")
        end = DirectorGuideFrame(panel_id="p3", placement="end")
        self.assertEqual(start.start_ratio, 0.0)
        self.assertFalse(start.is_end_frame)
        self.assertEqual(mid.start_ratio, 0.5)
        self.assertFalse(mid.is_end_frame)
        self.assertEqual(end.start_ratio, 1.0)
        self.assertTrue(end.is_end_frame)

    def test_render_unit_requires_guide(self):
        with self.assertRaises(ValueError):
            DirectorRenderUnit(unit_id="u1", duration_seconds=6)

    def test_scene_plan_syncs_duration_from_clips(self):
        plan = StoryboardVideoScenePlan(
            scene_id="scene_01",
            duration_total_seconds=99,
            clips=[
                {
                    "clip_id": "c1",
                    "segment_id": "s1",
                    "start_panel_id": "a",
                    "end_panel_id": "a",
                    "workflow": "i2v",
                    "duration_seconds": 10,
                },
                {
                    "clip_id": "c2",
                    "segment_id": "s1",
                    "start_panel_id": "b",
                    "end_panel_id": "c",
                    "workflow": "flf2v",
                    "continuous": True,
                    "duration_seconds": 12,
                    "guide_frames": [
                        {"panel_id": "b", "placement": "start"},
                        {"panel_id": "c", "placement": "end"},
                    ],
                },
            ],
        )
        self.assertEqual(plan.duration_total_seconds, 22)
        self.assertEqual(plan.duration_budget_seconds, 22)

    def test_scene_plan_accepts_render_units(self):
        plan = StoryboardVideoScenePlan(
            scene_id="scene_07",
            scene_global_prompt="Warm meadow light.",
            render_units=[
                {
                    "unit_id": "scene_07_unit_01",
                    "cut_before": False,
                    "duration_seconds": 12,
                    "guide_frames": [
                        {"panel_id": "scene_07_shot_01", "placement": "start"},
                        {
                            "panel_id": "scene_07_shot_02",
                            "placement": "middle",
                            "start_ratio": 0.45,
                        },
                        {"panel_id": "scene_07_shot_03", "placement": "end"},
                    ],
                    "motion_segments": [
                        {
                            "start_ratio": 0.0,
                            "end_ratio": 1.0,
                            "prompt": "Camera pushes through the feed beat.",
                        }
                    ],
                    "motion_prompt": "Camera pushes through the feed beat.",
                }
            ],
        )
        self.assertEqual(len(plan.render_units), 1)
        self.assertEqual(len(plan.render_units[0].guide_frames), 3)
        self.assertTrue(plan.render_units[0].guide_frames[-1].is_end_frame)


if __name__ == "__main__":
    unittest.main()
