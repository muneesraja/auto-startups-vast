"""story-intake tests: CLI commands + naming-convention imports."""

import json
import os
import subprocess
import sys

import pytest

CLI = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "cli.py")
V5_TOOLS = os.path.join(os.path.dirname(CLI), "..", "story-maker-v5")
sys.path.insert(0, os.path.abspath(V5_TOOLS))

from tools import story_input as si  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40
MP3 = b"ID3" + b"0" * 40


def _cli(tmp_path, *argv, check=True):
    res = subprocess.run(
        [sys.executable, CLI, "--stories-root", str(tmp_path / "stories"),
         "--outputs-root", str(tmp_path / "outputs"), *argv],
        capture_output=True, text=True)
    if check:
        assert res.returncode == 0, res.stderr
    return res


def test_init(tmp_path):
    res = _cli(tmp_path, "init", "My Tale", "--title", "Tale")
    assert "my-tale" in res.stdout
    sd = tmp_path / "stories" / "my-tale"
    assert (sd / "episodes" / "episode-1" / "episode-1.md").is_file()
    assert (sd / "episodes" / "episode-1" / "meta.json").is_file()
    assert (sd / "episodes" / "episode-1" / "audio").is_dir()


def test_episode_create_no_clobber(tmp_path):
    _cli(tmp_path, "init", "demo")
    res = _cli(tmp_path, "episode", "demo", "3", "--title", "Three")
    assert "episode-3" in res.stdout
    ep3 = tmp_path / "stories" / "demo" / "episodes" / "episode-3"
    assert (ep3 / "episode-3.md").is_file() and (ep3 / "audio").is_dir()
    res = _cli(tmp_path, "episode", "demo", "3", check=False)
    assert res.returncode != 0 and "already exists" in res.stderr


def test_add_asset_entity_naming(tmp_path):
    _cli(tmp_path, "init", "demo")
    f = tmp_path / "pic.png"
    f.write_bytes(PNG)
    res = _cli(tmp_path, "add-asset", "demo", "characters", str(f))
    assert "characters/char_01.png" in res.stdout
    res = _cli(tmp_path, "add-asset", "demo", "characters", str(f))
    assert "characters/char_02.png" in res.stdout
    res = _cli(tmp_path, "add-asset", "demo", "locations", str(f),
               "--entity", "loc_05")
    assert "locations/loc_05.png" in res.stdout
    # wrong extension rejected
    bad = tmp_path / "x.mp3"
    bad.write_bytes(MP3)
    res = _cli(tmp_path, "add-asset", "demo", "characters", str(bad),
               check=False)
    assert res.returncode != 0


def test_add_audio_role_naming(tmp_path):
    _cli(tmp_path, "init", "demo")
    f = tmp_path / "v.mp3"
    f.write_bytes(MP3)
    res = _cli(tmp_path, "add-audio", "demo", str(f),
               "--role", "voice", "--speaker", "S1")
    assert "audio/voice_S1.mp3" in res.stdout
    res = _cli(tmp_path, "add-audio", "demo", str(f),
               "--role", "ambience", "--scene", "s1")
    assert "audio/s1__ambience.mp3" in res.stdout
    res = _cli(tmp_path, "add-audio", "demo", str(f),
               "--role", "voice", "--speaker", "S2",
               "--scene", "s1", "--gen", "g2")
    assert "audio/s1_g2__voice_S2.mp3" in res.stdout
    # voice without speaker → error
    res = _cli(tmp_path, "add-audio", "demo", str(f), "--role", "voice",
               check=False)
    assert res.returncode != 0 and "speaker" in res.stderr


def test_add_audio_episode_scoped(tmp_path):
    _cli(tmp_path, "init", "demo")
    _cli(tmp_path, "episode", "demo", "2")
    f = tmp_path / "v.mp3"
    f.write_bytes(MP3)
    res = _cli(tmp_path, "add-audio", "demo", str(f),
               "--role", "voice", "--speaker", "S1", "--episode", "2")
    assert "episodes/episode-2/audio/voice_S1.mp3" in res.stdout
    assert (tmp_path / "stories" / "demo" / "episodes" / "episode-2"
            / "audio" / "voice_S1.mp3").read_bytes() == MP3


def test_check_and_status(tmp_path):
    _cli(tmp_path, "init", "demo")
    ep1 = tmp_path / "stories" / "demo" / "episodes" / "episode-1"
    (ep1 / "episode-1.md").write_text("   ")  # empty content
    res = _cli(tmp_path, "check", "demo", check=False)
    assert res.returncode == 1 and "empty" in res.stderr
    res = _cli(tmp_path, "status", "demo")
    assert "epi-1" in res.stdout and "writing=" in res.stdout


def test_prepare(tmp_path):
    _cli(tmp_path, "init", "demo")
    ep1 = tmp_path / "stories" / "demo" / "episodes" / "episode-1"
    (ep1 / "episode-1.md").write_text("# E1\na real story")
    res = _cli(tmp_path, "prepare", "demo", "1")
    assert "prepared demo/epi-1" in res.stdout
    assert (tmp_path / "outputs" / "demo" / "epi-1"
            / "episode_spec.json").is_file()


def test_list(tmp_path):
    _cli(tmp_path, "init", "alpha")
    _cli(tmp_path, "init", "beta")
    res = _cli(tmp_path, "list")
    assert "alpha" in res.stdout and "beta" in res.stdout


def test_import_file_unit(tmp_path):
    sd = si.init_story(str(tmp_path / "stories"), "demo")
    f = tmp_path / "a.png"
    f.write_bytes(PNG)
    rel = si.import_file(sd, "characters", str(f))
    assert rel == "characters/char_01.png"
    f2 = tmp_path / "v.mp3"
    f2.write_bytes(MP3)
    rel = si.import_file(sd, "audio", str(f2), role="voice", speaker="S3",
                         scene="s2", episode=1)
    assert rel == "episodes/episode-1/audio/s2__voice_S3.mp3"
    with pytest.raises(ValueError):
        si.import_file(sd, "characters", str(f2))
