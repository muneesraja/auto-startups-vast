"""Tests for location lock normalize + storyboard continuity refs."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

from scripts.nodes.plan_pipeline_nodes import (  # noqa: E402
    normalize_production_plan,
)
from scripts.nodes.storyboard_nodes import (  # noqa: E402
    build_storyboard_sheet_ref_urls,
    storyboard_sheet_generator,
    storyboard_sheet_planner,
)
from scripts.nodes.storyboard_sheet_builder import (  # noqa: E402
    build_reference_roles_block,
    resolve_environment_block,
)


class _Ctx:
    def __init__(self, state: dict):
        self.state = state


class TestNormalizeLocations(unittest.TestCase):
    def test_synthesize_locations_and_assign_location_id(self):
        plan = {
            "meta": {
                "story_title": "LocTest",
                "style": "reel_v2",
                "aesthetic": "warm",
                "total_duration_seconds": 2,
                "total_scenes": 2,
                "total_shots": 2,
            },
            "characters": [
                {
                    "id": "char_01",
                    "name": "A",
                    "appearance": "girl",
                    "voice_profile": "soft",
                }
            ],
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "title": "Forest",
                    "environment": "lush forest sanctuary",
                    "time_of_day": "morning",
                    "lighting": "golden",
                    "shots": [
                        {
                            "shot_id": "scene_01_shot_01",
                            "scene_id": "scene_01",
                            "duration_seconds": 1,
                            "characters_present": ["char_01"],
                            "description": "Wide",
                        }
                    ],
                },
                {
                    "scene_id": "scene_02",
                    "title": "Forest again",
                    "environment": "lush forest sanctuary",
                    "time_of_day": "morning",
                    "lighting": "golden",
                    "shots": [
                        {
                            "shot_id": "scene_02_shot_01",
                            "scene_id": "scene_02",
                            "duration_seconds": 1,
                            "characters_present": ["char_01"],
                            "description": "Closer",
                        }
                    ],
                },
            ],
        }
        ctx = _Ctx(
            {
                "style_id": "reel_v2",
                "pipeline_mode": "storyboard",
                "output_dir": tempfile.mkdtemp(),
            }
        )
        out = normalize_production_plan(plan, ctx)
        self.assertEqual(len(out["locations"]), 1)
        self.assertEqual(out["locations"][0]["id"], "loc_01")
        self.assertEqual(out["scenes"][0]["location_id"], "loc_01")
        self.assertEqual(out["scenes"][1]["location_id"], "loc_01")
        self.assertIn("establishing_prompt", out["locations"][0])


class TestStoryboardContinuityPlanner(unittest.IsolatedAsyncioTestCase):
    async def test_planner_sets_continuity_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            story = {
                "meta": {},
                "characters": [{"id": "char_01", "name": "A", "appearance": "x"}],
                "locations": [
                    {
                        "id": "loc_01",
                        "name": "Forest",
                        "description": "Lush forest",
                        "establishing_prompt": "Wide empty forest",
                    }
                ],
                "scenes": [
                    {
                        "scene_id": "scene_01",
                        "title": "One",
                        "environment": "forest",
                        "time_of_day": "morning",
                        "lighting": "warm",
                        "location_id": "loc_01",
                        "shots": [
                            {
                                "shot_id": f"scene_01_shot_{i:02d}",
                                "characters_present": ["char_01"],
                                "description": f"Beat {i}",
                                "camera_intent": "Wide",
                            }
                            for i in range(1, 12)
                        ],
                    }
                ],
            }
            import json

            specs = {
                "character_sheets": {
                    "char_01": {
                        "character_id": "char_01",
                        "sheet_prompt": "x",
                        "status": "completed",
                    }
                },
                "location_sheets": {
                    "loc_01": {
                        "location_id": "loc_01",
                        "sheet_prompt": "x",
                        "output_path": os.path.join(tmp, "locations", "loc_01.png"),
                        "status": "completed",
                    }
                },
            }
            ctx = _Ctx(
                {
                    "output_dir": tmp,
                    "style_id": "reel_v2",
                    "panels_per_sheet": 10,
                    "story_plan_content": json.dumps(story),
                    "generation_specs_content": json.dumps(specs),
                }
            )
            # Also write specs path used by _load_specs
            specs_path = os.path.join(tmp, "generation_specs.json")
            with open(specs_path, "w", encoding="utf-8") as f:
                json.dump(specs, f)

            await storyboard_sheet_planner(ctx)
            with open(specs_path, encoding="utf-8") as f:
                saved = json.load(f)
            sheets = saved["storyboard_sheets"]
            self.assertIn("scene_01_sheet_01", sheets)
            self.assertIn("scene_01_sheet_02", sheets)
            s1 = sheets["scene_01_sheet_01"]
            s2 = sheets["scene_01_sheet_02"]
            self.assertEqual(s1["location_ref_id"], "loc_01")
            self.assertIsNone(s1["continuity_from_sheet_id"])
            self.assertEqual(s2["continuity_from_sheet_id"], "scene_01_sheet_01")
            self.assertEqual(s2["location_ref_id"], "loc_01")


class TestStoryboardRefOrder(unittest.TestCase):
    def test_ref_list_order_location_prev_chars(self):
        specs = {
            "location_sheets": {
                "loc_01": {"fal_image_url": "https://example.com/loc.png"}
            },
            "storyboard_sheets": {
                "scene_01_sheet_01": {
                    "fal_image_url": "https://example.com/prev.png"
                }
            },
            "character_sheets": {
                "char_01": {"fal_image_url": "https://example.com/char1.png"},
                "char_02": {"fal_image_url": "https://example.com/char2.png"},
            },
        }
        entry = {
            "location_ref_id": "loc_01",
            "continuity_from_sheet_id": "scene_01_sheet_01",
            "character_ref_ids": ["char_01", "char_02"],
        }
        with patch(
            "scripts.nodes.storyboard_nodes._url_reachable", return_value=True
        ):
            urls = build_storyboard_sheet_ref_urls(specs, entry, ref_limit=10)
        self.assertEqual(
            urls,
            [
                "https://example.com/loc.png",
                "https://example.com/prev.png",
                "https://example.com/char1.png",
                "https://example.com/char2.png",
            ],
        )

    def test_ref_list_caps_at_limit(self):
        specs = {
            "location_sheets": {
                "loc_01": {"fal_image_url": "https://example.com/loc.png"}
            },
            "storyboard_sheets": {
                "s1": {"fal_image_url": "https://example.com/prev.png"}
            },
            "character_sheets": {
                "c1": {"fal_image_url": "https://example.com/c1.png"},
                "c2": {"fal_image_url": "https://example.com/c2.png"},
            },
        }
        entry = {
            "location_ref_id": "loc_01",
            "continuity_from_sheet_id": "s1",
            "character_ref_ids": ["c1", "c2"],
        }
        with patch(
            "scripts.nodes.storyboard_nodes._url_reachable", return_value=True
        ):
            urls = build_storyboard_sheet_ref_urls(specs, entry, ref_limit=2)
        self.assertEqual(
            urls,
            [
                "https://example.com/loc.png",
                "https://example.com/prev.png",
            ],
        )


class TestStoryboardSequentialGen(unittest.IsolatedAsyncioTestCase):
    async def test_generator_calls_sheets_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            import json

            call_order: list[str] = []

            def fake_edit(prompt, refs, out_path, **kwargs):
                sheet_id = os.path.splitext(os.path.basename(out_path))[0]
                call_order.append(sheet_id)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, "wb") as f:
                    f.write(b"png")
                return {
                    "status": "success",
                    "generated_image_path": out_path,
                    "fal_image_url": f"https://example.com/{sheet_id}.png",
                }

            specs = {
                "character_sheets": {
                    "char_01": {
                        "character_id": "char_01",
                        "fal_image_url": "https://example.com/char.png",
                        "status": "completed",
                    }
                },
                "location_sheets": {
                    "loc_01": {
                        "location_id": "loc_01",
                        "fal_image_url": "https://example.com/loc.png",
                        "status": "completed",
                    }
                },
                "storyboard_sheets": {
                    "scene_01_sheet_01": {
                        "sheet_id": "scene_01_sheet_01",
                        "scene_id": "scene_01",
                        "character_ref_ids": ["char_01"],
                        "location_ref_id": "loc_01",
                        "continuity_from_sheet_id": None,
                        "sheet_prompt": "sheet one",
                        "output_path": os.path.join(
                            tmp, "storyboard_sheets", "scene_01_sheet_01.png"
                        ),
                        "status": "pending",
                    },
                    "scene_01_sheet_02": {
                        "sheet_id": "scene_01_sheet_02",
                        "scene_id": "scene_01",
                        "character_ref_ids": ["char_01"],
                        "location_ref_id": "loc_01",
                        "continuity_from_sheet_id": "scene_01_sheet_01",
                        "sheet_prompt": "sheet two",
                        "output_path": os.path.join(
                            tmp, "storyboard_sheets", "scene_01_sheet_02.png"
                        ),
                        "status": "pending",
                    },
                },
            }
            with open(os.path.join(tmp, "generation_specs.json"), "w", encoding="utf-8") as f:
                json.dump(specs, f)
            ctx = _Ctx({"output_dir": tmp})
            with patch(
                "scripts.nodes.storyboard_nodes.generate_grok_edit", side_effect=fake_edit
            ), patch(
                "scripts.nodes.storyboard_nodes.config.get_storyboard_image_provider",
                return_value="replicate",
            ), patch(
                "scripts.nodes.storyboard_nodes._url_reachable", return_value=True
            ):
                await storyboard_sheet_generator(ctx)
            self.assertEqual(
                call_order, ["scene_01_sheet_01", "scene_01_sheet_02"]
            )


class TestLocationEnvironmentBlock(unittest.TestCase):
    def test_plan_location_preferred_over_canon(self):
        scene = {
            "location_id": "loc_01",
            "environment": "clearing",
            "time_of_day": "dusk",
            "lighting": "purple",
        }
        locations = [
            {
                "id": "loc_01",
                "name": "River Dock",
                "description": "Wooden dock on a wide river",
                "establishing_prompt": "Empty dock at dusk",
            }
        ]
        block = resolve_environment_block(scene, locations)
        self.assertIn("River Dock", block)
        self.assertIn("Wooden dock", block)
        self.assertNotIn("lush forest sanctuary", block.lower())

    def test_reference_roles_order(self):
        text = build_reference_roles_block(
            has_location=True,
            has_previous_sheet=True,
            character_ids=["char_01"],
        )
        self.assertIn("1. LOCATION LOCK", text)
        self.assertIn("2. PREVIOUS STORYBOARD SHEET", text)
        self.assertIn("3. CHARACTER SHEETS", text)


class TestLocationSpecsPath(unittest.TestCase):
    def test_build_specs_seeds_location_paths(self):
        from scripts.nodes.plan_pipeline_nodes import _build_location_sheet_prompt

        prompt = _build_location_sheet_prompt(
            {
                "id": "loc_01",
                "name": "Dock",
                "description": "River dock",
                "establishing_prompt": "Wide empty dock",
            },
            render_style="Pixar CGI",
            style_id="reel_v2",
        )
        self.assertIn("loc_01", prompt)
        self.assertIn("Wide empty dock", prompt)
        self.assertIn("Pixar CGI", prompt)


if __name__ == "__main__":
    unittest.main()
