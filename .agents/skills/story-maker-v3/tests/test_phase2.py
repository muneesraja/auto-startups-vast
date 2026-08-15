"""Unit tests: duration budget, Minimax helpers, validators (de-hallucination)."""

import textwrap

from tools import duration_budget as db
from tools import validators


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


def test_generation_count_for_scene():
    assert db.generation_count_for_scene(70) == 5   # ceil(70/15)
    assert db.generation_count_for_scene(15) == 1
    assert db.generation_count_for_scene(16) == 2
    assert db.generation_count_for_scene(0) == 0


def test_minimax_frames_snap():
    # max(5, round(s*24)) bumped to the next count where frames % 17 == 5.
    for secs in (5, 8, 12.5, 15):
        n = db.minimax_frames(secs)
        assert n % 17 == 5
        assert n >= round(secs * 24)
    assert db.minimax_frames(0.01) >= 5


def test_within_tolerance():
    assert db.within_tolerance(80, 80)
    assert db.within_tolerance(86, 80, tolerance_percent=10)
    assert not db.within_tolerance(100, 80, tolerance_percent=10)


# --- minimax_workflow: pure helpers ------------------------------------------

def test_resolution_for_matches_workflow_table():
    from tools.minimax_workflow import resolution_for

    assert resolution_for(0.6, "16:9") == (1056, 608)
    assert resolution_for(0.2, "16:9") == (608, 352)
    w, h = resolution_for(0.6, "16:9")
    assert w % 32 == 0 and h % 32 == 0


# --- validators: inline parsers ---------------------------------------------

def test_parse_cid_list():
    assert validators.parse_cid_list("[char_01, char_02]") == ["char_01", "char_02"]
    assert validators.parse_cid_list("char_01") == ["char_01"]
    assert validators.parse_cid_list("[]") == []


def test_parse_int_list():
    assert validators.parse_int_list("[1, 2, 3]") == [1, 2, 3]
    assert validators.parse_int_list("[1, x]") == [1, -1]


# --- validators: scenes ------------------------------------------------------

SCENES_MD = textwrap.dedent("""
    # Scenes
    target_seconds: 55
    scene_budget: 70

    ## Scene s1 — Baby meets dino
    scene_id: s1
    target_seconds: 27
    cast: [char_01, char_02]
    characters_present: [char_01, char_02]
    location_id: loc_basement
    beat: Baby flees the dino, then befriends it.

    ## Scene s2 — Up the stairs
    scene_id: s2
    target_seconds: 28
    cast: [char_01, char_02]
    characters_present: [char_01, char_02]
    location_id: loc_basement
    beat: They climb toward the light together.
""").strip()


def test_validate_scenes_pass():
    res = validators.validate_scenes(SCENES_MD, target_seconds=55)
    assert res.ok, res.errors


def test_validate_scenes_fail_missing_location():
    bad = SCENES_MD.replace("location_id: loc_basement\nbeat: Baby flees the dino, then befriends it.",
                            "beat: Baby flees the dino, then befriends it.")
    res = validators.validate_scenes(bad, target_seconds=55)
    assert not res.ok
    assert any("location_id" in e for e in res.errors)


# --- validators: storyboard (generations + 15s rule) --------------------------

STORYBOARD_MD = textwrap.dedent("""
    # Scene s1 — Baby meets dino
    scene_id: s1
    target_seconds: 27
    cast: [char_01, char_02]
    location_ref_id: loc_basement

    ## Generation g1 — 0.0-15.0s
    duration_seconds: 15.0
    panel_grid: 2x3

    ### Shot 1 — 0.0-7.2s (continuous)
    panels: [1, 2, 3]
    characters_present: [char_01, char_02]
    action: The baby runs down the corridor; the dino bounces behind; the baby hits a dead end and throws a stick.
    camera: Handheld tracking shot behind the baby, then arc shot to a front three-quarter angle.
    audio: Little footsteps, excited chirps, stick clattering.
    dialogue:

    ### Shot 2 — 7.2-15.0s (hard_cut)
    panels: [4, 5, 6]
    characters_present: [char_01, char_02]
    action: The baby leaps, lands on the dino; they tumble; fear melts into a first pat.
    camera: Tracking Shot from a low side angle, then slow Push In at slow speed.
    audio: Soft thud, warm strings.
    dialogue: char_02: "Mama."

    ## Generation g2 — 15.0-27.0s
    duration_seconds: 12.0
    panel_grid: 2x2

    ### Shot 1 — 15.0-27.0s (continuous)
    panels: [1, 2, 3, 4]
    characters_present: [char_01, char_02]
    action: The baby pets the dino; the dino leans in; both smile in the dusty half-light.
    camera: Static Shot, then Zoom In with small amplitude at slow speed.
    audio: Calm ambience, music softens.
    dialogue:

    ## Scene-end handoff -> scene s2
    on_screen: [char_01, char_02]
    mood: calm
    transition: hard_cut
""").strip()


def test_validate_storyboard_pass():
    scenes = validators.parse_scenes(SCENES_MD)
    res = validators.validate_storyboard(STORYBOARD_MD, scenes=scenes)
    assert res.ok, res.errors


