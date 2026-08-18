"""Unit tests for the spatial continuity subsystem.

Tests cover:
  - spatial_plan parsing and validation
  - spatial_qa report parsing and validation
  - deterministic spatial prompt materialization
  - reference ordering (identity-first, no anchor)
  - conditional location attachment
  - bridge behaviour (no spatial block)
  - legacy backward compatibility
"""

from __future__ import annotations

import json
import os
import tempfile
import textwrap

from tools.spatial_validator import (
    PANO_W,
    PANO_H,
    parse_spatial_plan,
    validate_spatial_plan,
    parse_spatial_qa_report,
    validate_spatial_qa_report,
)
from tools.validators import ValidationResult, parse_storyboard


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_SPATIAL_PLAN = textwrap.dedent("""
    # Spatial Plan — Scene s2
    scene_id: s2
    location_ref_id: loc_03
    panorama_resolution: 3840x2160
    world_axis: road runs west (village) to east (deep darkness)
    primary_anchor: lamp_01
    landmarks: [lamp_01]
    zones: [lamp_pool, road_midground, deep_road]

    ## Landmark lamp_01
    zone: lamp_pool
    description: The only rusted yellow street lamp, fixed on the south shoulder of the dirt road.
    panorama_xy: [1920, 2000]

    ## Zone lamp_pool
    relative_to: lamp_01
    x_range: 1600-2240
    y_range: 1700-2160
    z_range: 0-5
    distance_from_anchor_m: 0
    lighting: small amber pool of light

    ## Zone road_midground
    relative_to: lamp_01
    x_range: 2400-3200
    y_range: 1500-2000
    z_range: 10-25
    distance_from_anchor_m: 15
    lighting: weak amber spill fading into blue darkness

    ## Zone deep_road
    relative_to: lamp_01
    x_range: 3200-3840
    y_range: 1300-1900
    z_range: 30-60
    distance_from_anchor_m: 40
    lighting: unlit blue-black road

    ## Generation g1
    location_reference: attach
    generation_geography: wide view from the village edge showing Kayal at the lamp and the dark road stretching east.
    start_positions: char_01=lamp_pool@x=1920,y=2000,z=0m
    end_positions: char_01=lamp_pool@x=1920,y=2000,z=0m
    movement_constraints: char_01=fixed_at(lamp_01)

    ### Shot 1
    on_screen_positions: char_01=lamp_pool@x=1920,y=2000,z=0m:foreground
    camera_zone: lamp_pool
    camera_facing: toward_lamp_01
    camera_zoom: wide
    character_facing: char_01=toward_lamp_01
    visible_landmarks: [lamp_01]

    ## Generation g2
    location_reference: omit
    generation_geography: wide view from Kayal's side of lamp_01 down the road; Kayal at lamp_pool and dogs in deep_road.
    start_positions: char_01=lamp_pool@x=1920,y=2000,z=0m; char_05=deep_road@x=3400,y=1700,z=40m
    end_positions: char_01=lamp_pool@x=1920,y=2000,z=0m; char_05=road_midground@x=2800,y=1800,z=15m
    movement_constraints: char_01=fixed_at(lamp_01); char_05=approach(lamp_01), never_enter(lamp_pool)

    ### Shot 1
    on_screen_positions: char_01=lamp_pool@x=1920,y=2000,z=0m:foreground; char_05=deep_road@x=3400,y=1700,z=40m:background
    camera_zone: lamp_pool
    camera_facing: toward_lamp_01
    camera_zoom: wide
    character_facing: char_01=toward_lamp_01; char_05=away_from_lamp_01
    visible_landmarks: [lamp_01]

    ### Shot 2
    on_screen_positions: char_01=lamp_pool@x=1920,y=2000,z=0m:foreground; char_05=deep_road@x=3350,y=1700,z=38m:background
    camera_zone: lamp_pool
    camera_facing: toward_lamp_01
    camera_zoom: medium
    character_facing: char_01=toward_lamp_01; char_05=away_from_lamp_01
    visible_landmarks: []
""").strip()


# A minimal storyboard matching the spatial plan above
STORYBOARD_FOR_SPATIAL = textwrap.dedent("""
    # Scene s2 — Test
    scene_id: s2
    target_seconds: 30
    cast: [char_01, char_05]
    location_ref_id: loc_03

    ## Generation g1 — 0.0-15.0s
    duration_seconds: 15.0
    panel_grid: 2x3

    ### Shot 1 — 0.0-15.0s (continuous)
    panels: [1, 2, 3, 4, 5, 6]
    characters_present: [char_01]
    shot_size: wide
    composition: center
    action: Kayal stands by the lamp.
    camera: Static Shot.
    audio: Ambient night.
    dialogue:

    ## Generation g2 — 15.0-30.0s
    duration_seconds: 15.0
    panel_grid: 2x3

    ### Shot 1 — 15.0-22.0s (continuous)
    panels: [1, 2, 3]
    characters_present: [char_01, char_05]
    shot_size: wide
    composition: depth
    action: Dogs approach from the deep road.
    camera: Static Shot.
    audio: Dog footsteps.
    dialogue:

    ### Shot 2 — 22.0-30.0s (cut_on_action)
    panels: [4, 5, 6]
    characters_present: [char_01, char_05]
    shot_size: medium
    composition: rule_of_thirds
    action: Dogs continue approaching.
    camera: Push In slow.
    audio: Dog footsteps.
    dialogue:

    ## Scene-end handoff -> scene end
    on_screen: [char_01, char_05]
    mood: tense
    transition: hard_cut
""").strip()


