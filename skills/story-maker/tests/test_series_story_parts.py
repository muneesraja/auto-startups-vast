"""Tests for series story_root / part-N layout and migration path rewrite."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

from main import resolve_output_layout  # noqa: E402
from scripts.migrate_story_series import migrate, rewrite_series_paths  # noqa: E402
from scripts.nodes.resume_router import resume_router  # noqa: E402
from scripts.nodes.save_artifact_nodes import _asset_dir, _asset_root  # noqa: E402


class TestResolveOutputLayout(unittest.TestCase):
    def test_flat_name(self):
        root, out, asset = resolve_output_layout(
            name="story-naila-5m-v2",
            story_id=None,
            part=None,
            base_dir="/tmp/out",
        )
        self.assertEqual(root, "/tmp/out/story-naila-5m-v2")
        self.assertEqual(out, root)
        self.assertEqual(asset, root)

    def test_series_part(self):
        root, out, asset = resolve_output_layout(
            name=None,
            story_id="story-naila",
            part=2,
            base_dir="/tmp/out",
        )
        self.assertEqual(root, "/tmp/out/story-naila")
        self.assertEqual(out, "/tmp/out/story-naila/part-2")
        self.assertEqual(asset, root)

    def test_rejects_both_or_neither(self):
        with self.assertRaises(ValueError):
            resolve_output_layout(name="x", story_id="y", part=1, base_dir="/tmp")
        with self.assertRaises(ValueError):
            resolve_output_layout(name=None, story_id=None, part=None, base_dir="/tmp")
        with self.assertRaises(ValueError):
            resolve_output_layout(name=None, story_id="y", part=0, base_dir="/tmp")


class TestAssetRootResolver(unittest.TestCase):
    def test_defaults_to_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = MagicMock()
            ctx.state = {"output_dir": tmp}
            self.assertEqual(_asset_root(ctx), tmp)
            chars = _asset_dir(ctx, "characters")
            self.assertEqual(chars, os.path.join(tmp, "characters"))
            self.assertTrue(os.path.isdir(chars))

    def test_uses_asset_root_when_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            story = os.path.join(tmp, "story")
            part = os.path.join(story, "part-1")
            os.makedirs(part)
            ctx = MagicMock()
            ctx.state = {
                "output_dir": part,
                "asset_root": story,
                "story_root": story,
            }
            self.assertEqual(_asset_root(ctx), story)
            self.assertEqual(
                _asset_dir(ctx, "locations"),
                os.path.join(story, "locations"),
            )


class TestRewriteSeriesPaths(unittest.TestCase):
    def test_shared_vs_part_vs_adhoc(self):
        src = "/runs/story-naila-5m-v2"
        story = "/runs/story-naila"
        part = "/runs/story-naila/part-1"
        text = json.dumps(
            {
                "character_sheets": {
                    "char_01": {"output_path": f"{src}/characters/char_01.png"}
                },
                "shot_images": {
                    "scene_01_shot_01": {
                        "output_path": f"{src}/images/scene_01_shot_01.png"
                    }
                },
                "clips": [
                    {
                        "output_path": f"{src}/Naila-final-v2-videos/scene_02_seg_01_clip_01.mp4"
                    }
                ],
            }
        )
        out, counts = rewrite_series_paths(
            text, source_root=src, story_root=story, part_dir=part
        )
        self.assertIn(f"{story}/characters/char_01.png", out)
        self.assertIn(f"{part}/images/scene_01_shot_01.png", out)
        self.assertIn(f"{part}/videos/scene_02_seg_01_clip_01.mp4", out)
        self.assertNotIn(src, out)
        self.assertGreater(counts["shared"], 0)
        self.assertGreater(counts["part"], 0)
        self.assertGreater(counts["adhoc_videos"], 0)


class TestMigrateCopy(unittest.TestCase):
    def test_migrate_copy_and_reuse_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "story-naila-5m-v2"
            (src / "characters").mkdir(parents=True)
            (src / "locations").mkdir()
            (src / "backgrounds").mkdir()
            (src / "images").mkdir()
            (src / "videos").mkdir()
            char = src / "characters" / "char_01.png"
            char.write_bytes(b"png")
            img = src / "images" / "scene_01_shot_01.png"
            img.write_bytes(b"img")
            specs = {
                "character_sheets": {
                    "char_01": {
                        "output_path": str(char),
                        "status": "completed",
                    }
                },
                "shot_images": {
                    "scene_01_shot_01": {"output_path": str(img)}
                },
            }
            (src / "generation_specs.json").write_text(
                json.dumps(specs), encoding="utf-8"
            )
            (src / "developed_story.md").write_text("# Story\n", encoding="utf-8")
            (src / "scene_paper.md").write_text("# Paper\n", encoding="utf-8")
            (src / "plan.json").write_text("{}", encoding="utf-8")

            story_root = Path(tmp) / "story-naila"
            summary = migrate(source=src, story_root=story_root, part=1)
            self.assertTrue((story_root / "characters" / "char_01.png").is_file())
            self.assertTrue((story_root / "part-1" / "images" / "scene_01_shot_01.png").is_file())
            # Original untouched
            self.assertTrue(char.is_file())
            new_specs = json.loads(
                (story_root / "part-1" / "generation_specs.json").read_text()
            )
            self.assertEqual(
                os.path.realpath(new_specs["character_sheets"]["char_01"]["output_path"]),
                os.path.realpath(story_root / "characters" / "char_01.png"),
            )
            self.assertEqual(
                os.path.realpath(new_specs["shot_images"]["scene_01_shot_01"]["output_path"]),
                os.path.realpath(story_root / "part-1" / "images" / "scene_01_shot_01.png"),
            )
            self.assertEqual(summary["missing_assets"], [])


class TestFreshPreservesSharedAssets(unittest.TestCase):
    def test_fresh_wipes_part_not_shared(self):
        with tempfile.TemporaryDirectory() as tmp:
            story = os.path.join(tmp, "story-naila")
            part = os.path.join(story, "part-2")
            chars = os.path.join(story, "characters")
            os.makedirs(part)
            os.makedirs(chars)
            shared = os.path.join(chars, "char_01.png")
            with open(shared, "wb") as f:
                f.write(b"png")
            for name in ("developed_story.md", "scene_paper.md", "plan.json"):
                with open(os.path.join(part, name), "w", encoding="utf-8") as f:
                    f.write("x\n")
            ctx = MagicMock()
            ctx.state = {
                "output_dir": part,
                "asset_root": story,
                "story_root": story,
                "fresh": True,
                "skip_story_developer": False,
                "story_text": "hello",
            }
            import asyncio

            asyncio.run(resume_router(ctx))
            self.assertTrue(os.path.isfile(shared))
            self.assertFalse(os.path.isfile(os.path.join(part, "plan.json")))
            self.assertEqual(ctx.route, "developed_story")


class TestCrossPartReuseSeed(unittest.TestCase):
    def test_build_specs_marks_existing_character_completed(self):
        from scripts.nodes.plan_pipeline_nodes import build_generation_specs_from_plan
        import asyncio

        with tempfile.TemporaryDirectory() as tmp:
            story = os.path.join(tmp, "story")
            part = os.path.join(story, "part-2")
            chars = os.path.join(story, "characters")
            locs = os.path.join(story, "locations")
            os.makedirs(part)
            os.makedirs(chars)
            os.makedirs(locs)
            with open(os.path.join(chars, "char_01.png"), "wb") as f:
                f.write(b"png")
            with open(os.path.join(locs, "loc_01.png"), "wb") as f:
                f.write(b"png")
            plan = {
                "meta": {
                    "story_title": "T",
                    "style": "reel",
                    "aesthetic": "warm",
                    "total_duration_seconds": 2,
                    "total_scenes": 1,
                    "total_shots": 1,
                },
                "characters": [
                    {
                        "id": "char_01",
                        "name": "Naila",
                        "appearance": "green dress",
                        "voice_profile": "soft",
                    }
                ],
                "locations": [
                    {
                        "id": "loc_01",
                        "name": "Meadow",
                        "description": "grass",
                        "establishing_prompt": "empty",
                    }
                ],
                "scenes": [
                    {
                        "scene_id": "scene_01",
                        "title": "A",
                        "environment": "meadow",
                        "time_of_day": "day",
                        "lighting": "sun",
                        "location_id": "loc_01",
                        "assets": {
                            "generate_background": False,
                            "background_reference_mode": "style_anchor",
                            "background_prompt": "",
                            "rationale": "x",
                        },
                        "audio_scene": {"music_bed": "", "ending_state": ""},
                        "shots": [
                            {
                                "shot_id": "scene_01_shot_01",
                                "scene_id": "scene_01",
                                "duration_seconds": 2,
                                "description": "Naila waves",
                                "characters_present": ["char_01"],
                                "camera_intent": "Wide",
                            }
                        ],
                        "video_shots": [],
                    }
                ],
            }
            ctx = MagicMock()
            ctx.state = {
                "output_dir": part,
                "asset_root": story,
                "story_root": story,
                "style_id": "reel_v2",
                "pipeline_mode": "storyboard",
                "use_backgrounds": False,
                "plan_content": plan,
                "character_sheet_prompts_content": {},
                "shot_image_specs_content": {},
            }
            asyncio.run(build_generation_specs_from_plan(ctx))
            specs = json.loads(ctx.state["generation_specs_content"])
            self.assertEqual(specs["character_sheets"]["char_01"]["status"], "completed")
            self.assertEqual(
                specs["character_sheets"]["char_01"]["output_path"],
                os.path.join(chars, "char_01.png"),
            )
            self.assertEqual(specs["location_sheets"]["loc_01"]["status"], "completed")
            self.assertEqual(
                specs["location_sheets"]["loc_01"]["output_path"],
                os.path.join(locs, "loc_01.png"),
            )


if __name__ == "__main__":
    unittest.main()
