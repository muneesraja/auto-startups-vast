"""Unit tests: duration budget, Minimax helpers, validators (de-hallucination)."""

import json
import os
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
    panel_grid: 2x3

    ### Shot 1 — 15.0-27.0s (continuous)
    panels: [1, 2, 3, 4, 5, 6]
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
    res = validators.validate_video_prompt_legacy(GOOD_PROMPT, _sb(), "g1")
    assert res.ok, res.errors


def test_validate_video_prompt_catches_wrong_ranges():
    bad = GOOD_PROMPT.replace("SHOT 2 — 7.2–15.0s", "SHOT 2 — 7.2–14.0s")
    res = validators.validate_video_prompt_legacy(bad, _sb(), "g1")
    assert not res.ok
    assert any("SHOT 2" in e for e in res.errors)


def test_validate_video_prompt_catches_char_ids_and_missing_negative():
    bad = GOOD_PROMPT.replace("the toddler in the white onesie", "char_01") \
                     .replace("Negative Prompt", "Closing Notes")
    res = validators.validate_video_prompt_legacy(bad, _sb(), "g1")
    assert not res.ok
    assert any("char_01" in e for e in res.errors)
    assert any("Negative Prompt" in e for e in res.errors)


def test_validate_video_prompt_generation_local_times():
    # g2 is 15.0-27.0 scene-relative -> prompt must be 0.0-12.0 local.
    g2_prompt = GOOD_PROMPT.replace("SHOT 1 — 0.0–7.2s (Continuous Shot)", "SHOT 1 — 0.0–12.0s (Continuous Shot)")
    # strip the second shot block
    g2_prompt = g2_prompt.split("Hard cinematic cut.")[0] + "\nFinal frame:\nCalm.\n\nNegative Prompt\n\nNo text."
    res = validators.validate_video_prompt_legacy(g2_prompt, _sb(), "g2")
    assert res.ok, res.errors


# --- bridge generations (no longer supported) --------------------------------

STORYBOARD_WITH_BRIDGE = textwrap.dedent("""
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
    action: The baby runs down the corridor; the dino bounces behind.
    camera: Handheld tracking shot behind the baby.
    audio: Little footsteps, excited chirps.
    dialogue:

    ### Shot 2 — 7.2-15.0s (hard_cut)
    panels: [4, 5, 6]
    characters_present: [char_01, char_02]
    action: The baby leaps, lands on the dino; they tumble.
    camera: Tracking Shot from a low side angle.
    audio: Soft thud, warm strings.
    dialogue: char_02: "Mama."

    ## Generation b1 — 0.0-8.0s
    duration_seconds: 8.0
    panel_grid: 1x2
    bridge_from: g1
    bridge_to: g2

    ### Shot 1 — 0.0-8.0s (continuous)
    panels: [1, 2]
    characters_present: [char_01, char_02]
    action: Whip pan from the baby's shocked face to the dinosaur's joyful expression.
    camera: Whip Pan fast through dust, then settle on a two-shot.
    audio: Whoosh of the pan, dust settling, warm strings.
    dialogue:

    ## Generation g2 — 15.0-27.0s
    duration_seconds: 12.0
    panel_grid: 2x3

    ### Shot 1 — 15.0-27.0s (continuous)
    panels: [1, 2, 3, 4, 5, 6]
    characters_present: [char_01, char_02]
    action: The baby pets the dino; the dino leans in; both smile.
    camera: Static Shot, then Zoom In with small amplitude at slow speed.
    audio: Calm ambience, music softens.
    dialogue:

    ## Scene-end handoff -> scene s2
    on_screen: [char_01, char_02]
    mood: calm
    transition: hard_cut
""").strip()


def test_storyboard_with_bridge_rejected():
    """Bridge generations are no longer supported and must fail validation."""
    res = validators.validate_storyboard(STORYBOARD_WITH_BRIDGE)
    assert not res.ok
    assert any("bridge" in e.lower() and "no longer" in e.lower() for e in res.errors)


def test_validate_storyboard_bridge_free_storyboard_unchanged():
    """A storyboard with no bridges must validate exactly as before."""
    res = validators.validate_storyboard(STORYBOARD_MD)
    assert res.ok, res.errors


# --- duration_budget: panel minimums -----------------------------------------

def test_panel_min_is_six():
    assert db.PANELS_MIN == 6


def test_no_bridge_constants():
    assert not hasattr(db, "BRIDGE_MIN")
    assert not hasattr(db, "BRIDGE_MAX")
    assert not hasattr(db, "BRIDGE_PANELS_MIN")
    # 6s and 10s also on the grid
    assert db.minimax_frames(6) % 17 == 5
    assert db.minimax_frames(10) % 17 == 5


# --- transition grammar (8 values) -------------------------------------------

def test_shot_transitions_has_8_values():
    assert len(validators.SHOT_TRANSITIONS) == 8
    assert "continuous" in validators.SHOT_TRANSITIONS
    assert "hard_cut" in validators.SHOT_TRANSITIONS
    assert "cut_on_action" in validators.SHOT_TRANSITIONS
    assert "reaction_cut" in validators.SHOT_TRANSITIONS
    assert "match_cut" in validators.SHOT_TRANSITIONS
    assert "whip_pan" in validators.SHOT_TRANSITIONS
    assert "audio_led" in validators.SHOT_TRANSITIONS
    assert "camera_move" in validators.SHOT_TRANSITIONS


def test_transition_phrases_complete():
    phrases = validators.TRANSITION_PHRASES
    assert phrases["hard_cut"] == "Hard cinematic cut."
    assert phrases["cut_on_action"] == "Cut on the action."
    assert phrases["reaction_cut"] == "Cut to the reaction."
    assert phrases["whip_pan"] == "Whip pan transition."
    assert phrases["audio_led"] == "Audio leads the cut."
    # match_cut is a prefix (completed with the element)
    assert phrases["match_cut"].startswith("Match cut on ")
    # continuous and camera_move have no phrase
    assert "continuous" not in phrases
    assert "camera_move" not in phrases


