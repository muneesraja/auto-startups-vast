import os
import sys
import unittest

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

from profiles import get_profile, resolve_style


class TestStyleProfiles(unittest.TestCase):
    def test_get_profile(self):
        cinematic = get_profile("cinematic")
        reels = get_profile("reels")
        reel_v2 = get_profile("reel_v2")
        self.assertEqual(cinematic.default_target_seconds, 120)
        self.assertEqual(cinematic.min_shot_seconds, 4)
        self.assertEqual(reels.default_target_seconds, 30)
        self.assertEqual(reels.max_shot_seconds, 4)
        self.assertEqual(reel_v2.pipeline_mode, "storyboard")
        self.assertEqual(reel_v2.min_shot_seconds, 2)
        self.assertEqual(reel_v2.max_shot_seconds, 6)
        self.assertEqual(reel_v2.panels_per_sheet, 10)
        self.assertEqual(reel_v2.min_panels_per_sheet, 10)
        self.assertFalse(reel_v2.use_backgrounds)

    def test_resolve_style_precedence(self):
        self.assertEqual(resolve_style("reels", "cinematic").id, "reels")
        self.assertEqual(resolve_style(None, "reels").id, "reels")
        self.assertEqual(resolve_style(None, None).id, "cinematic")

if __name__ == "__main__":
    unittest.main()
