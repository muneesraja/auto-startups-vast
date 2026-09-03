"""Image generation via fal.ai — default openai/gpt-image-2 (same model as Replicate)."""
from __future__ import annotations

import os
import re

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

# Legacy xAI Grok on fal rejects prompts longer than this.
_FAL_GROK_PROMPT_MAX_CHARS = 8000

_FAL_GPT_IMAGE_T2I = "openai/gpt-image-2"
_FAL_GPT_IMAGE_EDIT = "openai/gpt-image-2/edit"
_FAL_GROK_T2I = "xai/grok-imagine-image"
_FAL_GROK_EDIT = "xai/grok-imagine-image/edit"

_FAL_ASPECT_ENUM = {
    "2:1",
    "20:9",
    "19.5:9",
    "16:9",
    "4:3",
    "3:2",
    "1:1",
    "2:3",
    "3:4",
    "9:16",
    "9:19.5",
    "9:20",
    "1:2",
    "auto",
}


def _ensure_fal_key() -> str | None:
    if not os.environ.get("FAL_KEY"):
        os.environ["FAL_KEY"] = config.FAL_KEY or ""
    return os.environ.get("FAL_KEY")


def _fal_model_id() -> str:
    """Same model slug config as Replicate (default openai/gpt-image-2)."""
    return (
        os.getenv("GROK_FAL_MODEL")
        or os.getenv("GROK_REPLICATE_MODEL")
        or config.GROK_REPLICATE_MODEL
        or "openai/gpt-image-2"
    )


def _is_gpt_image(model: str) -> bool:
    return "gpt-image" in (model or "").lower()


def _default_quality() -> str:
    return (
        os.getenv("REPLICATE_IMAGE_QUALITY")
        or getattr(config, "REPLICATE_IMAGE_QUALITY", None)
        or "low"
    )


def fal_aspect_ratio_from_size(size: str | None, *, default: str = "16:9") -> str:
    """Map size / ratio strings to fal Grok ``aspect_ratio`` (legacy path)."""
    raw = (size or "").strip().lower().replace(" ", "")
    if not raw:
        return default
    if raw in _FAL_ASPECT_ENUM:
        return raw
    m = re.fullmatch(r"(\d+)x(\d+)", raw)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        if w <= 0 or h <= 0:
            return default
        if (w, h) in {(1152, 2048), (1080, 1920)}:
            return "9:16"
        if (w, h) in {(2048, 1152), (1920, 1080), (1280, 720)}:
            return "16:9"
        return "9:16" if h > w else "16:9" if w > h else "1:1"
    return default


def fal_resolution_from_size(size: str | None, resolution: str | None = None) -> str:
    """Legacy Grok 1k/2k resolution from pixel size."""
    if resolution:
        return resolution
    raw = (size or "").strip().lower()
    m = re.fullmatch(r"(\d+)x(\d+)", raw)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        if max(w, h) >= 1536:
            return "2k"
    return grok_resolution()


