import unittest

from tools.fal_tools import NO_TEXT_CLAUSE, _ensure_no_text


class TestFalToolsNoText(unittest.TestCase):
    def test_appends_clause_when_missing(self):
        result = _ensure_no_text("A forest clearing at dawn.")
        self.assertIn("no subtitles", result.lower())
        self.assertTrue(result.endswith(NO_TEXT_CLAUSE.strip()) or NO_TEXT_CLAUSE.strip() in result)

    def test_idempotent_when_clause_present(self):
        prompt = "Forest scene. No text, no captions."
        self.assertEqual(_ensure_no_text(prompt), prompt)


if __name__ == "__main__":
    unittest.main()
