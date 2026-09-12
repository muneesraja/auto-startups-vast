"""Phase 5 tests: canonical stories/ input folder contract.

(The story-intake CLI lives in skills/story-intake — its tests are in
skills/story-intake/tests/test_intake.py.)
"""

import json
import os
import subprocess
import sys

import pytest

from tools import episode_spec as es
from tools import story_input as si

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREPARE = os.path.join(SKILL_ROOT, "scripts", "prepare_episode.py")
INIT = os.path.join(SKILL_ROOT, "scripts", "init_story.py")


# -- scaffold -----------------------------------------------------------------


def test_init_story_scaffold(tmp_path):
    sd = si.init_story(str(tmp_path / "stories"), "Lord Shiva Furious Moments")
    assert os.path.basename(sd) == "lord-shiva-furious-moments"
    for sub in ("episodes", "audio", "characters", "locations", "objects",
                "style", "references",
                "episodes/episode-1", "episodes/episode-1/audio",
                "episodes/episode-1/references"):
        assert os.path.isdir(os.path.join(sd, sub)), sub
    cfg = json.loads(open(os.path.join(sd, "config.json")).read())
    assert cfg["style"] == "3d_animation"
    assert cfg["title"] == "Lord Shiva Furious Moments"
    ep1 = os.path.join(sd, "episodes", "episode-1")
    assert os.path.isfile(os.path.join(ep1, "episode-1.md"))
    assert os.path.isfile(os.path.join(ep1, "meta.json"))
    assert os.path.isfile(os.path.join(sd, "series.md"))
    assert os.path.isfile(os.path.join(sd, "README.intake.md"))


def test_init_story_idempotent(tmp_path):
    root = str(tmp_path / "stories")
    sd = si.init_story(root, "demo")
    cfg_path = os.path.join(sd, "config.json")
    with open(cfg_path, "w") as f:
        json.dump({"style": "watercolor"}, f)
    si.init_story(root, "demo")  # must not clobber
    assert json.loads(open(cfg_path).read())["style"] == "watercolor"


