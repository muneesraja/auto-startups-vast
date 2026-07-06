import unittest
from unittest.mock import patch

import config


class TestImageRefLimit(unittest.TestCase):
    def test_fal_default(self):
        with patch.dict(
            "os.environ",
            {"PROVIDER": "fal", "FAL_KEY": "k", "IMAGE_REF_LIMIT": ""},
            clear=False,
        ):
            self.assertEqual(config.get_image_ref_limit(), config.FAL_GROK_REF_LIMIT)

    def test_replicate_gpt_image_default(self):
        with patch.dict(
            "os.environ",
            {
                "PROVIDER": "replicate",
                "REPLICATE_API_TOKEN": "r8_x",
                "GROK_REPLICATE_MODEL": "openai/gpt-image-2",
            },
            clear=False,
        ):
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
            },
            clear=False,
        ):
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
            },
            clear=False,
        ):
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


if __name__ == "__main__":
    unittest.main()
