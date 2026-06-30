import asyncio
import json
import unittest

from scripts.nodes.duration_budget_validator_node import duration_budget_validator


class _Ctx:
    def __init__(self, state):
        self.state = state


class TestDurationBudgetValidator(unittest.TestCase):
    def test_within_budget_passes(self):
        story = {
            "meta": {
                "target_duration_seconds": 300,
                "duration_tolerance_percent": 15,
                "total_duration_seconds": 290,
            },
            "scenes": [],
        }
        ctx = _Ctx({"story_plan_content": json.dumps(story)})
        asyncio.run(duration_budget_validator(ctx))

    def test_over_budget_raises(self):
        story = {
            "meta": {
                "target_duration_seconds": 300,
                "duration_tolerance_percent": 15,
                "total_duration_seconds": 400,
            },
            "scenes": [],
        }
        ctx = _Ctx({"story_plan_content": json.dumps(story)})
        with self.assertRaises(ValueError):
            asyncio.run(duration_budget_validator(ctx))


if __name__ == "__main__":
    unittest.main()
