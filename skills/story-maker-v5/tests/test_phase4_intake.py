"""Phase 4 tests: EpisodeSpec intake, audio materialization, status tracking."""

import json
import os
import subprocess
import sys

import pytest

from tools import episode_spec as es
from tools.audio_refs import find_audio_refs

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREPARE = os.path.join(SKILL_ROOT, "scripts", "prepare_episode.py")


def _story_root(tmp_path, series="shiva"):
    story_dir = tmp_path / "stories" / series
    story_dir.mkdir(parents=True)
    return tmp_path / "stories", story_dir


def test_find_episode_story_exact(tmp_path):
    root, sd = _story_root(tmp_path)
    (sd / "episode-6.md").write_text("# Ep 6")
    assert es.find_episode_story(str(root), "shiva", 6).endswith("episode-6.md")


def test_find_episode_story_glob_and_story_fallback(tmp_path):
    root, sd = _story_root(tmp_path)
    (sd / "Episode 6 — The River.md").write_text("# Ep 6")
    assert "Episode 6" in es.find_episode_story(str(root), "shiva", 6)

    # Story.md fallback when no episode file matches.
    root2, sd2 = _story_root(tmp_path, "other")
    (sd2 / "Story.md").write_text("# Whole story")
    assert es.find_episode_story(str(root2), "other", 3).endswith("Story.md")


def test_find_episode_story_missing_lists_searched(tmp_path):
    root, sd = _story_root(tmp_path, "empty")
    with pytest.raises(es.EpisodeNotFoundError) as exc:
        es.find_episode_story(str(root), "empty", 2)
    assert "episode-2.md" in str(exc.value)
    assert "Story.md" in str(exc.value)


def test_meta_merge_and_spec_shape(tmp_path):
    root, sd = _story_root(tmp_path)
    (sd / "episode-6.md").write_text("# Ep 6")
    (sd / "episode-6.meta.json").write_text(json.dumps({
        "title": "The River",
        "intake_mode": "develop_from_concept",
        "duration_mode": "fixed",
        "target_seconds": 180,
        "handoff_from": "epi-5",
        "audio": {"voice_refs": {"S1": "audio/voice.mp3"}},
    }))
    story = es.find_episode_story(str(root), "shiva", 6)
    meta = es.load_meta(str(sd), 6)
    spec = es.build_episode_spec(
        series="shiva", episode=6, story_path=story, meta=meta,
        stories_root=str(root), outputs_root=str(tmp_path / "out"),
    )
    assert spec["schema"] == "story-maker-v5.episode_spec/v1"
    assert spec["title"] == "The River"
    assert spec["intake_mode"] == "develop_from_concept"
    assert spec["target_seconds"] == 180
    assert spec["handoff_from"] == "epi-5"
    assert spec["run_dir"].endswith("out/shiva/epi-6")


def test_materialize_audio_roles(tmp_path):
    root, sd = _story_root(tmp_path)
    (sd / "episode-6.md").write_text("# Ep 6")
    (sd / "audio").mkdir()
    (sd / "audio" / "narrator.mp3").write_bytes(b"mp3data")
    (sd / "audio" / "bed.wav").write_bytes(b"wavdata")
    (sd / "episode-6.meta.json").write_text(json.dumps({
        "audio": {
            "voice_refs": {"S1": "audio/narrator.mp3"},
            "music_track": "audio/bed.wav",
        }
    }))
    meta = es.load_meta(str(sd), 6)
    spec = es.build_episode_spec(
        series="shiva", episode=6,
        story_path=str(sd / "episode-6.md"), meta=meta,
        stories_root=str(root), outputs_root=str(tmp_path / "out"),
    )
    run = str(tmp_path / "out" / "shiva" / "epi-6")
    written = es.materialize_audio(spec, run, str(sd))
    names = {os.path.basename(w) for w in written}
    assert "voice_S1.mp3" in names
    assert "music.wav" in names

    # Episode-wide roles resolve for every generation.
    refs = find_audio_refs(run, "s1", "g1")
    roles = {r["role"] for r in refs}
    assert "voice_S1" in roles and "music" in roles
    assert all(r["scope"] == "episode" for r in refs)
    refs2 = find_audio_refs(run, "s3", "g7")
    assert {r["role"] for r in refs2} == roles


def test_episode_scope_shadowed_by_scene_scope(tmp_path):
    run = str(tmp_path / "run")
    ad = os.path.join(run, "audio")
    os.makedirs(ad)
    open(os.path.join(ad, "music.mp3"), "wb").write(b"ep")
    open(os.path.join(ad, "s1__music.mp3"), "wb").write(b"scene")
    refs = find_audio_refs(run, "s1", "g1")
    music = [r for r in refs if r["role"] == "music"]
    assert len(music) == 1 and music[0]["scope"] == "scene"
    # A scene without an override still gets the episode ref.
    refs2 = find_audio_refs(run, "s2", "g1")
    assert any(r["role"] == "music" and r["scope"] == "episode" for r in refs2)


def test_prepare_episode_end_to_end(tmp_path):
    root, sd = _story_root(tmp_path)
    (sd / "episode-6.md").write_text("# Ep 6\nShiva crosses the river.")
    (sd / "episode-6.meta.json").write_text(json.dumps({
        "title": "The River", "target_seconds": 120,
    }))
    out = tmp_path / "outputs"
    res = subprocess.run(
        [sys.executable, PREPARE,
         "--stories-root", str(root), "--outputs-root", str(out),
         "--series", "shiva", "--episode", "6"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    run = out / "shiva" / "epi-6"
    spec = json.loads((run / "episode_spec.json").read_text())
    assert spec["episode"] == 6 and spec["title"] == "The River"
    assert (run / "story_source.md").read_text().startswith("# Ep 6")
    status = json.loads((run / "status.json").read_text())
    assert status["stage"] == "planned"
    index = json.loads((out / "shiva" / "episodes.json").read_text())
    assert index["episodes"]["epi-6"]["writing"] == "planned"
    assert index["episodes"]["epi-6"]["production"] == "planned"


def test_prepare_episode_story_file_mode(tmp_path):
    root, sd = _story_root(tmp_path)
    (sd / "Episode 7.md").write_text("# Ep 7")
    out = tmp_path / "outputs"
    res = subprocess.run(
        [sys.executable, PREPARE,
         "--story-file", str(sd / "Episode 7.md"),
         "--outputs-root", str(out)],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    assert (out / "shiva" / "epi-7" / "episode_spec.json").is_file()


def test_status_transitions(tmp_path):
    run = str(tmp_path / "out" / "shiva" / "epi-1")
    os.makedirs(run)
    es.set_production_status(run, "planned")
    es.set_production_status(run, "rendering")
    st = es.episode_status(run)
    assert st["stage"] == "rendering"
    assert [h["stage"] for h in st["history"]] == ["planned", "rendering"]

    story_dir = str(tmp_path / "out" / "shiva")
    es.set_writing_status(story_dir, 1, "ready", run_dir=run)
    es.set_index_production(story_dir, 1, "complete", run_dir=run)
    idx = json.loads(open(os.path.join(story_dir, "episodes.json")).read())
    assert idx["episodes"]["epi-1"]["writing"] == "ready"
    assert idx["episodes"]["epi-1"]["production"] == "complete"

    with pytest.raises(ValueError):
        es.set_production_status(run, "bogus_stage")
