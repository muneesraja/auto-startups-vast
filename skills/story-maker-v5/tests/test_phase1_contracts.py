"""Phase 1 contract tests: boundary policy, audio refs, per-generation sheets,
episode-scoped registry keys, manifest approval, oner support, scene ordering."""

import json
import os
import textwrap

from tools import boundary, duration_budget as db, image_pipeline as ip, validators
from tools.audio_refs import find_audio_ref, find_audio_refs


# --- fixtures ---------------------------------------------------------------

SCENES_MD = textwrap.dedent("""
    # Scenes
    target_seconds: 30
    scene_budget: 70

    ## Scene s1 — First
    scene_id: s1
    target_seconds: 15
    cast: [char_01]
    characters_present: [char_01]
    location_id: loc_a
    style_target: polished 3D cartoon
    acting_beat: arrive → settle
    layout_strategy: centered staging
    visual_motif: warm light
    sound_world: room tone
    beat: Arrival.

    ## Scene s2 — Second
    scene_id: s2
    target_seconds: 15
    cast: [char_01]
    characters_present: [char_01]
    location_id: loc_a
    style_target: polished 3D cartoon
    acting_beat: rise → act
    layout_strategy: diagonal
    visual_motif: gold
    sound_world: creaks
    beat: Action.

    ## Scene s10 — Tenth
    scene_id: s10
    target_seconds: 15
    cast: [char_01]
    characters_present: [char_01]
    location_id: loc_a
    style_target: polished 3D cartoon
    acting_beat: turn → exit
    layout_strategy: depth
    visual_motif: dusk
    sound_world: wind
    beat: Departure.
""").strip()


def _storyboard_md(scene_id: str, *, shot1_transition: str = "continuous",
                   gen2_transition: str = "hard_cut",
                   handoff: str = "hard_cut", two_gens: bool = False) -> str:
    """Minimal valid storyboard. Shot-1 transition and handoff are parameterised."""
    g1_end, g1_dur = ("7.5", "7.5") if two_gens else ("15.0", "15.0")
    gen2 = ""
    if two_gens:
        gen2 = textwrap.dedent(f"""
            ## Generation g2 — 7.5-15.0s
            duration_seconds: 7.5
            panel_grid: 3x2

            ### Shot 1 — 7.5-15.0s ({gen2_transition})
            panels: [1, 2, 3]
            characters_present: [char_01]
            acting_beat: snap → freeze → settle
            layout: centered single figure against flat backdrop
            screen_direction: held
            camera_angle: eye_level
            action: A wholly new setup: the figure stands motionless in frame center.
            camera: Static Shot.
            audio: Dead room tone.
            dialogue:
        """)
    return textwrap.dedent(f"""
        # Scene {scene_id} — Test
        scene_id: {scene_id}
        target_seconds: 15
        cast: [char_01]
        location_ref_id: loc_a

        ## Generation g1 — 0.0-{g1_end}s
        duration_seconds: {g1_dur}
        panel_grid: 3x2

        ### Shot 1 — 0.0-{g1_end}s ({shot1_transition})
        panels: [1, 2, 3, 4, 5, 6]
        characters_present: [char_01]
        acting_beat: anticipation → motion → settle
        layout: foreground figure against receding corridor
        screen_direction: left_to_right
        camera_angle: eye_level
        action: The figure crosses the corridor and pauses at the door.
        camera: Tracking Shot at slow speed.
        audio: Footsteps, room tone.
        dialogue:
    """).strip() + "\n\n" + gen2 + textwrap.dedent(f"""
        ## Scene-end handoff -> scene s_next
        on_screen: [char_01]
        mood: calm
        transition: {handoff}
    """).strip()


