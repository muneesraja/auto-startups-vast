import os
import sys
import unittest

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

from scripts.nodes.flf_storyboard_planner import (
    allows_flf_continuous,
    build_flf_planner_user_text,
    cast_allows_continuous,
    derive_segments_from_clips,
    migrate_legacy_flf_scene,
    normalize_flf_clip_plan,
    panel_cast_lookup,
    panel_grid_map,
    same_row_pairs,
    scene_paper_budgets,
    scene_paper_duration_budget,
    snap_director_clip_duration,
)
from scripts.nodes.storyboard_director_nodes import (
    is_director_video_mode,
    load_or_migrate_scene_plan,
)


def _scene():
    return {
        "scene_id": "scene_01",
        "duration_budget_seconds": 24,
        "shots": [
            {
                "shot_id": "scene_01_shot_01",
                "characters_present": [],
                "motion_intent": "Birds cross the canopy",
                "camera_intent": "Wide reveal",
            },
            {
                "shot_id": "scene_01_shot_02",
                "characters_present": ["char_01", "char_02", "char_03", "char_04"],
                "motion_intent": "Girl peers at the gate",
                "camera_intent": "Push in",
            },
            {
                "shot_id": "scene_01_shot_03",
                "characters_present": ["char_01", "char_02"],
                "motion_intent": "Hands pull the latch",
                "camera_intent": "Closer on latch",
            },
            {
                "shot_id": "scene_01_shot_04",
                "characters_present": ["char_01", "char_02"],
                "motion_intent": "Gates swing open",
                "camera_intent": "Dolly through",
            },
            {
                "shot_id": "scene_01_shot_05",
                "characters_present": ["char_06"],
                "motion_intent": "Deer lift heads",
                "camera_intent": "Wide on meadow",
            },
        ],
    }


_SCENE_PAPER = """# Scene Paper

## Scene 01 — The Sanctuary
**Duration budget:** 24s
**Panel target:** 10

### Panel 01
- **CAM:** WIDE
"""


