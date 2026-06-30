"""LiteLLM vision calls for post-image motion prompt authoring."""
from __future__ import annotations

import base64
import os

import config


def encode_image_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def get_vision_api_config() -> tuple[str, str | None, str | None]:
    """Return (model, api_key, api_base) from central config."""
    return config.get_vision_model_config()


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


_IMAGE_QA_SYSTEM = """You are a strict QA reviewer for AI-generated animation still frames.
Return ONLY valid JSON with keys: pass (boolean), reason (string), has_text (boolean),
character_count_ok (boolean), pose_match_ok (boolean).
Fail if ANY rendered text/letters/watermark, wrong character count vs brief, or gross pose/scene mismatch."""


async def vision_image_qa(image_path: str, shot_brief: dict) -> dict:
    """Score a PNG against its shot brief; returns {pass, reason, ...}."""
    import json as _json

    from litellm import acompletion

    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    default_model, default_key, default_base = get_vision_api_config()
    b64 = encode_image_base64(image_path)
    present = shot_brief.get("characters_present", [])
    user_text = _json.dumps(
        {
            "description": shot_brief.get("description", ""),
            "characters_present": present,
            "expected_character_count": len(present),
            "frame_strategy": shot_brief.get("frame_strategy"),
            "environment_state": shot_brief.get("environment_state", ""),
        },
        ensure_ascii=False,
    )
    kwargs: dict = {
        "model": default_model,
        "api_key": default_key,
        "num_retries": 3,
        "timeout": 180,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _IMAGE_QA_SYSTEM},
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
    if default_base:
        kwargs["api_base"] = default_base

    resp = await acompletion(**kwargs)
    raw = str(resp.choices[0].message.content or "").strip()
    try:
        data = _json.loads(raw)
    except _json.JSONDecodeError:
        return {"pass": False, "reason": f"invalid QA JSON: {raw[:200]}"}
    data.setdefault("pass", False)
    data.setdefault("reason", "unspecified")
    return data