def test_anti_monotony_warns_on_all_identical_transitions():
    """4 shots all using hard_cut should warn (but not error)."""
    sb_md = textwrap.dedent("""
        # Scene s1 — Test
        scene_id: s1
        target_seconds: 15
        cast: [char_01, char_02]
        location_ref_id: loc_test

        ## Generation g1 — 0.0-15.0s
        duration_seconds: 15.0
        panel_grid: 2x3

        ### Shot 1 — 0.0-2.5s (hard_cut)
        panels: [1]
        characters_present: [char_01]
        action: Char runs left.
        camera: Tracking Shot fast.
        audio: Footsteps.

        ### Shot 2 — 2.5-5.0s (hard_cut)
        panels: [2]
        characters_present: [char_02]
        action: Char runs right.
        camera: Pan Left fast.
        audio: Door slam.

        ### Shot 3 — 5.0-7.5s (hard_cut)
        panels: [3]
        characters_present: [char_01]
        action: Char jumps.
        camera: Tilt Up fast.
        audio: Whoosh.

        ### Shot 4 — 7.5-10.0s (hard_cut)
        panels: [4]
        characters_present: [char_02]
        action: Char lands.
        camera: Static Shot.
        audio: Thud.

        ### Shot 5 — 10.0-12.5s (hard_cut)
        panels: [5]
        characters_present: [char_01]
        action: Char stands up.
        camera: Pedestal Up slow.
        audio: Clothes rustle.

        ### Shot 6 — 12.5-15.0s (hard_cut)
        panels: [6]
        characters_present: [char_02]
        action: Char walks away.
        camera: Static Shot.
        audio: Footsteps fading.

        ## Scene-end handoff -> scene s2
        on_screen: [char_01]
        mood: tense
        transition: hard_cut
    """).strip()
    res = validators.validate_storyboard(sb_md)
    assert res.ok  # warnings don't break ok
    assert any("all 6 transitions" in w for w in res.warnings)


def test_new_transition_values_accepted():
    """cut_on_action, reaction_cut, whip_pan, audio_led should all be accepted."""
    sb_md = textwrap.dedent("""
        # Scene s1 — Test
        scene_id: s1
        target_seconds: 15
        cast: [char_01, char_02]
        location_ref_id: loc_test

        ## Generation g1 — 0.0-15.0s
        duration_seconds: 15.0
        panel_grid: 2x3

        ### Shot 1 — 0.0-3.75s (cut_on_action)
        panels: [1, 2]
        characters_present: [char_01]
        action: Char throws a stick mid-swing.
        camera: Tracking Shot fast.
        audio: Whoosh of stick.

        ### Shot 2 — 3.75-7.5s (reaction_cut)
        panels: [3, 4]
        characters_present: [char_02]
        action: Char's eyes widen in shock.
        camera: Push In fast on eyes.
        audio: Sharp gasp.

        ### Shot 3 — 7.5-11.25s (audio_led)
        panels: [5]
        characters_present: [char_01]
        action: Door creaks open before we see it.
        camera: Static Shot.
        audio: Door creak starts before the visual.

        ### Shot 4 — 11.25-15.0s (whip_pan)
        panels: [6]
        characters_present: [char_02]
        action: Whip pan reveals the new room.
        camera: Whip Pan fast.
        audio: Whoosh.

        ## Scene-end handoff -> scene s2
        on_screen: [char_01]
        mood: tense
        transition: hard_cut
    """).strip()
    res = validators.validate_storyboard(sb_md)
    assert res.ok, res.errors


def test_audio_led_requires_audio():
    """audio_led transition with empty audio should error."""
    sb_md = STORYBOARD_MD.replace(
        "### Shot 2 — 7.2-15.0s (hard_cut)", "### Shot 2 — 7.2-15.0s (audio_led)"
    ).replace("audio: Soft thud, warm strings.", "audio:")
    res = validators.validate_storyboard(sb_md)
    assert not res.ok
    assert any("audio_led" in e for e in res.errors)


# --- 6-section Ref2VA validator ----------------------------------------------

REF2VA_PROMPT = textwrap.dedent("""
    subject_definitions:
    <Subject 1> is the toddler in the white onesie in <Picture 1>, with chubby cheeks and big eyes.
    <Subject 2> is the tiny green dinosaur in <Picture 1>, with large yellow eyes and a playful expression.
    <Picture 1> is the storyboard sheet for this generation.

    summary:
    [reference generation] The target video shows the baby running from the dinosaur, then befriending it.

    retention_analysis:
    <Subject 1> (appears in [Shot 1], [Shot 2]): fully_preserved - the toddler's onesie, chubby cheeks, and big eyes are retained.
    <Subject 2> (appears in [Shot 1], [Shot 2]): fully_preserved - the dinosaur's green color, large yellow eyes, and playful expression are retained.
    <Picture 1> (storyboard reference): fully_preserved - composition, framing, and panel sequence.

    detailed_description:
    The target video uses Pixar-quality cinematic 3D animation with warm natural lighting.
    [Shot 1] The baby runs through the corridor while the dinosaur happily chases. Begin with a handheld tracking shot following behind the baby. As the baby reaches the dead end, smoothly arc around to a front three-quarter angle. The dinosaur softly says, <d>[English] Mama.</d> Never generate duplicate characters or extra babies.
    [Shot 2] At 00:07.200, the shot cuts to the baby petting the smiling dinosaur. The baby carefully reaches out and gently pats the dinosaur's head. Finish with a slow cinematic push-in toward both characters.

    overall_soundscape:
    Little footsteps, excited chirps, stick clattering, soft thud, and warm strings throughout.

    non_diegetic_music:
    Gentle orchestral strings with a warm, uplifting tempo that softens in the second shot.
""").strip()


def test_ref2va_prompt_pass():
    res = validators.validate_video_prompt(REF2VA_PROMPT, _sb(), "g1")
    assert res.ok, res.errors


def test_ref2va_prompt_rejects_missing_sections():
    bad = REF2VA_PROMPT.replace("overall_soundscape:\n", "deleted_section:\n")
    res = validators.validate_video_prompt(bad, _sb(), "g1")
    assert not res.ok
    assert any("missing" in e for e in res.errors)


def test_ref2va_prompt_rejects_shot1_with_timestamp():
    bad = REF2VA_PROMPT.replace("[Shot 1]", "[Shot 1] At 00:00.000")
    res = validators.validate_video_prompt(bad, _sb(), "g1")
    assert not res.ok
    assert any("[Shot 1]" in e and "timestamp" in e for e in res.errors)