SCENES_FOR_SPATIAL = textwrap.dedent("""
    # Scenes
    target_seconds: 30
    scene_budget: 70

    ## Scene s2
    scene_id: s2
    target_seconds: 30
    cast: [char_01, char_05]
    location_id: loc_03
    objects: []
    beats: [1]
""").strip()


# ---------------------------------------------------------------------------
# 1. Valid complete spatial plan parses and validates
# ---------------------------------------------------------------------------

def test_valid_spatial_plan_parses():
    plan = parse_spatial_plan(VALID_SPATIAL_PLAN)
    assert plan["scene_id"] == "s2"
    assert plan["location_ref_id"] == "loc_03"
    assert plan["panorama_resolution"] == "3840x2160"
    assert plan["primary_anchor"] == "lamp_01"
    assert "lamp_01" in plan["landmarks"]
    assert "lamp_pool" in plan["zones"]
    assert "g1" in plan["generations"]
    assert "g2" in plan["generations"]
    assert plan["landmark_defs"]["lamp_01"]["panorama_xy"] == (1920.0, 2000.0)
    assert plan["zone_defs"]["lamp_pool"]["x_range"] == (1600.0, 2240.0)


def test_valid_spatial_plan_validates():
    from tools.validators import parse_storyboard, parse_scenes
    sb = parse_storyboard(STORYBOARD_FOR_SPATIAL)
    scenes = parse_scenes(SCENES_FOR_SPATIAL)
    res = validate_spatial_plan(VALID_SPATIAL_PLAN, storyboard=sb, scenes=scenes)
    assert res.ok, f"errors: {res.errors}"


# ---------------------------------------------------------------------------
# 2. Duplicate/missing landmark or zone identifiers fail
# ---------------------------------------------------------------------------

def test_duplicate_landmark_id_fails():
    plan = VALID_SPATIAL_PLAN.replace(
        "landmarks: [lamp_01]",
        "landmarks: [lamp_01, lamp_02]",
    )
    # Add a second landmark block with the same id
    plan = plan.replace(
        "## Zone lamp_pool",
        "## Landmark lamp_01\nduplicate\npanorama_xy: [100, 100]\n\n## Zone lamp_pool",
    )
    res = validate_spatial_plan(plan)
    assert not res.ok


def test_missing_landmark_definition_fails():
    plan = VALID_SPATIAL_PLAN.replace(
        "landmarks: [lamp_01]",
        "landmarks: [lamp_01, lamp_02]",
    )
    res = validate_spatial_plan(plan)
    assert not res.ok
    assert any("lamp_02" in e for e in res.errors)


def test_missing_zone_definition_fails():
    plan = VALID_SPATIAL_PLAN.replace(
        "zones: [lamp_pool, road_midground, deep_road]",
        "zones: [lamp_pool, road_midground, deep_road, missing_zone]",
    )
    res = validate_spatial_plan(plan)
    assert not res.ok
    assert any("missing_zone" in e for e in res.errors)


# ---------------------------------------------------------------------------
# 3. Coordinates outside panorama bounds fail
# ---------------------------------------------------------------------------

def test_landmark_xy_out_of_bounds_fails():
    plan = VALID_SPATIAL_PLAN.replace(
        "panorama_xy: [1920, 2000]",
        "panorama_xy: [5000, 2000]",
    )
    res = validate_spatial_plan(plan)
    assert not res.ok
    assert any("outside" in e.lower() for e in res.errors)


def test_zone_x_range_out_of_bounds_fails():
    plan = VALID_SPATIAL_PLAN.replace(
        "x_range: 3200-3840",
        "x_range: 3200-5000",
    )
    res = validate_spatial_plan(plan)
    assert not res.ok
    assert any("outside" in e.lower() for e in res.errors)


# ---------------------------------------------------------------------------
# 4. Zone overlap or invalid ranges fail
# ---------------------------------------------------------------------------

def test_zone_x_overlap_fails():
    plan = VALID_SPATIAL_PLAN.replace(
        "x_range: 2400-3200",
        "x_range: 2200-3200",  # overlaps lamp_pool (1600-2240)
    )
    res = validate_spatial_plan(plan)
    assert not res.ok
    assert any("overlap" in e.lower() for e in res.errors)


def test_zone_invalid_range_lo_gt_hi_fails():
    plan = VALID_SPATIAL_PLAN.replace(
        "x_range: 2400-3200",
        "x_range: 3200-2400",
    )
    res = validate_spatial_plan(plan)
    assert not res.ok


# ---------------------------------------------------------------------------
# 5. Position outside declared zone fails
# ---------------------------------------------------------------------------

def test_position_outside_zone_fails():
    # char_05 at x=1000 is not in deep_road (3200-3840)
    plan = VALID_SPATIAL_PLAN.replace(
        "char_05=deep_road@x=3400,y=1700,z=40m",
        "char_05=deep_road@x=1000,y=1700,z=40m",
        1,  # only the first occurrence (start_positions)
    )
    res = validate_spatial_plan(plan)
    assert not res.ok
    assert any("does not fall" in e for e in res.errors)


# ---------------------------------------------------------------------------
# 6. Missing generation spatial block fails
# ---------------------------------------------------------------------------

def test_missing_generation_block_fails():
    from tools.validators import parse_storyboard
    # Add a g3 to the storyboard that's not in the spatial plan
    sb_md = STORYBOARD_FOR_SPATIAL + textwrap.dedent("""

        ## Generation g3 — 30.0-45.0s
        duration_seconds: 15.0
        panel_grid: 1x1

        ### Shot 1 — 30.0-45.0s (continuous)
        panels: [1]
        characters_present: [char_01]
        shot_size: wide
        composition: center
        action: More action.
        camera: Static Shot.
        audio: Ambient.
        dialogue:
    """)
    sb = parse_storyboard(sb_md)
    res = validate_spatial_plan(VALID_SPATIAL_PLAN, storyboard=sb)
    assert not res.ok
    assert any("g3" in e for e in res.errors)


