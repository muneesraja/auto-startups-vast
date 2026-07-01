"""Shared Grok image generation helpers (provider-agnostic)."""
from __future__ import annotations

import os

import httpx

NO_TEXT_CLAUSE = (
    " No text, no captions, no subtitles, no title cards, no watermark, "
    "no logos, no letters, no words, no numbers, no UI overlays."
)

GROK_REF_LIMIT = 3


def grok_resolution() -> str:
    return os.getenv("GROK_IMAGE_RESOLUTION", "1k")


def ensure_no_text(prompt: str) -> str:
    lower = prompt.lower()
    if "no text" in lower or "no captions" in lower or "no subtitles" in lower:
        return prompt
    return prompt.rstrip() + NO_TEXT_CLAUSE


def success_result(
    output_path: str,
    image_url: str,
    *,
    revised_prompt: str | None = None,
) -> dict:
    result = {
        "status": "success",
        "generated_image_path": output_path,
        "fal_image_url": image_url,
    }
    if revised_prompt:
        result["revised_prompt"] = revised_prompt
    return result


def error_result(message: str) -> dict:
    return {"status": "error", "message": message}


def download_url_to_path(image_url: str, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    resp = httpx.get(image_url, timeout=120.0)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(resp.content)


def write_bytes_to_path(data: bytes, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(data)


def extract_replicate_output_url(output) -> str | None:
    """Normalize Replicate run() return value to a downloadable URL."""
    if output is None:
        return None
    if isinstance(output, str) and output.startswith("http"):
        return output
    if isinstance(output, list) and output:
        return extract_replicate_output_url(output[0])
    url_attr = getattr(output, "url", None)
    if callable(url_attr):
        return url_attr()
    if isinstance(url_attr, str):
        return url_attr
    return None
