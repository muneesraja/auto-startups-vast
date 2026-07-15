import unittest

from tools.workflow_builder import snap_duration_seconds, snap_ltx_duration


class TestFrameSnap(unittest.TestCase):
    def test_snap_duration_near_requested(self):
        self.assertEqual(snap_duration_seconds(8, fps=25), 8)
        self.assertIn(snap_duration_seconds(4, fps=25), (4, 5))

    def test_snap_minimum_one_second(self):
        self.assertGreaterEqual(snap_duration_seconds(1, fps=25), 1)

    def test_snap_sixteen_second_cap(self):
        self.assertEqual(snap_duration_seconds(16, fps=25), 16)

    def test_snap_ltx_duration_primary(self):
        self.assertEqual(snap_ltx_duration(8), 8)
        self.assertEqual(snap_ltx_duration(6), 6)
        self.assertEqual(snap_ltx_duration(10), 10)
        self.assertEqual(snap_ltx_duration(7), 8)  # tie distance → prefer higher primary
        self.assertEqual(snap_ltx_duration(9), 10)
        self.assertEqual(snap_ltx_duration(1), 6)
        self.assertEqual(snap_ltx_duration(20), 10)

    def test_snap_ltx_duration_optional_band(self):
        self.assertEqual(snap_ltx_duration(3, prefer_primary=False), 3)
        self.assertEqual(snap_ltx_duration(15, prefer_primary=False), 15)
        self.assertEqual(snap_ltx_duration(2, prefer_primary=False), 3)
        self.assertEqual(snap_ltx_duration(16, prefer_primary=False), 15)


if __name__ == "__main__":
    unittest.main()
