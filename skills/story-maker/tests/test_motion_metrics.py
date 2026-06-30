import unittest
from unittest.mock import patch

from tools.motion_metrics import motion_energy_passes, strengthen_motion_prompt


class TestMotionMetrics(unittest.TestCase):
    def test_strengthen_motion_prompt_adds_opener(self):
        out = strengthen_motion_prompt("The figure runs forward.")
        self.assertTrue(out.lower().startswith("a cinematic scene"))
        self.assertIn("Natural character animation", out)

    @patch("tools.motion_metrics.measure_motion_energy", return_value=0.05)
    def test_low_energy_fails(self, _mock):
        ok, energy = motion_energy_passes("/tmp/fake.mp4", min_energy=0.15)
        self.assertFalse(ok)
        self.assertEqual(energy, 0.05)

    @patch("tools.motion_metrics.measure_motion_energy", return_value=0.25)
    def test_high_energy_passes(self, _mock):
        ok, energy = motion_energy_passes("/tmp/fake.mp4", min_energy=0.15)
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
