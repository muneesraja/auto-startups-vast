"""Panel regen refs: characters_present repair, slots, integrity, prompts."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

from scripts.nodes.plan_pipeline_nodes import (  # noqa: E402
    _character_reference_slots,
    _fill_empty_characters_present,
    normalize_production_plan,
)
from scripts.nodes.reference_integrity_node import reference_integrity  # noqa: E402
from scripts.nodes.storyboard_nodes import (  # noqa: E402
    _filter_chars_with_sheets,
    build_panel_regen_prompt,
    panel_regen,
)


class _Ctx:
    def __init__(self, state: dict):
        self.state = state


class TestFillCharactersPresent(unittest.TestCase):
    def test_fills_from_description_name_hits(self):
        scenes = [
            {
                "scene_id": "scene_01",
                "shots": [
                    {
                        "shot_id": "scene_01_shot_01",
                        "characters_present": [],
                        "description": "Naila rests while Azhagi watches.",
                    },
                    {
                        "shot_id": "scene_01_shot_02",
                        "characters_present": [],
                        "description": "Lush green sanctuary center with a hanging swing.",
                    },
                ],
            }
        ]
        characters = [
            {"id": "char_01", "name": "Naila"},
            {"id": "char_02", "name": "Azhagi"},
            {"id": "char_03", "name": "Neju"},
        ]
        _fill_empty_characters_present(scenes, characters)
        self.assertEqual(
            scenes[0]["shots"][0]["characters_present"], ["char_01", "char_02"]
        )
        self.assertEqual(scenes[0]["shots"][1]["characters_present"], [])

    def test_preserves_existing_characters_present(self):
        scenes = [
            {
                "scene_id": "scene_01",
                "shots": [
                    {
                        "shot_id": "s1",
                        "characters_present": ["char_03"],
                        "description": "Naila waves.",
                    }
                ],
            }
        ]
        _fill_empty_characters_present(
            scenes, [{"id": "char_01", "name": "Naila"}, {"id": "char_03", "name": "Neju"}]
        )
        self.assertEqual(scenes[0]["shots"][0]["characters_present"], ["char_03"])

    def test_normalize_fills_characters_present(self):
        plan = {
            "meta": {
                "story_title": "T",
                "style": "reel_v2",
                "aesthetic": "warm",
                "total_duration_seconds": 2,
                "total_scenes": 1,
                "total_shots": 1,
            },
            "characters": [
                {"id": "char_01", "name": "Naila", "appearance": "girl", "voice_profile": "soft"}
            ],
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "title": "Open",
                    "environment": "forest",
                    "time_of_day": "morning",
                    "lighting": "sun",
                    "shots": [
                        {
                            "shot_id": "scene_01_shot_01",
                            "scene_id": "scene_01",
                            "duration_seconds": 2,
                            "characters_present": [],
                            "description": "Naila sleeps on the swing.",
                        }
                    ],
                }
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
        self.assertEqual(
            out["scenes"][0]["shots"][0]["characters_present"], ["char_01"]
        )


class TestStoryboardReferenceSlots(unittest.TestCase):
    def test_character_reference_slots_order(self):
        slots = _character_reference_slots(["char_02", "char_01"])
        self.assertEqual(
            slots,
            [
                {"role": "character_sheet", "asset_id": "char_02", "priority": 0},
                {"role": "character_sheet", "asset_id": "char_01", "priority": 1},
            ],
        )


class TestStoryboardReferenceIntegrity(unittest.IsolatedAsyncioTestCase):
    async def test_storyboard_empty_chars_stays_grok_edit(self):
        story = {
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "shots": [
                        {
                            "shot_id": "scene_01_shot_01",
                            "characters_present": [],
                        }
                    ],
                }
            ]
        }
        specs = {
            "shot_images": {
                "scene_01_shot_01": {
                    "shot_id": "scene_01_shot_01",
                    "characters_present": [],
                    "generation_mode": "grok_edit",
                    "reference_strategy": "char_sheets_only",
                    "reference_slots": [],
                    "reference_images": [],
                }
            }
        }
        ctx = _Ctx(
            {
                "pipeline_mode": "storyboard",
                "story_plan_content": json.dumps(story),
                "scene_assets_content": json.dumps(
                    {
                        "scenes": [
                            {
                                "scene_id": "scene_01",
                                "background_reference_mode": "style_anchor",
                            }
                        ]
                    }
                ),
                "generation_specs_content": json.dumps(specs),
            }
        )
        await reference_integrity(ctx)
        entry = json.loads(ctx.state["generation_specs_content"])["shot_images"][
            "scene_01_shot_01"
        ]
        self.assertEqual(entry["generation_mode"], "grok_edit")
        self.assertEqual(entry["reference_strategy"], "char_sheets_only")
        self.assertEqual(entry["reference_slots"], [])
        self.assertEqual(entry["reference_images"], [])

    async def test_storyboard_rewrites_t2i_back_to_edit(self):
        story = {
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "shots": [
                        {
                            "shot_id": "scene_01_shot_01",
                            "characters_present": ["char_01"],
                        }
                    ],
                }
            ]
        }
        specs = {
            "shot_images": {
                "scene_01_shot_01": {
                    "shot_id": "scene_01_shot_01",
                    "characters_present": ["char_01"],
                    "generation_mode": "grok_t2i",
                    "reference_strategy": "no_references",
                    "reference_slots": [],
                    "reference_images": [],
                }
            }
        }
        ctx = _Ctx(
            {
                "pipeline_mode": "storyboard",
                "story_plan_content": json.dumps(story),
                "scene_assets_content": json.dumps({"scenes": []}),
                "generation_specs_content": json.dumps(specs),
            }
        )
        await reference_integrity(ctx)
        entry = json.loads(ctx.state["generation_specs_content"])["shot_images"][
            "scene_01_shot_01"
        ]
        self.assertEqual(entry["generation_mode"], "grok_edit")
        self.assertEqual(entry["reference_strategy"], "char_sheets_only")
        self.assertEqual(
            entry["reference_slots"],
            [{"role": "character_sheet", "asset_id": "char_01", "priority": 0}],
        )
        self.assertIn(
            "{{character_sheets.char_01.fal_image_url}}", entry["reference_images"]
        )


class TestFilterCharsWithSheets(unittest.TestCase):
    def test_keeps_only_chars_with_url_or_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            sheet_path = os.path.join(tmp, "char_01.png")
            with open(sheet_path, "wb") as f:
                f.write(b"sheet")
            specs = {
                "character_sheets": {
                    "char_01": {"output_path": sheet_path},
                    "char_02": {"fal_image_url": "https://example.com/char_02.png"},
                    "char_03": {"output_path": os.path.join(tmp, "missing.png")},
                    "char_04": {},
                }
            }
            self.assertEqual(
                _filter_chars_with_sheets(
                    specs, ["char_01", "char_02", "char_03", "char_04", "char_01"]
                ),
                ["char_01", "char_02"],
            )


class TestPanelRegenPromptWording(unittest.TestCase):
    def test_omits_motion_arc_and_forbids_invention(self):
        prompt = build_panel_regen_prompt(
            {
                "characters_present": [],
                "description": "Wide forest clearing",
                "camera_intent": "wide",
                "video_motion_arc": "Naila and Azhagi enter frame.",
            },
            render_style="Pixar CGI",
        )
        self.assertNotIn("Naila and Azhagi enter", prompt)
        self.assertIn("do not add", prompt.lower())
        self.assertIn("empty-stage", prompt.lower())

    def test_names_chars_only_when_present(self):
        with_chars = build_panel_regen_prompt(
            {
                "characters_present": ["char_01"],
                "description": "Close on hero",
                "camera_intent": "close-up",
            },
            render_style="Pixar CGI",
            character_labels={"char_01": "Naila"},
        )
        self.assertIn("char_01", with_chars)
        self.assertIn("REPLACE", with_chars)
        self.assertIn("Image 2 = char_01 (Naila)", with_chars)
        self.assertIn("footwear", with_chars.lower())
        self.assertIn("accessories", with_chars.lower())
        self.assertIn("height", with_chars.lower())
        self.assertIn("expression", with_chars.lower())
        self.assertIn("do NOT replace the crop expression", with_chars)
        self.assertIn("identity conflicts resolve", with_chars.lower())

    def test_preserves_expression_language(self):
        prompt = build_panel_regen_prompt(
            {
                "characters_present": ["char_01", "char_02"],
                "description": "Two heroes react",
                "camera_intent": "medium",
            },
            render_style="Pixar CGI",
        )
        self.assertIn("Image 2 = char_01", prompt)
        self.assertIn("Image 3 = char_02", prompt)
        self.assertIn("facial expression", prompt.lower())
        self.assertIn("sheet identity wins", prompt.lower())
        self.assertIn("laughing", prompt.lower())
        self.assertIn("do NOT replace the crop expression", prompt)
        self.assertIn("footwear", prompt.lower())
        self.assertIn("proportions", prompt.lower())


class TestPanelRegenRuntimeRefs(unittest.IsolatedAsyncioTestCase):
    async def test_ref_order_crop_then_chars(self):
        with tempfile.TemporaryDirectory() as tmp:
            crops = os.path.join(tmp, "panel_crops")
            images = os.path.join(tmp, "images")
            os.makedirs(crops)
            os.makedirs(images)
            crop_path = os.path.join(crops, "scene_01_shot_01.png")
            with open(crop_path, "wb") as f:
                f.write(b"crop")

            captured: dict = {}

            def fake_edit(prompt, refs, out_path, **kwargs):
                captured["refs"] = list(refs)
                captured["prompt"] = prompt
                with open(out_path, "wb") as f:
                    f.write(b"out")
                return {
                    "status": "success",
                    "generated_image_path": out_path,
                    "fal_image_url": "https://example.com/out.png",
                }

            specs = {
                "character_sheets": {
                    "char_01": {
                        "character_id": "char_01",
                        "fal_image_url": "https://example.com/char.png",
                    }
                },
                "storyboard_sheets": {
                    "scene_01_sheet_01": {
                        "panel_shot_ids": ["scene_01_shot_01"],
                    }
                },
                "shot_images": {
                    "scene_01_shot_01": {
                        "shot_id": "scene_01_shot_01",
                        "characters_present": ["char_01"],
                        "panel_crop_path": crop_path,
                        "storyboard_sheet_id": "scene_01_sheet_01",
                        "status": "pending",
                    }
                },
            }
            with open(os.path.join(tmp, "generation_specs.json"), "w", encoding="utf-8") as f:
                json.dump(specs, f)

            story = {
                "scenes": [
                    {
                        "scene_id": "scene_01",
                        "shots": [
                            {
                                "shot_id": "scene_01_shot_01",
                                "characters_present": ["char_01"],
                                "description": "Hero smiles",
                                "camera_intent": "medium",
                            }
                        ],
                    }
                ]
            }
            ctx = _Ctx(
                {
                    "output_dir": tmp,
                    "style_id": "reel_v2",
                    "story_plan_content": json.dumps(story),
                    "video_shot_plan_content": json.dumps({"scenes": []}),
                    "generation_specs_content": json.dumps(specs),
                }
            )
            with patch(
                "scripts.nodes.storyboard_nodes.generate_grok_edit",
                side_effect=fake_edit,
            ), patch(
                "scripts.nodes.storyboard_nodes._url_reachable", return_value=True
            ), patch(
                "tools.grok_replicate.upload_local_image",
                return_value="https://example.com/crop.png",
            ), patch.dict(
                os.environ,
                {
                    "SMOKE_MAX_PANEL_REGENS": "1",
                    "SMOKE_MAX_PANELS_PER_SHEET": "0",
                    "SMOKE_MAX_STORYBOARD_SHEETS": "0",
                    "PANEL_IMAGE_FALLBACK_PROVIDER": "none",
                    "PROVIDER": "replicate",
                    "REPLICATE_API_TOKEN": "r8_test",
                },
                clear=False,
            ):
                await panel_regen(ctx)

            self.assertEqual(
                captured["refs"],
                ["https://example.com/crop.png", "https://example.com/char.png"],
            )
            self.assertNotIn("Motion arc", captured["prompt"])
            self.assertIn("REPLACE", captured["prompt"])
            self.assertIn("footwear", captured["prompt"].lower())
            self.assertIn("do NOT replace the crop expression", captured["prompt"])
            self.assertIn("Image 2 = char_01", captured["prompt"])
            saved = json.loads(ctx.state["generation_specs_content"])
            entry = saved["shot_images"]["scene_01_shot_01"]
            self.assertEqual(
                entry["reference_slots"],
                [{"role": "character_sheet", "asset_id": "char_01", "priority": 0}],
            )
            self.assertEqual(entry["generation_mode"], "grok_edit")

    async def test_drops_chars_without_sheets(self):
        with tempfile.TemporaryDirectory() as tmp:
            crops = os.path.join(tmp, "panel_crops")
            images = os.path.join(tmp, "images")
            os.makedirs(crops)
            os.makedirs(images)
            crop_path = os.path.join(crops, "scene_01_shot_01.png")
            with open(crop_path, "wb") as f:
                f.write(b"crop")

            captured: dict = {}

            def fake_edit(prompt, refs, out_path, **kwargs):
                captured["refs"] = list(refs)
                captured["prompt"] = prompt
                with open(out_path, "wb") as f:
                    f.write(b"out")
                return {
                    "status": "success",
                    "generated_image_path": out_path,
                    "fal_image_url": "https://example.com/out.png",
                }

            specs = {
                "character_sheets": {
                    "char_01": {
                        "character_id": "char_01",
                        "fal_image_url": "https://example.com/char.png",
                    }
                    # char_02 intentionally missing
                },
                "storyboard_sheets": {
                    "scene_01_sheet_01": {
                        "panel_shot_ids": ["scene_01_shot_01"],
                    }
                },
                "shot_images": {
                    "scene_01_shot_01": {
                        "shot_id": "scene_01_shot_01",
                        "characters_present": ["char_01", "char_02"],
                        "panel_crop_path": crop_path,
                        "storyboard_sheet_id": "scene_01_sheet_01",
                        "status": "pending",
                    }
                },
            }
            with open(os.path.join(tmp, "generation_specs.json"), "w", encoding="utf-8") as f:
                json.dump(specs, f)

            story = {
                "characters": [
                    {"id": "char_01", "name": "Naila"},
                    {"id": "char_02", "name": "Azhagi"},
                ],
                "scenes": [
                    {
                        "scene_id": "scene_01",
                        "shots": [
                            {
                                "shot_id": "scene_01_shot_01",
                                "characters_present": ["char_01", "char_02"],
                                "description": "Heroes react",
                                "camera_intent": "medium",
                            }
                        ],
                    }
                ],
            }
            ctx = _Ctx(
                {
                    "output_dir": tmp,
                    "style_id": "reel_v2",
                    "story_plan_content": json.dumps(story),
                    "video_shot_plan_content": json.dumps({"scenes": []}),
                    "generation_specs_content": json.dumps(specs),
                }
            )
            with patch(
                "scripts.nodes.storyboard_nodes.generate_grok_edit",
                side_effect=fake_edit,
            ), patch(
                "scripts.nodes.storyboard_nodes._url_reachable", return_value=True
            ), patch(
                "tools.grok_replicate.upload_local_image",
                return_value="https://example.com/crop.png",
            ), patch.dict(
                os.environ,
                {
                    "SMOKE_MAX_PANEL_REGENS": "1",
                    "SMOKE_MAX_PANELS_PER_SHEET": "0",
                    "SMOKE_MAX_STORYBOARD_SHEETS": "0",
                    "PANEL_IMAGE_FALLBACK_PROVIDER": "none",
                    "PROVIDER": "replicate",
                    "REPLICATE_API_TOKEN": "r8_test",
                },
                clear=False,
            ):
                await panel_regen(ctx)

            self.assertEqual(
                captured["refs"],
                ["https://example.com/crop.png", "https://example.com/char.png"],
            )
            self.assertIn("Image 2 = char_01 (Naila)", captured["prompt"])
            self.assertNotIn("char_02", captured["prompt"])
            saved = json.loads(ctx.state["generation_specs_content"])
            entry = saved["shot_images"]["scene_01_shot_01"]
            self.assertEqual(entry["characters_present"], ["char_01"])


class TestPanelFalFallback(unittest.IsolatedAsyncioTestCase):
    async def test_fal_fallback_after_replicate_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            crops = os.path.join(tmp, "panel_crops")
            images = os.path.join(tmp, "images")
            os.makedirs(crops)
            os.makedirs(images)
            crop_path = os.path.join(crops, "scene_01_shot_01.png")
            with open(crop_path, "wb") as f:
                f.write(b"crop")

            calls: list[str] = []

            def fake_edit(prompt, refs, out_path, **kwargs):
                provider = kwargs.get("provider") or "replicate"
                calls.append(provider)
                if provider != "fal":
                    return {
                        "status": "error",
                        "message": "ModelError: flagged as sensitive (E005)",
                    }
                with open(out_path, "wb") as f:
                    f.write(b"fal-out")
                return {
                    "status": "success",
                    "generated_image_path": out_path,
                    "fal_image_url": "https://fal.media/out.png",
                }

            specs = {
                "character_sheets": {
                    "char_01": {
                        "fal_image_url": "https://example.com/char.png",
                        "output_path": os.path.join(tmp, "char_01.png"),
                        "status": "completed",
                    }
                },
                "storyboard_sheets": {
                    "scene_01_sheet_01": {
                        "sheet_id": "scene_01_sheet_01",
                        "scene_id": "scene_01",
                        "panel_shot_ids": ["scene_01_shot_01"],
                    }
                },
                "shot_images": {
                    "scene_01_shot_01": {
                        "shot_id": "scene_01_shot_01",
                        "characters_present": ["char_01"],
                        "panel_crop_path": crop_path,
                        "status": "pending",
                    }
                },
            }
            with open(os.path.join(tmp, "char_01.png"), "wb") as f:
                f.write(b"char")
            with open(os.path.join(tmp, "generation_specs.json"), "w", encoding="utf-8") as f:
                json.dump(specs, f)

            story = {
                "scenes": [
                    {
                        "scene_id": "scene_01",
                        "shots": [
                            {
                                "shot_id": "scene_01_shot_01",
                                "characters_present": ["char_01"],
                                "description": "Hero smiles",
                                "camera_intent": "medium",
                            }
                        ],
                    }
                ]
            }
            ctx = _Ctx(
                {
                    "output_dir": tmp,
                    "style_id": "reel_v2",
                    "story_plan_content": json.dumps(story),
                    "video_shot_plan_content": json.dumps({"scenes": []}),
                    "generation_specs_content": json.dumps(specs),
                }
            )

            async def _immediate_to_thread(fn, *args, **kwargs):
                return fn(*args, **kwargs)

            with patch(
                "scripts.nodes.storyboard_nodes.generate_grok_edit",
                side_effect=fake_edit,
            ), patch(
                "scripts.nodes.storyboard_nodes._url_reachable",
                return_value=True,
            ), patch(
                "tools.grok_replicate.upload_local_image",
                return_value="https://example.com/crop-rep.png",
            ), patch(
                "fal_client.upload_file",
                return_value="https://fal.media/crop.png",
            ), patch(
                "scripts.nodes.storyboard_nodes.asyncio.to_thread",
                side_effect=_immediate_to_thread,
            ), patch(
                "scripts.nodes._shot_image_gen.asyncio.to_thread",
                side_effect=_immediate_to_thread,
            ), patch(
                "scripts.nodes._shot_image_gen.asyncio.sleep",
                return_value=None,
            ), patch(
                "scripts.nodes._shot_image_gen._MAX_SENSITIVE_RETRIES",
                0,
            ), patch.dict(
                os.environ,
                {
                    "SMOKE_MAX_PANEL_REGENS": "1",
                    "PANEL_IMAGE_PROVIDER": "replicate",
                    "PANEL_IMAGE_FALLBACK_PROVIDER": "fal",
                    "PROVIDER": "replicate",
                    "REPLICATE_API_TOKEN": "r8_test",
                    "FAL_KEY": "fal_test",
                    "PANEL_REGEN_ALLOW_SOFT_FAIL": "0",
                },
                clear=False,
            ):
                await panel_regen(ctx)

            self.assertIn("fal", calls)
            self.assertTrue(any(p == "replicate" for p in calls))
            with open(os.path.join(tmp, "generation_specs.json"), encoding="utf-8") as f:
                saved = json.load(f)
            entry = saved["shot_images"]["scene_01_shot_01"]
            self.assertEqual(entry["status"], "completed")
            self.assertEqual(entry.get("image_provider"), "fal")
            self.assertEqual(entry.get("fallback_mode"), "fal_after_primary_failure")
            self.assertTrue(
                os.path.isfile(os.path.join(images, "scene_01_shot_01.png"))
            )


if __name__ == "__main__":
    unittest.main()