REF2VA_G1 = textwrap.dedent("""
    subject_definitions:
    <Subject 1> is the toddler in the white onesie in <Picture 1>, with chubby cheeks and big eyes.
    <Picture 1> is the storyboard reference for [Shot 1], defining viewpoint, subject placement, and shot order.
    (S1) is <Subject 1>'s voice.

    summary:
    [reference generation] The target video shows the figure crossing the corridor.

    retention_analysis:
    <Subject 1> (appears in [Shot 1]): fully_preserved - the onesie, cheeks, and eyes are retained.
    <Picture 1> (storyboard reference): fully_preserved - composition, framing, and panel sequence.

    detailed_description:
    Polished stylized 3D cartoon animation with warm natural lighting.
    [Shot 1] The figure in the white onesie walks across the corridor, footfalls echoing. <Subject 1> (S1) pauses at the door and whispers, <d>[English] Hello.</d> The camera tracks slowly at waist height, then pushes in with small amplitude. Never generate duplicate characters.

    overall_soundscape:
    Footsteps, soft room tone, a door creak.

    non_diegetic_music:
    Low cello drone at a slow tempo.
""").strip()


# --- boundary policy ---------------------------------------------------------

def test_gen_boundary_first_fresh_continuation():
    sb = validators.parse_storyboard(_storyboard_md("s1", two_gens=True))
    assert boundary.gen_boundary(sb, "g1") == boundary.FIRST
    # g2's shot 1 is hard_cut -> fresh cut
    assert boundary.gen_boundary(sb, "g2") == boundary.FRESH_CUT


def test_gen_boundary_continuation_when_not_hard_cut():
    md = _storyboard_md("s1", two_gens=True, gen2_transition="continuous")
    sb = validators.parse_storyboard(md)
    assert boundary.gen_boundary(sb, "g2") == boundary.CONTINUATION


def test_scene_boundary_from_handoff():
    prev = validators.parse_storyboard(_storyboard_md("s1", handoff="hard_cut"))
    nxt = validators.parse_storyboard(_storyboard_md("s2", shot1_transition="hard_cut"))
    assert boundary.scene_boundary(prev, nxt) == boundary.FRESH_CUT

    prev_cont = validators.parse_storyboard(_storyboard_md("s1", handoff="match_cut"))
    nxt_cont = validators.parse_storyboard(_storyboard_md("s2", shot1_transition="continuous"))
    assert boundary.scene_boundary(prev_cont, nxt_cont) == boundary.CONTINUATION

    # hard_cut on the next scene's g1 shot 1 is itself a fresh-cut signal
    assert boundary.scene_boundary(prev_cont, nxt) == boundary.FRESH_CUT
    # No data -> continuation (legacy renderer behaviour)
    assert boundary.scene_boundary(None, None) == boundary.CONTINUATION


def test_needs_tail_ref_episode_global():
    s1 = validators.parse_storyboard(_storyboard_md("s1", handoff="hard_cut", two_gens=True))
    s2 = validators.parse_storyboard(_storyboard_md("s2", shot1_transition="continuous"))
    ids = ["s1", "s2"]
    # Episode's very first generation: never a tail.
    assert boundary.needs_tail_ref(ids, "s1", s1, "g1") is False
    # s1/g2 opens on hard_cut: fresh.
    assert boundary.needs_tail_ref(ids, "s1", s1, "g2") is False
    # s2/g1: prev handoff was hard_cut -> fresh.
    assert boundary.needs_tail_ref(ids, "s2", s2, "g1", prev_storyboard=s1) is False
    # s2/g1 with a continuation handoff: tail attached.
    s1_cont = validators.parse_storyboard(_storyboard_md("s1", handoff="continuous", two_gens=True))
    assert boundary.needs_tail_ref(ids, "s2", s2, "g1", prev_storyboard=s1_cont) is True


def test_boundary_consistency_contradictions():
    prev_cut = validators.parse_storyboard(_storyboard_md("s1", handoff="hard_cut"))
    nxt_cont = validators.parse_storyboard(_storyboard_md("s2", shot1_transition="continuous"))
    errs, _ = boundary.boundary_consistency_errors(prev_cut, nxt_cont)
    assert any("hard_cut" in e and "continuous" in e for e in errs)

    prev_cont = validators.parse_storyboard(_storyboard_md("s1", handoff="match_cut"))
    nxt_cut = validators.parse_storyboard(_storyboard_md("s2", shot1_transition="hard_cut"))
    errs, _ = boundary.boundary_consistency_errors(prev_cont, nxt_cut)
    assert errs

    nxt_cut_ok = validators.parse_storyboard(_storyboard_md("s2", shot1_transition="hard_cut"))
    errs, _ = boundary.boundary_consistency_errors(prev_cut, nxt_cut_ok)
    assert not errs