def test_ref2va_prompt_rejects_non_increasing_timestamps():
    # 5.0s is increasing from Shot 1 (0.0), but disagrees with storyboard (7.2s)
    bad = REF2VA_PROMPT.replace("At 00:07.200", "At 00:05.000")
    res = validators.validate_video_prompt(bad, _sb(), "g1")
    assert not res.ok
    assert any("storyboard shot start" in e for e in res.errors)


def test_ref2va_prompt_rejects_undefined_label():
    # Replace only in detailed_description, not in subject_definitions
    bad = REF2VA_PROMPT.replace(
        "[Shot 1] The baby runs", "[Shot 1] <Subject 3> runs"
    )
    res = validators.validate_video_prompt(bad, _sb(), "g1")
    assert not res.ok
    assert any("not defined" in e for e in res.errors)


def test_ref2va_prompt_rejects_char_nn():
    bad = REF2VA_PROMPT.replace("the toddler in the white onesie", "char_01")
    res = validators.validate_video_prompt(bad, _sb(), "g1")
    assert not res.ok
    assert any("char_01" in e for e in res.errors)


def test_ref2va_prompt_rejects_bad_task_type():
    bad = REF2VA_PROMPT.replace("[reference generation]", "[unknown type]")
    res = validators.validate_video_prompt(bad, _sb(), "g1")
    assert not res.ok
    assert any("unknown type" in e for e in res.errors)


def test_ref2va_prompt_rejects_wrong_shot_count():
    # Add a third shot inside detailed_description (before overall_soundscape)
    bad = REF2VA_PROMPT.replace(
        "\noverall_soundscape:",
        "\n[Shot 3] At 00:12.000, the shot cuts to nothing.\noverall_soundscape:"
    )
    res = validators.validate_video_prompt(bad, _sb(), "g1")
    assert not res.ok
    assert any("3 [Shot N]" in e for e in res.errors)


def test_ref2va_prompt_rejects_empty_audio_section():
    bad = REF2VA_PROMPT.replace(
        "overall_soundscape:\nLittle footsteps, excited chirps, stick clattering, soft thud, and warm strings throughout.",
        "overall_soundscape:\n"
    )
    res = validators.validate_video_prompt(bad, _sb(), "g1")
    assert not res.ok
    assert any("overall_soundscape" in e for e in res.errors)


def test_legacy_validator_still_works():
    """The legacy 4-part validator should still pass on the old GOOD_PROMPT."""
    res = validators.validate_video_prompt_legacy(GOOD_PROMPT, _sb(), "g1")
    assert res.ok, res.errors


# --- shot_size + composition schema fields (Phase 1) ------------------------

def test_shot_sizes_has_7_values():
    assert len(validators.SHOT_SIZES) == 7
    for s in ("extreme_wide", "wide", "full", "medium",
              "medium_closeup", "closeup", "extreme_closeup"):
        assert s in validators.SHOT_SIZES


def test_composition_types_has_12_values():
    assert len(validators.COMPOSITION_TYPES) == 12
    for c in ("rule_of_thirds", "center", "symmetry", "leading_lines",
              "negative_space", "depth", "silhouette", "frame_within_frame",
              "visual_hierarchy", "headroom", "look_room", "screen_direction"):
        assert c in validators.COMPOSITION_TYPES


def _make_storyboard_with_shots(shots_config: str) -> str:
    """Build a minimal valid storyboard with custom shot fields."""
    return textwrap.dedent(f"""
        # Scene s1 — Test
        scene_id: s1
        target_seconds: 15
        cast: [char_01, char_02]
        location_ref_id: loc_test

        ## Generation g1 — 0.0-15.0s
        duration_seconds: 15.0
        panel_grid: 2x3
{shots_config}
        ## Scene-end handoff -> scene s2
        on_screen: [char_01]
        mood: tense
        transition: hard_cut
    """).strip()


def test_shot_size_valid_values_accepted():
    for size in validators.SHOT_SIZES:
        shots = f"""
        ### Shot 1 — 0.0-7.5s (continuous)
        panels: [1, 2, 3]
        characters_present: [char_01]
        shot_size: {size}
        composition: rule_of_thirds
        action: Char runs.
        camera: Tracking Shot fast.
        audio: Footsteps.

        ### Shot 2 — 7.5-15.0s (hard_cut)
        panels: [4, 5, 6]
        characters_present: [char_02]
        shot_size: {size}
        composition: center
        action: Char jumps.
        camera: Push In fast.
        audio: Whoosh.
"""
        sb_md = _make_storyboard_with_shots(shots)
        res = validators.validate_storyboard(sb_md)
        assert res.ok, f"shot_size={size} failed: {res.errors}"


def test_shot_size_invalid_value_rejected():
    shots = """
        ### Shot 1 — 0.0-7.5s (continuous)
        panels: [1, 2, 3]
        characters_present: [char_01]
        shot_size: tiny
        composition: rule_of_thirds
        action: Char runs.
        camera: Tracking Shot fast.
        audio: Footsteps.

        ### Shot 2 — 7.5-15.0s (hard_cut)
        panels: [4, 5, 6]
        characters_present: [char_02]
        shot_size: medium
        composition: center
        action: Char jumps.
        camera: Push In fast.
        audio: Whoosh.
"""
    sb_md = _make_storyboard_with_shots(shots)
    res = validators.validate_storyboard(sb_md)
    assert not res.ok
    assert any("shot_size" in e and "tiny" in e for e in res.errors)


def test_composition_valid_multiple_values_accepted():
    shots = """
        ### Shot 1 — 0.0-7.5s (continuous)
        panels: [1, 2, 3]
        characters_present: [char_01]
        shot_size: wide
        composition: rule_of_thirds, leading_lines, depth
        action: Char runs.
        camera: Tracking Shot fast.
        audio: Footsteps.

        ### Shot 2 — 7.5-15.0s (hard_cut)
        panels: [4, 5, 6]
        characters_present: [char_02]
        shot_size: closeup
        composition: center, visual_hierarchy
        action: Char jumps.
        camera: Push In fast.
        audio: Whoosh.
"""
    sb_md = _make_storyboard_with_shots(shots)
    res = validators.validate_storyboard(sb_md)
    assert res.ok, res.errors