def fal_image_size_from_size(size: str | None) -> dict[str, int] | str:
    """Map ``1152x2048`` / ratios to fal GPT Image ``image_size``."""
    raw = (size or "").strip().lower().replace(" ", "")
    if not raw:
        return {"width": 2048, "height": 1152}
    m = re.fullmatch(r"(\d+)x(\d+)", raw)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        # fal requires multiples of 16
        w = max(16, (w // 16) * 16)
        h = max(16, (h // 16) * 16)
        return {"width": w, "height": h}
    if raw in {"9:16", "2:3", "3:4"}:
        return {"width": 1152, "height": 2048}
    if raw in {"8:9"}:
        return {"width": 1024, "height": 1152}
    if raw in {"16:9", "3:2", "4:3"}:
        return {"width": 2048, "height": 1152}
    if raw in {"1:1"}:
        return {"width": 1024, "height": 1024}
    return {"width": 2048, "height": 1152}


def _clamp_prompt(prompt: str, *, max_chars: int | None) -> str:
    text = prompt or ""
    if not max_chars or len(text) <= max_chars:
        return text
    truncated = text[: max_chars - 1]
    cut = truncated.rfind("\n")
    if cut >= max_chars // 2:
        truncated = truncated[:cut]
    return truncated


def _extract_image_url(result: dict) -> str | None:
    images = result.get("images") or []
    if not images:
        return None
    first = images[0]
    if isinstance(first, dict):
        return first.get("url")
    return None


def generate_grok_t2i(
    prompt: str,
    output_path: str,
    resolution: str | None = None,
    *,
    size: str | None = None,
    quality: str | None = None,
    text_policy: str = "default",
    image_urls: list[str] | None = None,
) -> dict:
    """Generate an image via fal (default: openai/gpt-image-2, optional refs)."""
    if not _ensure_fal_key():
        return error_result("FAL_KEY is not set in environment or config.")

    model = _fal_model_id()
    final_prompt = apply_prompt_text_policy(prompt, text_policy)
    q = (quality or _default_quality()).strip().lower() or "medium"

    try:
        if _is_gpt_image(model):
            image_size = fal_image_size_from_size(size)
            print(
                f"🖼️ [fal] {model} t2i quality={q} "
                f"image_size={image_size}"
            )
            arguments = {
                "prompt": final_prompt,
                "num_images": 1,
                "quality": q,
                "image_size": image_size,
                "output_format": "png",
            }
            if image_urls:
                arguments["image_urls"] = image_urls[:10]
            result = fal_client.subscribe(
                _FAL_GPT_IMAGE_T2I,
                arguments=arguments,
            )
        else:
            # Legacy xAI Grok Imagine path
            aspect_ratio = fal_aspect_ratio_from_size(size, default="16:9")
            res = fal_resolution_from_size(size, resolution)
            final_prompt = _clamp_prompt(
                final_prompt, max_chars=_FAL_GROK_PROMPT_MAX_CHARS
            )
            print(
                f"🖼️ [fal] {_FAL_GROK_T2I} t2i aspect={aspect_ratio} resolution={res}"
            )
            result = fal_client.subscribe(
                _FAL_GROK_T2I,
                arguments={
                    "prompt": final_prompt,
                    "num_images": 1,
                    "resolution": res,
                    "aspect_ratio": aspect_ratio,
                    "output_format": "png",
                },
            )

        image_url = _extract_image_url(result)
        if not image_url:
            return error_result(f"fal T2I returned no images: {result}")
        download_url_to_path(image_url, output_path)
        return success_result(
            output_path, image_url, revised_prompt=result.get("revised_prompt")
        )
    except Exception as e:
        return error_result(f"fal T2I failed: {e}")


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
    """Edit / multi-ref generate via fal (default: openai/gpt-image-2/edit)."""
    if not _ensure_fal_key():
        return error_result("FAL_KEY is not set in environment or config.")
    if not image_urls:
        return error_result("fal edit requires at least one reference image URL.")

    model = _fal_model_id()
    final_prompt = apply_prompt_text_policy(prompt, text_policy)
    q = (quality or _default_quality()).strip().lower() or "medium"
    ref_limit = config.get_image_ref_limit("fal")
    capped_urls = cap_ref_urls(image_urls, ref_limit)

    try:
        if _is_gpt_image(model):
            image_size = fal_image_size_from_size(size)
            print(
                f"🖼️ [fal] {_FAL_GPT_IMAGE_EDIT} with {len(capped_urls)} ref(s) "
                f"quality={q} image_size={image_size}"
            )
            result = fal_client.subscribe(
                _FAL_GPT_IMAGE_EDIT,
                arguments={
                    "prompt": final_prompt,
                    "image_urls": capped_urls,
                    "num_images": 1,
                    "quality": q,
                    "image_size": image_size,
                    "output_format": "png",
                },
            )
        else:
            aspect_ratio = fal_aspect_ratio_from_size(size, default="16:9")
            res = fal_resolution_from_size(size, resolution)
            final_prompt = _clamp_prompt(
                final_prompt, max_chars=_FAL_GROK_PROMPT_MAX_CHARS
            )
            print(
                f"🖼️ [fal] {_FAL_GROK_EDIT} with {len(capped_urls)} ref(s) "
                f"aspect={aspect_ratio} resolution={res}"
            )
            result = fal_client.subscribe(
                _FAL_GROK_EDIT,
                arguments={
                    "prompt": final_prompt,
                    "image_urls": capped_urls,
                    "num_images": 1,
                    "resolution": res,
                    "aspect_ratio": aspect_ratio,
                    "output_format": "png",
                },
            )

        image_url = _extract_image_url(result)
        if not image_url:
            return error_result(f"fal edit returned no images: {result}")
        download_url_to_path(image_url, output_path)
        return success_result(
            output_path, image_url, revised_prompt=result.get("revised_prompt")
        )
    except Exception as e:
        return error_result(f"fal edit failed: {e}")