# --- audio refs discovery -----------------------------------------------------

def _touch(path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"audio-bytes")
    return path


def test_find_audio_refs_scoping_and_roles(tmp_path):
    run = str(tmp_path)
    _touch(os.path.join(run, "audio", "s1_g2__voice_S1.mp3"))
    _touch(os.path.join(run, "audio", "s1__ambience.wav"))
    _touch(os.path.join(run, "audio", "s2_g1.mp3"))

    g2 = find_audio_refs(run, "s1", "g2")
    roles = {r["role"] for r in g2}
    assert "voice_S1" in roles and "ambience" in roles

    g1 = find_audio_refs(run, "s1", "g1")
    assert [r["role"] for r in g1] == ["ambience"]

    s2 = find_audio_refs(run, "s2", "g1")
    assert [r["role"] for r in s2] == ["reference"]

    assert find_audio_refs(run, "s9", "g1") == []
    assert find_audio_refs(os.path.join(run, "nonexistent"), "s1", "g1") == []


def test_find_audio_refs_specific_scope_shadows_role(tmp_path):
    run = str(tmp_path)
    gen_file = _touch(os.path.join(run, "audio", "s1_g1__ambience.mp3"))
    _touch(os.path.join(run, "audio", "s1__ambience.wav"))
    refs = find_audio_refs(run, "s1", "g1")
    assert len([r for r in refs if r["role"] == "ambience"]) == 1
    assert refs[0]["path"] == gen_file
    assert find_audio_ref(run, "s1", "g1") == gen_file


def test_find_audio_refs_ignores_empty_and_bad_ext(tmp_path):
    run = str(tmp_path)
    empty = os.path.join(run, "audio", "s1_g1.mp3")
    os.makedirs(os.path.dirname(empty), exist_ok=True)
    open(empty, "wb").close()
    _touch(os.path.join(run, "s1_g1.txt"))  # wrong extension
    assert find_audio_refs(run, "s1", "g1") == []


# --- <Audio N> + speaker binding + <Video 1> contracts ------------------------

def _sb1():
    return validators.parse_storyboard(_storyboard_md("s1"))


def test_audio_attached_requires_audio_label():
    refs = [{"path": "/a/s1_g1__voice_S1.mp3", "role": "voice_S1", "scope": "gen"}]
    res = validators.validate_video_prompt(REF2VA_G1, _sb1(), "g1", audio_refs=refs)
    assert not res.ok
    assert any("<Audio" in e for e in res.errors)


def test_audio_label_without_file_warns():
    prompt = REF2VA_G1.replace(
        "(S1) is <Subject 1>'s voice.",
        "(S1) is <Subject 1>'s voice.\n<Audio 1> is the voice reference for (S1)'s delivery.",
    ).replace(
        "<Picture 1> (storyboard reference): fully_preserved - composition, framing, and panel sequence.",
        "<Picture 1> (storyboard reference): fully_preserved - composition, framing, and panel sequence.\n"
        "<Audio 1> (voice reference): partially_preserved - timbre and delivery guide for (S1).",
    )
    res = validators.validate_video_prompt(prompt, _sb1(), "g1", audio_refs=[])
    assert any("<Audio" in w for w in res.warnings)


def test_audio_attached_and_declared_passes():
    prompt = REF2VA_G1.replace(
        "(S1) is <Subject 1>'s voice.",
        "(S1) is <Subject 1>'s voice.\n<Audio 1> is the voice reference for (S1)'s delivery.",
    ).replace(
        "<Picture 1> (storyboard reference): fully_preserved - composition, framing, and panel sequence.",
        "<Picture 1> (storyboard reference): fully_preserved - composition, framing, and panel sequence.\n"
        "<Audio 1> (voice reference): partially_preserved - timbre and delivery guide for (S1).",
    )
    refs = [{"path": "/a/s1_g1__voice_S1.mp3", "role": "voice_S1", "scope": "gen"}]
    res = validators.validate_video_prompt(prompt, _sb1(), "g1", audio_refs=refs)
    assert not any("<Audio" in e for e in res.errors)


