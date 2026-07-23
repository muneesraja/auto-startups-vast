import unittest

from scripts.nodes.sheet_map import (
    build_sheet_chunks,
    render_sheet_map_markdown,
    sheet_map_context_for_prompt,
)


_SAMPLE_PAPER = """# Scene Paper: Naila

## Scene 01: Sanctuary Heart
**Duration budget:** ~10s

### Panel 01
Wide forest

### Panel 02
Medium

### Panel 03
Close

### Panel 04
Wide

### Panel 05
Close

### Panel 06
Medium

### Panel 07
Wide

### Panel 08
Close

## Scene 02: Swing
**Duration budget:** ~10s

### Panel 01
Cry

### Panel 02
Comfort

### Panel 03
Hug

### Panel 04
Look

### Panel 05
Stand

### Panel 06
Walk

### Panel 07
Call

### Panel 08
Run
"""


class TestSheetMap(unittest.TestCase):
    def test_builds_one_sheet_per_eight_panels(self):
        chunks = build_sheet_chunks(_SAMPLE_PAPER, panels_per_sheet=8)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].panel_count, 8)
        self.assertEqual(chunks[0].duration_budget_seconds, 10)
        self.assertEqual(chunks[1].source_scene_label, "Scene 02")

    def test_splits_long_scene(self):
        paper = "## Scene 01: Long\n**Duration budget:** ~14s\n\n" + "\n\n".join(
            f"### Panel {i:02d}\nbeat" for i in range(1, 13)
        )
        chunks = build_sheet_chunks(paper, panels_per_sheet=8)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].panel_count, 8)
        self.assertEqual(chunks[1].panel_count, 4)
        self.assertEqual(chunks[1].part_index, 2)
        self.assertEqual(chunks[1].part_total, 2)

    def test_render_and_context(self):
        md = render_sheet_map_markdown(_SAMPLE_PAPER, panels_per_sheet=8)
        self.assertIn("Total sheets:** 2", md)
        ctx = sheet_map_context_for_prompt(_SAMPLE_PAPER, panels_per_sheet=8)
        self.assertIn("exactly 2 storyboard", ctx)
        self.assertIn("4×2", ctx)


if __name__ == "__main__":
    unittest.main()
