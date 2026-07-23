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
        self.assertIn("4 rows × 2 columns", prompt)
        self.assertIn("8:9", prompt)
        self.assertIn("NOT 9:16", prompt)
        self.assertIn("16:9", prompt)
        self.assertIn("Maintain perfect character consistency", prompt)
        self.assertIn("Storyboard Sheet 01 includes these shots", prompt)
        self.assertIn("Panel-by-panel direction", prompt)
        self.assertIn("Extreme Wide Establishing", prompt)
        self.assertIn("Pixar CGI test style", prompt)
        self.assertIn("NEGATIVE PROMPT", prompt)
        self.assertIn("text-free", prompt.lower())
        self.assertIn("no typography", prompt.lower())
        self.assertIn("Motion spine", prompt)
        self.assertIn("Keyframe paint rules", prompt)
        self.assertIn("FLF", prompt)
        self.assertIn("start frame", prompt.lower())
        self.assertIn("end frame", prompt.lower())
        self.assertIn("Preferred FLF role: start", prompt)
        # On-page production chrome should not be required
        self.assertNotIn('production header ("STORYBOARD SHEET', prompt)

    def test_motion_spine_injected_into_sheet_prompt(self):
        scene = {
            "scene_id": "scene_01",
            "title": "Walk",
            "environment": "path",
            "time_of_day": "day",
            "lighting": "sun",
            "staging": "L→R path",
            "director_motion_spine": "P01→P02: Father walks with Naila; Azhagi trots ahead.",
        }
        shots = [
            {
                "shot_id": "scene_01_shot_01",
                "camera_intent": "Wide",
                "description": "Family on path",
                "motion_intent": "Walk toward medium panel",
                "director_bridge_to_next": "Morph: continue. Track L→R.",
                "duration_seconds": 2,
            },
            {
                "shot_id": "scene_01_shot_02",
                "camera_intent": "Medium",
                "description": "Closer walk",
                "duration_seconds": 2,
            },
        ]
        prompt = build_storyboard_sheet_prompt(
            scene,
            shots,
            sheet_number=1,
            render_style="Pixar",
        )
        self.assertIn("Father walks with Naila", prompt)
        self.assertIn("Outgoing bridge → next panel:", prompt)
        self.assertIn("Incoming bridge", prompt)
        self.assertIn("Motion (toward next panel):", prompt)
        self.assertIn("Preferred FLF role: start (left cell of this row pair)", prompt)
        self.assertIn("Preferred FLF role: end (right cell of this row pair)", prompt)
        self.assertIn("paint each row as an FLF start→end pair", prompt)

    def test_panel_lines_default_flf_row_roles(self):
        lines = build_panel_lines(
            [
                {"camera_intent": "Wide", "description": "Establish"},
                {"camera_intent": "Medium", "description": "Closer"},
                {
                    "camera_intent": "Close",
                    "description": "Bridge",
                    "director_guide_role": "middle",
                },
                {"camera_intent": "Wide", "description": "Land"},
            ]
        )
        self.assertIn("Preferred FLF role: start (left cell of this row pair)", lines)
        self.assertIn("Preferred FLF role: end (right cell of this row pair)", lines)
        self.assertIn("Director guide role: middle", lines)
        # Authored role replaces the default column hint for that panel.
        middle_block = lines.split("\n\n")[2]
        self.assertIn("Director guide role: middle", middle_block)
        self.assertNotIn("Preferred FLF role:", middle_block)

    def test_grid_layout_instruction_is_album_4x2(self):
        full = build_grid_layout_instruction(8, 8)
        self.assertIn("4 rows × 2 columns", full)
        self.assertIn("8:9", full)
        self.assertIn("NOT 9:16", full)
        self.assertIn("16:9", full)
        self.assertNotIn("2 rows × 4 columns", full)
        partial = build_grid_layout_instruction(3, 8)
        self.assertIn("2 rows × 2 columns", partial)
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
        # Grid is sheet-local from list offset, not from start_index.
        self.assertIn("grid row 1 col 1", lines)
        self.assertIn("Preferred FLF role: start (left cell of this row pair)", lines)

    def test_panel_lines_grid_is_sheet_local_even_with_high_start_index(self):
        shots = [
            {"camera_intent": "Wide", "description": f"Beat {i}", "duration_seconds": 1}
            for i in range(8)
        ]
        # Legacy callers may pass a story-wide ordinal; grid must stay 4×2 on-page.
        lines = build_panel_lines(shots, start_index=9)
        self.assertIn("Panel 9 | grid row 1 col 1", lines)
        self.assertIn("Panel 10 | grid row 1 col 2", lines)
        self.assertIn("Panel 16 | grid row 4 col 2", lines)
        self.assertNotIn("grid row 5", lines)
        self.assertNotIn("grid row 8", lines)

    def test_sheet_prompt_ignores_global_shot_offset_for_grid(self):
        scene = {
            "scene_id": "scene_02",
            "title": "Path",
            "environment": "path",
            "time_of_day": "day",
            "lighting": "sun",
            "staging": "L→R",
        }
        shots = [
            {
                "shot_id": f"scene_02_shot_{i:02d}",
                "camera_intent": "Wide",
                "description": f"Travel beat {i}",
                "duration_seconds": 1,
            }
            for i in range(1, 9)
        ]
        prompt = build_storyboard_sheet_prompt(
            scene,
            shots,
            sheet_number=1,
            render_style="Pixar",
            global_shot_offset=8,  # must not force row 5+
        )
        self.assertIn("Panel 1 | grid row 1 col 1", prompt)
        self.assertIn("Panel 8 | grid row 4 col 2", prompt)
        self.assertNotIn("grid row 5", prompt)
        self.assertIn("1. CAM:", prompt)
        self.assertNotIn("9. CAM:", prompt)
        self.assertIn("never 5 rows", prompt.lower())

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
            panels_per_sheet=8,
            render_style="Pixar",
        )
        self.assertIn("no blank", prompt.lower())
        self.assertNotIn("keep unused grid slots visually empty", prompt.lower())

    def test_reel_v2_profile_uses_storyboard_template_mode(self):
        profile = get_profile("reel_v2")
        self.assertEqual(profile.storyboard_sheet_mode, "template")


if __name__ == "__main__":
    unittest.main()