def test_speaker_id_must_bind_to_subject():
    bad = REF2VA_G1.replace("(S1) is <Subject 1>'s voice.\n", "")
    res = validators.validate_video_prompt(bad, _sb1(), "g1")
    assert not res.ok
    assert any("(S1)" in e and "subject_definitions" in e for e in res.errors)


def test_video1_declaration_matches_boundary():
    # Fresh-cut generation must not declare <Video 1>.
    prompt_with_v1 = REF2VA_G1.replace(
        "<Picture 1> is the storyboard reference",
        "<Video 1> is the previous generation's rendered tail.\n<Picture 1> is the storyboard reference",
    ).replace(
        "<Picture 1> (storyboard reference): fully_preserved - composition, framing, and panel sequence.",
        "<Picture 1> (storyboard reference): fully_preserved - composition, framing, and panel sequence.\n"
        "<Video 1> (continuation starting point): fully_preserved - ending pose and motion state.",
    )
    res = validators.validate_video_prompt(prompt_with_v1, _sb1(), "g1", has_tail_ref=False)
    assert not res.ok
    assert any("fresh cut" in e for e in res.errors)

    # Continuation generation missing <Video 1> errors.
    res2 = validators.validate_video_prompt(REF2VA_G1, _sb1(), "g1", has_tail_ref=True)
    assert not res2.ok
    assert any("<Video 1>" in e for e in res2.errors)


# --- oner support -------------------------------------------------------------

def test_shots_per_gen_min_allows_oner():
    assert db.SHOTS_PER_GEN_MIN == 1
    assert db.SHOTS_PER_GEN_MAX == 8


def test_oner_storyboard_passes():
    res = validators.validate_storyboard(_storyboard_md("s1"))
    assert res.ok, res.errors


def test_oner_shallow_description_warns():
    # REF2VA_G1's detailed_description is well under the high-detail threshold.
    res = validators.validate_video_prompt(REF2VA_G1, _sb1(), "g1")
    assert any("slow-paced" in w or "master-take" in w for w in res.warnings)


# --- per-generation sheet prompts ---------------------------------------------

def test_sheet_prompt_path_is_per_generation(tmp_path):
    p = ip.sheet_prompt_path(str(tmp_path), "s1", "g2")
    assert p.endswith(os.path.join("image_prompts", "s1", "storyboard_sheet_g2.txt"))


def test_scene_level_sheet_prompt_rejected(tmp_path):
    run = str(tmp_path)
    scene_dir = os.path.join(run, "image_prompts", "s1")
    os.makedirs(scene_dir)
    # Satisfy the other prompt requirements first.
    _touch_prompt(run, "characters", "char_01")
    _touch_prompt(run, "locations", "loc_a")
    _touch_prompt(run, "s1", "storyboard_sheet_g1")
    # The retired scene-level file must be rejected even though per-gen exists.
    _touch_prompt(run, "s1", "storyboard_sheet")
    res = validators.validate_prompts(run, "s1", sb=_sb1())
    assert not res.ok
    assert any("scene-level" in e for e in res.errors)


def _touch_prompt(run: str, sub: str, stem: str) -> str:
    p = os.path.join(run, "image_prompts", sub, f"{stem}.txt")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write("prompt text")
    return p


# --- episode-scoped sheet registry keys ----------------------------------------

def test_sheet_keys_are_episode_scoped(tmp_path):
    run = str(tmp_path / "epi-2")
    assets = str(tmp_path / "assets")
    os.makedirs(run)
    reg = ip.AssetRegistry(run, assets)
    entry = reg.sheet("s1_g1")
    assert "epi-2.s1_g1" in reg.data["sheets"]
    assert "s1_g1" not in reg.data["sheets"]
    assert entry is reg.data["sheets"]["epi-2.s1_g1"]


