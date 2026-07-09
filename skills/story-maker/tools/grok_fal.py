"""Grok Imagine image generation via fal.ai."""
from __future__ import annotations

import os

import fal_client

import config
from .grok_image_common import (
    apply_prompt_text_policy,
    cap_ref_urls,
    download_url_to_path,
    error_result,
    grok_resolution,
    success_result,
)


def _ensure_fal_key() -> str | None:
    if not os.environ.get("FAL_KEY"):
        os.environ["FAL_KEY"] = config.FAL_KEY or ""
    return os.environ.get("FAL_KEY")


def generate_grok_t2i(
    prompt: str,
    output_path: str,
    resolution: str | None = None,
    *,
    size: str | None = None,
    quality: str | None = None,
    text_policy: str = "default",
) -> dict:
    """Generate an image with xai/grok-imagine-image via fal.ai."""
    if not _ensure_fal_key():
        return error_result("FAL_KEY is not set in environment or config.")
    # fal Grok T2I does not support custom WxH; panoramic backgrounds use Replicate.
    _ = size
    _ = quality

    resolution = resolution or grok_resolution()
    final_prompt = apply_prompt_text_policy(prompt, text_policy)

    try:
        result = fal_client.subscribe(
            "xai/grok-imagine-image",
            arguments={
                "prompt": final_prompt,
                "num_images": 1,
                "resolution": resolution,
                "aspect_ratio": "16:9",
                "output_format": "png",
            },
        )
        images = result.get("images", [])
        if not images:
            return error_result(f"Grok T2I returned no images: {result}")

        image_url = images[0]["url"]
        download_url_to_path(image_url, output_path)
        return success_result(
            output_path, image_url, revised_prompt=result.get("revised_prompt")
        )
    except Exception as e:
        return error_result(f"Grok T2I failed: {e}")


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
    """Generate an edited image with xai/grok-imagine-image/edit via fal.ai."""
    if not _ensure_fal_key():
        return error_result("FAL_KEY is not set in environment or config.")
    if not image_urls:
        return error_result("Grok Edit requires at least one reference image URL.")
    _ = size
    _ = quality

    resolution = resolution or grok_resolution()
    final_prompt = apply_prompt_text_policy(prompt, text_policy)
    ref_limit = config.get_image_ref_limit()
    capped_urls = cap_ref_urls(image_urls, ref_limit)

    try:
        result = fal_client.subscribe(
            "xai/grok-imagine-image/edit",
            arguments={
                "prompt": final_prompt,
                "image_urls": capped_urls,
                "num_images": 1,
                "resolution": resolution,
                "aspect_ratio": "16:9",
                "output_format": "png",
            },
        )
        images = result.get("images", [])
        if not images:
            return error_result(f"Grok Edit returned no images: {result}")

        image_url = images[0]["url"]
        download_url_to_path(image_url, output_path)
        return success_result(
            output_path, image_url, revised_prompt=result.get("revised_prompt")
        )
    except Exception as e:
        return error_result(f"Grok Edit failed: {e}")