def test_composition_invalid_value_rejected():
    shots = """
        ### Shot 1 — 0.0-7.5s (continuous)
        panels: [1, 2, 3]
        characters_present: [char_01]
        shot_size: wide
        composition: golden_ratio
        action: Char runs.
        camera: Tracking Shot fast.
        audio: Footsteps.

        ### Shot 2 — 7.5-15.0s (hard_cut)
        panels: [4, 5, 6]
        characters_present: [char_02]
        shot_size: closeup
        composition: center
        action: Char jumps.
        camera: Push In fast.
        audio: Whoosh.
"""
    sb_md = _make_storyboard_with_shots(shots)
    res = validators.validate_storyboard(sb_md)
    assert not res.ok
    assert any("composition" in e and "golden_ratio" in e for e in res.errors)


def test_shot_size_missing_warns_not_errors():
    """Existing storyboards without shot_size should pass with warnings."""
    res = validators.validate_storyboard(STORYBOARD_MD)
    assert res.ok  # warnings don't break ok
    assert any("shot_size" in w for w in res.warnings)
    assert any("composition" in w for w in res.warnings)


def test_new_information_rule_errors_on_same_shot_size():
    """same chars + same shot_size + hard_cut → ERROR (framing-only change)."""
    shots = """
        ### Shot 1 — 0.0-7.5s (continuous)
        panels: [1, 2, 3]
        characters_present: [char_01]
        shot_size: medium
        composition: rule_of_thirds
        action: Char runs left.
        camera: Tracking Shot fast.
        audio: Footsteps.

        ### Shot 2 — 7.5-15.0s (hard_cut)
        panels: [4, 5, 6]
        characters_present: [char_01]
        shot_size: medium
        composition: center
        action: Char runs right.
        camera: Pan Left fast.
        audio: Door slam.
"""
    sb_md = _make_storyboard_with_shots(shots)
    res = validators.validate_storyboard(sb_md)
    assert not res.ok
    assert any("framing-only" in e for e in res.errors)


def test_new_information_rule_ok_with_different_shot_size():
    """same chars + different shot_size + hard_cut → OK (size change is new info)."""
    shots = """
        ### Shot 1 — 0.0-7.5s (continuous)
        panels: [1, 2, 3]
        characters_present: [char_01]
        shot_size: wide
        composition: rule_of_thirds
        action: Char runs left.
        camera: Tracking Shot fast.
        audio: Footsteps.

        ### Shot 2 — 7.5-15.0s (hard_cut)
        panels: [4, 5, 6]
        characters_present: [char_01]
        shot_size: closeup
        composition: center
        action: Char's face reacts.
        camera: Push In fast.
        audio: Gasps.
"""
    sb_md = _make_storyboard_with_shots(shots)
    res = validators.validate_storyboard(sb_md)
    assert res.ok, res.errors
    # Should NOT have the same-characters hard_cut warning
    assert not any("shares the same characters" in w for w in res.warnings)


# --- animation direction + sound design (Phase 2) ---------------------------

def test_action_with_micro_beats_accepted():
    """action: with comma-separated micro-beats should pass without warning."""
    shots = """
        ### Shot 1 — 0.0-15.0s (continuous)
        panels: [1, 2, 3, 4, 5, 6]
        characters_present: [char_01]
        shot_size: medium
        composition: rule_of_thirds
        action: The baby freezes, eyes dart to the sound, head turns, body follows, mouth drops open.
        camera: Push In fast.
        audio: Footsteps, soft gasp.
"""
    sb_md = _make_storyboard_with_shots(shots)
    res = validators.validate_storyboard(sb_md)
    assert res.ok, res.errors


def test_audio_with_silence_accepted():
    """audio: Silence. is a valid sound design choice."""
    shots = """
        ### Shot 1 — 0.0-15.0s (continuous)
        panels: [1, 2, 3, 4, 5, 6]
        characters_present: [char_01]
        shot_size: closeup
        composition: center, visual_hierarchy
        action: The baby freezes, eyes widen, holds breath.
        camera: Static Shot.
        audio: Silence.
"""
    sb_md = _make_storyboard_with_shots(shots)
    res = validators.validate_storyboard(sb_md)
    assert res.ok, res.errors


def test_audio_with_foley_ambient_impact_accepted():
    """audio: with foley + ambient + impact layers should pass."""
    shots = """
        ### Shot 1 — 0.0-15.0s (continuous)
        panels: [1, 2, 3, 4, 5, 6]
        characters_present: [char_01]
        shot_size: wide
        composition: depth, leading_lines
        action: The baby runs through the corridor, feet pounding, arms pumping.
        camera: Tracking Shot fast.
        audio: Footsteps on wood, distant thunder, wind through windows, sharp door slam.
"""
    sb_md = _make_storyboard_with_shots(shots)
    res = validators.validate_storyboard(sb_md)
    assert res.ok, res.errors


# --- action drift detection --------------------------------------------------

def test_extract_action_words_filters_stop_words():
    words = validators._extract_action_words("The baby runs frantically down the corridor")
    assert "runs" in words
    assert "frantically" in words
    assert "corridor" in words
    assert "the" not in words
    assert "down" not in words


def test_extract_panel_text_finds_panel_lines():
    prompt = (
        "Panel 1 (top left, medium shot): Mother stands on the verandah angrily.\n"
        "Panel 2 (middle left, wide shot): Kayal runs frantically across courtyard.\n"
    )
    text = validators._extract_panel_text(prompt)
    assert "mother" in text
    assert "angrily" in text
    assert "kayal" in text
    assert "frantically" in text


def test_check_action_drift_no_drift():
    """When panel text contains the action verbs, no warnings."""
    sb = validators.parse_storyboard(STORYBOARD_MD)
    gen = sb["generations"][0]
    # Build a prompt that faithfully uses all shots' action words
    panel_lines = []
    for i, shot in enumerate(gen["shots"], 1):
        panel_lines.append(f"Panel {i} (medium shot): {shot['action']}")
    prompt = "\n".join(panel_lines) + "\n"
    warnings = validators.check_action_drift(sb, gen, prompt)
    assert warnings == []