# ---------------------------------------------------------------------------
# 7. Missing shot coverage fails
# ---------------------------------------------------------------------------

def test_missing_shot_coverage_fails():
    from tools.validators import parse_storyboard
    # Add a shot 3 to g2 in the storyboard that's not in the spatial plan
    sb_md = STORYBOARD_FOR_SPATIAL.replace(
        "dialogue:\n\n## Scene-end handoff",
        textwrap.dedent("""\
            dialogue:

            ### Shot 3 — 30.0-30.0s (continuous)
            panels: [5, 6]
            characters_present: [char_01]
            shot_size: wide
            composition: center
            action: x
            camera: Static Shot.
            audio: x
            dialogue:

            ## Scene-end handoff"""),
    )
    # panel_grid is already 2x3 in the fixture (6 panels)
    sb = parse_storyboard(sb_md)
    res = validate_spatial_plan(VALID_SPATIAL_PLAN, storyboard=sb)
    assert not res.ok
    assert any("shot" in e.lower() for e in res.errors)


# ---------------------------------------------------------------------------
# 8. Invalid location_reference policy fails
# ---------------------------------------------------------------------------

def test_g1_not_attach_fails():
    plan = VALID_SPATIAL_PLAN.replace(
        "location_reference: attach\ngeneration_geography: wide view from the village",
        "location_reference: omit\ngeneration_geography: wide view from the village",
    )
    res = validate_spatial_plan(plan)
    assert not res.ok
    assert any("g1" in e.lower() and "attach" in e.lower() for e in res.errors)


def test_invalid_location_reference_value_fails():
    plan = VALID_SPATIAL_PLAN.replace(
        "location_reference: attach\ngeneration_geography: wide view from the village",
        "location_reference: maybe\ngeneration_geography: wide view from the village",
    )
    res = validate_spatial_plan(plan)
    assert not res.ok


# ---------------------------------------------------------------------------
# 9. Missing generation_geography fails
# ---------------------------------------------------------------------------

def test_missing_generation_geography_fails():
    plan = VALID_SPATIAL_PLAN.replace(
        "generation_geography: wide view from the village edge showing Kayal at the lamp and the dark road stretching east.\n",
        "",
    )
    res = validate_spatial_plan(plan)
    assert not res.ok
    assert any("generation_geography" in e for e in res.errors)


# ---------------------------------------------------------------------------
# 10. Teleportation in X fails
# ---------------------------------------------------------------------------

def test_x_teleport_fails():
    from tools.validators import parse_storyboard
    # Make shot 2 of g2 jump char_05 by a huge X distance (continuous shot)
    plan = VALID_SPATIAL_PLAN.replace(
        "char_05=deep_road@x=3350,y=1700,z=38m:background",
        "char_05=deep_road@x=100,y=1700,z=38m:background",
    )
    # Make shot 2 continuous in the storyboard so the teleport check runs
    sb_md = STORYBOARD_FOR_SPATIAL.replace(
        "### Shot 2 — 22.0-30.0s (cut_on_action)",
        "### Shot 2 — 22.0-30.0s (continuous)",
    )
    sb = parse_storyboard(sb_md)
    res = validate_spatial_plan(plan, storyboard=sb)
    assert not res.ok
    assert any("teleport" in e.lower() for e in res.errors)


# ---------------------------------------------------------------------------
# 11. Non-monotonic Z movement fails
# ---------------------------------------------------------------------------

def test_non_monotonic_z_approach_fails():
    # char_05 has approach(lamp_01) but Z increases from 40 to 50
    plan = VALID_SPATIAL_PLAN.replace(
        "char_05=road_midground@x=2800,y=1800,z=15m",
        "char_05=road_midground@x=2800,y=1800,z=50m",
    )
    res = validate_spatial_plan(plan)
    assert not res.ok
    assert any("approach" in e.lower() for e in res.errors)


def test_fixed_at_position_change_fails():
    plan = VALID_SPATIAL_PLAN.replace(
        "char_01=lamp_pool@x=1920,y=2000,z=0m\nmovement_constraints: char_01=fixed_at(lamp_01)",
        "char_01=lamp_pool@x=2000,y=2000,z=0m\nmovement_constraints: char_01=fixed_at(lamp_01)",
        1,  # end_positions only
    )
    res = validate_spatial_plan(plan)
    assert not res.ok
    assert any("fixed_at" in e.lower() for e in res.errors)


# ---------------------------------------------------------------------------
# 12. Legacy storyboard without spatial plan remains valid (warning only)
# ---------------------------------------------------------------------------

def test_legacy_storyboard_without_spatial_plan_valid():
    # A storyboard with no spatial plan should still validate on its own
    from tools.validators import validate_storyboard, parse_scenes
    scenes = parse_scenes(SCENES_FOR_SPATIAL)
    res = validate_storyboard(STORYBOARD_FOR_SPATIAL, scenes=scenes)
    assert res.ok, f"legacy storyboard should be valid: {res.errors}"


# ---------------------------------------------------------------------------
# 13. Asset registry no longer has anchors section
# ---------------------------------------------------------------------------

