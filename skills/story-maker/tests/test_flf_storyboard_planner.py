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
    director_chain_mode_enabled,
    derive_segments_from_clips,
    migrate_legacy_flf_scene,
    normalize_flf_clip_plan,
    panel_ids_in_order,
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
    def test_chain_mode_default_follows_director_flag(self):
        old_mode = os.environ.get("STORYBOARD_VIDEO_MODE")
        old_chain = os.environ.get("STORY_MAKER_DIRECTOR_CHAIN")
        try:
            os.environ.pop("STORY_MAKER_DIRECTOR_CHAIN", None)
            os.environ["STORYBOARD_VIDEO_MODE"] = "fallback"
            self.assertFalse(director_chain_mode_enabled())
            os.environ["STORYBOARD_VIDEO_MODE"] = "director"
            self.assertTrue(director_chain_mode_enabled())
            os.environ["STORY_MAKER_DIRECTOR_CHAIN"] = "0"
            self.assertFalse(director_chain_mode_enabled())
        finally:
            if old_mode is None:
                os.environ.pop("STORYBOARD_VIDEO_MODE", None)
            else:
                os.environ["STORYBOARD_VIDEO_MODE"] = old_mode
            if old_chain is None:
                os.environ.pop("STORY_MAKER_DIRECTOR_CHAIN", None)
            else:
                os.environ["STORY_MAKER_DIRECTOR_CHAIN"] = old_chain

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
        self.assertEqual(snap_director_clip_duration(10), 12)  # snaps to nearest primary
        self.assertEqual(snap_director_clip_duration(9), 12)  # floor snaps up to primary
        self.assertEqual(snap_director_clip_duration(12), 12)
        self.assertEqual(snap_director_clip_duration(15), 15)
        self.assertEqual(snap_director_clip_duration(16), 15)
        self.assertEqual(snap_director_clip_duration(6), 12)  # floor then primary
        self.assertEqual(snap_director_clip_duration(3), 12)  # floor then primary
        self.assertIn(snap_director_clip_duration(11), (12, 15))
        self.assertIn(snap_director_clip_duration(13), (12, 15))
        self.assertIn(snap_director_clip_duration(14), (12, 15))

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

    def test_normalize_preserves_director_motion_segments(self):
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
                            "motion_class": "large_reveal",
                            "guidance": "balanced",
                            "global_prompt": "Warm sanctuary light, cinematic 3D.",
                            "motion_segments": [
                                {
                                    "start_ratio": 0.0,
                                    "end_ratio": 0.5,
                                    "prompt": "Dust drifts; camera pushes in.",
                                },
                                {
                                    "start_ratio": 0.5,
                                    "end_ratio": 1.0,
                                    "prompt": "Push settles; faint birdsong.",
                                },
                            ],
                            "motion_prompt": "Dust drifts; camera pushes in. Push settles; faint birdsong.",
                        }
                    ],
                }
            ]
        }
        out = normalize_flf_clip_plan(raw, _scene(), duration_budget_seconds=24)
        clip = out["clips"][0]
        self.assertEqual(clip["global_prompt"], "Warm sanctuary light, cinematic 3D.")
        self.assertEqual(len(clip["motion_segments"]), 2)
        self.assertEqual(clip["motion_segments"][0]["start_ratio"], 0.0)
        self.assertEqual(clip["motion_segments"][-1]["end_ratio"], 1.0)
        self.assertTrue(clip.get("guide_frames"))

    def test_normalize_render_units_multi_guide(self):
        raw = {
            "duration_total_seconds": 8,
            "scene_global_prompt": "Meadow daylight, cinematic 3D.",
            "render_units": [
                {
                    "unit_id": "scene_01_unit_01",
                    "cut_before": False,
                    "duration_seconds": 8,
                    "pace": "medium",
                    "motion_class": "walking",
                    "guidance": "balanced",
                    "guide_frames": [
                        {"panel_id": "scene_01_shot_02", "placement": "start"},
                        {
                            "panel_id": "scene_01_shot_03",
                            "placement": "middle",
                            "start_ratio": 0.5,
                        },
                        {"panel_id": "scene_01_shot_04", "placement": "end"},
                    ],
                    "motion_segments": [
                        {
                            "start_ratio": 0.0,
                            "end_ratio": 0.5,
                            "prompt": "Family moves to the latch.",
                        },
                        {
                            "start_ratio": 0.5,
                            "end_ratio": 1.0,
                            "prompt": "Gate begins to open; camera settles.",
                        },
                    ],
                    "motion_prompt": "Family moves to the latch. Gate begins to open; camera settles.",
                    "rationale": "Multi-guide continuous gate open.",
                }
            ],
        }
        out = normalize_flf_clip_plan(raw, _scene())
        self.assertEqual(out["scene_global_prompt"], "Meadow daylight, cinematic 3D.")
        clip = next(
            c
            for c in out["clips"]
            if len(c.get("guide_frames") or []) >= 3
            and c.get("start_panel_id") == "scene_01_shot_02"
        )
        self.assertEqual(clip["end_panel_id"], "scene_01_shot_04")
        self.assertEqual(len(clip["guide_frames"]), 3)
        self.assertTrue(clip["continuous"])
        self.assertEqual(clip["workflow"], "flf2v")
        self.assertGreaterEqual(out["duration_total_seconds"], 8)
        self.assertTrue(
            any(len(u.get("guide_frames") or []) >= 3 for u in out["render_units"])
        )
        self.assertTrue(any("keep multi-guide" in r for r in out["repairs"]))

    def test_normalize_multi_guide_with_cast_reveal_chain(self):
        """Adjacent guide hops can reveal new cast; first→last subset alone may fail."""
        scene = {
            "scene_id": "scene_07",
            "shots": [
                {
                    "shot_id": "scene_07_shot_03",
                    "characters_present": ["char_03"],
                    "motion_intent": "Dog arrives",
                    "camera_intent": "Track",
                },
                {
                    "shot_id": "scene_07_shot_04",
                    "characters_present": ["char_03", "char_02"],
                    "motion_intent": "Looks to father",
                    "camera_intent": "Widen",
                },
                {
                    "shot_id": "scene_07_shot_05",
                    "characters_present": ["char_03", "char_02"],
                    "motion_intent": "Urgent bark",
                    "camera_intent": "Close",
                },
            ],
        }
        raw = {
            "duration_total_seconds": 8,
            "render_units": [
                {
                    "unit_id": "scene_07_unit_multi",
                    "cut_before": False,
                    "duration_seconds": 8,
                    "guide_frames": [
                        {"panel_id": "scene_07_shot_03", "placement": "start"},
                        {
                            "panel_id": "scene_07_shot_04",
                            "placement": "middle",
                            "start_ratio": 0.55,
                        },
                        {"panel_id": "scene_07_shot_05", "placement": "end"},
                    ],
                    "motion_segments": [
                        {
                            "start_ratio": 0.0,
                            "end_ratio": 1.0,
                            "prompt": "Arrival into bark.",
                        }
                    ],
                    "motion_prompt": "Arrival into bark.",
                }
            ],
        }
        from scripts.nodes.flf_storyboard_planner import allows_multi_guide_continuous

        cast = panel_cast_lookup(scene)
        panels = [s["shot_id"] for s in scene["shots"]]
        self.assertFalse(
            cast_allows_continuous(
                "scene_07_shot_03", "scene_07_shot_05", cast
            )
        )
        self.assertTrue(
            allows_multi_guide_continuous(
                "scene_07_shot_03",
                "scene_07_shot_05",
                raw["render_units"][0]["guide_frames"],
                panels,
                cast,
            )
        )
        out = normalize_flf_clip_plan(raw, scene)
        clip = next(c for c in out["clips"] if len(c.get("guide_frames") or []) >= 3)
        self.assertTrue(clip["continuous"])
        self.assertEqual(clip["workflow"], "flf2v")
        self.assertEqual(clip["start_panel_id"], "scene_07_shot_03")
        self.assertEqual(clip["end_panel_id"], "scene_07_shot_05")

    def test_sync_ad_durations_to_plan_scene(self):
        from scripts.nodes.flf_storyboard_planner import sync_ad_durations_to_plan_scene

        plan = {
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "duration_budget_seconds": 99,
                    "shots": [
                        {"shot_id": "scene_01_shot_01", "duration_seconds": 1},
                        {"shot_id": "scene_01_shot_02", "duration_seconds": 1},
                    ],
                }
            ]
        }
        scene_plan = {
            "scene_id": "scene_01",
            "duration_total_seconds": 14,
            "clips": [
                {
                    "clip_id": "a",
                    "start_panel_id": "scene_01_shot_01",
                    "duration_seconds": 8,
                },
                {
                    "clip_id": "b",
                    "start_panel_id": "scene_01_shot_02",
                    "duration_seconds": 6,
                },
            ],
        }
        synced = sync_ad_durations_to_plan_scene(plan, scene_plan)
        scene = synced["scenes"][0]
        self.assertEqual(scene["duration_budget_seconds"], 14)
        self.assertEqual(scene["shots"][0]["duration_seconds"], 8)
        self.assertEqual(scene["shots"][1]["duration_seconds"], 6)

    def test_normalize_synthesizes_motion_segments_from_flat_prompt(self):
        raw = {
            "clips": [
                {
                    "start_panel_id": "scene_01_shot_01",
                    "end_panel_id": "scene_01_shot_01",
                    "workflow": "i2v",
                    "continuous": False,
                    "duration_seconds": 6,
                    "motion_prompt": "Light sweeps the empty sanctuary.",
                }
            ]
        }
        out = normalize_flf_clip_plan(raw, _scene(), duration_budget_seconds=24)
        clip = next(
            c for c in out["clips"] if c["start_panel_id"] == "scene_01_shot_01"
        )
        self.assertEqual(len(clip["motion_segments"]), 1)
        self.assertEqual(clip["motion_segments"][0]["end_ratio"], 1.0)
        self.assertIn("Light sweeps", clip["motion_segments"][0]["prompt"])

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

    def test_chain_mode_builds_shared_boundaries(self):
        old_mode = os.environ.get("STORYBOARD_VIDEO_MODE")
        old_chain = os.environ.get("STORY_MAKER_DIRECTOR_CHAIN")
        try:
            os.environ["STORYBOARD_VIDEO_MODE"] = "director"
            os.environ.pop("STORY_MAKER_DIRECTOR_CHAIN", None)
            raw = {
                "scene_global_prompt": "Warm sanctuary daylight.",
                "clips": [
                    {
                        "start_panel_id": "scene_01_shot_01",
                        "end_panel_id": "scene_01_shot_02",
                        "workflow": "flf2v",
                        "continuous": False,
                        "duration_seconds": 10,
                        "motion_prompt": "Reveal into family entrance.",
                    },
                    {
                        "start_panel_id": "scene_01_shot_02",
                        "end_panel_id": "scene_01_shot_03",
                        "workflow": "flf2v",
                        "continuous": True,
                        "duration_seconds": 10,
                        "motion_prompt": "Push to latch.",
                    },
                    {
                        "start_panel_id": "scene_01_shot_03",
                        "end_panel_id": "scene_01_shot_04",
                        "workflow": "flf2v",
                        "continuous": True,
                        "duration_seconds": 10,
                        "motion_prompt": "Gate opens.",
                    },
                    {
                        "start_panel_id": "scene_01_shot_04",
                        "end_panel_id": "scene_01_shot_05",
                        "workflow": "flf2v",
                        "continuous": False,
                        "duration_seconds": 10,
                        "motion_prompt": "Cut to meadow deer.",
                    },
                ],
            }
            out = normalize_flf_clip_plan(raw, _scene())
            clips = out["clips"]
            self.assertGreaterEqual(len(clips), 2)
            covered: set[str] = set()
            for c in clips:
                self.assertEqual(c["workflow"], "flf2v")
                self.assertTrue(c["continuous"])
                self.assertGreaterEqual(c["duration_seconds"], 9)
                self.assertLessEqual(c["duration_seconds"], 15)
                covered.add(c["start_panel_id"])
                covered.add(c["end_panel_id"])
                for g in c.get("guide_frames") or []:
                    pid = g.get("panel_id")
                    if pid:
                        covered.add(pid)
            # Shared boundaries
            for idx, (prev, cur) in enumerate(zip(clips, clips[1:]), start=1):
                self.assertEqual(prev["end_panel_id"], cur["start_panel_id"])
                self.assertTrue(out["segments"][idx]["cut_before"])
                start_guide = (cur.get("guide_frames") or [{}])[0]
                self.assertGreaterEqual(float(start_guide.get("guide_strength") or 0), 0.9)
            self.assertEqual(covered, set(panel_ids_in_order(_scene())))
        finally:
            if old_mode is None:
                os.environ.pop("STORYBOARD_VIDEO_MODE", None)
            else:
                os.environ["STORYBOARD_VIDEO_MODE"] = old_mode
            if old_chain is None:
                os.environ.pop("STORY_MAKER_DIRECTOR_CHAIN", None)
            else:
                os.environ["STORY_MAKER_DIRECTOR_CHAIN"] = old_chain


