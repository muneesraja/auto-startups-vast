"""Grok Imagine image generation — dispatches to fal or Replicate via PROVIDER env."""
from __future__ import annotations

import config
from .grok_image_common import NO_TEXT_CLAUSE, ensure_no_text

# Re-export for tests and legacy imports
_ensure_no_text = ensure_no_text


def _backend():
    provider = config.get_image_provider()
    if provider == "replicate":
        from . import grok_replicate

        return grok_replicate
    from . import grok_fal

    return grok_fal


def generate_grok_t2i(
    prompt: str,
    output_path: str,
    resolution: str | None = None,
    *,
    size: str | None = None,
    quality: str | None = None,
    text_policy: str = "default",
) -> dict:
    return _backend().generate_grok_t2i(
        prompt,
        output_path,
        resolution=resolution,
        size=size,
        quality=quality,
        text_policy=text_policy,
    )


def generate_grok_edit(
    prompt: str,
    image_urls: list[str],
    output_path: str,
    resolution: str | None = None,
    *,
    size: str | None = None,
    quality: str | None = None,
    text_policy: str = "default",
) -> dict:
    return _backend().generate_grok_edit(
        prompt,
        image_urls,
        output_path,
        resolution=resolution,
        size=size,
        quality=quality,
        text_policy=text_policy,
    )
