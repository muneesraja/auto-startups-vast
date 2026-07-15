"""Credit-safe E005 / sensitive retry + storyboard edit-only (no T2I fallback)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

from scripts.nodes._shot_image_gen import retry_async  # noqa: E402
from scripts.nodes.storyboard_nodes import (  # noqa: E402
    build_storyboard_sheet_ref_urls,
    storyboard_sheet_generator,
)


class _Ctx:
    def __init__(self, state: dict):
        self.state = state


async def _immediate_to_thread(fn, *args, **kwargs):
    return fn(*args, **kwargs) if args or kwargs else fn()


class TestSensitiveRetryCap(unittest.IsolatedAsyncioTestCase):
    async def test_max_sensitive_retries_stops_after_strategy_shot(self):
        calls = {"n": 0}
        softened = {"n": 0}

        def flaky():
            calls["n"] += 1
            return {"status": "error", "message": "flagged as sensitive E005"}

        def on_sensitive(_err, _attempt):
            softened["n"] += 1

        with patch(
            "scripts.nodes._shot_image_gen.asyncio.to_thread",
            side_effect=_immediate_to_thread,
        ), patch(
            "scripts.nodes._shot_image_gen.asyncio.sleep",
            return_value=None,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                await retry_async(
                    flaky,
                    "test sheet",
                    on_sensitive=on_sensitive,
                    max_sensitive_retries=1,
                )
        # attempt1 fail → on_sensitive; attempt2 fail → raise (cap exceeded)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(softened["n"], 2)
        self.assertIn("E005", str(ctx.exception))

    async def test_transient_errors_still_use_full_budget(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                return {"status": "error", "message": "429 rate limit"}
            return {
                "status": "success",
                "generated_image_path": "/tmp/x.png",
                "fal_image_url": "https://example.com/x.png",
            }

        with patch(
            "scripts.nodes._shot_image_gen.asyncio.to_thread",
            side_effect=_immediate_to_thread,
        ), patch(
            "scripts.nodes._shot_image_gen.asyncio.sleep",
            return_value=None,
        ):
            result = await retry_async(flaky, "transient", max_sensitive_retries=1)
        self.assertEqual(result["status"], "success")
        self.assertEqual(calls["n"], 3)


class TestLeanStoryboardRefs(unittest.TestCase):
    def test_lean_edit_excludes_character_sheets(self):
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
            urls = build_storyboard_sheet_ref_urls(
                specs, entry, ref_limit=10, include_character_sheets=False
            )
        self.assertEqual(
            urls,
            [
                "https://example.com/loc.png",
                "https://example.com/prev.png",
            ],
        )

    def test_full_edit_still_includes_characters(self):
        specs = {
            "location_sheets": {
                "loc_01": {"fal_image_url": "https://example.com/loc.png"}
            },
            "character_sheets": {
                "char_01": {"fal_image_url": "https://example.com/char1.png"},
            },
        }
        entry = {
            "location_ref_id": "loc_01",
            "character_ref_ids": ["char_01"],
        }
        with patch(
            "scripts.nodes.storyboard_nodes._url_reachable", return_value=True
        ):
            urls = build_storyboard_sheet_ref_urls(
                specs, entry, ref_limit=10, include_character_sheets=True
            )
        self.assertEqual(
            urls,
            [
                "https://example.com/loc.png",
                "https://example.com/char1.png",
            ],
        )


class TestStoryboardNoT2IFallback(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_t2i_mode_still_uses_edit_with_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            edit_calls = {"n": 0, "refs": None}

            def fake_edit(prompt, refs, out_path, **kwargs):
                edit_calls["n"] += 1
                edit_calls["refs"] = list(refs)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, "wb") as f:
                    f.write(b"png")
                return {
                    "status": "success",
                    "generated_image_path": out_path,
                    "fal_image_url": "https://example.com/sheet.png",
                }

            specs = {
                "_meta": {"storyboard_generation_mode": "t2i"},
                "character_sheets": {
                    "char_01": {
                        "fal_image_url": "https://example.com/char.png",
                        "status": "completed",
                    }
                },
                "location_sheets": {
                    "loc_01": {
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
                        "sheet_prompt": "young girl in forest",
                        "output_path": os.path.join(
                            tmp, "storyboard_sheets", "scene_01_sheet_01.png"
                        ),
                        "status": "pending",
                    }
                },
            }
            specs_path = os.path.join(tmp, "generation_specs.json")
            with open(specs_path, "w", encoding="utf-8") as f:
                json.dump(specs, f)

            ctx = _Ctx({"output_dir": tmp, "style_id": "reel_v2"})

            with patch(
                "scripts.nodes.storyboard_nodes.generate_grok_edit",
                side_effect=fake_edit,
            ), patch(
                "scripts.nodes.storyboard_nodes.config.get_storyboard_image_provider",
                return_value="replicate",
            ), patch(
                "scripts.nodes._shot_image_gen.asyncio.to_thread",
                side_effect=_immediate_to_thread,
            ), patch(
                "scripts.nodes._shot_image_gen.asyncio.sleep",
                return_value=None,
            ), patch(
                "scripts.nodes.storyboard_nodes._url_reachable",
                return_value=True,
            ):
                await storyboard_sheet_generator(ctx)

            self.assertEqual(edit_calls["n"], 1)
            self.assertEqual(edit_calls["refs"], ["https://example.com/loc.png"])
            with open(specs_path, encoding="utf-8") as f:
                saved = json.load(f)
            self.assertNotEqual(
                saved.get("_meta", {}).get("storyboard_generation_mode"), "t2i"
            )
            self.assertEqual(
                saved["storyboard_sheets"]["scene_01_sheet_01"]["status"],
                "completed",
            )

    async def test_edit_failure_marks_failed_and_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            edit_calls = {"ids": []}

            def fake_edit(prompt, refs, out_path, **kwargs):
                sheet_id = os.path.basename(out_path).replace(".png", "")
                edit_calls["ids"].append(sheet_id)
                if sheet_id == "scene_01_sheet_01":
                    return {
                        "status": "error",
                        "message": "ModelError: flagged as sensitive (E005)",
                    }
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, "wb") as f:
                    f.write(b"png")
                return {
                    "status": "success",
                    "generated_image_path": out_path,
                    "fal_image_url": "https://example.com/sheet2.png",
                }

            specs = {
                "character_sheets": {
                    "char_01": {
                        "fal_image_url": "https://example.com/char.png",
                        "status": "completed",
                    }
                },
                "location_sheets": {
                    "loc_01": {
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
                        "sheet_prompt": "scene album",
                        "output_path": os.path.join(
                            tmp, "storyboard_sheets", "scene_01_sheet_01.png"
                        ),
                        "status": "pending",
                    },
                    "scene_02_sheet_01": {
                        "sheet_id": "scene_02_sheet_01",
                        "scene_id": "scene_02",
                        "character_ref_ids": ["char_01"],
                        "location_ref_id": "loc_01",
                        "continuity_from_sheet_id": "scene_01_sheet_01",
                        "sheet_prompt": "next sheet",
                        "output_path": os.path.join(
                            tmp, "storyboard_sheets", "scene_02_sheet_01.png"
                        ),
                        "status": "pending",
                    },
                },
            }
            specs_path = os.path.join(tmp, "generation_specs.json")
            with open(specs_path, "w", encoding="utf-8") as f:
                json.dump(specs, f)

            ctx = _Ctx({"output_dir": tmp, "style_id": "reel_v2"})

            with patch(
                "scripts.nodes.storyboard_nodes.generate_grok_edit",
                side_effect=fake_edit,
            ), patch(
                "scripts.nodes.storyboard_nodes.config.get_storyboard_image_provider",
                return_value="replicate",
            ), patch(
                "scripts.nodes._shot_image_gen.asyncio.to_thread",
                side_effect=_immediate_to_thread,
            ), patch(
                "scripts.nodes._shot_image_gen.asyncio.sleep",
                return_value=None,
            ), patch(
                "scripts.nodes.storyboard_nodes._url_reachable",
                return_value=True,
            ):
                await storyboard_sheet_generator(ctx)

            self.assertEqual(
                edit_calls["ids"], ["scene_01_sheet_01", "scene_02_sheet_01"]
            )
            with open(specs_path, encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(
                saved["storyboard_sheets"]["scene_01_sheet_01"]["status"],
                "failed",
            )
            self.assertEqual(
                saved["storyboard_sheets"]["scene_02_sheet_01"]["status"],
                "completed",
            )


if __name__ == "__main__":
    unittest.main()
