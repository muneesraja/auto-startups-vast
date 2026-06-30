import unittest

from tools.workflow_builder import snap_duration_seconds


class TestFrameSnap(unittest.TestCase):
    def test_snap_duration_near_requested(self):
        self.assertEqual(snap_duration_seconds(8, fps=25), 8)
        self.assertIn(snap_duration_seconds(4, fps=25), (4, 5))

    def test_snap_minimum_one_second(self):
        self.assertGreaterEqual(snap_duration_seconds(1, fps=25), 1)


if __name__ == "__main__":
    unittest.main()
