"""LiteLLM vision calls for post-image motion prompt authoring."""
from __future__ import annotations

import base64
import os

import config

DEFAULT_VISION_MODEL = "openai/gpt-5-mini"
DEFAULT_API_BASE = "https://openrouter.ai/api/v1"


def encode_image_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def get_vision_api_config() -> tuple[str, str | None, str]:
    """Return (model, api_key, api_base)."""
    if config.OPENROUTER_API_KEY:
        return DEFAULT_VISION_MODEL, config.OPENROUTER_API_KEY, DEFAULT_API_BASE
    if config.GEMINI_API_KEY:
        return "gemini/gemini-2.5-flash", config.GEMINI_API_KEY, None
    raise ValueError("Set OPENROUTER_API_KEY or GEMINI_API_KEY for vision motion prompter")


async def vision_motion_prompt(
    image_path: str,
    system_prompt: str,
    user_text: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
) -> str:
    """Return motion_prompt plain text from a vision LLM call."""
    from litellm import acompletion

    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Starting frame not found: {image_path}")

    default_model, default_key, default_base = get_vision_api_config()
    model = model or default_model
    api_key = api_key if api_key is not None else default_key
    api_base = api_base if api_base is not None else default_base

    b64 = encode_image_base64(image_path)
    kwargs: dict = {
        "model": model,
        "api_key": api_key,
        "num_retries": 3,
        "timeout": 300,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                    {"type": "text", "text": user_text},
                ],
            },
        ],
    }
    if api_base:
        kwargs["api_base"] = api_base

    resp = await acompletion(**kwargs)
    content = resp.choices[0].message.content
    if not content or not str(content).strip():
        raise RuntimeError("Vision model returned empty motion prompt")
    return _strip_wrapping_quotes(str(content).strip())


def _strip_wrapping_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        return text[1:-1].strip()
    return text
