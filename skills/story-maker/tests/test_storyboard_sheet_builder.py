import os
import sys
import unittest

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

from profiles import get_profile  # noqa: E402
from scripts.nodes.storyboard_sheet_builder import (  # noqa: E402
    build_grid_layout_instruction,
    build_panel_lines,
    build_shot_listing,
    build_storyboard_sheet_prompt,
    resolve_character_consistency,
    resolve_environment_block,
)


class TestStoryboardSheetBuilder(unittest.TestCase):
    def test_shot_listing_uses_cam_and_action(self):
        shots = [
            {
                "camera_intent": "Wide Shot",
                "description": "Visual: Naila walks with Azhagi.",
                "motion_intent": "gentle walk",
            }
        ]
        listing = build_shot_listing(shots)
        self.assertIn("1. CAM: Wide Shot", listing)
        self.assertIn("Naila walks with Azhagi", listing)

    def test_character_consistency_uses_research_canon(self):
        block = resolve_character_consistency(["naila", "neju"])
        self.assertIn("forest-green dress", block)
        self.assertIn("orange beak", block)

    def test_build_storyboard_sheet_prompt_has_research_sections(self):
        scene = {
            "scene_id": "scene_01",
            "title": "THE SANCTUARY HEART",
            "environment": "forest sanctuary",
            "time_of_day": "morning",
            "lighting": "warm golden light",
            "staging": "swing center frame",
        }
        shots = [
            {
                "shot_id": "scene_01_shot_01",
                "camera_intent": "Extreme Wide Establishing",
                "description": "Dense green forest sanctuary.",
                "characters_present": ["naila", "azhagi", "neju"],
                "duration_seconds": 1,
            }
        ]
        prompt = build_storyboard_sheet_prompt(
            scene,
            shots,
            sheet_number=1,
            render_style="Pixar CGI test style",
        )
        self.assertIn("photo album", prompt.lower())
        self.assertIn("THE SANCTUARY HEART", prompt)
        self.assertIn("5 rows × 2 columns", prompt)
        self.assertIn("9:16", prompt)
        self.assertIn("16:9", prompt)
        self.assertIn("Maintain perfect character consistency", prompt)
        self.assertIn("Storyboard Sheet 01 includes these shots", prompt)
        self.assertIn("Panel-by-panel direction", prompt)
        self.assertIn("Extreme Wide Establishing", prompt)
        self.assertIn("Pixar CGI test style", prompt)
        self.assertIn("NEGATIVE PROMPT", prompt)
        self.assertIn("text-free", prompt.lower())
        self.assertIn("no typography", prompt.lower())
        # On-page production chrome should not be required
        self.assertNotIn('production header ("STORYBOARD SHEET', prompt)

    def test_grid_layout_instruction_is_album_5x2(self):
        full = build_grid_layout_instruction(10, 10)
        self.assertIn("5 rows × 2 columns", full)
        self.assertIn("9:16", full)
        self.assertIn("16:9", full)
        self.assertNotIn("2 rows × 5 columns", full)
        partial = build_grid_layout_instruction(3, 10)
        self.assertIn("5 rows × 2 columns", partial)
        self.assertIn("no blank", partial.lower())

    def test_environment_block_includes_canon(self):
        block = resolve_environment_block({"environment": "clearing with swing"})
        self.assertIn("lush forest sanctuary", block.lower())
        self.assertIn("Wooden treehouse", block)

    def test_panel_lines_include_board_beat(self):
        lines = build_panel_lines(
            [{"camera_intent": "Close Up", "description": "Naila sleeps", "duration_seconds": 2}],
            start_index=3,
        )
        self.assertIn("Panel 3", lines)
        self.assertIn("board beat ~2s", lines)
        self.assertIn("grid row", lines)

    def test_build_storyboard_sheet_prompt_forbids_blank_cells(self):
        scene = {
            "scene_id": "scene_01",
            "title": "TEST",
            "environment": "forest",
            "time_of_day": "morning",
            "lighting": "warm",
            "staging": "center",
        }
        shots = [{"camera_intent": "Wide", "description": "Beat one"}]
        prompt = build_storyboard_sheet_prompt(
            scene,
            shots,
            sheet_number=1,
            panels_per_sheet=10,
            render_style="Pixar",
        )
        self.assertIn("no blank", prompt.lower())
        self.assertNotIn("keep unused grid slots visually empty", prompt.lower())

    def test_reel_v2_profile_uses_storyboard_template_mode(self):
        profile = get_profile("reel_v2")
        self.assertEqual(profile.storyboard_sheet_mode, "template")


if __name__ == "__main__":
    unittest.main()
