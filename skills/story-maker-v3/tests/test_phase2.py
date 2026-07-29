"""Phase-2 unit tests: duration budget, panel crop, validators (de-hallucination)."""

import os
import textwrap

import pytest

from tools import duration_budget as db
from tools import panel_crop, validators


# --- duration_budget --------------------------------------------------------

def test_parse_target_duration():
    assert db.parse_target_duration("5m") == 300
    assert db.parse_target_duration("5min") == 300
    assert db.parse_target_duration("300") == 300
    assert db.parse_target_duration(300) == 300
    assert db.parse_target_duration("90s") == 90


def test_scene_count_for_target():
    assert db.scene_count_for_target(300) == 5      # 300 / 70 -> 5
    assert db.scene_count_for_target(140) == 2
    assert db.scene_count_for_target(70) == 1
    assert db.scene_count_for_target(10) == 1


def test_snap_clip_duration():
    assert db.snap_clip_duration(10) == 10
    assert db.snap_clip_duration(4) == 9            # below min -> 9
    assert db.snap_clip_duration(99) == 15          # classic clamp
    assert db.snap_clip_duration(99, allow_beats=True) == 20
    assert db.snap_clip_duration(18, allow_beats=True) == 18


def test_row_scene_totals_and_tolerance():
    assert db.row_total([10, 10, 10, 10]) == 40
    assert db.scene_total([40, 40]) == 80
    assert db.within_tolerance(80, 80)
    assert db.within_tolerance(86, 80, tolerance_percent=10)
    assert not db.within_tolerance(100, 80, tolerance_percent=10)


# --- panel_crop --------------------------------------------------------------

def test_album_grid_shape_v3_is_4x2():
    assert panel_crop.album_grid_shape(8) == (4, 2)
    assert panel_crop.album_grid_shape(8, cols=2) == (4, 2)


def test_fallback_panel_bboxes_row_major():
    bboxes = panel_crop.fallback_panel_bboxes(8)
    assert len(bboxes) == 8
    # 4 rows x 2 cols: each cell is 0.5 wide, 0.25 tall
    assert bboxes[0] == {"x": 0.0, "y": 0.0, "w": 0.5, "h": 0.25}
    assert bboxes[1] == {"x": 0.5, "y": 0.0, "w": 0.5, "h": 0.25}
    assert bboxes[2] == {"x": 0.0, "y": 0.25, "w": 0.5, "h": 0.25}
    assert bboxes[3] == {"x": 0.5, "y": 0.25, "w": 0.5, "h": 0.25}
    assert bboxes[7] == {"x": 0.5, "y": 0.75, "w": 0.5, "h": 0.25}


def test_crop_panel(tmp_path):
    from PIL import Image

    sheet = Image.new("RGB", (1024, 1792), (255, 255, 255))
    sheet_path = tmp_path / "sheet.png"
    sheet.save(sheet_path)
    out = tmp_path / "panel_11.png"
    panel_crop.crop_panel(str(sheet_path), {"x": 0.0, "y": 0.0, "w": 0.5, "h": 0.25}, str(out))
    assert out.is_file()
    with Image.open(out) as im:
        assert im.size == (512, 448)


# --- validators: inline parsers ---------------------------------------------

def test_parse_cid_list():
    assert validators.parse_cid_list("[char_01, char_02]") == ["char_01", "char_02"]
    assert validators.parse_cid_list("char_01") == ["char_01"]
    assert validators.parse_cid_list("[]") == []


def test_parse_depth_map():
    assert validators.parse_depth_map("{char_01:2, char_02:3}") == {"char_01": 2, "char_02": 3}
    assert validators.parse_depth_map("{char_01:7}") == {"char_01": 7}


def test_parse_position_map():
    assert validators.parse_position_map("{char_01:[0.5,0.5], char_02:[0.7,0.5]}") == {
        "char_01": [0.5, 0.5], "char_02": [0.7, 0.5]
    }


# --- validators: scenes ------------------------------------------------------

SCENES_MD = textwrap.dedent("""
    # Scenes
    target_seconds: 150
    scene_budget: 70

    ## Scene s1 — Rabbit sledge
    scene_id: s1
    target_seconds: 80
    cast: [char_01, char_02, char_03]
    characters_present: [char_01, char_02, char_03]
    location_id: loc_forest
    beat: Rabbit and deer talk.

    ## Scene s2 — Rabbit meets tortoise
    scene_id: s2
    target_seconds: 70
    cast: [char_01, char_04]
    characters_present: [char_01, char_04]
    location_id: loc_forest
    beat: Tortoise challenges rabbit.
""").strip()


def test_validate_scenes_pass():
    res = validators.validate_scenes(SCENES_MD, target_seconds=150)
    assert res.ok, res.errors


