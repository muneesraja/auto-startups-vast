import os
import sys
import unittest

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

from profiles import get_profile  # noqa: E402
from scripts.nodes.character_sheet_builder import (  # noqa: E402
    build_character_sheet_prompt,
    build_character_sheet_specs,
    resolve_character_sheet_fields,
)


class TestCharacterSheetBuilder(unittest.TestCase):
    def test_naila_canon_includes_research_sections(self):
        fields = resolve_character_sheet_fields(
            {
                "id": "naila",
                "name": "Naila",
                "appearance": "5-year-old girl in a green dress",
            }
        )
        self.assertEqual(fields["species"], "Human")
        self.assertIn("leaf embroidery", " ".join(fields["clothing_accessories"]).lower())
        self.assertEqual(len(fields["action_poses"]), 10)
        self.assertEqual(len(fields["detail_closeups"]), 8)
        self.assertIn("Azhagi", fields["action_poses"][5])

    def test_neju_canon_is_parrot_not_elephant(self):
        fields = resolve_character_sheet_fields(
            {
                "id": "neju",
                "name": "Neju",
                "appearance": "small helper bird",
            }
        )
        self.assertEqual(fields["species"], "Green Parrot")
        self.assertIn("orange beak", " ".join(fields["distinctive_features"]).lower())

    def test_build_character_sheet_prompt_has_all_sections(self):
        prompt = build_character_sheet_prompt(
            {"id": "naila", "name": "Naila", "appearance": "forest girl"},
            sheet_number=1,
            render_style="Pixar CGI test style",
        )
        self.assertIn("CHARACTER SHEET 01", prompt)
        self.assertIn("1. CHARACTER PROFILE", prompt)
        self.assertIn("2. TURNAROUND VIEWS", prompt)
        self.assertIn("3. EXPRESSION SHEET", prompt)
        self.assertIn("4. SCALE REFERENCE", prompt)
        self.assertIn("5. ACTION POSES", prompt)
        self.assertIn("6. DETAIL CLOSE-UPS", prompt)
        self.assertIn("Front View", prompt)
        self.assertIn("Determined", prompt)
        self.assertIn("Pixar CGI test style", prompt)
        self.assertIn("model-sheet typography", prompt.lower())

    def test_build_character_sheet_specs_keys_by_character_id(self):
        specs = build_character_sheet_specs(
            [
                {"id": "naila", "name": "Naila", "appearance": "girl"},
                {"id": "neju", "name": "Neju", "appearance": "parrot"},
            ],
            render_style="Pixar CGI",
        )
        self.assertIn("naila", specs)
        self.assertIn("neju", specs)
        self.assertIn("TURNAROUND VIEWS", specs["naila"]["sheet_prompt"])

    def test_reel_v2_profile_uses_template_mode(self):
        profile = get_profile("reel_v2")
        self.assertEqual(profile.character_sheet_mode, "template")
        self.assertEqual(profile.storyboard_sheet_mode, "template")


if __name__ == "__main__":
    unittest.main()