def test_unscoped_sheet_keys_migrate(tmp_path):
    run = str(tmp_path / "epi-2")
    assets = str(tmp_path / "assets")
    os.makedirs(run)
    os.makedirs(assets)
    sheet_file = os.path.join(run, "storyboard_sheet_s1_g1.webp")
    with open(sheet_file, "wb") as f:
        f.write(b"img")
    registry = {
        "sheets": {
            # inside this run -> becomes epi-2.s1_g1
            "s1_g1": {"output_path": sheet_file, "fal_image_url": "https://x/1"},
            # outside this run (another episode's) -> parked in sheets_legacy
            "s1_g2": {"output_path": "/elsewhere/epi-1/s1_g2.webp", "fal_image_url": "https://x/2"},
        }
    }
    with open(os.path.join(assets, "asset_registry.json"), "w") as f:
        json.dump(registry, f)
    reg = ip.AssetRegistry(run, assets)
    assert "epi-2.s1_g1" in reg.data["sheets"]
    assert "s1_g2" in reg.data["sheets_legacy"]
    assert "s1_g2" not in reg.data["sheets"]


def test_resolve_ref_name_scoped_and_unscoped(tmp_path):
    run = str(tmp_path / "epi-2")
    assets = str(tmp_path / "assets")
    os.makedirs(run)
    reg = ip.AssetRegistry(run, assets)
    entry = reg.sheet("s1_g1")
    # output_path must be truthy for resolution but point at a file that does
    # not exist locally — ensure_asset_url then returns the persisted URL
    # without touching the network.
    entry["output_path"] = os.path.join(run, "storyboard_sheet_s1_g1.webp")
    entry["fal_image_url"] = "https://cdn.example/sheet.webp"
    # Unscoped name resolves within this run.
    assert reg.resolve_ref_name("s1_g1") == "https://cdn.example/sheet.webp"
    # Explicit cross-episode scope resolves too.
    reg.data["sheets"]["epi-1.s1_g1"] = {
        "output_path": "/other/epi-1/s1_g1.webp", "fal_image_url": "https://cdn.example/old.webp",
    }
    assert reg.resolve_ref_name("epi-1.s1_g1") == "https://cdn.example/old.webp"
    assert reg.resolve_ref_name("s9_g9") is None


# --- manifest approval + hash contract -----------------------------------------

def _write_manifest_run(tmp_path) -> str:
    run = str(tmp_path)
    os.makedirs(run, exist_ok=True)
    for name in ("storyboard_sheet_s1_g1.webp",):
        with open(os.path.join(run, name), "wb") as f:
            f.write(b"sheet")
    vp_dir = os.path.join(run, "video_prompts")
    os.makedirs(vp_dir, exist_ok=True)
    with open(os.path.join(vp_dir, "s1_g1.txt"), "w") as f:
        f.write("prompt")
    return run


def _manifest(run: str, **over) -> dict:
    def sha(p):
        import hashlib
        return hashlib.sha256(open(p, "rb").read()).hexdigest()
    m = {
        "manifest_version": "1.1",
        "status": "approved",
        "generations": [{
            "scene_id": "s1", "gen_id": "g1", "duration_seconds": 7.5,
            "sheet_path": "storyboard_sheet_s1_g1.webp",
            "sheet_sha256": sha(os.path.join(run, "storyboard_sheet_s1_g1.webp")),
            "video_prompt_path": "video_prompts/s1_g1.txt",
            "video_prompt_sha256": sha(os.path.join(run, "video_prompts", "s1_g1.txt")),
            "audio_refs": [],
        }],
    }
    m.update(over)
    return m


def test_manifest_requires_approved_status(tmp_path):
    run = _write_manifest_run(tmp_path)
    mp = os.path.join(run, "render_manifest.json")
    with open(mp, "w") as f:
        json.dump(_manifest(run, status="pending"), f)
    res = validators.validate_render_manifest(mp, run_dir=run)
    assert not res.ok
    assert any("approved" in e for e in res.errors)