def test_validate_scenes_fail_missing_location():
    bad = SCENES_MD.replace("location_id: loc_forest\nbeat: Rabbit and deer talk.",
                            "beat: Rabbit and deer talk.")
    res = validators.validate_scenes(bad, target_seconds=150)
    assert not res.ok
    assert any("location_id" in e for e in res.errors)


# --- validators: storyboard --------------------------------------------------

STORYBOARD_MD = textwrap.dedent("""
    # Scene s1 — Rabbit sledge
    target_seconds: 80
    cast: [char_01, char_02, char_03]
    location_ref_id: loc_forest

    ## Row 1 (LTX session 1)
    | col | shot_id | duration_seconds | characters_present | depth_per_char | camera_angle | position_xy | looks_at | expression | mood | intent | facing | angle | spatial_relation | must_not_show |
    | 1 | s1_p1 | 10 | [char_01] | {char_01:2} | eye_level | {char_01:[0.5,0.5]} | char_02 | stern | tense | confront | forward | 15deg | char_01 centered alone | no char_02, no char_03 |
    | 2 | s1_p2 | 10 | [char_01,char_02] | {char_01:3,char_02:2} | over_shoulder | {char_01:[0.3,0.5],char_02:[0.7,0.5]} | char_01 | alarmed | rising | defend | left | 0deg | char_02 enters right, 40% gap | no char_03 |
    | 3 | s1_p3 | 10 | [char_01,char_02] | {char_01:3,char_02:2} | eye_level | {char_01:[0.3,0.5],char_02:[0.7,0.5]} | char_02 | amused | playful | mock | right | 5deg | char_02 leans closer to char_01 | no char_03 |
    | 4 | s1_p4 | 10 | [char_01,char_02,char_03] | {char_01:3,char_02:2,char_03:4} | wide | {char_01:[0.3,0.5],char_02:[0.7,0.5],char_03:[0.5,0.8]} | char_03 | sad | somber | reveal | forward | 0deg | char_03 deep background center | no extra characters |

    ## Row 2 (LTX session 2)
    | col | shot_id | duration_seconds | characters_present | depth_per_char | camera_angle | position_xy | looks_at | expression | mood | intent | facing | angle | spatial_relation | must_not_show |
    | 1 | s1_p5 | 10 | [char_03] | {char_03:2} | close_up | {char_03:[0.5,0.5]} | none | tearful | sad | pity | forward | 0deg | char_03 centered close | no char_01, no char_02 |
    | 2 | s1_p6 | 10 | [char_01,char_02] | {char_01:2,char_02:2} | two_shot | {char_01:[0.4,0.5],char_02:[0.6,0.5]} | char_02 | guilty | tense | regret | left | 10deg | char_01 left, char_02 right | no char_03 |
    | 3 | s1_p7 | 10 | [char_01] | {char_01:2} | medium | {char_01:[0.5,0.5]} | none | resolved | determined | resolve | forward | 0deg | char_01 alone center | no char_02, no char_03 |
    | 4 | s1_p8 | 10 | [char_01,char_02] | {char_01:2,char_02:3} | wide | {char_01:[0.4,0.5],char_02:[0.6,0.6]} | char_02 | calm | calm | settle | right | 0deg | char_02 one step back right | no char_03 |

    ## Inter-column motion deltas (row 1)
    | from -> to | depth_delta | camera_motion_hint |
    | s1_p1->s1_p2 | char_01: 2->3 (+1 recede) | push_in |
    | s1_p2->s1_p3 | char_01: 3->3 (hold) | pan |

    ## Inter-column motion deltas (row 2)
    | from -> to | depth_delta | camera_motion_hint |
    | s1_p5->s1_p6 | char_01: 2->2 (hold) | static |

    ## Scene-end handoff -> scene s2
    on_screen: [char_01, char_02]
    positions: {char_01:[0.4,0.5], char_02:[0.6,0.6]}
    facing: {char_01: left, char_02: right}
    mood: calm
    transition: hard_cut
""").strip()


def test_validate_storyboard_pass():
    scenes = validators.parse_scenes(SCENES_MD)
    res = validators.validate_storyboard(STORYBOARD_MD, scenes=scenes)
    assert res.ok, res.errors


def test_validate_storyboard_catches_depth_and_invented_char():
    bad = STORYBOARD_MD.replace("{char_01:2}", "{char_01:7}", 1).replace(
        "[char_01]", "[char_01,char_99]", 1
    )
    res = validators.validate_storyboard(bad)
    assert not res.ok
    assert any("char_99" in e for e in res.errors)
    assert any("outside [1,5]" in e for e in res.errors)


def test_validate_storyboard_catches_wrong_cell_count():
    # Drop one row -> only 4 cells.
    bad = STORYBOARD_MD.split("## Row 2")[0]
    res = validators.validate_storyboard(bad)
    assert not res.ok
    assert any("expected 2 rows" in e or "cells" in e for e in res.errors)


