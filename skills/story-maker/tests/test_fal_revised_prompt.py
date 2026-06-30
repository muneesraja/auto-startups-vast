import unittest
from unittest.mock import MagicMock, patch

from tools.fal_tools import generate_grok_t2i


class TestFalRevisedPrompt(unittest.TestCase):
    @patch("tools.fal_tools.httpx.get")
    @patch("tools.fal_tools.fal_client.subscribe")
    def test_captures_revised_prompt(self, mock_subscribe, mock_get):
        mock_subscribe.return_value = {
            "images": [{"url": "https://example.com/img.png"}],
            "revised_prompt": "rewritten by grok",
        }
        mock_get.return_value = MagicMock(
            raise_for_status=MagicMock(),
            content=b"pngbytes",
        )
        with patch.dict("os.environ", {"FAL_KEY": "test-key"}):
            result = generate_grok_t2i("a cat", "/tmp/out.png")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["revised_prompt"], "rewritten by grok")


if __name__ == "__main__":
    unittest.main()