def test_init_story_cli(tmp_path):
    res = subprocess.run(
        [sys.executable, INIT, "my tale", "--stories-root",
         str(tmp_path / "stories")],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    assert (tmp_path / "stories" / "my-tale" / "config.json").is_file()


# -- discovery: episode folders first, flat fallbacks --------------------------


def test_episode_folder_preferred(tmp_path):
    sd = si.init_story(str(tmp_path / "stories"), "demo")
    ep2 = tmp_path / "stories" / "demo" / "episodes" / "episode-2"
    ep2.mkdir()
    (ep2 / "episode-2.md").write_text("# folder")
    (tmp_path / "stories" / "demo" / "episodes"
     / "episode-2.md").write_text("# flat")
    (tmp_path / "stories" / "demo" / "episode-2.md").write_text("# root")
    got = es.find_episode_story(str(tmp_path / "stories"), "demo", 2)
    assert got.endswith("episode-2/episode-2.md")


def test_episodes_flat_still_found(tmp_path):
    sd = si.init_story(str(tmp_path / "stories"), "demo")
    (tmp_path / "stories" / "demo" / "episodes" / "episode-3.md").write_text(
        "# flat")
    got = es.find_episode_story(str(tmp_path / "stories"), "demo", 3)
    assert got.endswith("episodes/episode-3.md")


def test_flat_root_still_found(tmp_path):
    sd = tmp_path / "stories" / "legacy"
    sd.mkdir(parents=True)
    (sd / "episode-6.md").write_text("# old")
    got = es.find_episode_story(str(tmp_path / "stories"), "legacy", 6)
    assert got.endswith("episode-6.md")


def test_meta_episode_folder(tmp_path):
    sd = si.init_story(str(tmp_path / "stories"), "demo")
    ep2 = tmp_path / "stories" / "demo" / "episodes" / "episode-2"
    ep2.mkdir()
    (ep2 / "meta.json").write_text(json.dumps({"title": "Two"}))
    assert es.load_meta(sd, 2)["title"] == "Two"


def test_meta_flat_still_found(tmp_path):
    sd = si.init_story(str(tmp_path / "stories"), "demo")
    (tmp_path / "stories" / "demo" / "episodes"
     / "episode-2.meta.json").write_text(json.dumps({"title": "Flat"}))
    assert es.load_meta(sd, 2)["title"] == "Flat"


# -- config merge --------------------------------------------------------------


def test_config_merges_into_spec(tmp_path):
    sd = si.init_story(str(tmp_path / "stories"), "demo")
    cfg = si.load_story_config(sd)
    cfg.update({
        "style": "pixar", "language": "ta", "tone": "epic",
        "constraints": ["no blood"], "never_show": ["crying"],
        "default_duration_minutes": 2,
        "intake_mode": "develop_from_concept",
        "cast": [{"id": "char_01", "name": "Shiva", "speaker": "S1",
                  "ref": "characters/char_01.png"}],
    })
    si.save_story_config(sd, cfg)
    spec = es.build_episode_spec(
        series="demo", episode=1, story_path="/x/ep.md", meta={},
        stories_root=str(tmp_path / "stories"),
        outputs_root=str(tmp_path / "out"),
        config=si.load_story_config(sd),
    )
    assert spec["style"] == "pixar" and spec["language"] == "ta"
    assert spec["intake_mode"] == "develop_from_concept"
    assert spec["target_seconds"] == 120  # default_duration_minutes fallback
    assert spec["constraints"] == ["no blood"]
    assert spec["never_show"] == ["crying"]
    assert spec["cast"][0]["speaker"] == "S1"


def test_meta_overrides_config(tmp_path):
    spec = es.build_episode_spec(
        series="demo", episode=1, story_path="/x/ep.md",
        meta={"intake_mode": "preserve_script", "target_seconds": 45,
              "cast": [{"id": "char_01", "speaker": "S2"}]},
        stories_root="/x", outputs_root="/o",
        config={"intake_mode": "develop_from_concept",
                "default_duration_minutes": 3,
                "cast": [{"id": "char_01", "name": "A", "speaker": "S1"},
                         {"id": "char_02", "name": "B", "speaker": "S9"}]},
    )
    assert spec["intake_mode"] == "preserve_script"
    assert spec["target_seconds"] == 45
    cast = {c["id"]: c for c in spec["cast"]}
    assert cast["char_01"]["speaker"] == "S2"   # meta override wins
    assert cast["char_01"]["name"] == "A"        # config field preserved
    assert cast["char_02"]["name"] == "B"


# -- user assets ----------------------------------------------------------------


def _png(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)


def test_materialize_user_assets_approved(tmp_path):
    root = tmp_path / "stories"
    sd = si.init_story(str(root), "demo")
    _png(tmp_path / "stories" / "demo" / "characters" / "char_01.png")
    _png(tmp_path / "stories" / "demo" / "characters" / "shiva.png")
    _png(tmp_path / "stories" / "demo" / "locations" / "loc_01.jpg")
    _png(tmp_path / "stories" / "demo" / "objects" / "obj_01.png")
    (tmp_path / "stories" / "demo" / "series.md").write_text("# bible")
    (tmp_path / "stories" / "demo" / "references").mkdir(exist_ok=True)
    (tmp_path / "stories" / "demo" / "references" / "seed.mp4").write_bytes(b"v")

    spec = es.build_episode_spec(
        series="demo", episode=1, story_path="/x/ep.md", meta={},
        stories_root=str(root), outputs_root=str(tmp_path / "out"),
        config={"cast": [{"id": "char_02", "name": "Shiva",
                          "ref": "characters/shiva.png"}]},
    )
    run = str(tmp_path / "out" / "demo" / "epi-1")
    os.makedirs(run, exist_ok=True)
    assets_dir = str(tmp_path / "out" / "demo" / "assets")
    res = es.materialize_user_assets(spec, run, sd, assets_dir)

    dests = {i["entity"]: i["dest"] for i in res["imported"]
             if i["section"] in ("characters", "locations", "objects")}
    assert "char_01" in dests and "char_02" in dests  # cast ref mapped
    assert "loc_01" in dests and "obj_01" in dests
    assert any("shiva" in w or "char_02" not in w for w in res["warnings"]) \
        or not res["warnings"]
    # Registry entries exist, approved, origin user.
    reg = json.loads(open(os.path.join(assets_dir,
                                       "asset_registry.json")).read())
    by_ent = {a["entity_id"]: a for a in reg["assets"].values()}
    assert by_ent["char_01"]["status"] == "approved"
    assert by_ent["char_01"]["origin"] == "user"
    assert by_ent["char_02"]["status"] == "approved"
    # series bible + style/reference copies land in run dir.
    assert (tmp_path / "out" / "demo" / "epi-1" / "series_bible.md").is_file()
    assert (tmp_path / "out" / "demo" / "epi-1" / "references"
            / "seed.mp4").is_file()


def test_materialize_warns_on_noncanonical_id(tmp_path):
    root = tmp_path / "stories"
    sd = si.init_story(str(root), "demo")
    _png(tmp_path / "stories" / "demo" / "characters" / "hero.png")
    spec = es.build_episode_spec(
        series="demo", episode=1, story_path="/x/ep.md", meta={},
        stories_root=str(root), outputs_root=str(tmp_path / "out"),
    )
    run = str(tmp_path / "out" / "demo" / "epi-1")
    os.makedirs(run, exist_ok=True)
    res = es.materialize_user_assets(
        spec, run, sd, str(tmp_path / "out" / "demo" / "assets"))
    assert any("hero" in w for w in res["warnings"])


def test_episode_audio_shadows_series(tmp_path):
    root, sd = tmp_path / "stories", si.init_story(
        str(tmp_path / "stories"), "demo")
    ep6 = tmp_path / "stories" / "demo" / "episodes" / "episode-6"
    (ep6 / "audio").mkdir(parents=True)
    (tmp_path / "stories" / "demo" / "audio" / "music.wav").write_bytes(b"ser")
    (ep6 / "audio" / "music.wav").write_bytes(b"ep6")
    (ep6 / "audio" / "voice_S1.mp3").write_bytes(b"ep6voice")
    spec = es.build_episode_spec(
        series="demo", episode=6, story_path="/x/ep.md", meta={},
        stories_root=str(root), outputs_root=str(tmp_path / "out"))
    run = str(tmp_path / "out" / "demo" / "epi-6")
    os.makedirs(run, exist_ok=True)
    written = es.materialize_audio(spec, run, sd)
    run_audio = tmp_path / "out" / "demo" / "epi-6" / "audio"
    assert (run_audio / "music.wav").read_bytes() == b"ep6"   # ep shadows
    assert (run_audio / "voice_S1.mp3").read_bytes() == b"ep6voice"


def test_prepare_end_to_end_new_layout(tmp_path):
    root = tmp_path / "stories"
    sd = si.init_story(str(root), "shiva")
    ep6 = root / "shiva" / "episodes" / "episode-6"
    ep6.mkdir()
    (ep6 / "episode-6.md").write_text("# Ep 6\nFire.")
    _png(root / "shiva" / "characters" / "char_01.png")
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
    assert spec["style"] == "3d_animation"
    assert (run / "series_bible.md").is_file()
    assert any(i["entity"] == "char_01" for i in
               spec["user_assets"]["imported"])
    assert spec["user_assets"]["imported"]