# --- validators: motion ------------------------------------------------------

MOTION_JSON = textwrap.dedent("""
    {
      "scene_id": "s1",
      "scene_global_prompt": "warm forest",
      "render_units": [
        {"unit_id": "s1_r1_c1", "duration_seconds": 13, "motion_class": "talking", "guidance": "balanced", "global_prompt": "warm", "guide_frames": [{"panel_id": "s1_p1", "placement": "start"}, {"panel_id": "s1_p2", "placement": "end", "is_end_frame": true}], "motion_segments": [{"start_ratio": 0.0, "end_ratio": 1.0, "prompt": "b"}], "motion_prompt": "f"},
        {"unit_id": "s1_r1_c2", "duration_seconds": 14, "motion_class": "walking", "guidance": "prompt_follow", "global_prompt": "warm", "guide_frames": [{"panel_id": "s1_p2", "placement": "start"}, {"panel_id": "s1_p3", "placement": "end", "is_end_frame": true}], "motion_segments": [{"start_ratio": 0.0, "end_ratio": 1.0, "prompt": "b"}], "motion_prompt": "f"},
        {"unit_id": "s1_r1_c3", "duration_seconds": 13, "motion_class": "large_reveal", "guidance": "balanced", "global_prompt": "warm", "guide_frames": [{"panel_id": "s1_p3", "placement": "start"}, {"panel_id": "s1_p4", "placement": "end", "is_end_frame": true}], "motion_segments": [{"start_ratio": 0.0, "end_ratio": 1.0, "prompt": "b"}], "motion_prompt": "f"},
        {"unit_id": "s1_r2_c1", "duration_seconds": 13, "motion_class": "talking", "guidance": "balanced", "global_prompt": "warm", "guide_frames": [{"panel_id": "s1_p5", "placement": "start"}, {"panel_id": "s1_p6", "placement": "end", "is_end_frame": true}], "motion_segments": [{"start_ratio": 0.0, "end_ratio": 1.0, "prompt": "b"}], "motion_prompt": "f"},
        {"unit_id": "s1_r2_c2", "duration_seconds": 14, "motion_class": "general", "guidance": "balanced", "global_prompt": "warm", "guide_frames": [{"panel_id": "s1_p6", "placement": "start"}, {"panel_id": "s1_p7", "placement": "end", "is_end_frame": true}], "motion_segments": [{"start_ratio": 0.0, "end_ratio": 1.0, "prompt": "b"}], "motion_prompt": "f"},
        {"unit_id": "s1_r2_c3", "duration_seconds": 13, "motion_class": "general", "guidance": "balanced", "global_prompt": "warm", "guide_frames": [{"panel_id": "s1_p7", "placement": "start"}, {"panel_id": "s1_p8", "placement": "end", "is_end_frame": true}], "motion_segments": [{"start_ratio": 0.0, "end_ratio": 1.0, "prompt": "b"}], "motion_prompt": "f"}
      ]
    }
""").strip()  # 13+14+13 + 13+14+13 = 80s == storyboard target


def test_validate_motion_pass():
    sb = validators.parse_storyboard(STORYBOARD_MD)
    res = validators.validate_motion(MOTION_JSON, sb=sb)
    assert res.ok, res.errors


def test_validate_motion_catches_bad_enum_and_workflow():
    # Inject a forbidden workflow key on the first unit, and a bad enum on the second.
    bad = MOTION_JSON.replace(
        '"unit_id": "s1_r1_c1", "duration_seconds": 13, "motion_class": "talking"',
        '"unit_id": "s1_r1_c1", "duration_seconds": 13, "motion_class": "talking", "workflow": "flf2v"',
        1,
    ).replace('"motion_class": "walking"', '"motion_class": "sprinting"', 1)
    res = validators.validate_motion(bad)
    assert not res.ok
    assert any("invalid motion_class" in e for e in res.errors)
    assert any("must NOT set 'workflow'" in e for e in res.errors)


def test_validate_motion_catches_broken_intra_row_boundary():
    # Unit 2 start -> s1_p3 (should be s1_p2 to chain from unit 1's end).
    bad = MOTION_JSON.replace('"s1_p2", "placement": "start"', '"s1_p3", "placement": "start"', 1)
    res = validators.validate_motion(bad)
    assert not res.ok
    assert any("FLF2V chain broken" in e for e in res.errors)


def test_validate_motion_row_break_is_not_a_chain_error():
    # Row 2 starts at s1_p5 != row1 end s1_p3 -> that's a cut, must NOT error.
    res = validators.validate_motion(MOTION_JSON)
    assert res.ok, res.errors
    assert not any("FLF2V chain broken" in e for e in res.errors)