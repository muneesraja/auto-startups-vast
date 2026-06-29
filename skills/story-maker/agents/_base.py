import os
from typing import Callable

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils

import config

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_prompt(name: str) -> str:
    path = os.path.join(_SKILL_DIR, "prompts", f"{name}.md")
    with open(path, encoding="utf-8") as f:
        return f.read()


def make_json_agent(
    *,
    name: str,
    prompt_name: str,
    output_key: str,
    extra_instruction: str,
    model_factory: Callable | None = None,
) -> LlmAgent:
    system_prompt = load_prompt(prompt_name)

    async def instruction_provider(context: ReadonlyContext) -> str:
        full = system_prompt + extra_instruction
        return await instructions_utils.inject_session_state(full, context)

    return LlmAgent(
        model=(model_factory or config.get_reasoning_model)(),
        name=name,
        instruction=instruction_provider,
        tools=[],
        output_key=output_key,
    )