def test_manifest_detects_post_approval_edit(tmp_path):
    run = _write_manifest_run(tmp_path)
    mp = os.path.join(run, "render_manifest.json")
    with open(mp, "w") as f:
        json.dump(_manifest(run), f)
    assert validators.validate_render_manifest(mp, run_dir=run).ok
    # Mutate the sheet after approval -> stale manifest error.
    with open(os.path.join(run, "storyboard_sheet_s1_g1.webp"), "ab") as f:
        f.write(b"changed")
    res = validators.validate_render_manifest(mp, run_dir=run)
    assert not res.ok
    assert any("sha256 mismatch" in e for e in res.errors)


def test_manifest_audio_ref_hash_checked(tmp_path):
    run = _write_manifest_run(tmp_path)
    apath = _touch(os.path.join(run, "audio", "s1_g1__voice_S1.mp3"))
    m = _manifest(run)
    m["generations"][0]["audio_refs"] = [
        {"path": "audio/s1_g1__voice_S1.mp3", "role": "voice_S1", "sha256": "0" * 64}
    ]
    mp = os.path.join(run, "render_manifest.json")
    with open(mp, "w") as f:
        json.dump(m, f)
    res = validators.validate_render_manifest(mp, run_dir=run)
    assert not res.ok
    assert any("audio ref sha256 mismatch" in e for e in res.errors)


# --- render ordering ------------------------------------------------------------

def test_ordered_scene_ids_follows_scenes_md(tmp_path):
    from scripts.render_all import _ordered_scene_ids
    run = str(tmp_path)
    with open(os.path.join(run, "scenes.md"), "w") as f:
        f.write(SCENES_MD)
    # Write storyboards in misleading creation order; s10 must still come last.
    for sid in ("s10", "s2", "s1"):
        with open(os.path.join(run, f"storyboard_{sid}.md"), "w") as f:
            f.write(_storyboard_md(sid))
    assert _ordered_scene_ids(run) == ["s1", "s2", "s10"]


def test_ordered_scene_ids_natural_fallback(tmp_path):
    from scripts.render_all import _ordered_scene_ids
    run = str(tmp_path)
    for sid in ("s10", "s2", "s1"):
        with open(os.path.join(run, f"storyboard_{sid}.md"), "w") as f:
            f.write(_storyboard_md(sid))
    assert _ordered_scene_ids(run) == ["s1", "s2", "s10"]


# --- vocal performance tags (micro-expressions-minimax research) --------------

def test_dialogue_delivery_modifiers_accepted():
    """[Language, delivery] and [Hum] brackets are valid dialogue tags."""
    prompt = REF2VA_G1.replace(
        "<d>[English] Hello.</d>",
        "<d>[English, crying] <pants> I... <i>tried</i>.</d>",
    )
    res = validators.validate_video_prompt(prompt, _sb1(), "g1")
    assert not any("<d>" in e for e in res.errors)
    assert not any("vocal tag" in w for w in res.warnings)

    hum = REF2VA_G1.replace(
        "<d>[English] Hello.</d>",
        "<d>[Hum] <humming> daa-da-da.</humming></d>",
    )
    res = validators.validate_video_prompt(hum, _sb1(), "g1")
    assert not any("<d>" in e for e in res.errors)


def test_unknown_vocal_tag_warns_not_errors():
    prompt = REF2VA_G1.replace(
        "<d>[English] Hello.</d>",
        "<d>[English] <slurps> Hello.</d>",
    )
    res = validators.validate_video_prompt(prompt, _sb1(), "g1")
    assert any("vocal tag" in w for w in res.warnings)
    assert not any("<d>" in e for e in res.errors)


def test_empty_dialogue_bracket_still_errors():
    prompt = REF2VA_G1.replace(
        "<d>[English] Hello.</d>",
        "<d>[] Hello.</d>",
    )
    res = validators.validate_video_prompt(prompt, _sb1(), "g1")
    assert any("<d>" in e for e in res.errors)