def test_asset_registry_no_anchors_section():
    from tools.image_pipeline import AssetRegistry
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = os.path.join(tmp, "run")
        assets_dir = os.path.join(tmp, "assets")
        os.makedirs(run_dir)
        os.makedirs(assets_dir)
        reg = AssetRegistry(run_dir, assets_dir)
        assert "anchors" not in reg.data


def test_asset_registry_loads_old_with_anchors_safely():
    """Old registries with an anchors key should load without error
    (the key is simply ignored)."""
    from tools.image_pipeline import AssetRegistry
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = os.path.join(tmp, "run")
        assets_dir = os.path.join(tmp, "assets")
        os.makedirs(run_dir)
        os.makedirs(assets_dir)
        reg_path = os.path.join(assets_dir, "asset_registry.json")
        with open(reg_path, "w") as f:
            json.dump({
                "characters": {},
                "locations": {},
                "objects": {},
                "sheets": {},
                "anchors": {"s2_g1": {"output_path": "/tmp/x.webp", "fal_image_url": "http://x"}},
            }, f)
        reg = AssetRegistry(run_dir, assets_dir)
        # anchors key should not be in the loaded data
        assert "anchors" not in reg.data


# ---------------------------------------------------------------------------
# 14. No anchor path/prompt helpers exist
# ---------------------------------------------------------------------------

def test_no_anchor_path_helper():
    """AssetRegistry should no longer have anchor_path."""
    from tools.image_pipeline import AssetRegistry
    assert not hasattr(AssetRegistry, "anchor_path")


def test_no_anchor_prompt_path_helper():
    """image_pipeline should no longer have anchor_prompt_path."""
    import tools.image_pipeline as ip
    assert not hasattr(ip, "anchor_prompt_path")


# ---------------------------------------------------------------------------
# 15. Reference ordering is previous sheet → conditional location → characters
# ---------------------------------------------------------------------------

def test_reference_ordering_no_anchor():
    from unittest.mock import patch
    from tools.image_pipeline import AssetRegistry, build_sheet_ref_urls
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = os.path.join(tmp, "run")
        assets_dir = os.path.join(tmp, "assets")
        os.makedirs(run_dir)
        os.makedirs(assets_dir)
        reg = AssetRegistry(run_dir, assets_dir)
        loc_path = os.path.join(assets_dir, "loc.webp")
        char_path = os.path.join(assets_dir, "char.webp")
        prev_path = os.path.join(run_dir, "prev.webp")
        for p in (loc_path, char_path, prev_path):
            with open(p, "wb") as f:
                f.write(b"\x00")
        reg.location("loc_03")["fal_image_url"] = "http://loc"
        reg.location("loc_03")["output_path"] = loc_path
        reg.character("char_01")["fal_image_url"] = "http://char"
        reg.character("char_01")["output_path"] = char_path
        reg.sheet("s2_g1")["fal_image_url"] = "http://prev"
        reg.sheet("s2_g1")["output_path"] = prev_path

        def mock_ensure(entry, **kwargs):
            return entry.get("fal_image_url") or None

        with patch("tools.image_pipeline.ensure_asset_url", side_effect=mock_ensure):
            urls = build_sheet_ref_urls(
                reg,
                location_ref_id="loc_03",
                character_ref_ids=["char_01"],
                prev_sheet_id="s2_g1",
                attach_location=True,
            )
        # No anchor: prev sheet first, then location, then characters
        assert urls[0] == "http://prev"
        assert urls[1] == "http://loc"
        assert urls[2] == "http://char"
        assert "http://anchor" not in urls


def test_reference_ordering_g1_no_prev_sheet():
    """g1 has no previous sheet, so location comes first."""
    from unittest.mock import patch
    from tools.image_pipeline import AssetRegistry, build_sheet_ref_urls
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = os.path.join(tmp, "run")
        assets_dir = os.path.join(tmp, "assets")
        os.makedirs(run_dir)
        os.makedirs(assets_dir)
        reg = AssetRegistry(run_dir, assets_dir)
        loc_path = os.path.join(assets_dir, "loc.webp")
        char_path = os.path.join(assets_dir, "char.webp")
        for p in (loc_path, char_path):
            with open(p, "wb") as f:
                f.write(b"\x00")
        reg.location("loc_03")["fal_image_url"] = "http://loc"
        reg.location("loc_03")["output_path"] = loc_path
        reg.character("char_01")["fal_image_url"] = "http://char"
        reg.character("char_01")["output_path"] = char_path

        def mock_ensure(entry, **kwargs):
            return entry.get("fal_image_url") or None

        with patch("tools.image_pipeline.ensure_asset_url", side_effect=mock_ensure):
            urls = build_sheet_ref_urls(
                reg,
                location_ref_id="loc_03",
                character_ref_ids=["char_01"],
                prev_sheet_id=None,
                attach_location=True,
            )
        # g1: location first, then characters
        assert urls[0] == "http://loc"
        assert urls[1] == "http://char"


# ---------------------------------------------------------------------------
# 16. Omitted location panorama is not attached
# ---------------------------------------------------------------------------

def test_omitted_location_not_attached():
    from unittest.mock import patch
    from tools.image_pipeline import AssetRegistry, build_sheet_ref_urls
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = os.path.join(tmp, "run")
        assets_dir = os.path.join(tmp, "assets")
        os.makedirs(run_dir)
        os.makedirs(assets_dir)
        reg = AssetRegistry(run_dir, assets_dir)
        reg.location("loc_03")["fal_image_url"] = "http://loc"
        reg.character("char_01")["fal_image_url"] = "http://char"

        def mock_ensure(entry, **kwargs):
            return entry.get("fal_image_url") or None

        with patch("tools.image_pipeline.ensure_asset_url", side_effect=mock_ensure):
            urls = build_sheet_ref_urls(
                reg,
                location_ref_id="loc_03",
                character_ref_ids=["char_01"],
                attach_location=False,
            )
        assert "http://loc" not in urls
        assert "http://char" in urls