def test_check_action_drift_detects_softening():
    """When panel text softens the action, warnings are emitted."""
    sb = validators.parse_storyboard(STORYBOARD_MD)
    gen = sb["generations"][0]
    # Build a prompt that replaces action verbs with softer language
    prompt = "Panel 1 (medium shot): A calm quiet scene with gentle lighting.\n"
    warnings = validators.check_action_drift(sb, gen, prompt)
    assert len(warnings) > 0
    assert "action drift" in warnings[0]


def test_check_action_drift_real_kutty_karuppu_g3():
    """The actual g3 drift case: 'runs frantically' softened to 'walking'."""
    # Simulated storyboard action (from storyboard_s1.md g3 shot 4)
    gen = {
        "gen_id": "g3",
        "shots": [
            {"shot": 1, "action": "Mother steps aggressively through the wooden doorway and points finger in anger"},
            {"shot": 4, "action": "Kayal abruptly spins around, leaps off the verandah steps, and runs out past the wooden courtyard gate into the deepening twilight"},
        ],
    }
    # Simulated drifted panel text (from the actual storyboard_sheet_g3.txt)
    drifted_prompt = (
        "Panel 1 (top left, medium shot): Mother stands on the verandah with a concerned expression.\n"
        "Panel 5 (bottom middle, wide shot): Kayal walking across the courtyard toward the gate.\n"
        "Panel 6 (bottom right, wide shot): Kayal walking through the gate into the village road.\n"
    )
    warnings = validators.check_action_drift({}, gen, drifted_prompt)
    # Shot 1 should drift: "aggressively", "points", "finger", "anger" all missing
    assert any("shot 1" in w for w in warnings)
    # Shot 4 should drift: "abruptly", "spins", "leaps", "runs", "frantically" all missing
    assert any("shot 4" in w for w in warnings)


def test_extract_panel_text_new_hierarchical_format():
    """Panel text extraction works for the new `### PANEL N — BEAT` format."""
    prompt = (
        "### PANEL 1 — ESTABLISH\n"
        "(top left). Camera well back in the courtyard. Kayal sits on the thinnai.\n"
        "### PANEL 2 — MOVE CLOSER\n"
        "(middle left). Camera closer. Kayal stirs leaves in her toy pot.\n"
    )
    text = validators._extract_panel_text(prompt)
    assert "courtyard" in text
    assert "thinnai" in text
    assert "stirs" in text
    assert "pot" in text


def test_check_prompt_quality_pixar_warns():
    """Brand references like 'Pixar' produce a warning."""
    prompt = "High quality Pixar-style 3D animation."
    warnings = validators._check_prompt_quality(prompt)
    assert any("pixar" in w.lower() for w in warnings)


def test_check_prompt_quality_disney_warns():
    """Brand references like 'Disney' produce a warning."""
    prompt = "Disney-like magical scene."
    warnings = validators._check_prompt_quality(prompt)
    assert any("disney" in w.lower() for w in warnings)


def test_check_prompt_quality_excessive_negatives_warns():
    """A very long negative list produces a warning."""
    negatives = ". ".join([f"no word{i}" for i in range(30)])
    prompt = f"## HARD EXCLUSIONS\n{negatives}\n"
    warnings = validators._check_prompt_quality(prompt)
    assert any("negative" in w.lower() for w in warnings)


def test_check_prompt_quality_short_negatives_pass():
    """A short negative list produces no warnings."""
    prompt = "## HARD EXCLUSIONS\nno text, no labels, no watermarks."
    warnings = validators._check_prompt_quality(prompt)
    assert warnings == []


# --- cross-episode asset registry + objects + ref_images ---------------------

def test_parse_scenes_with_objects():
    """scenes.md with objects: field should parse object ids."""
    md = textwrap.dedent("""
        # Scenes
        target_seconds: 140
        scene_budget: 70

        ## Scene s1 — Test
        scene_id: s1
        target_seconds: 70
        cast: [char_01, char_02]
        characters_present: [char_01, char_02]
        location_id: loc_kitchen
        objects: [obj_01, obj_02]
        beat: Tom and Jerry fight in the kitchen.

        ## Scene s2 — Test
        scene_id: s2
        target_seconds: 70
        cast: [char_01, char_02]
        characters_present: [char_01, char_02]
        location_id: loc_kitchen
        objects: [obj_01]
        beat: They reconcile over food.
    """).strip()
    scenes = validators.parse_scenes(md)
    assert scenes["scenes"][0]["objects"] == ["obj_01", "obj_02"]
    assert scenes["scenes"][1]["objects"] == ["obj_01"]


def test_parse_scenes_objects_defaults_empty():
    """scenes.md without objects: field should default to empty list."""
    md = textwrap.dedent("""
        # Scenes
        target_seconds: 70
        scene_budget: 70

        ## Scene s1 — Test
        scene_id: s1
        target_seconds: 70
        cast: [char_01]
        characters_present: [char_01]
        location_id: loc_test
        beat: Test.
    """).strip()
    scenes = validators.parse_scenes(md)
    assert scenes["scenes"][0]["objects"] == []


def test_asset_registry_stores_objects(tmp_path):
    """AssetRegistry should store and retrieve objects in the objects section."""
    from tools import image_pipeline as ip
    run_dir = str(tmp_path / "epi-1")
    assets_dir = str(tmp_path / "assets")
    os.makedirs(run_dir)
    os.makedirs(assets_dir)
    reg = ip.AssetRegistry(run_dir, assets_dir)
    entry = reg.object("obj_01")
    entry["output_path"] = "/fake/path/obj_01.webp"
    entry["fal_image_url"] = "https://example.com/obj_01.webp"
    reg.save()
    # Reload
    reg2 = ip.AssetRegistry(run_dir, assets_dir)
    assert "obj_01" in reg2.data["objects"]
    assert reg2.data["objects"]["obj_01"]["fal_image_url"] == "https://example.com/obj_01.webp"


def test_asset_registry_object_path():
    """object_path should return assets/objects/<oid>.<ext>."""
    from tools import image_pipeline as ip
    reg = ip.AssetRegistry.__new__(ip.AssetRegistry)
    reg.assets_dir = "/fake/assets"
    path = reg.object_path("obj_01")
    assert "objects" in path
    assert "obj_01" in path


