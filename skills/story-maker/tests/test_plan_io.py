import json
import os
import tempfile
import unittest

from scripts.nodes.plan_io import (
    audio_plan_view,
    load_plan,
    merge_legacy_files,
    save_plan_dict,
    scene_assets_view,
    story_plan_view,
    sync_legacy_state,
    video_shot_plan_view,
)
from schemas.plan import ProductionPlanDraft


def _sample_plan() -> dict:
    return {
        "meta": {
            "story_title": "Test",
            "style": "reel",
            "aesthetic": "warm",
            "target_duration_seconds": 10,
            "duration_tolerance_percent": 15,
            "total_duration_seconds": 4,
            "total_scenes": 1,
            "total_shots": 2,
        },
        "characters": [
            {
                "id": "char_01",
                "name": "A",
                "appearance": "girl",
                "voice_profile": "soft",
            }
        ],
        "scenes": [
            {
                "scene_id": "scene_01",
                "title": "Open",
                "environment": "forest",
                "time_of_day": "morning",
                "lighting": "sun",
                "duration_budget_seconds": 4,
                "assets": {
                    "generate_background": False,
                    "background_reference_mode": "style_anchor",
                    "background_prompt": "",
                    "rationale": "test",
                },
                "audio_scene": {"music_bed": "soft", "ending_state": "resolve"},
                "shots": [
                    {
                        "shot_id": "scene_01_shot_01",
                        "scene_id": "scene_01",
                        "duration_seconds": 2,
                        "characters_present": ["char_01"],
                        "description": "Wide",
                        "audio": {
                            "dialogue": [],
                            "music": "",
                            "sfx": ["birds"],
                            "ambience": "wind",
                        },
                    },
                    {
                        "shot_id": "scene_01_shot_02",
                        "scene_id": "scene_01",
                        "duration_seconds": 2,
                        "characters_present": ["char_01"],
                        "description": "Close",
                        "audio": {"dialogue": [], "sfx": [], "ambience": ""},
                    },
                ],
                "video_shots": [
                    {
                        "video_shot_id": "scene_01_vshot_01",
                        "scene_id": "scene_01",
                        "panel_ids": ["scene_01_shot_01", "scene_01_shot_02"],
                        "anchor_panel_id": "scene_01_shot_01",
                        "duration_seconds": 4,
                        "motion_arc": "Walks forward",
                        "pace": "fast",
                    }
                ],
            }
        ],
    }


class TestPlanIo(unittest.TestCase):
    def test_round_trip_and_views(self):
        plan = _sample_plan()
        ProductionPlanDraft(
            meta=plan["meta"],
            characters=plan["characters"],
            scenes=plan["scenes"],
        ).to_plan()
        story = story_plan_view(plan)
        self.assertNotIn("audio", story["scenes"][0]["shots"][0])
        audio = audio_plan_view(plan)
        self.assertIn("scene_01_shot_01", audio["shots"])
        self.assertEqual(audio["shots"]["scene_01_shot_01"]["audio"]["sfx"], ["birds"])
        assets = scene_assets_view(plan)
        self.assertFalse(assets["scenes"][0]["generate_background"])
        video = video_shot_plan_view(plan)
        self.assertEqual(len(video["scenes"][0]["video_shots"]), 1)

    def test_legacy_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            story = story_plan_view(_sample_plan())
            with open(os.path.join(tmp, "story_plan.json"), "w", encoding="utf-8") as f:
                json.dump(story, f)
            with open(os.path.join(tmp, "audio_plan.json"), "w", encoding="utf-8") as f:
                json.dump(audio_plan_view(_sample_plan()), f)
            with open(os.path.join(tmp, "scene_assets.json"), "w", encoding="utf-8") as f:
                json.dump(scene_assets_view(_sample_plan()), f)
            with open(os.path.join(tmp, "video_shot_plan.json"), "w", encoding="utf-8") as f:
                json.dump(video_shot_plan_view(_sample_plan()), f)

            merged = merge_legacy_files(tmp)
            self.assertIsNotNone(merged)
            self.assertEqual(len(merged["scenes"][0]["video_shots"]), 1)
            self.assertIn("audio", merged["scenes"][0]["shots"][0])

            loaded = load_plan(tmp, write_if_legacy=True)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "plan.json")))
            self.assertEqual(loaded["meta"]["story_title"], "Test")

    def test_sync_legacy_state(self):
        state: dict = {}
        sync_legacy_state(state, _sample_plan())
        self.assertIn("plan_content", state)
        self.assertIn("story_plan_content", state)
        self.assertIn("audio_plan_content", state)
        self.assertIn("scene_assets_content", state)
        self.assertIn("video_shot_plan_content", state)

    def test_save_plan_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = save_plan_dict(tmp, _sample_plan())
            self.assertTrue(os.path.isfile(path))
            loaded = load_plan(tmp)
            self.assertEqual(loaded["characters"][0]["id"], "char_01")


if __name__ == "__main__":
    unittest.main()