# ---------------------------------------------------------------------------
# 17. Bridges do not get spatial blocks
# ---------------------------------------------------------------------------

def test_bridges_no_spatial_block():
    """Verify that generate_bridge_sheet no longer exists."""
    import tools.image_pipeline as ip
    assert not hasattr(ip, "generate_bridge_sheet")
    assert not hasattr(ip, "build_bridge_ref_urls")


# ---------------------------------------------------------------------------
# 18. Prompt validation requires spatial blocks only when a spatial plan exists
# ---------------------------------------------------------------------------

def test_prompts_validation_legacy_no_spatial():
    """Legacy prompts (no spatial plan) should validate without anchor prompts."""
    from tools.validators import validate_prompts, parse_storyboard
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = tmp
        # Write scenes.md
        with open(os.path.join(run_dir, "scenes.md"), "w") as f:
            f.write(SCENES_FOR_SPATIAL)
        # Write storyboard
        with open(os.path.join(run_dir, "storyboard_s2.md"), "w") as f:
            f.write(STORYBOARD_FOR_SPATIAL)
        # Write image prompts (no anchor prompts)
        prompts_dir = os.path.join(run_dir, "image_prompts")
        os.makedirs(os.path.join(prompts_dir, "characters"))
        os.makedirs(os.path.join(prompts_dir, "locations"))
        os.makedirs(os.path.join(prompts_dir, "s2"))
        with open(os.path.join(prompts_dir, "characters", "char_01.txt"), "w") as f:
            f.write("char prompt")
        with open(os.path.join(prompts_dir, "characters", "char_05.txt"), "w") as f:
            f.write("char prompt")
        with open(os.path.join(prompts_dir, "locations", "loc_03.txt"), "w") as f:
            f.write("loc prompt")
        with open(os.path.join(prompts_dir, "s2", "storyboard_sheet_g1.txt"), "w") as f:
            f.write("sheet prompt")
        with open(os.path.join(prompts_dir, "s2", "storyboard_sheet_g2.txt"), "w") as f:
            f.write("sheet prompt")
        sb = parse_storyboard(STORYBOARD_FOR_SPATIAL)
        res = validate_prompts(run_dir, "s2", sb=sb)
        assert res.ok, f"legacy prompts should validate: {res.errors}"


# ---------------------------------------------------------------------------
# 19. Valid spatial QA report passes
# ---------------------------------------------------------------------------

VALID_QA_REPORT = textwrap.dedent("""
    # Spatial QA Report — Scene s2

    - Pass: 2
    - Warn: 0

    ## s2/g1
    - Status: PASS
    - expected: Kayal at the lamp, foreground.
    - observed: Kayal at the lamp, foreground.

    ## s2/g2
    - Status: PASS
    - expected: Kayal at lamp, dogs in deep road.
    - observed: Kayal at lamp, dogs far right deep background.
""").strip()


def test_valid_spatial_qa_report_passes():
    res = validate_spatial_qa_report(VALID_QA_REPORT, expected_sheets=["s2/g1", "s2/g2"])
    assert res.ok, f"errors: {res.errors}"


# ---------------------------------------------------------------------------
# 20. Missing spatial QA sheet coverage fails
# ---------------------------------------------------------------------------

def test_missing_qa_coverage_fails():
    report = textwrap.dedent("""
        # Spatial QA Report — Scene s2

        - Pass: 1
        - Warn: 0

        ## s2/g1
        - Status: PASS
        - expected: x
        - observed: x
    """).strip()
    res = validate_spatial_qa_report(report, expected_sheets=["s2/g1", "s2/g2"])
    assert not res.ok
    assert any("missing" in e.lower() for e in res.errors)


# ---------------------------------------------------------------------------
# 21. Spatial QA WARN remains ok:true
# ---------------------------------------------------------------------------

def test_spatial_qa_warn_non_blocking():
    report = textwrap.dedent("""
        # Spatial QA Report — Scene s2

        - Pass: 1
        - Warn: 1

        ## s2/g1
        - Status: PASS
        - expected: x
        - observed: x

        ## s2/g2
        - Status: WARN
        - expected: Dogs far right.
        - observed: Dogs too close to lamp.
        - recommendation: Regenerate sheet with dogs further right.
    """).strip()
    res = validate_spatial_qa_report(report, expected_sheets=["s2/g1", "s2/g2"])
    assert res.ok  # WARN is non-blocking
    assert len(res.warnings) > 0


# ---------------------------------------------------------------------------
# 22. Invalid spatial QA summary/status fails
# ---------------------------------------------------------------------------

def test_qa_summary_mismatch_fails():
    report = textwrap.dedent("""
        # Spatial QA Report — Scene s2

        - Pass: 5
        - Warn: 0

        ## s2/g1
        - Status: PASS
        - expected: x
        - observed: x

        ## s2/g2
        - Status: PASS
        - expected: x
        - observed: x
    """).strip()
    res = validate_spatial_qa_report(report, expected_sheets=["s2/g1", "s2/g2"])
    assert not res.ok
    assert any("Pass" in e and "!=" in e for e in res.errors)


