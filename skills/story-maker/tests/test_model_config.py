import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)


class TestModelConfig(unittest.TestCase):
    def setUp(self):
        self._env_keys = (
            "PLANNING_MODEL",
            "NARRATIVE_EXPANDER_MODEL",
            "STORY_PLAN_MODEL",
            "SECONDARY_MODEL",
            "VISION_MODEL",
            "REASONING_MODEL",
            "LIGHT_MODEL",
            "PLANNING_REASONING_EFFORT",
            "OPENROUTER_API_KEY",
        )
        self._saved = {k: os.environ.get(k) for k in self._env_keys}
        os.environ["OPENROUTER_API_KEY"] = "test-key"
        for k in self._env_keys:
            if k != "OPENROUTER_API_KEY":
                os.environ.pop(k, None)
        import config

        config._llm_cache.clear()
        self.config = config

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.config._llm_cache.clear()

    def test_normalize_openrouter_model(self):
        self.assertEqual(
            self.config._normalize_openrouter_model("z-ai/glm-5.2"),
            "openrouter/z-ai/glm-5.2",
        )
        self.assertEqual(
            self.config._normalize_openrouter_model("openai/gpt-5-mini"),
            "openrouter/openai/gpt-5-mini",
        )
        self.assertEqual(
            self.config._normalize_openrouter_model("anthropic/claude-sonnet-4.6"),
            "openrouter/anthropic/claude-sonnet-4.6",
        )

    def test_resolve_role_specific_over_planning_model(self):
        os.environ["PLANNING_MODEL"] = "z-ai/glm-5.2"
        os.environ["STORY_PLAN_MODEL"] = "openai/gpt-5-mini"
        self.assertEqual(
            self.config.get_story_plan_model_id(),
            "openai/gpt-5-mini",
        )
        self.assertEqual(
            self.config.get_narrative_expander_model_id(),
            "z-ai/glm-5.2",
        )

    def test_planning_model_fallback(self):
        os.environ["PLANNING_MODEL"] = "z-ai/glm-5.2"
        self.assertEqual(
            self.config.get_narrative_expander_model_id(),
            "z-ai/glm-5.2",
        )
        self.assertEqual(
            self.config.get_story_plan_model_id(),
            "z-ai/glm-5.2",
        )

    def test_default_when_unset(self):
        self.assertEqual(
            self.config.get_narrative_expander_model_id(),
            "openai/gpt-5.4-mini",
        )
        self.assertEqual(
            self.config.get_story_plan_model_id(),
            "openai/gpt-5.4-mini",
        )
        self.assertEqual(
            self.config.get_secondary_model_id(),
            "z-ai/glm-5.2",
        )
        self.assertEqual(
            self.config.get_vision_model_id(),
            "openai/gpt-5-mini",
        )

    def test_secondary_model_override(self):
        os.environ["SECONDARY_MODEL"] = "openai/gpt-5-mini"
        self.assertEqual(
            self.config.get_secondary_model_id(),
            "openai/gpt-5-mini",
        )

    @patch("google.adk.models.lite_llm.LiteLlm")
    def test_planning_model_passes_reasoning_effort(self, mock_lite_llm):
        mock_lite_llm.side_effect = lambda **kwargs: MagicMock(model=kwargs.get("model"))
        os.environ["PLANNING_REASONING_EFFORT"] = "low"
        self.config.get_narrative_expander_model()
        _, kwargs = mock_lite_llm.call_args
        self.assertEqual(kwargs.get("reasoning_effort"), "low")

    @patch("google.adk.models.lite_llm.LiteLlm")
    def test_get_llm_caches_by_model_and_timeout(self, mock_lite_llm):
        mock_lite_llm.side_effect = lambda **kwargs: MagicMock(model=kwargs.get("model"))
        a = self.config.get_llm("z-ai/glm-5.2", timeout=600)
        b = self.config.get_llm("z-ai/glm-5.2", timeout=600)
        c = self.config.get_llm("openai/gpt-5-mini", timeout=300)
        self.assertIs(a, b)
        self.assertIsNot(a, c)
        self.assertEqual(mock_lite_llm.call_count, 2)

    def test_apply_model_cli_overrides(self):
        from main import _apply_model_cli_overrides

        _apply_model_cli_overrides(
            ["--planning-model", "z-ai/glm-5.2", "--name", "x"]
        )
        self.assertEqual(os.environ.get("PLANNING_MODEL"), "z-ai/glm-5.2")

        _apply_model_cli_overrides(
            [
                "--narrative-expander-model",
                "openai/gpt-5-mini",
                "--story-plan-model",
                "z-ai/glm-5.2",
            ]
        )
        self.assertEqual(
            os.environ.get("NARRATIVE_EXPANDER_MODEL"),
            "openai/gpt-5-mini",
        )
        self.assertEqual(os.environ.get("STORY_PLAN_MODEL"), "z-ai/glm-5.2")


if __name__ == "__main__":
    unittest.main()