class TestFlfStoryboardPlanner(unittest.TestCase):
    def test_cast_allows_continuous(self):
        cast = panel_cast_lookup(_scene())
        self.assertTrue(
            cast_allows_continuous("scene_01_shot_02", "scene_01_shot_03", cast)
        )
        self.assertFalse(
            cast_allows_continuous("scene_01_shot_01", "scene_01_shot_02", cast)
        )
        self.assertFalse(
            cast_allows_continuous("scene_01_shot_04", "scene_01_shot_05", cast)
        )

    def test_normalize_forces_cut_on_cast_jump(self):
        raw = {
            "clips": [
                {
                    "first_panel_id": "scene_01_shot_01",
                    "last_panel_id": "scene_01_shot_02",
                    "continuous": True,
                    "mode": "flf2v",
                    "duration_seconds": 8,
                    "motion_prompt": "Family walks into empty clearing.",
                }
            ]
        }
        out = normalize_flf_clip_plan(raw, _scene(), duration_budget_seconds=24)
        # Cast jump must not remain a continuous FLF morph
        flf_jump = [
            c
            for c in out["clips"]
            if c["start_panel_id"] == "scene_01_shot_01"
            and c["end_panel_id"] == "scene_01_shot_02"
            and c["workflow"] == "flf2v"
            and c["continuous"]
        ]
        self.assertEqual(flf_jump, [])
        self.assertTrue(any("cast jump" in r or "split" in r for r in out["repairs"]))

    def test_normalize_adjacent_continuous_ok(self):
        raw = {
            "segments": [
                {
                    "segment_id": "scene_01_seg_01",
                    "cut_before": False,
                    "clips": [
                        {
                            "start_panel_id": "scene_01_shot_01",
                            "end_panel_id": "scene_01_shot_01",
                            "workflow": "i2v",
                            "continuous": False,
                            "duration_seconds": 4,
                            "motion_prompt": "Light sweeps the empty sanctuary.",
                        }
                    ],
                },
                {
                    "segment_id": "scene_01_seg_02",
                    "cut_before": True,
                    "clips": [
                        {
                            "start_panel_id": "scene_01_shot_02",
                            "end_panel_id": "scene_01_shot_03",
                            "workflow": "flf2v",
                            "continuous": True,
                            "duration_seconds": 6,
                            "motion_prompt": "Girl and father move from peer to latch pull.",
                        },
                        {
                            "start_panel_id": "scene_01_shot_03",
                            "end_panel_id": "scene_01_shot_04",
                            "workflow": "flf2v",
                            "continuous": True,
                            "duration_seconds": 6,
                            "motion_prompt": "Hands finish the latch and gates swing.",
                        },
                    ],
                },
                {
                    "segment_id": "scene_01_seg_03",
                    "cut_before": True,
                    "clips": [
                        {
                            "start_panel_id": "scene_01_shot_05",
                            "end_panel_id": "scene_01_shot_05",
                            "workflow": "i2v",
                            "continuous": False,
                            "duration_seconds": 4,
                            "motion_prompt": "Deer hold in the meadow light.",
                        }
                    ],
                },
            ]
        }
        out = normalize_flf_clip_plan(raw, _scene(), duration_budget_seconds=24)
        covered = set()
        for c in out["clips"]:
            covered.add(c["start_panel_id"])
            covered.add(c["end_panel_id"])
        self.assertEqual(
            covered,
            {
                "scene_01_shot_01",
                "scene_01_shot_02",
                "scene_01_shot_03",
                "scene_01_shot_04",
                "scene_01_shot_05",
            },
        )
        cont = [
            c
            for c in out["clips"]
            if c["start_panel_id"] == "scene_01_shot_02"
            and c["end_panel_id"] == "scene_01_shot_03"
        ][0]
        self.assertTrue(cont["continuous"])
        self.assertEqual(cont["workflow"], "flf2v")
        # Shared-endpoint chain in one segment
        seg = next(
            s
            for s in out["segments"]
            if any(
                c["start_panel_id"] == "scene_01_shot_02"
                and c["end_panel_id"] == "scene_01_shot_03"
                for c in s["clips"]
            )
        )
        ends = [(c["start_panel_id"], c["end_panel_id"]) for c in seg["clips"]]
        self.assertIn(("scene_01_shot_02", "scene_01_shot_03"), ends)
        self.assertIn(("scene_01_shot_03", "scene_01_shot_04"), ends)

    def test_normalize_fills_missing_coverage(self):
        raw = {"clips": []}
        out = normalize_flf_clip_plan(raw, _scene(), duration_budget_seconds=24)
        covered = set()
        for c in out["clips"]:
            covered.add(c["start_panel_id"])
            covered.add(c["end_panel_id"])
        self.assertEqual(len(covered), 5)
        self.assertTrue(out["repairs"])

    def test_solo_i2v_segment(self):
        raw = {
            "clips": [
                {
                    "start_panel_id": "scene_01_shot_01",
                    "end_panel_id": "scene_01_shot_01",
                    "workflow": "i2v",
                    "duration_seconds": 6,
                    "motion_prompt": "Sanctuary breathe.",
                }
            ]
        }
        out = normalize_flf_clip_plan(raw, _scene(), duration_budget_seconds=24)
        first = out["clips"][0]
        self.assertEqual(first["workflow"], "i2v")
        self.assertEqual(first["start_panel_id"], first["end_panel_id"])

    def test_reject_flf_across_hard_cut(self):
        raw = {
            "clips": [
                {
                    "start_panel_id": "scene_01_shot_04",
                    "end_panel_id": "scene_01_shot_05",
                    "continuous": False,
                    "workflow": "flf2v",
                    "duration_seconds": 6,
                    "motion_prompt": "Bad morph across subjects.",
                }
            ]
        }
        out = normalize_flf_clip_plan(raw, _scene(), duration_budget_seconds=24)
        bad = [
            c
            for c in out["clips"]
            if c["start_panel_id"] == "scene_01_shot_04"
            and c["end_panel_id"] == "scene_01_shot_05"
            and c["workflow"] == "flf2v"
        ]
        self.assertEqual(bad, [])

    def test_grid_map_and_same_row_pairs(self):
        ids = [f"scene_01_shot_{i:02d}" for i in range(1, 11)]
        grid = panel_grid_map(ids, columns=2)
        self.assertEqual(grid[6]["row"], 4)
        self.assertEqual(grid[6]["col"], 1)
        self.assertEqual(grid[7]["row"], 4)
        self.assertEqual(grid[7]["col"], 2)
        pairs = same_row_pairs(ids, columns=2)
        self.assertIn(("scene_01_shot_07", "scene_01_shot_08"), pairs)

    def test_user_text_includes_grid_and_camera_hint(self):
        text = build_flf_planner_user_text(_scene(), panel_ids_in_order := [
            s["shot_id"] for s in _scene()["shots"]
        ])
        self.assertIn("Storyboard grid", text)
        self.assertIn("Same-row FLF candidate pairs", text)
        self.assertIn("camera pan", text.lower())
        self.assertIn("row 1 col 1", text)

    def test_adjacent_camera_motivated_flf_allowed(self):
        # Family at gate → deer: adjacent cast jump, but continuous camera pan OK
        cast = panel_cast_lookup(_scene())
        self.assertFalse(
            cast_allows_continuous("scene_01_shot_04", "scene_01_shot_05", cast)
        )
        ids = [s["shot_id"] for s in _scene()["shots"]]
        self.assertTrue(
            allows_flf_continuous(
                "scene_01_shot_04",
                "scene_01_shot_05",
                ids,
                cast,
                continuous=True,
            )
        )
        raw = {
            "clips": [
                {
                    "start_panel_id": "scene_01_shot_04",
                    "end_panel_id": "scene_01_shot_05",
                    "continuous": True,
                    "workflow": "flf2v",
                    "duration_seconds": 8,
                    "motion_prompt": (
                        "Camera pans from the open gate along the pointing path "
                        "into the meadow where deer lift their heads."
                    ),
                }
            ]
        }
        out = normalize_flf_clip_plan(raw, _scene())
        flf = [
            c
            for c in out["clips"]
            if c["start_panel_id"] == "scene_01_shot_04"
            and c["end_panel_id"] == "scene_01_shot_05"
            and c["workflow"] == "flf2v"
            and c["continuous"]
        ]
        self.assertEqual(len(flf), 1)
        self.assertTrue(any("camera-motivated" in r for r in out["repairs"]))

    def test_empty_to_cast_still_blocked(self):
        cast = panel_cast_lookup(_scene())
        ids = [s["shot_id"] for s in _scene()["shots"]]
        self.assertFalse(
            allows_flf_continuous(
                "scene_01_shot_01",
                "scene_01_shot_02",
                ids,
                cast,
                continuous=True,
            )
        )

    def test_duration_snap_prefers_ltx_primary(self):
        self.assertEqual(snap_director_clip_duration(8), 8)
        self.assertEqual(snap_director_clip_duration(6), 6)
        self.assertEqual(snap_director_clip_duration(10), 10)
        self.assertEqual(snap_director_clip_duration(3), 3)
        self.assertEqual(snap_director_clip_duration(12), 10)
        self.assertIn(snap_director_clip_duration(7), (6, 8))

    def test_director_chooses_scene_total(self):
        raw = {
            "clips": [
                {
                    "start_panel_id": "scene_01_shot_01",
                    "end_panel_id": "scene_01_shot_01",
                    "workflow": "i2v",
                    "duration_seconds": 8,
                    "motion_prompt": "Establish.",
                },
                {
                    "start_panel_id": "scene_01_shot_02",
                    "end_panel_id": "scene_01_shot_03",
                    "workflow": "flf2v",
                    "continuous": True,
                    "duration_seconds": 10,
                    "motion_prompt": "Gate action.",
                },
            ]
        }
        out = normalize_flf_clip_plan(raw, _scene())
        # Scene total comes from clip sum, not scene_paper / plan 24s field
        self.assertEqual(out["duration_total_seconds"], out["duration_budget_seconds"])
        self.assertGreaterEqual(out["duration_total_seconds"], 18)

    def test_scene_paper_budget_helpers_still_parse(self):
        self.assertEqual(scene_paper_duration_budget(_SCENE_PAPER, "scene_01"), 24)
        self.assertEqual(scene_paper_budgets(_SCENE_PAPER)["scene_01"], 24)

    def test_chain_shared_endpoints(self):
        clips = [
            {
                "clip_id": "a",
                "start_panel_id": "scene_01_shot_02",
                "end_panel_id": "scene_01_shot_03",
                "first_panel_id": "scene_01_shot_02",
                "last_panel_id": "scene_01_shot_03",
                "workflow": "flf2v",
                "continuous": True,
                "duration_seconds": 6,
                "motion_prompt": "a",
                "_cut_before": False,
            },
            {
                "clip_id": "b",
                "start_panel_id": "scene_01_shot_03",
                "end_panel_id": "scene_01_shot_04",
                "first_panel_id": "scene_01_shot_03",
                "last_panel_id": "scene_01_shot_04",
                "workflow": "flf2v",
                "continuous": True,
                "duration_seconds": 6,
                "motion_prompt": "b",
                "_cut_before": False,
            },
        ]
        segs = derive_segments_from_clips(clips, "scene_01")
        self.assertEqual(len(segs), 1)
        self.assertEqual(len(segs[0]["clips"]), 2)
        self.assertEqual(segs[0]["clips"][0]["end_panel_id"], segs[0]["clips"][1]["start_panel_id"])

    def test_legacy_migration(self):
        legacy = {
            "scene_id": "scene_01",
            "clips": [
                {
                    "clip_id": "scene_01_flf_01",
                    "first_panel_id": "scene_01_shot_01",
                    "last_panel_id": "scene_01_shot_01",
                    "continuous": False,
                    "mode": "i2v_hold",
                    "duration_seconds": 6,
                    "motion_prompt": "Hold.",
                }
            ],
        }
        out = migrate_legacy_flf_scene(legacy, _scene())
        self.assertTrue(out.get("segments"))
        self.assertEqual(out["clips"][0]["workflow"], "i2v")

    def test_load_or_migrate_prefers_modern(self):
        specs = {
            "storyboard_video_scenes": {
                "scene_01": {
                    "scene_id": "scene_01",
                    "segments": [{"segment_id": "s", "clips": [{"clip_id": "c"}]}],
                    "clips": [{"clip_id": "c"}],
                    "status": "planned",
                }
            },
            "flf2v_scenes": {
                "scene_01": {"scene_id": "scene_01", "clips": [{"clip_id": "legacy"}]}
            },
        }
        plan = load_or_migrate_scene_plan(specs, "scene_01", _scene())
        self.assertEqual(plan["clips"][0]["clip_id"], "c")

    def test_director_mode_gate(self):
        class _Ctx:
            state = {"storyboard_video_mode": "director"}

        self.assertTrue(is_director_video_mode(_Ctx()))
        _Ctx.state = {"storyboard_video_mode": "fallback"}
        self.assertFalse(is_director_video_mode(_Ctx()))


if __name__ == "__main__":
    unittest.main()