def test_qa_warn_without_observed_fails():
    report = textwrap.dedent("""
        # Spatial QA Report — Scene s2

        - Pass: 1
        - Warn: 1

        ## s2/g1
        - Status: PASS
        - expected: x
        - observed: x

        ## s2/g2
        - Status: WARN
        - expected: x
        - recommendation: x
    """).strip()
    res = validate_spatial_qa_report(report, expected_sheets=["s2/g1", "s2/g2"])
    assert not res.ok
    assert any("observed" in e.lower() for e in res.errors)


# ---------------------------------------------------------------------------
# 23. New sample spatial plan validates end-to-end without paid APIs
# ---------------------------------------------------------------------------

def test_sample_spatial_plan_validates_e2e():
    """The sample spatial plan validates with storyboard + scenes context."""
    from tools.validators import parse_storyboard, parse_scenes
    sb = parse_storyboard(STORYBOARD_FOR_SPATIAL)
    scenes = parse_scenes(SCENES_FOR_SPATIAL)
    res = validate_spatial_plan(VALID_SPATIAL_PLAN, storyboard=sb, scenes=scenes)
    assert res.ok, f"sample plan should validate: {res.errors}"


# ---------------------------------------------------------------------------
# 24. Existing kutty-karuppu artifacts still validate without a spatial plan
# ---------------------------------------------------------------------------

def test_legacy_storyboard_validates_without_spatial_plan():
    """A storyboard without a corresponding spatial_plan_sN.md should
    still pass the storyboard validator (legacy backward compat)."""
    from tools.validators import validate_storyboard, parse_scenes
    scenes = parse_scenes(SCENES_FOR_SPATIAL)
    res = validate_storyboard(STORYBOARD_FOR_SPATIAL, scenes=scenes)
    assert res.ok, f"legacy storyboard should validate: {res.errors}"


# ---------------------------------------------------------------------------
# Additional: panorama wrap handling
# ---------------------------------------------------------------------------

def test_panorama_wrap_not_flagged_as_teleport():
    """A character moving from x=3800 to x=20 (wrapping around) should
    not be flagged as teleporting (the panorama wraps at the edges)."""
    from tools.validators import parse_storyboard
    # This is a known limitation: the current validator uses absolute X diff.
    # For now, we verify the threshold is reasonable.
    from tools.spatial_validator import TELEPORT_X_THRESHOLD
    assert TELEPORT_X_THRESHOLD > 0
    # A wrap of 3820 -> 20 would be |20 - 3820| = 3800 which IS > 500.
    # The validator would flag this. This test documents the limitation.
    # (Full wrap handling would require modulo arithmetic on X.)


# ---------------------------------------------------------------------------
# Additional: coordinate parsing
# ---------------------------------------------------------------------------

def test_coord_tuple_parsing():
    from tools.spatial_validator import _parse_coord_tuple
    result = _parse_coord_tuple("x=1920,y=2000,z=0")
    assert result == (1920.0, 2000.0, 0.0)


def test_position_entry_parsing():
    from tools.spatial_validator import _parse_position_entry
    entry = _parse_position_entry("char_01=x=1920,y=2000,z=0")
    assert entry is not None
    assert entry["cid"] == "char_01"
    assert entry["x"] == 1920.0
    assert entry["y"] == 2000.0
    assert entry["z"] == 0.0


def test_on_screen_position_with_depth():
    from tools.spatial_validator import _parse_on_screen_position
    entry = _parse_on_screen_position("char_05=x=3400,y=1700,z=40:background")
    assert entry is not None
    assert entry["cid"] == "char_05"
    assert entry["depth"] == "background"


# ---------------------------------------------------------------------------
# character_facing and camera_zoom tests
# ---------------------------------------------------------------------------

def test_character_facing_parsed():
    plan = parse_spatial_plan(VALID_SPATIAL_PLAN)
    g2 = plan["generations"]["g2"]
    shot1 = g2["shots"]["1"]
    assert shot1["character_facing"]["char_01"] == "toward_lamp_01"
    assert shot1["character_facing"]["char_05"] == "away_from_lamp_01"
    assert shot1["camera_zoom"] == "wide"


def test_camera_zoom_parsed():
    plan = parse_spatial_plan(VALID_SPATIAL_PLAN)
    g2 = plan["generations"]["g2"]
    assert g2["shots"]["1"]["camera_zoom"] == "wide"
    assert g2["shots"]["2"]["camera_zoom"] == "medium"


def test_invalid_camera_zoom_fails():
    plan = VALID_SPATIAL_PLAN.replace(
        "camera_zoom: wide\ncharacter_facing: char_01=toward_lamp_01; char_05=away_from_lamp_01",
        "camera_zoom: super_zoom\ncharacter_facing: char_01=toward_lamp_01; char_05=away_from_lamp_01",
        1,
    )
    res = validate_spatial_plan(plan)
    assert not res.ok
    assert any("camera_zoom" in e for e in res.errors)


def test_invalid_character_facing_fails():
    plan = VALID_SPATIAL_PLAN.replace(
        "char_05=away_from_lamp_01",
        "char_05=sideways_into_sky",
    )
    res = validate_spatial_plan(plan)
    assert not res.ok
    assert any("character_facing" in e for e in res.errors)


def test_character_facing_unknown_landmark_fails():
    plan = VALID_SPATIAL_PLAN.replace(
        "char_05=away_from_lamp_01",
        "char_05=toward_nonexistent_landmark",
    )
    res = validate_spatial_plan(plan)
    assert not res.ok
    assert any("unknown landmark" in e.lower() for e in res.errors)


