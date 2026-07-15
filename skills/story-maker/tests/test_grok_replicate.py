import unittest
from unittest.mock import MagicMock, patch

from tools.grok_replicate import generate_grok_edit, generate_grok_t2i


class TestGrokReplicate(unittest.TestCase):
    @patch("tools.grok_image_common.httpx.get")
    @patch("tools.grok_replicate.replicate.Client")
    def test_gpt_image_t2i_input_shape(self, mock_client_cls, mock_get):
        mock_run = mock_client_cls.return_value.run
        mock_run.return_value = ["https://replicate.delivery/out.png"]
        mock_get.return_value = MagicMock(
            raise_for_status=MagicMock(),
            content=b"pngbytes",
        )
        with patch.dict(
            "os.environ",
            {
                "REPLICATE_API_TOKEN": "r8_test",
                "GROK_REPLICATE_MODEL": "openai/gpt-image-2",
                "REPLICATE_IMAGE_QUALITY": "low",
            },
        ):
            with patch("tools.grok_replicate.config.GROK_REPLICATE_MODEL", "openai/gpt-image-2"):
                result = generate_grok_t2i("forest clearing", "/tmp/rep.png")
        self.assertEqual(result["status"], "success")
        inp = mock_run.call_args[1]["input"]
        self.assertEqual(inp["aspect_ratio"], "2048x1152")
        self.assertEqual(inp["quality"], "low")
        self.assertEqual(inp["output_format"], "png")
        self.assertNotIn("input_images", inp)

    @patch("tools.grok_image_common.httpx.get")
    @patch("tools.grok_replicate.replicate.Client")
    def test_gpt_image_edit_multi_ref(self, mock_client_cls, mock_get):
        mock_run = mock_client_cls.return_value.run
        mock_run.return_value = ["https://replicate.delivery/edit.png"]
        mock_get.return_value = MagicMock(
            raise_for_status=MagicMock(),
            content=b"pngbytes",
        )
        refs = ["https://example.com/a.png", "https://example.com/b.png"]
        with patch.dict(
            "os.environ",
            {
                "REPLICATE_API_TOKEN": "r8_test",
                "GROK_REPLICATE_MODEL": "openai/gpt-image-2",
            },
        ):
            with patch("tools.grok_replicate.config.GROK_REPLICATE_MODEL", "openai/gpt-image-2"):
                result = generate_grok_edit("scene", refs, "/tmp/edit.png")
        self.assertEqual(result["status"], "success")
        inp = mock_run.call_args[1]["input"]
        self.assertEqual(inp["input_images"], refs)

    @patch("tools.grok_image_common.httpx.get")
    @patch("tools.grok_replicate.replicate.Client")
    def test_gpt_image_edit_passes_thirteen_refs(self, mock_client_cls, mock_get):
        mock_run = mock_client_cls.return_value.run
        mock_run.return_value = ["https://replicate.delivery/edit13.png"]
        mock_get.return_value = MagicMock(
            raise_for_status=MagicMock(),
            content=b"pngbytes",
        )
        refs = [f"https://example.com/r{i}.png" for i in range(13)]
        with patch.dict(
            "os.environ",
            {
                "REPLICATE_API_TOKEN": "r8_test",
                "GROK_REPLICATE_MODEL": "openai/gpt-image-2",
                "PROVIDER": "replicate",
            },
        ):
            with patch("tools.grok_replicate.config.GROK_REPLICATE_MODEL", "openai/gpt-image-2"):
                result = generate_grok_edit("scene", refs, "/tmp/edit13.png")
        self.assertEqual(result["status"], "success")
        inp = mock_run.call_args[1]["input"]
        self.assertEqual(len(inp["input_images"]), 13)

    @patch("tools.grok_image_common.httpx.get")
    @patch("tools.grok_replicate.replicate.Client")
    def test_gpt_image_edit_truncates_beyond_thirteen_refs(self, mock_client_cls, mock_get):
        mock_run = mock_client_cls.return_value.run
        mock_run.return_value = ["https://replicate.delivery/edit13c.png"]
        mock_get.return_value = MagicMock(
            raise_for_status=MagicMock(),
            content=b"pngbytes",
        )
        refs = [f"https://example.com/r{i}.png" for i in range(15)]
        with patch.dict(
            "os.environ",
            {
                "REPLICATE_API_TOKEN": "r8_test",
                "GROK_REPLICATE_MODEL": "openai/gpt-image-2",
                "PROVIDER": "replicate",
            },
        ):
            with patch("tools.grok_replicate.config.GROK_REPLICATE_MODEL", "openai/gpt-image-2"):
                result = generate_grok_edit("scene", refs, "/tmp/edit13c.png")
        self.assertEqual(result["status"], "success")
        inp = mock_run.call_args[1]["input"]
        self.assertEqual(len(inp["input_images"]), 13)

    @patch("tools.grok_image_common.httpx.get")
    @patch("tools.grok_replicate.replicate.Client")
    def test_gpt_image_t2i_panoramic_size(self, mock_client_cls, mock_get):
        mock_run = mock_client_cls.return_value.run
        mock_run.return_value = ["https://replicate.delivery/bg.png"]
        mock_get.return_value = MagicMock(
            raise_for_status=MagicMock(),
            content=b"pngbytes",
        )
        with patch.dict(
            "os.environ",
            {
                "REPLICATE_API_TOKEN": "r8_test",
                "GROK_REPLICATE_MODEL": "openai/gpt-image-2",
                "REPLICATE_IMAGE_QUALITY": "low",
            },
        ):
            with patch("tools.grok_replicate.config.GROK_REPLICATE_MODEL", "openai/gpt-image-2"):
                result = generate_grok_t2i(
                    "wide classroom panorama",
                    "/tmp/bg.png",
                    size="2048x1024",
                )
        self.assertEqual(result["status"], "success")
        inp = mock_run.call_args[1]["input"]
        self.assertEqual(inp["aspect_ratio"], "2048x1152")
        self.assertNotIn("size", inp)

    @patch("tools.grok_image_common.httpx.get")
    @patch("tools.grok_replicate.replicate.Client")
    def test_seedream_edit_uses_image_input(self, mock_client_cls, mock_get):
        mock_run = mock_client_cls.return_value.run
        mock_run.return_value = ["https://replicate.delivery/edit2.png"]
        mock_get.return_value = MagicMock(
            raise_for_status=MagicMock(),
            content=b"pngbytes",
        )
        with patch.dict(
            "os.environ",
            {
                "REPLICATE_API_TOKEN": "r8_test",
                "GROK_REPLICATE_MODEL": "bytedance/seedream-4",
            },
        ):
            with patch("tools.grok_replicate.config.GROK_REPLICATE_MODEL", "bytedance/seedream-4"):
                result = generate_grok_edit(
                    "hero",
                    ["https://example.com/ref.png"],
                    "/tmp/edit2.png",
                )
        self.assertEqual(result["status"], "success")
        inp = mock_run.call_args[1]["input"]
        self.assertEqual(inp["image_input"], ["https://example.com/ref.png"])

    @patch("tools.grok_image_common.httpx.get")
    @patch("tools.grok_replicate.replicate.Client")
    def test_gpt_image_edit_accepts_aspect_ratio(self, mock_client_cls, mock_get):
        mock_run = mock_client_cls.return_value.run
        mock_run.return_value = ["https://replicate.delivery/edit-size.png"]
        mock_get.return_value = MagicMock(
            raise_for_status=MagicMock(),
            content=b"pngbytes",
        )
        with patch.dict(
            "os.environ",
            {
                "REPLICATE_API_TOKEN": "r8_test",
                "GROK_REPLICATE_MODEL": "openai/gpt-image-2",
            },
        ):
            with patch("tools.grok_replicate.config.GROK_REPLICATE_MODEL", "openai/gpt-image-2"):
                result = generate_grok_edit(
                    "storyboard sheet",
                    ["https://example.com/ref.png"],
                    "/tmp/edit-size.png",
                    size="16:9",
                )
        self.assertEqual(result["status"], "success")
        inp = mock_run.call_args[1]["input"]
        # Ratio aliases bump to Replicate 2K pixel enums
        self.assertEqual(inp["aspect_ratio"], "2048x1152")
        self.assertNotIn("size", inp)

    @patch("tools.grok_image_common.httpx.get")
    @patch("tools.grok_replicate.replicate.Client")
    def test_gpt_image_passes_pixel_enum_through(self, mock_client_cls, mock_get):
        mock_run = mock_client_cls.return_value.run
        mock_run.return_value = ["https://replicate.delivery/edit-legacy.png"]
        mock_get.return_value = MagicMock(
            raise_for_status=MagicMock(),
            content=b"pngbytes",
        )
        with patch.dict(
            "os.environ",
            {
                "REPLICATE_API_TOKEN": "r8_test",
                "GROK_REPLICATE_MODEL": "openai/gpt-image-2",
            },
        ):
            with patch("tools.grok_replicate.config.GROK_REPLICATE_MODEL", "openai/gpt-image-2"):
                result = generate_grok_edit(
                    "storyboard sheet",
                    ["https://example.com/ref.png"],
                    "/tmp/edit-legacy.png",
                    size="2048x1152",
                )
        self.assertEqual(result["status"], "success")
        inp = mock_run.call_args[1]["input"]
        self.assertEqual(inp["aspect_ratio"], "2048x1152")
        self.assertNotIn("size", inp)

if __name__ == "__main__":
    unittest.main()