class TestBeatsTimelineNormalization(unittest.TestCase):
    """AD free-form beats[] timeline: parsing, coverage, and the long-gap guard."""

    def _beats_render_unit(self, *, bridge_role="bridge"):
        return {
            "unit_id": "scene_01_unit_01",
            "cut_before": False,
            "duration_seconds": 12,
            "pace": "medium",
            "motion_class": "large_reveal",
            "guidance": "balanced",
            "global_prompt": "sunlit meadow",
            "negative_prompt": "extra people, duplicated characters",
            "locked_cast": ["char_01"],
            "beats": [
                {"kind": "guide", "panel_id": "scene_01_shot_01", "role": "start"},
                {
                    "kind": "text",
                    "duration_seconds": 4,
                    "prompt": "camera pushes in; figure lifts an object",
                },
                {"kind": "guide", "panel_id": "scene_01_shot_02", "role": bridge_role},
                {
                    "kind": "text",
                    "duration_seconds": 4,
                    "prompt": "camera whip-pans right off empty ground; no new figures enter",
                },
                {"kind": "guide", "panel_id": "scene_01_shot_04", "role": "end"},
            ],
        }

    def test_beats_clip_normalized_and_preserved(self):
        raw = {
            "scene_id": "scene_01",
            "scene_global_prompt": "sunlit meadow",
            "render_units": [self._beats_render_unit()],
        }
        out = normalize_flf_clip_plan(raw, _scene())
        clips = out["clips"]
        beats_clips = [c for c in clips if c.get("beats")]
        self.assertEqual(len(beats_clips), 1)
        clip = beats_clips[0]
        self.assertEqual(clip["start_panel_id"], "scene_01_shot_01")
        self.assertEqual(clip["end_panel_id"], "scene_01_shot_04")
        self.assertEqual(clip["workflow"], "flf2v")
        self.assertTrue(clip["continuous"])
        self.assertEqual(clip["negative_prompt"], "extra people, duplicated characters")
        self.assertEqual(clip["locked_cast"], ["char_01"])
        # duration_seconds must be >= sum(text) so DirectorClip validation holds.
        text_total = sum(
            b["duration_seconds"] for b in clip["beats"] if b["kind"] == "text"
        )
        self.assertGreaterEqual(clip["duration_seconds"], text_total)
        # Bridge panel is covered via the beats path, not double-filled.
        self.assertNotIn(
            "scene_01_shot_02",
            [
                r
                for r in out["repairs"]
                if "coverage missing" in r and "scene_01_shot_02" in r
            ],
        )
        all_panels = set()
        for c in clips:
            all_panels.add(c["start_panel_id"])
            all_panels.add(c["end_panel_id"])
            for g in c.get("guide_frames") or []:
                if g.get("panel_id"):
                    all_panels.add(g["panel_id"])
        self.assertEqual(all_panels, set(panel_ids_in_order(_scene())))

    def test_beats_unknown_guide_panel_falls_back_gracefully(self):
        raw = {
            "scene_id": "scene_01",
            "clips": [
                {
                    "clip_id": "bad_clip",
                    "beats": [
                        {"kind": "guide", "panel_id": "not_a_real_panel", "role": "start"},
                        {"kind": "text", "duration_seconds": 4, "prompt": "drifts"},
                    ],
                }
            ],
        }
        # Should not raise; unknown-only-guide beats drop the clip entirely
        # and full coverage is still produced via the normal fallback path.
        out = normalize_flf_clip_plan(raw, _scene())
        self.assertTrue(
            any("no usable guide" in r or "drop" in r for r in out["repairs"])
        )
        covered = {c["start_panel_id"] for c in out["clips"]} | {
            c["end_panel_id"] for c in out["clips"]
        }
        self.assertTrue(set(panel_ids_in_order(_scene())).issubset(covered))

    def test_beats_preserved_under_chain_mode_with_gap_fill(self):
        old_mode = os.environ.get("STORYBOARD_VIDEO_MODE")
        old_chain = os.environ.get("STORY_MAKER_DIRECTOR_CHAIN")
        try:
            os.environ["STORYBOARD_VIDEO_MODE"] = "director"
            os.environ.pop("STORY_MAKER_DIRECTOR_CHAIN", None)
            raw = {
                "scene_id": "scene_01",
                "scene_global_prompt": "sunlit meadow",
                "render_units": [self._beats_render_unit()],
            }
            out = normalize_flf_clip_plan(raw, _scene())
            clips = out["clips"]
            beats_clips = [c for c in clips if c.get("beats")]
            # The beats-authored unit must survive untouched under chain mode
            # (never rebuilt from cast heuristics), and any remaining panel
            # (shot_03, shot_05) is filled by the heuristic gap-fill path.
            self.assertEqual(len(beats_clips), 1)
            self.assertEqual(beats_clips[0]["start_panel_id"], "scene_01_shot_01")
            self.assertEqual(beats_clips[0]["end_panel_id"], "scene_01_shot_04")
            self.assertTrue(
                any("beats-authored units cover" in r for r in out["repairs"])
            )
            all_panels = set()
            for c in clips:
                all_panels.add(c["start_panel_id"])
                all_panels.add(c["end_panel_id"])
                for g in c.get("guide_frames") or []:
                    if g.get("panel_id"):
                        all_panels.add(g["panel_id"])
            self.assertEqual(all_panels, set(panel_ids_in_order(_scene())))
        finally:
            if old_mode is None:
                os.environ.pop("STORYBOARD_VIDEO_MODE", None)
            else:
                os.environ["STORYBOARD_VIDEO_MODE"] = old_mode
            if old_chain is None:
                os.environ.pop("STORY_MAKER_DIRECTOR_CHAIN", None)
            else:
                os.environ["STORY_MAKER_DIRECTOR_CHAIN"] = old_chain

    def test_long_gap_guard_caps_unauthored_chains_at_three_guides(self):
        old_mode = os.environ.get("STORYBOARD_VIDEO_MODE")
        old_chain = os.environ.get("STORY_MAKER_DIRECTOR_CHAIN")
        try:
            os.environ["STORYBOARD_VIDEO_MODE"] = "director"
            os.environ.pop("STORY_MAKER_DIRECTOR_CHAIN", None)
            # Same cast on every shot so cast heuristics want to chain the
            # whole scene continuous -- the guard must still cap at 3 guides
            # instead of morphing through all 5 panels in one unit.
            scene = {
                "scene_id": "scene_09",
                "shots": [
                    {"shot_id": f"scene_09_shot_{i:02d}", "characters_present": ["father"]}
                    for i in range(1, 6)
                ],
            }
            out = normalize_flf_clip_plan({"scene_id": "scene_09", "clips": []}, scene)
            self.assertTrue(
                any("long-gap guard" in r for r in out["repairs"])
            )
            for clip in out["clips"]:
                n_guides = len(clip.get("guide_frames") or [])
                self.assertLessEqual(n_guides, 3)
        finally:
            if old_mode is None:
                os.environ.pop("STORYBOARD_VIDEO_MODE", None)
            else:
                os.environ["STORYBOARD_VIDEO_MODE"] = old_mode
            if old_chain is None:
                os.environ.pop("STORY_MAKER_DIRECTOR_CHAIN", None)
            else:
                os.environ["STORY_MAKER_DIRECTOR_CHAIN"] = old_chain


if __name__ == "__main__":
    unittest.main()