def test_asset_registry_migrates_from_per_episode(tmp_path):
    """If per-episode registry exists and story-level doesn't, migrate it."""
    from tools import image_pipeline as ip
    run_dir = str(tmp_path / "epi-1")
    assets_dir = str(tmp_path / "assets")
    os.makedirs(run_dir)
    os.makedirs(assets_dir)
    # Write a per-episode registry (old format, no objects section)
    old_path = os.path.join(run_dir, "asset_registry.json")
    with open(old_path, "w") as f:
        json.dump({
            "characters": {"char_01": {"output_path": "/x", "fal_image_url": "y"}},
            "locations": {"loc_01": {"output_path": "/x", "fal_image_url": "y"}},
            "sheets": {"s1_g1": {"output_path": "/x", "fal_image_url": "y"}},
        }, f)
    # Create registry — should migrate
    reg = ip.AssetRegistry(run_dir, assets_dir)
    assert os.path.isfile(os.path.join(assets_dir, "asset_registry.json"))
    assert "char_01" in reg.data["characters"]
    assert "loc_01" in reg.data["locations"]
    assert "objects" in reg.data  # added during migration
    assert reg.data["objects"] == {}


def test_parse_ref_images_extracts_names():
    """parse_ref_images should extract ref names and strip the line."""
    from tools import image_pipeline as ip
    prompt = "ref_images: loc_kitchen, char_01, obj_stick\n\nA beautiful hall."
    names, cleaned = ip.parse_ref_images(prompt)
    assert names == ["loc_kitchen", "char_01", "obj_stick"]
    assert "ref_images:" not in cleaned
    assert "A beautiful hall." in cleaned


def test_parse_ref_images_no_line():
    """parse_ref_images with no ref_images line returns empty list + original."""
    from tools import image_pipeline as ip
    prompt = "A beautiful hall with warm lighting."
    names, cleaned = ip.parse_ref_images(prompt)
    assert names == []
    assert cleaned == prompt


def test_resolve_ref_names_finds_object(tmp_path):
    """resolve_ref_names should resolve object names to URLs."""
    from tools import image_pipeline as ip
    run_dir = str(tmp_path / "epi-1")
    assets_dir = str(tmp_path / "assets")
    os.makedirs(run_dir)
    os.makedirs(assets_dir)
    reg = ip.AssetRegistry(run_dir, assets_dir)
    entry = reg.object("obj_01")
    entry["fal_image_url"] = "https://example.com/obj_01.webp"
    entry["output_path"] = "/fake/path"
    reg.save()
    reg2 = ip.AssetRegistry(run_dir, assets_dir)
    urls = ip.resolve_ref_names(reg2, ["obj_01"])
    assert urls == ["https://example.com/obj_01.webp"]


def test_resolve_ref_names_resolution_order(tmp_path):
    """resolve_ref_names should resolve objects → locations → characters → sheets."""
    from tools import image_pipeline as ip
    run_dir = str(tmp_path / "epi-1")
    assets_dir = str(tmp_path / "assets")
    os.makedirs(run_dir)
    os.makedirs(assets_dir)
    reg = ip.AssetRegistry(run_dir, assets_dir)
    # Put the same name in objects and locations — objects should win
    reg.object("shared_id")["fal_image_url"] = "https://obj.example.com/x.webp"
    reg.object("shared_id")["output_path"] = "/fake/obj"
    reg.location("shared_id")["fal_image_url"] = "https://loc.example.com/x.webp"
    reg.location("shared_id")["output_path"] = "/fake/loc"
    reg.save()
    reg2 = ip.AssetRegistry(run_dir, assets_dir)
    urls = ip.resolve_ref_names(reg2, ["shared_id"])
    assert urls == ["https://obj.example.com/x.webp"]


def test_object_sheet_builder_builds_prompt():
    """object_sheet_builder should fill the template from object fields."""
    from tools import object_sheet_builder
    prompt = object_sheet_builder.build_object_sheet_prompt(
        {"id": "obj_01", "name": "Magic Egg", "description": "A glowing egg.",
         "appearance": "Speckled cream shell with golden glow."},
        render_style="Pixar-style 3D.",
    )
    assert "Magic Egg" in prompt
    assert "glowing egg" in prompt
    assert "Speckled cream shell" in prompt
    assert "Pixar-style 3D." in prompt


def test_object_prompt_path():
    """object_prompt_path should return image_prompts/objects/<oid>.txt."""
    from tools import image_pipeline as ip
    path = ip.object_prompt_path("/run", "obj_01")
    assert path.endswith("objects/obj_01.txt")


# --- beat board parsing + validation -----------------------------------------

GOOD_BEAT_BOARD = textwrap.dedent("""
    # Beat Board — Test Story

    target_seconds: 90
    beat_count: 5

    ## Beat 1 — Joy
    description: Kemi and baby Timi forage peacefully along a sunlit jungle stream.
    emotion: joy
    estimated_seconds: 15

    ## Beat 2 — Omen
    description: Birdsong fades to dead silence; menacing yellow eyes open in the undergrowth.
    emotion: unease
    estimated_seconds: 8

    ## Beat 3 — Threat
    description: A fierce hyena emerges snarling from the shadows.
    emotion: fear
    estimated_seconds: 7

    ## Beat 4 — Chase
    description: Kemi clutches her plantains and sprints through thick foliage with the predator in pursuit.
    emotion: tension
    estimated_seconds: 20

    ## Beat 5 — Triumph
    description: Kemi hoists the Fufu tin proudly toward camera on the sunlit ridge.
    emotion: triumph
    estimated_seconds: 10
""").strip()


def test_parse_beat_board_valid():
    """parse_beat_board should extract beats with all fields."""
    data = validators.parse_beat_board(GOOD_BEAT_BOARD)
    assert data["target_seconds"] == 90
    assert data["beat_count"] == 5
    assert len(data["beats"]) == 5
    assert data["beats"][0]["beat_num"] == 1
    assert data["beats"][0]["emotion"] == "joy"
    assert data["beats"][0]["estimated_seconds"] == 15
    assert "Kemi" in data["beats"][0]["description"]
    assert data["beats"][4]["beat_num"] == 5
    assert data["beats"][4]["emotion"] == "triumph"