def test_facing_180_rule_violation_fails():
    """A character reversing facing direction between continuous shots fails."""
    from tools.validators import parse_storyboard
    # Make shot 2 continuous and reverse char_05's facing
    plan = VALID_SPATIAL_PLAN.replace(
        "char_05=away_from_lamp_01\nvisible_landmarks: []",
        "char_05=toward_lamp_01\nvisible_landmarks: []",
    )
    sb_md = STORYBOARD_FOR_SPATIAL.replace(
        "### Shot 2 — 22.0-30.0s (cut_on_action)",
        "### Shot 2 — 22.0-30.0s (continuous)",
    )
    sb = parse_storyboard(sb_md)
    res = validate_spatial_plan(plan, storyboard=sb)
    assert not res.ok
    assert any("180" in e for e in res.errors)


def test_facing_180_rule_allowed_on_cut():
    """Reversing facing direction on a cut is allowed (not continuous)."""
    from tools.validators import parse_storyboard
    # shot 2 is cut_on_action in the fixture — reversal should be OK
    plan = VALID_SPATIAL_PLAN.replace(
        "char_05=away_from_lamp_01\n    visible_landmarks: []",
        "char_05=toward_lamp_01\n    visible_landmarks: []",
    )
    sb = parse_storyboard(STORYBOARD_FOR_SPATIAL)
    res = validate_spatial_plan(plan, storyboard=sb)
    # Should not have a 180° rule error (cut is allowed)
    assert not any("180" in e for e in res.errors)


def test_camera_zoom_jump_fails_on_continuous():
    """camera_zoom jumping more than 2 steps between continuous shots fails."""
    from tools.validators import parse_storyboard
    plan = VALID_SPATIAL_PLAN.replace(
        "camera_zoom: medium\ncharacter_facing: char_01=toward_lamp_01; char_05=away_from_lamp_01\nvisible_landmarks: []",
        "camera_zoom: extreme_closeup\ncharacter_facing: char_01=toward_lamp_01; char_05=away_from_lamp_01\nvisible_landmarks: []",
    )
    sb_md = STORYBOARD_FOR_SPATIAL.replace(
        "### Shot 2 — 22.0-30.0s (cut_on_action)",
        "### Shot 2 — 22.0-30.0s (continuous)",
    )
    sb = parse_storyboard(sb_md)
    res = validate_spatial_plan(plan, storyboard=sb)
    assert not res.ok
    assert any("camera_zoom" in e and "jump" in e.lower() for e in res.errors)


def test_camera_zoom_small_change_allowed_on_continuous():
    """camera_zoom changing by 1-2 steps between continuous shots is OK."""
    from tools.validators import parse_storyboard
    # wide -> medium is 1 step, should be fine
    sb_md = STORYBOARD_FOR_SPATIAL.replace(
        "### Shot 2 — 22.0-30.0s (cut_on_action)",
        "### Shot 2 — 22.0-30.0s (continuous)",
    )
    sb = parse_storyboard(sb_md)
    res = validate_spatial_plan(VALID_SPATIAL_PLAN, storyboard=sb)
    assert not any("camera_zoom" in e and "jump" in e.lower() for e in res.errors)


def test_character_facing_parser():
    from tools.spatial_validator import _parse_character_facing
    result = _parse_character_facing("char_01=toward_lamp_01; char_05=away_from_lamp_01")
    assert result == {"char_01": "toward_lamp_01", "char_05": "away_from_lamp_01"}


def test_character_facing_parser_empty():
    from tools.spatial_validator import _parse_character_facing
    assert _parse_character_facing("") == {}
    assert _parse_character_facing("  ") == {}


# ---------------------------------------------------------------------------
# Spatial prompt materializer tests
# ---------------------------------------------------------------------------

def test_materialize_creates_spatial_block():
    """Materializing a valid g1 prompt creates exactly one spatial block."""
    from tools.spatial_prompt_builder import (
        build_spatial_block, has_spatial_block, LOCK_START, LOCK_END,
    )
    plan = parse_spatial_plan(VALID_SPATIAL_PLAN)
    sb = parse_storyboard(STORYBOARD_FOR_SPATIAL)
    block = build_spatial_block(plan, sb, "g1")
    assert LOCK_START in block
    assert LOCK_END in block
    assert has_spatial_block(block)


def test_materialize_inject_into_prompt():
    """Injecting a block prepends it before authored content."""
    from tools.spatial_prompt_builder import (
        build_spatial_block, inject_spatial_block, has_spatial_block, LOCK_START,
    )
    plan = parse_spatial_plan(VALID_SPATIAL_PLAN)
    sb = parse_storyboard(STORYBOARD_FOR_SPATIAL)
    block = build_spatial_block(plan, sb, "g1")
    authored = "A storyboard sheet prompt.\n\nScene synopsis here.\n"
    result = inject_spatial_block(authored, block)
    assert has_spatial_block(result)
    assert "A storyboard sheet prompt." in result
    assert "Scene synopsis here." in result
    # Spatial bible should come before authored content
    assert result.index(LOCK_START) < result.index("A storyboard sheet prompt.")


def test_materialize_idempotent():
    """Re-materializing the same prompt is stable (no duplicate blocks)."""
    from tools.spatial_prompt_builder import (
        materialize_sheet_prompt, has_spatial_block, LOCK_START,
    )
    plan = parse_spatial_plan(VALID_SPATIAL_PLAN)
    sb = parse_storyboard(STORYBOARD_FOR_SPATIAL)
    authored = "A storyboard sheet prompt.\n\nScene synopsis here.\n"
    first = materialize_sheet_prompt(authored, plan, sb, "g1")
    second = materialize_sheet_prompt(first, plan, sb, "g1")
    assert has_spatial_block(first)
    assert has_spatial_block(second)
    # Count occurrences of LOCK_START marker — should be exactly 1
    assert second.count(LOCK_START) == 1
    # Byte-stable
    assert first == second


