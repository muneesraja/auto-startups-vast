import unittest
from unittest.mock import patch

import config
from tools import grok_tools


class TestGetImageProvider(unittest.TestCase):
    def test_defaults_to_fal(self):
        with patch.dict(
            "os.environ",
            {"PROVIDER": "fal", "FAL_KEY": "test"},
            clear=False,
        ):
            self.assertEqual(config.get_image_provider(), "fal")

    def test_replicate_requires_token(self):
        env = {
            "PROVIDER": "replicate",
            "REPLICATE_API_TOKEN": "",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch.object(config, "REPLICATE_API_TOKEN", None):
                with self.assertRaises(ValueError) as ctx:
                    config.get_image_provider()
                self.assertIn("REPLICATE_API_TOKEN", str(ctx.exception))

    def test_invalid_provider_raises(self):
        with patch.dict("os.environ", {"PROVIDER": "banana", "FAL_KEY": "x"}):
            with self.assertRaises(ValueError) as ctx:
                config.get_image_provider()
            self.assertIn("Invalid PROVIDER", str(ctx.exception))


class TestGrokProviderDispatch(unittest.TestCase):
    @patch("tools.grok_fal.generate_grok_t2i")
    def test_dispatch_fal(self, mock_fal_t2i):
        mock_fal_t2i.return_value = {"status": "success"}
        with patch.dict("os.environ", {"PROVIDER": "fal", "FAL_KEY": "k"}):
            grok_tools.generate_grok_t2i("p", "/tmp/x.png")
        mock_fal_t2i.assert_called_once_with("p", "/tmp/x.png", resolution=None)

    @patch("tools.grok_replicate.generate_grok_t2i")
    def test_dispatch_replicate(self, mock_rep_t2i):
        mock_rep_t2i.return_value = {"status": "success"}
        with patch.dict(
            "os.environ",
            {"PROVIDER": "replicate", "REPLICATE_API_TOKEN": "r8_xxx"},
        ):
            grok_tools.generate_grok_t2i("p", "/tmp/x.png")
        mock_rep_t2i.assert_called_once_with("p", "/tmp/x.png", resolution=None)


if __name__ == "__main__":
    unittest.main()
