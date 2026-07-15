import unittest
from unittest.mock import MagicMock, patch

from tools.grok_fal import (
    fal_aspect_ratio_from_size,
    fal_image_size_from_size,
    fal_resolution_from_size,
)
from tools.grok_tools import generate_grok_edit, generate_grok_t2i


class TestFalRevisedPrompt(unittest.TestCase):
    @patch("tools.grok_image_common.httpx.get")
    @patch("tools.grok_fal.fal_client.subscribe")
    def test_gpt_image_t2i_uses_medium_and_pixel_size(self, mock_subscribe, mock_get):
        mock_subscribe.return_value = {
            "images": [{"url": "https://example.com/img.png"}],
            "revised_prompt": "rewritten",
        }
        mock_get.return_value = MagicMock(
            raise_for_status=MagicMock(),
            content=b"pngbytes",
        )
        with patch.dict(
            "os.environ",
            {
                "PROVIDER": "fal",
                "FAL_KEY": "test-key",
                "GROK_REPLICATE_MODEL": "openai/gpt-image-2",
            },
        ):
            result = generate_grok_t2i(
                "a cat",
                "/tmp/out.png",
                size="1152x2048",
                quality="medium",
            )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["revised_prompt"], "rewritten")
        self.assertEqual(mock_subscribe.call_args.args[0], "openai/gpt-image-2")
        payload = mock_subscribe.call_args.kwargs["arguments"]
        self.assertEqual(payload["quality"], "medium")
        self.assertEqual(payload["image_size"], {"width": 1152, "height": 2048})


class TestFalStoryboardAspect(unittest.TestCase):
    def test_size_1152x2048_maps_to_pixel_object(self):
        self.assertEqual(
            fal_image_size_from_size("1152x2048"),
            {"width": 1152, "height": 2048},
        )
        self.assertEqual(fal_aspect_ratio_from_size("1152x2048"), "9:16")
        self.assertEqual(fal_resolution_from_size("1152x2048"), "2k")

    def test_size_2048x1152_maps_to_landscape(self):
        self.assertEqual(
            fal_image_size_from_size("2048x1152"),
            {"width": 2048, "height": 1152},
        )
        self.assertEqual(fal_aspect_ratio_from_size("2048x1152"), "16:9")

    @patch("tools.grok_image_common.httpx.get")
    @patch("tools.grok_fal.fal_client.subscribe")
    def test_edit_uses_gpt_image_edit_medium_portrait(self, mock_subscribe, mock_get):
        mock_subscribe.return_value = {
            "images": [{"url": "https://example.com/img.png"}],
        }
        mock_get.return_value = MagicMock(
            raise_for_status=MagicMock(),
            content=b"pngbytes",
        )
        with patch.dict(
            "os.environ",
            {
                "PROVIDER": "fal",
                "FAL_KEY": "test-key",
                "GROK_REPLICATE_MODEL": "openai/gpt-image-2",
                "IMAGE_REF_LIMIT": "5",
            },
        ):
            result = generate_grok_edit(
                "5x2 portrait storyboard",
                ["https://example.com/loc.png", "https://example.com/char.png"],
                "/tmp/sheet.png",
                size="1152x2048",
                quality="medium",
                text_policy="no_text",
            )
        self.assertEqual(result["status"], "success")
        self.assertEqual(mock_subscribe.call_args.args[0], "openai/gpt-image-2/edit")
        payload = mock_subscribe.call_args.kwargs["arguments"]
        self.assertEqual(payload["quality"], "medium")
        self.assertEqual(payload["image_size"], {"width": 1152, "height": 2048})
        self.assertEqual(len(payload["image_urls"]), 2)


if __name__ == "__main__":
    unittest.main()