def test_validate_beat_board_valid():
    """A well-formed beat board should pass."""
    res = validators.validate_beat_board(GOOD_BEAT_BOARD, target_seconds=90)
    assert res.ok, res.errors


def test_validate_beat_board_missing_field():
    """A beat missing description should error."""
    md = textwrap.dedent("""
        # Beat Board — Test
        target_seconds: 30
        beat_count: 2

        ## Beat 1 — Joy
        emotion: joy
        estimated_seconds: 15

        ## Beat 2 — Fear
        description: Something scary happens.
        emotion: fear
        estimated_seconds: 10
    """).strip()
    res = validators.validate_beat_board(md, target_seconds=30)
    assert not res.ok
    assert any("description" in e for e in res.errors)


def test_validate_beat_board_count_mismatch():
    """beat_count not matching actual blocks should error."""
    md = textwrap.dedent("""
        # Beat Board — Test
        target_seconds: 30
        beat_count: 5

        ## Beat 1 — Joy
        description: Happy.
        emotion: joy
        estimated_seconds: 15

        ## Beat 2 — Fear
        description: Scary.
        emotion: fear
        estimated_seconds: 10
    """).strip()
    res = validators.validate_beat_board(md, target_seconds=30)
    assert not res.ok
    assert any("beat_count" in e for e in res.errors)


def test_validate_beat_board_non_sequential():
    """Non-sequential beat numbers should error."""
    md = textwrap.dedent("""
        # Beat Board — Test
        target_seconds: 30
        beat_count: 3

        ## Beat 1 — Joy
        description: Happy.
        emotion: joy
        estimated_seconds: 10

        ## Beat 3 — Fear
        description: Scary.
        emotion: fear
        estimated_seconds: 10

        ## Beat 4 — Triumph
        description: Win.
        emotion: triumph
        estimated_seconds: 10
    """).strip()
    res = validators.validate_beat_board(md, target_seconds=30)
    assert not res.ok
    assert any("sequential" in e for e in res.errors)


def test_validate_beat_board_sum_warning():
    """Sum of estimated_seconds far from target should warn (not error)."""
    md = textwrap.dedent("""
        # Beat Board — Test
        target_seconds: 300
        beat_count: 3

        ## Beat 1 — Joy
        description: Happy.
        emotion: joy
        estimated_seconds: 10

        ## Beat 2 — Fear
        description: Scary.
        emotion: fear
        estimated_seconds: 10

        ## Beat 3 — Triumph
        description: Win.
        emotion: triumph
        estimated_seconds: 10
    """).strip()
    res = validators.validate_beat_board(md, target_seconds=300)
    # 30s total vs 300s target = 10% → outside 50% → warn
    assert res.ok  # warnings don't break ok
    assert any("estimated_seconds" in w for w in res.warnings)


def test_parse_scenes_with_beats():
    """scenes.md with beats: field should parse beat numbers."""
    md = textwrap.dedent("""
        # Scenes
        target_seconds: 70
        scene_budget: 70

        ## Scene s1 — Test
        scene_id: s1
        target_seconds: 35
        cast: [char_01]
        characters_present: [char_01]
        location_id: loc_test
        objects: []
        beats: [1, 2]
        beat: First two beats.

        ## Scene s2 — Test
        scene_id: s2
        target_seconds: 35
        cast: [char_01]
        characters_present: [char_01]
        location_id: loc_test
        objects: []
        beats: [3]
        beat: Third beat.
    """).strip()
    scenes = validators.parse_scenes(md)
    assert scenes["scenes"][0]["beats"] == [1, 2]
    assert scenes["scenes"][1]["beats"] == [3]


def test_validate_scenes_beat_coverage(tmp_path):
    """Scenes should cover all beats when beat_board.md exists."""
    bb_path = str(tmp_path / "beat_board.md")
    with open(bb_path, "w") as f:
        f.write(GOOD_BEAT_BOARD)
    md = textwrap.dedent("""
        # Scenes
        target_seconds: 90
        scene_budget: 70

        ## Scene s1 — Test
        scene_id: s1
        target_seconds: 45
        cast: [char_01]
        characters_present: [char_01]
        location_id: loc_test
        objects: []
        beats: [1, 2, 3]
        beat: First three beats.

        ## Scene s2 — Test
        scene_id: s2
        target_seconds: 45
        cast: [char_01]
        characters_present: [char_01]
        location_id: loc_test
        objects: []
        beats: [4, 5]
        beat: Last two beats.
    """).strip()
    res = validators.validate_scenes(md, target_seconds=90, beat_board_path=bb_path)
    assert res.ok, res.errors


def test_validate_scenes_beat_duplication_error(tmp_path):
    """A beat claimed by two scenes should error."""
    bb_path = str(tmp_path / "beat_board.md")
    with open(bb_path, "w") as f:
        f.write(GOOD_BEAT_BOARD)
    md = textwrap.dedent("""
        # Scenes
        target_seconds: 90
        scene_budget: 70

        ## Scene s1 — Test
        scene_id: s1
        target_seconds: 45
        cast: [char_01]
        characters_present: [char_01]
        location_id: loc_test
        objects: []
        beats: [1, 2, 3]
        beat: First three beats.

        ## Scene s2 — Test
        scene_id: s2
        target_seconds: 45
        cast: [char_01]
        characters_present: [char_01]
        location_id: loc_test
        objects: []
        beats: [3, 4, 5]
        beat: Beats 3-5.
    """).strip()
    res = validators.validate_scenes(md, target_seconds=90, beat_board_path=bb_path)
    assert not res.ok
    assert any("already claimed" in e for e in res.errors)


def test_validate_scenes_no_beat_board_backward_compat():
    """Scenes.md without a beat_board.md should still validate (no beat checks)."""
    md = textwrap.dedent("""
        # Scenes
        target_seconds: 70
        scene_budget: 70

        ## Scene s1 — Test
        scene_id: s1
        target_seconds: 70
        cast: [char_01]
        characters_present: [char_01]
        location_id: loc_test
        objects: []
        beat: One beat.
    """).strip()
    res = validators.validate_scenes(md, target_seconds=70, beat_board_path=None)
    assert res.ok, res.errors


