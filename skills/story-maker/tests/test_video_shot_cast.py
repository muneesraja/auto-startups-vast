import os
import sys
import tempfile
import unittest

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

from scripts.nodes.video_shot_cast import (
    build_environment_motion_arc,
    chunk_panels_by_anchor_cast,
    ensure_env_safe_motion_arc,
    motion_arc_mentions_roster,
    split_video_shots_by_anchor_cast,
    synthesize_cast_coherent_video_shots,
)


class TestVideoShotCast(unittest.TestCase):
    def test_chunk_empty_then_cast_splits(self):
        panels = ["p1", "p2", "p3"]
        cast = {
            "p1": frozenset(),
            "p2": frozenset({"char_01", "char_02"}),
            "p3": frozenset({"char_01"}),
        }
        groups = chunk_panels_by_anchor_cast(panels, cast)
        self.assertEqual(groups, [["p1"], ["p2", "p3"]])

    def test_chunk_cast_growth_splits(self):
        panels = ["p1", "p2", "p3"]
        cast = {
            "p1": frozenset({"char_01", "char_02"}),
            "p2": frozenset({"char_01", "char_02"}),
            "p3": frozenset({"char_01", "char_02", "char_03"}),
        }
        groups = chunk_panels_by_anchor_cast(panels, cast)
        self.assertEqual(groups, [["p1", "p2"], ["p3"]])

    def test_chunk_subset_stays_grouped(self):
        panels = ["p1", "p2"]
        cast = {
            "p1": frozenset({"char_01", "char_02"}),
            "p2": frozenset({"char_01"}),
        }
        groups = chunk_panels_by_anchor_cast(panels, cast)
        self.assertEqual(groups, [["p1", "p2"]])

    def test_empty_motion_arc_rewrite(self):
        chars = [{"id": "char_01", "name": "Naila"}]
        member = [
            {
                "shot_id": "p1",
                "motion_intent": "Morning light spreads across the grounds",
                "camera_intent": "Wide establishing crane",
            }
        ]
        arc = ensure_env_safe_motion_arc(
            "First Naila walks in then father opens the gate.",
            anchor_cast=frozenset(),
            member_shots=member,
            characters=chars,
            duration_seconds=8,
        )
        self.assertFalse(motion_arc_mentions_roster(arc, chars))
        self.assertIn("light", arc.lower())

    def test_build_environment_motion_arc(self):
        arc = build_environment_motion_arc(
            [{"motion_intent": "Birds cross the canopy", "camera_intent": "Slow upward reveal"}],
            duration_seconds=8,
        )
        self.assertIn("birds", arc.lower())
        self.assertIn("reveal", arc.lower())

    def test_split_video_shots_renumbers(self):
        scene = {
            "scene_id": "scene_01",
            "shots": [
                {"shot_id": "scene_01_shot_01", "characters_present": [], "motion_intent": "light"},
                {
                    "shot_id": "scene_01_shot_02",
                    "characters_present": ["char_01"],
                    "motion_intent": "girl peers",
                },
                {
                    "shot_id": "scene_01_shot_03",
                    "characters_present": ["char_01"],
                    "motion_intent": "hand on latch",
                },
            ],
        }
        video_shots = [
            {
                "video_shot_id": "scene_01_vshot_01",
                "panel_ids": [
                    "scene_01_shot_01",
                    "scene_01_shot_02",
                    "scene_01_shot_03",
                ],
                "anchor_panel_id": "scene_01_shot_01",
                "duration_seconds": 11,
                "motion_arc": "Naila approaches then pulls the latch.",
                "pace": "fast",
            }
        ]
        out = split_video_shots_by_anchor_cast(
            video_shots,
            scene,
            characters=[{"id": "char_01", "name": "Naila"}],
        )
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["panel_ids"], ["scene_01_shot_01"])
        self.assertEqual(out[0]["video_shot_id"], "scene_01_vshot_01")
        self.assertEqual(
            out[1]["panel_ids"], ["scene_01_shot_02", "scene_01_shot_03"]
        )
        self.assertEqual(out[1]["video_shot_id"], "scene_01_vshot_02")
        self.assertFalse(
            motion_arc_mentions_roster(
                out[0]["motion_arc"], [{"id": "char_01", "name": "Naila"}]
            )
        )
        self.assertNotIn("Naila", out[0]["motion_arc"])
        self.assertNotIn("family", out[0]["motion_arc"].lower())
        # Character group should not keep the empty establishing parent arc.
        self.assertNotIn("sunlit sanctuary", out[1]["motion_arc"].lower())

    def test_synthesize_cast_aware(self):
        story = {
            "characters": [
                {"id": "char_01", "name": "Naila"},
                {"id": "char_03", "name": "Azhagi"},
            ],
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "shots": [
                        {"shot_id": "s1", "characters_present": []},
                        {"shot_id": "s2", "characters_present": ["char_01"]},
                        {"shot_id": "s3", "characters_present": ["char_01"]},
                        {"shot_id": "s4", "characters_present": ["char_01", "char_03"]},
                    ],
                }
            ],
        }
        out = synthesize_cast_coherent_video_shots(story, max_group_size=3)
        groups = [vs["panel_ids"] for vs in out["scenes"][0]["video_shots"]]
        self.assertEqual(groups[0], ["s1"])
        self.assertIn(["s2", "s3"], groups)
        self.assertIn(["s4"], groups)

    def test_normalize_applies_cast_split(self):
        from scripts.nodes.save_artifact_nodes import _normalize_video_shot_plan

        story = {
            "characters": [{"id": "char_01", "name": "Naila"}],
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "duration_budget_seconds": 16,
                    "shots": [
                        {
                            "shot_id": "scene_01_shot_01",
                            "duration_seconds": 1,
                            "characters_present": [],
                            "motion_intent": "Birds cross",
                            "camera_intent": "Wide reveal",
                        },
                        {
                            "shot_id": "scene_01_shot_02",
                            "duration_seconds": 1,
                            "characters_present": ["char_01"],
                            "motion_intent": "Girl peers",
                        },
                    ],
                }
            ],
        }
        plan = {
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "video_shots": [
                        {
                            "video_shot_id": "scene_01_vshot_01",
                            "panel_ids": ["scene_01_shot_01", "scene_01_shot_02"],
                            "anchor_panel_id": "scene_01_shot_01",
                            "duration_seconds": 8,
                            "motion_arc": "Naila walks into the empty gate.",
                            "pace": "fast",
                        }
                    ],
                }
            ]
        }
        out = _normalize_video_shot_plan(plan, story)
        vshots = out["scenes"][0]["video_shots"]
        self.assertEqual(len(vshots), 2)
        self.assertEqual(vshots[0]["panel_ids"], ["scene_01_shot_01"])
        self.assertEqual(vshots[1]["panel_ids"], ["scene_01_shot_02"])

    def test_repair_script_clears_vshot_motion(self):
        from scripts.repair_video_shots_cast import repair_plan_video_shots_cast_coherence
        import json

        with tempfile.TemporaryDirectory() as tmp:
            plan = {
                "meta": {"story_title": "t", "style": "reel_v2", "aesthetic": "x"},
                "characters": [{"id": "char_01", "name": "Naila", "appearance": "a", "voice_profile": "v"}],
                "locations": [],
                "scenes": [
                    {
                        "scene_id": "scene_01",
                        "title": "S",
                        "environment": "forest",
                        "time_of_day": "day",
                        "lighting": "warm",
                        "duration_budget_seconds": 16,
                        "shots": [
                            {
                                "shot_id": "scene_01_shot_01",
                                "scene_id": "scene_01",
                                "duration_seconds": 1,
                                "description": "empty",
                                "motion_intent": "light",
                                "camera_intent": "crane",
                                "characters_present": [],
                                "pace": "fast",
                                "ltx_shot_type": "establishing",
                                "ltx_complexity": "simple",
                                "audio": {},
                            },
                            {
                                "shot_id": "scene_01_shot_02",
                                "scene_id": "scene_01",
                                "duration_seconds": 1,
                                "description": "girl",
                                "motion_intent": "peers",
                                "camera_intent": "push",
                                "characters_present": ["char_01"],
                                "pace": "fast",
                                "ltx_shot_type": "action",
                                "ltx_complexity": "simple",
                                "audio": {},
                            },
                        ],
                        "video_shots": [
                            {
                                "video_shot_id": "scene_01_vshot_01",
                                "scene_id": "scene_01",
                                "panel_ids": ["scene_01_shot_01", "scene_01_shot_02"],
                                "anchor_panel_id": "scene_01_shot_01",
                                "duration_seconds": 8,
                                "motion_arc": "Naila enters.",
                                "pace": "fast",
                            }
                        ],
                        "assets": {
                            "generate_background": False,
                            "background_reference_mode": "style_anchor",
                            "background_prompt": "",
                            "rationale": "x",
                        },
                        "audio_scene": {"music_bed": "", "ending_state": ""},
                    }
                ],
            }
            with open(os.path.join(tmp, "plan.json"), "w", encoding="utf-8") as f:
                json.dump(plan, f)
            with open(os.path.join(tmp, "generation_specs.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "motion": {
                            "scene_01_shot_01": {"status": "pending"},
                            "scene_01_vshot_01": {
                                "status": "completed",
                                "motion_prompt": "bad",
                            },
                        }
                    },
                    f,
                )
            summary = repair_plan_video_shots_cast_coherence(tmp)
            self.assertEqual(summary["video_shots_before"], 1)
            self.assertEqual(summary["video_shots_after"], 2)
            with open(os.path.join(tmp, "plan.json"), encoding="utf-8") as f:
                repaired = json.load(f)
            self.assertEqual(len(repaired["scenes"][0]["video_shots"]), 2)
            with open(os.path.join(tmp, "generation_specs.json"), encoding="utf-8") as f:
                specs = json.load(f)
            self.assertNotIn("scene_01_vshot_01", specs["motion"])
            self.assertIn("scene_01_shot_01", specs["motion"])


if __name__ == "__main__":
    unittest.main()