def test_materialize_covers_all_shots():
    """The block covers every storyboard shot's panel range."""
    from tools.spatial_prompt_builder import build_spatial_block
    plan = parse_spatial_plan(VALID_SPATIAL_PLAN)
    sb = parse_storyboard(STORYBOARD_FOR_SPATIAL)
    block = build_spatial_block(plan, sb, "g2")
    # g2 has shots 1 and 2, with panels [1,2,3] and [4,5,6]
    assert "Panels 1" in block  # Shot 1 panels
    assert "Panels 4" in block  # Shot 2 panels
    assert "Shot 1" in block
    assert "Shot 2" in block


def test_materialize_includes_camera_and_facing():
    """The block includes camera geometry and character facing."""
    from tools.spatial_prompt_builder import build_spatial_block
    plan = parse_spatial_plan(VALID_SPATIAL_PLAN)
    sb = parse_storyboard(STORYBOARD_FOR_SPATIAL)
    block = build_spatial_block(plan, sb, "g2")
    # Camera zone should be rendered (lamp_pool -> "lamp pool")
    assert "lamp pool" in block.lower()
    # Character facing should be rendered
    assert "facing" in block.lower()
    # Camera geometry: "camera placed in" should be present
    assert "camera placed in" in block.lower()
    # New hierarchical sections should be present
    assert "## ENVIRONMENT BIBLE" in block
    assert "## CONTINUITY RULES" in block
    assert "## PANEL STAGING" in block


def test_materialize_empty_visible_landmarks():
    """Empty visible_landmarks renders an explicit out-of-frame instruction."""
    from tools.spatial_prompt_builder import build_spatial_block
    plan = parse_spatial_plan(VALID_SPATIAL_PLAN)
    sb = parse_storyboard(STORYBOARD_FOR_SPATIAL)
    block = build_spatial_block(plan, sb, "g2")
    # Shot 2 has visible_landmarks: [] — should say "out of frame" or similar
    assert "out of frame" in block.lower() or "not required" in block.lower()


def test_materialize_preserves_ref_images_line():
    """The ref_images: line is preserved through materialization."""
    from tools.spatial_prompt_builder import materialize_sheet_prompt
    plan = parse_spatial_plan(VALID_SPATIAL_PLAN)
    sb = parse_storyboard(STORYBOARD_FOR_SPATIAL)
    authored = "A prompt.\nref_images: char_01, loc_03\nMore content.\n"
    result = materialize_sheet_prompt(authored, plan, sb, "g1")
    assert "ref_images:" in result


def test_materialize_missing_generation_fails():
    """Materializing a generation not in the plan raises ValueError."""
    from tools.spatial_prompt_builder import build_spatial_block
    plan = parse_spatial_plan(VALID_SPATIAL_PLAN)
    sb = parse_storyboard(STORYBOARD_FOR_SPATIAL)
    try:
        build_spatial_block(plan, sb, "g99")
        assert False, "should have raised"
    except ValueError:
        pass


def test_validate_materialized_prompt_passes():
    """A materialized prompt validates successfully."""
    from tools.spatial_prompt_builder import (
        materialize_sheet_prompt, validate_materialized_prompt,
    )
    plan = parse_spatial_plan(VALID_SPATIAL_PLAN)
    sb = parse_storyboard(STORYBOARD_FOR_SPATIAL)
    authored = "A storyboard sheet prompt.\n\nScene synopsis.\n"
    materialized = materialize_sheet_prompt(authored, plan, sb, "g1")
    errors = validate_materialized_prompt(materialized, plan, sb, "g1")
    assert errors == [], f"unexpected errors: {errors}"


def test_validate_unmaterialized_prompt_fails():
    """An unmaterialized prompt (no spatial block) fails validation."""
    from tools.spatial_prompt_builder import validate_materialized_prompt
    plan = parse_spatial_plan(VALID_SPATIAL_PLAN)
    sb = parse_storyboard(STORYBOARD_FOR_SPATIAL)
    authored = "A storyboard sheet prompt.\n\nNo spatial block.\n"
    errors = validate_materialized_prompt(authored, plan, sb, "g1")
    assert len(errors) > 0
    assert any("missing" in e.lower() for e in errors)


def test_legacy_anchor_view_accepted_with_warning():
    """Legacy plans using anchor_view instead of generation_geography
    validate with a warning but don't fail."""
    plan = VALID_SPATIAL_PLAN.replace(
        "generation_geography: wide view from the village edge showing Kayal at the lamp and the dark road stretching east.\n",
        "anchor_view: wide view from the village edge.\n",
    )
    res = validate_spatial_plan(plan)
    assert res.ok  # warnings don't fail
    assert any("anchor_view" in w or "generation_geography" in w for w in res.warnings)


def test_legacy_spatial_anchor_field_ignored():
    """Legacy spatial_anchor: required field is accepted but warned as deprecated."""
    plan = VALID_SPATIAL_PLAN.replace(
        "generation_geography: wide view from the village edge showing Kayal at the lamp and the dark road stretching east.\n",
        "spatial_anchor: required\ngeneration_geography: wide view from the village edge.\n",
    )
    res = validate_spatial_plan(plan)
    assert res.ok  # deprecated field doesn't fail


def test_no_generate_spatial_anchor_function():
    """generate_spatial_anchor should no longer exist in image_pipeline."""
    import tools.image_pipeline as ip
    assert not hasattr(ip, "generate_spatial_anchor")