def test_validate_storyboard_catches_over_15s_generation():
    bad = STORYBOARD_MD.replace("## Generation g1 — 0.0-15.0s", "## Generation g1 — 0.0-16.0s") \
                       .replace("duration_seconds: 15.0", "duration_seconds: 16.0") \
                       .replace("### Shot 2 — 7.2-15.0s (hard_cut)", "### Shot 2 — 7.2-16.0s (hard_cut)") \
                       .replace("## Generation g2 — 15.0-27.0s", "## Generation g2 — 16.0-27.0s") \
                       .replace("### Shot 1 — 15.0-27.0s (continuous)", "### Shot 1 — 16.0-27.0s (continuous)") \
                       .replace("duration_seconds: 12.0", "duration_seconds: 11.0")
    res = validators.validate_storyboard(bad)
    assert not res.ok
    assert any("15s per generation" in e or "outside [5,15]" in e for e in res.errors)


def test_validate_storyboard_catches_shot_straddling_boundary():
    bad = STORYBOARD_MD.replace("### Shot 2 — 7.2-15.0s (hard_cut)", "### Shot 2 — 7.2-17.0s (hard_cut)")
    res = validators.validate_storyboard(bad)
    assert not res.ok
    assert any("straddle" in e or "leaves generation" in e for e in res.errors)


def test_validate_storyboard_catches_invented_char_and_bad_panels():
    bad = STORYBOARD_MD.replace("characters_present: [char_01, char_02]",
                                "characters_present: [char_01, char_99]", 1) \
                       .replace("panels: [4, 5, 6]", "panels: [4, 5]")
    res = validators.validate_storyboard(bad)
    assert not res.ok
    assert any("char_99" in e for e in res.errors)
    assert any("exactly once" in e for e in res.errors)


def test_validate_storyboard_catches_gap_between_generations():
    bad = STORYBOARD_MD.replace("## Generation g2 — 15.0-27.0s", "## Generation g2 — 16.0-27.0s")
    res = validators.validate_storyboard(bad)
    assert not res.ok
    assert any("contiguous" in e for e in res.errors)


def test_validate_storyboard_warns_on_unknown_camera_term():
    noisy = STORYBOARD_MD.replace(
        "camera: Static Shot, then Zoom In with small amplitude at slow speed.",
        "camera: The camera does something artistic.",
    )
    res = validators.validate_storyboard(noisy)
    assert res.ok, res.errors
    assert any("motion term" in w for w in res.warnings)


# --- validators: video_prompt --------------------------------------------------

GOOD_PROMPT = textwrap.dedent("""
    Reference

    Use the provided storyboard as the exact visual guide for composition,
    framing, character appearance, environment, and sequence progression.

    Maintain the exact appearance of the toddler in the white onesie and the
    tiny green dinosaur with large yellow eyes throughout.

    Pixar-quality cinematic 3D animation.

    Timeline

    SHOT 1 — 0.0–7.2s (Continuous Shot)

    The baby runs through the corridor. The dino happily chases.
    Begin with a handheld tracking shot following behind the baby.

    Hard cinematic cut.

    SHOT 2 — 7.2–15.0s (Continuous Shot)

    The baby leaps and lands on the dino. They tumble gently.
    The dinosaur softly says,
    "Mama."
    Finish with a slow push in.

    Final frame:
    The baby pets the smiling dinosaur.

    Negative Prompt

    No identity changes.
    No text.
    No watermark.
""").strip()


def _sb():
    return validators.parse_storyboard(STORYBOARD_MD)


def test_validate_video_prompt_pass():
    res = validators.validate_video_prompt(GOOD_PROMPT, _sb(), "g1")
    assert res.ok, res.errors


def test_validate_video_prompt_catches_wrong_ranges():
    bad = GOOD_PROMPT.replace("SHOT 2 — 7.2–15.0s", "SHOT 2 — 7.2–14.0s")
    res = validators.validate_video_prompt(bad, _sb(), "g1")
    assert not res.ok
    assert any("SHOT 2" in e for e in res.errors)


def test_validate_video_prompt_catches_char_ids_and_missing_negative():
    bad = GOOD_PROMPT.replace("the toddler in the white onesie", "char_01") \
                     .replace("Negative Prompt", "Closing Notes")
    res = validators.validate_video_prompt(bad, _sb(), "g1")
    assert not res.ok
    assert any("char_01" in e for e in res.errors)
    assert any("Negative Prompt" in e for e in res.errors)


def test_validate_video_prompt_generation_local_times():
    # g2 is 15.0-27.0 scene-relative -> prompt must be 0.0-12.0 local.
    g2_prompt = GOOD_PROMPT.replace("SHOT 1 — 0.0–7.2s (Continuous Shot)", "SHOT 1 — 0.0–12.0s (Continuous Shot)")
    # strip the second shot block
    g2_prompt = g2_prompt.split("Hard cinematic cut.")[0] + "\nFinal frame:\nCalm.\n\nNegative Prompt\n\nNo text."
    res = validators.validate_video_prompt(g2_prompt, _sb(), "g2")
    assert res.ok, res.errors


def test_object_sheet_builder():
    from tools import object_sheet_builder, image_pipeline as ip
    import tempfile

    prompt = object_sheet_builder.build_object_sheet_prompt(
        {
            "context_title": "Episode 2 Props",
            "hero_props": "1. Baby Bottle\n2. Milk Canister",
            "secondary_props": "3. Kitchen Table",
        },
        render_style="Pixar 3D style",
    )
    assert "Episode 2 Props" in prompt
    assert "Baby Bottle" in prompt
    assert "Pixar 3D style" in prompt

    with tempfile.TemporaryDirectory() as tmp_dir:
        reg = ip.AssetRegistry(tmp_dir, tmp_dir)
        reg.object_asset("obj_test")["output_path"] = "/tmp/obj_test.webp"
        reg.save()

        reg2 = ip.AssetRegistry(tmp_dir, tmp_dir)
        assert reg2.data["objects"]["obj_test"]["output_path"] == "/tmp/obj_test.webp"
