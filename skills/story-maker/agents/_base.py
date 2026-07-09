import os
from typing import Callable

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils

import config

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_prompt(name: str) -> str:
    style = (os.getenv("STORY_STYLE") or "").strip().lower()
    candidates: list[str] = []
    if style and style != "cinematic":
        candidates.append(os.path.join(_SKILL_DIR, "prompts", style, f"{name}.md"))
    candidates.append(os.path.join(_SKILL_DIR, "prompts", f"{name}.md"))
    for path in candidates:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
    raise FileNotFoundError(f"Prompt not found for {name!r}; tried: {candidates}")


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


def make_text_agent(
    *,
    name: str,
    prompt_name: str,
    output_key: str,
    extra_instruction: str,
    model_factory: Callable | None = None,
) -> LlmAgent:
    """LLM agent that returns plain text/markdown (not JSON)."""
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