def test_validate_scenes_beats_backward_compat():
    """Scenes.md without beats: field should still validate even with beat_board."""
    md = textwrap.dedent("""
        # Scenes
        target_seconds: 90
        scene_budget: 70

        ## Scene s1 — Test
        scene_id: s1
        target_seconds: 90
        cast: [char_01]
        characters_present: [char_01]
        location_id: loc_test
        objects: []
        beat: Old-style scene without beats field.
    """).strip()
    # No beat_board_path → no cross-check → passes
    res = validators.validate_scenes(md, target_seconds=90)
    assert res.ok, res.errors


# --- critique report parsing + validation ------------------------------------

SAMPLE_QUESTION_BANK = textwrap.dedent("""
    # Directing Questions Bank

    ## Section 1: Story & Visual Storytelling

    ### Q1.1 — Does every scene have a visible goal?
    - **Check:** scenes.md
    - **Pass:** every scene states a visible goal.
    - **Fail:** any scene with no visible goal.

    ### Q1.2 — Does every scene have a conflict?
    - **Check:** scenes.md
    - **Pass:** every scene has an obstacle.
    - **Fail:** any scene with no conflict.

    ## Section 2: Shot Design

    ### Q2.1 — Does every shot's shot_size serve the beat's emotion?
    - **Check:** storyboard_sN.md
    - **Pass:** shot_size matches emotion.
    - **Fail:** shot_size contradicts emotion.
""").strip()


GOOD_CRITIQUE_REPORT = textwrap.dedent("""
    # Critique Report — Test Story

    ## Summary
    - Questions evaluated: 3
    - Pass: 3
    - Fail: 0
    - Advisory: 0

    ## Section 1: Story & Visual Storytelling

    ### Q1.1 — Does every scene have a visible goal?
    - Status: PASS
    - Notes: All scenes have clear visible goals.

    ### Q1.2 — Does every scene have a conflict?
    - Status: PASS
    - Notes: Every scene has a conflict.

    ## Section 2: Shot Design

    ### Q2.1 — Does every shot's shot_size serve the beat's emotion?
    - Status: PASS
    - Notes: Shot sizes match the emotional intent of each beat.
""").strip()


FAIL_CRITIQUE_REPORT = textwrap.dedent("""
    # Critique Report — Test Story

    ## Summary
    - Questions evaluated: 3
    - Pass: 1
    - Fail: 2
    - Advisory: 0

    ## Section 1: Story & Visual Storytelling

    ### Q1.1 — Does every scene have a visible goal?
    - Status: PASS
    - Notes: All scenes have clear visible goals.

    ### Q1.2 — Does every scene have a conflict?
    - Status: FAIL
    - Notes: Scene s1 has no conflict.
    - Artifact: scenes.md, scene s1
    - Fix: Introduce the hyena threat earlier.

    ## Section 2: Shot Design

    ### Q2.1 — Does every shot's shot_size serve the beat's emotion?
    - Status: FAIL
    - Notes: Shot 3 uses closeup for geography.
    - Artifact: storyboard_s1.md, s1/g1 shot 3
    - Fix: Change shot_size to wide.
""").strip()


def test_parse_critique_report_valid():
    """parse_critique_report should extract questions with status."""
    from tools.critique_validator import parse_critique_report
    data = parse_critique_report(GOOD_CRITIQUE_REPORT)
    assert data["summary"]["Pass"] == 3
    assert data["summary"]["Fail"] == 0
    assert len(data["questions"]) == 3
    assert data["questions"][0]["id"] == "Q1.1"
    assert data["questions"][0]["status"] == "PASS"
    assert data["questions"][1]["id"] == "Q1.2"
    assert data["questions"][1]["status"] == "PASS"
    assert data["questions"][2]["id"] == "Q2.1"


def test_validate_critique_report_all_pass():
    """A report with all PASS should pass validation."""
    from tools.critique_validator import validate_critique_report
    res = validate_critique_report(GOOD_CRITIQUE_REPORT, question_bank_md=SAMPLE_QUESTION_BANK)
    assert res.ok, res.errors


def test_validate_critique_report_has_fails():
    """A report with FAILs should not pass validation."""
    from tools.critique_validator import validate_critique_report
    res = validate_critique_report(FAIL_CRITIQUE_REPORT, question_bank_md=SAMPLE_QUESTION_BANK)
    assert not res.ok
    assert any("FAIL" in e for e in res.errors)


def test_validate_critique_report_missing_question():
    """A report missing a question from the bank should error."""
    from tools.critique_validator import validate_critique_report
    # Report with only Q1.1 and Q1.2 (missing Q2.1)
    incomplete = textwrap.dedent("""
        # Critique Report — Test

        ## Summary
        - Questions evaluated: 2
        - Pass: 2
        - Fail: 0
        - Advisory: 0

        ## Section 1: Story & Visual Storytelling

        ### Q1.1 — Does every scene have a visible goal?
        - Status: PASS
        - Notes: Yes.

        ### Q1.2 — Does every scene have a conflict?
        - Status: PASS
        - Notes: Yes.
    """).strip()
    res = validate_critique_report(incomplete, question_bank_md=SAMPLE_QUESTION_BANK)
    assert not res.ok
    assert any("missing" in e.lower() for e in res.errors)


def test_validate_critique_report_count_mismatch():
    """Summary counts not matching actual statuses should error."""
    from tools.critique_validator import validate_critique_report
    mismatched = textwrap.dedent("""
        # Critique Report — Test

        ## Summary
        - Questions evaluated: 3
        - Pass: 3
        - Fail: 0
        - Advisory: 0

        ## Section 1: Story & Visual Storytelling

        ### Q1.1 — Does every scene have a visible goal?
        - Status: PASS
        - Notes: Yes.

        ### Q1.2 — Does every scene have a conflict?
        - Status: FAIL
        - Notes: No.
        - Artifact: scenes.md
        - Fix: Add conflict.

        ## Section 2: Shot Design

        ### Q2.1 — Does every shot's shot_size serve the beat's emotion?
        - Status: PASS
        - Notes: Yes.
    """).strip()
    res = validate_critique_report(mismatched, question_bank_md=SAMPLE_QUESTION_BANK)
    # Summary says Fail: 0 but there's 1 FAIL → mismatch
    assert not res.ok
    assert any("Fail" in e and "!=" in e for e in res.errors)
