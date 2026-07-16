import os
import unittest
from unittest.mock import patch

import config


class TestImageRefLimit(unittest.TestCase):
    def test_fal_gpt_image_default(self):
        with patch.dict(
            "os.environ",
            {
                "PROVIDER": "fal",
                "FAL_KEY": "k",
                "GROK_REPLICATE_MODEL": "openai/gpt-image-2",
                "IMAGE_REF_LIMIT": "",
            },
            clear=False,
        ):
            with patch.object(config, "GROK_REPLICATE_MODEL", "openai/gpt-image-2"):
                self.assertEqual(
                    config.get_image_ref_limit(), config.REPLICATE_GPT_IMAGE_REF_LIMIT
                )

    def test_fal_legacy_grok_default(self):
        with patch.dict(
            "os.environ",
            {
                "PROVIDER": "fal",
                "FAL_KEY": "k",
                "GROK_REPLICATE_MODEL": "xai/grok-imagine-image",
                "IMAGE_REF_LIMIT": "",
            },
            clear=False,
        ):
            with patch.object(config, "GROK_REPLICATE_MODEL", "xai/grok-imagine-image"):
                self.assertEqual(
                    config.get_image_ref_limit(), config.FAL_GROK_REF_LIMIT
                )

    def test_replicate_gpt_image_default(self):
        with patch.dict(
            "os.environ",
            {
                "PROVIDER": "replicate",
                "REPLICATE_API_TOKEN": "r8_x",
                "GROK_REPLICATE_MODEL": "openai/gpt-image-2",
                "IMAGE_REF_LIMIT": "",
            },
            clear=False,
        ):
            with patch.object(config, "GROK_REPLICATE_MODEL", "openai/gpt-image-2"):
                self.assertEqual(
                    config.get_image_ref_limit(), config.REPLICATE_GPT_IMAGE_REF_LIMIT
                )

    def test_replicate_seedream_default(self):
        with patch.dict(
            "os.environ",
            {
                "PROVIDER": "replicate",
                "REPLICATE_API_TOKEN": "r8_x",
                "GROK_REPLICATE_MODEL": "bytedance/seedream-4",
                "IMAGE_REF_LIMIT": "",
            },
            clear=False,
        ):
            with patch.object(config, "GROK_REPLICATE_MODEL", "bytedance/seedream-4"):
                self.assertEqual(
                    config.get_image_ref_limit(), config.REPLICATE_SEEDREAM_REF_LIMIT
                )

    def test_replicate_legacy_grok_default(self):
        with patch.dict(
            "os.environ",
            {
                "PROVIDER": "replicate",
                "REPLICATE_API_TOKEN": "r8_x",
                "GROK_REPLICATE_MODEL": "xai/grok-imagine-image",
                "IMAGE_REF_LIMIT": "",
            },
            clear=False,
        ):
            with patch.object(config, "GROK_REPLICATE_MODEL", "xai/grok-imagine-image"):
                self.assertEqual(
                    config.get_image_ref_limit(), config.REPLICATE_LEGACY_GROK_REF_LIMIT
                )

    def test_env_override(self):
        with patch.dict(
            "os.environ",
            {
                "PROVIDER": "replicate",
                "REPLICATE_API_TOKEN": "r8_x",
                "IMAGE_REF_LIMIT": "7",
            },
            clear=False,
        ):
            self.assertEqual(config.get_image_ref_limit(), 7)

    def test_storyboard_provider_defaults_to_fal(self):
        with patch.dict(
            "os.environ",
            {
                "PROVIDER": "replicate",
                "REPLICATE_API_TOKEN": "r8_x",
                "FAL_KEY": "fal_x",
                "STORYBOARD_IMAGE_PROVIDER": "",
            },
            clear=False,
        ):
            self.assertEqual(config.get_storyboard_image_provider(), "fal")
            self.assertEqual(config.get_image_provider(), "replicate")

    def test_storyboard_ref_limit_uses_fal_when_provider_arg(self):
        with patch.dict(
            "os.environ",
            {
                "PROVIDER": "replicate",
                "REPLICATE_API_TOKEN": "r8_x",
                "FAL_KEY": "fal_x",
                "GROK_REPLICATE_MODEL": "openai/gpt-image-2",
                "IMAGE_REF_LIMIT": "",
            },
            clear=False,
        ):
            with patch.object(config, "GROK_REPLICATE_MODEL", "openai/gpt-image-2"):
                self.assertEqual(
                    config.get_image_ref_limit("fal"),
                    config.REPLICATE_GPT_IMAGE_REF_LIMIT,
                )

    def test_panel_fallback_defaults_off(self):
        with patch.dict(
            "os.environ",
            {
                "PROVIDER": "replicate",
                "REPLICATE_API_TOKEN": "r8_x",
                "FAL_KEY": "fal_x",
                "PANEL_IMAGE_PROVIDER": "",
                "PANEL_IMAGE_FALLBACK_PROVIDER": "unset_sentinel",
            },
            clear=False,
        ):
            # Treat missing env as default: delete the sentinel key
            os.environ.pop("PANEL_IMAGE_FALLBACK_PROVIDER", None)
            self.assertEqual(config.get_panel_image_provider(), "replicate")
            self.assertIsNone(config.get_panel_image_fallback_provider())

    def test_panel_fallback_can_opt_in_to_fal(self):
        with patch.dict(
            "os.environ",
            {
                "PROVIDER": "replicate",
                "REPLICATE_API_TOKEN": "r8_x",
                "FAL_KEY": "fal_x",
                "PANEL_IMAGE_FALLBACK_PROVIDER": "fal",
            },
            clear=False,
        ):
            self.assertEqual(config.get_panel_image_fallback_provider(), "fal")

    def test_panel_fallback_can_be_disabled(self):
        with patch.dict(
            "os.environ",
            {
                "PROVIDER": "replicate",
                "REPLICATE_API_TOKEN": "r8_x",
                "FAL_KEY": "fal_x",
                "PANEL_IMAGE_FALLBACK_PROVIDER": "none",
            },
            clear=False,
        ):
            self.assertIsNone(config.get_panel_image_fallback_provider())

    def test_character_sheet_defaults_to_fal_when_keyed(self):
        with patch.dict(
            "os.environ",
            {
                "PROVIDER": "replicate",
                "REPLICATE_API_TOKEN": "r8_x",
                "FAL_KEY": "fal_x",
                "CHARACTER_SHEET_IMAGE_PROVIDER": "",
            },
            clear=False,
        ):
            os.environ.pop("CHARACTER_SHEET_IMAGE_PROVIDER", None)
            with patch.object(config, "FAL_KEY", "fal_x"):
                self.assertEqual(config.get_character_sheet_image_provider(), "fal")


if __name__ == "__main__":
    unittest.main()
