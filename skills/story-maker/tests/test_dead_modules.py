import importlib
import unittest
from pathlib import Path


class TestDeadModulesRemoved(unittest.TestCase):
    def test_legacy_agents_not_importable(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("agents.motion_prompter")
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("agents.story_planner")

    def test_agents_init_exports_current_only(self):
        init_path = Path(__file__).resolve().parents[1] / "agents" / "__init__.py"
        text = init_path.read_text(encoding="utf-8")
        self.assertNotIn("motion_prompter_agent", text)
        self.assertNotIn("story_planner_agent", text)


if __name__ == "__main__":
    unittest.main()
