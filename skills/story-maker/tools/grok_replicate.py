"""Image generation via Replicate (model slug from GROK_REPLICATE_MODEL)."""
from __future__ import annotations

import os
import threading
import time

import replicate

import config
from .grok_image_common import (
    apply_prompt_text_policy,
    cap_ref_urls,
    download_url_to_path,
    ensure_no_text,
    error_result,
    extract_replicate_output_url,
    grok_resolution,
    success_result,
    write_bytes_to_path,
)

_rate_lock = threading.Lock()
_last_call = 0.0
_MIN_INTERVAL = float(os.getenv("REPLICATE_MIN_INTERVAL_SEC", "12"))


def _throttle() -> None:
    """Serialize Replicate calls — low-credit accounts are ~6 req/min, burst 1."""
    global _last_call
    with _rate_lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def _replicate_client():
    token = os.environ.get("REPLICATE_API_TOKEN") or config.REPLICATE_API_TOKEN
    if not token:
        return None
    return replicate.Client(api_token=token)


def upload_local_image(image_path: str) -> str:
    """Upload a local PNG to Replicate Files API; return a public URL for edit refs."""
    if not os.path.isfile(image_path):
        raise FileNotFoundError(image_path)
    client = _replicate_client()
    if not client:
        raise RuntimeError("REPLICATE_API_TOKEN is not set")
    _throttle()
    with open(image_path, "rb") as fh:
        uploaded = client.files.create(fh)
    urls = getattr(uploaded, "urls", None) or {}
    if isinstance(urls, dict):
        url = urls.get("get") or urls.get("url")
        if url:
            return url
    url = getattr(uploaded, "url", None)
    if callable(url):
        url = url()
    if isinstance(url, str) and url.startswith("http"):
        return url
    # Newer SDKs expose .urls.get as a method-like object
    get_url = urls.get("get") if urls else None
    if callable(get_url):
        return get_url()
    raise RuntimeError(f"Could not resolve public URL for uploaded file: {uploaded!r}")


def _model_id() -> str:
    return config.GROK_REPLICATE_MODEL


def _is_gpt_image(model: str) -> bool:
    return "gpt-image" in model


def _is_seedream(model: str) -> bool:
    return "seedream" in model


def _replicate_image_quality() -> str:
    return os.getenv("REPLICATE_IMAGE_QUALITY", config.REPLICATE_IMAGE_QUALITY)


def _seedream_size(resolution: str | None) -> str:
    res = (resolution or grok_resolution()).strip().lower()
    if res in ("2k", "2048"):
        return "2K"
    return "1K"


def _gpt_image_input(
    prompt: str,
    image_urls: list[str] | None = None,
    *,
    size: str | None = None,
    quality: str | None = None,
) -> dict:
    inp: dict = {
        "prompt": prompt,
        "quality": quality or _replicate_image_quality(),
        "number_of_images": 1,
        "output_format": "png",
        "background": "opaque",
    }
    if size:
        inp["size"] = size
    else:
        inp["aspect_ratio"] = "16:9"
    openai_key = os.getenv("OPENAI_API_KEY") or getattr(config, "OPENAI_API_KEY", None)
    if openai_key:
        inp["openai_api_key"] = openai_key
    if image_urls:
        limit = config.get_image_ref_limit()
        inp["input_images"] = cap_ref_urls(image_urls, limit)
    return inp


def _seedream_input(
    prompt: str, resolution: str | None, image_urls: list[str] | None = None
) -> dict:
    inp: dict = {
        "prompt": prompt,
        "aspect_ratio": "16:9",
        "size": _seedream_size(resolution),
        "enhance_prompt": False,
        "sequential_image_generation": "disabled",
        "max_images": 1,
    }
    if image_urls:
        limit = config.get_image_ref_limit()
        inp["image_input"] = cap_ref_urls(image_urls, limit)
    return inp


def _build_input(
    prompt: str,
    resolution: str | None,
    image_urls: list[str] | None = None,
    *,
    size: str | None = None,
    quality: str | None = None,
) -> dict:
    model = _model_id()
    ref_limit = config.get_image_ref_limit()
    if _is_gpt_image(model):
        if image_urls and len(image_urls) > 1:
            capped = cap_ref_urls(image_urls, ref_limit)
            print(f"🖼️ [replicate] {model} edit with {len(capped)} ref(s)")
        return _gpt_image_input(prompt, image_urls, size=size, quality=quality)
    if _is_seedream(model):
        if image_urls and len(image_urls) > 1:
            capped = cap_ref_urls(image_urls, ref_limit)
            print(f"🖼️ [replicate] {model} edit with {len(capped)} ref(s)")
        return _seedream_input(prompt, resolution, image_urls)
    # Legacy Grok on Replicate — single image ref only
    if image_urls:
        refs = cap_ref_urls(image_urls, ref_limit)
        if len(image_urls) > 1:
            print(
                f"⚠️ [replicate] {model} only supports single ref; using primary"
            )
        return {
            "prompt": prompt,
            "image": refs[0],
            "aspect_ratio": "16:9",
        }
    return {
        "prompt": prompt,
        "aspect_ratio": "16:9",
        "resolution": resolution or grok_resolution(),
    }


def _save_replicate_output(output, output_path: str) -> str:
    """Persist Replicate output to disk; return hosted URL for spec refs."""
    url = extract_replicate_output_url(output)
    if url:
        download_url_to_path(url, output_path)
        return url
    if hasattr(output, "read"):
        write_bytes_to_path(output.read(), output_path)
        return f"file://{os.path.abspath(output_path)}"
    if isinstance(output, (bytes, bytearray)):
        write_bytes_to_path(bytes(output), output_path)
        return f"file://{os.path.abspath(output_path)}"
    raise ValueError(f"Unrecognized Replicate output type: {type(output)}")


def generate_grok_t2i(
    prompt: str,
    output_path: str,
    resolution: str | None = None,
    *,
    size: str | None = None,
    quality: str | None = None,
    text_policy: str = "default",
) -> dict:
    """Generate an image via Replicate."""
    client = _replicate_client()
    if not client:
        return error_result("REPLICATE_API_TOKEN is not set in environment or config.")

    final_prompt = apply_prompt_text_policy(prompt, text_policy)

    try:
        _throttle()
        output = client.run(
            _model_id(),
            input=_build_input(final_prompt, resolution, size=size, quality=quality),
        )
        image_url = _save_replicate_output(output, output_path)
        return success_result(output_path, image_url)
    except Exception as e:
        return error_result(f"Replicate T2I failed: {e}")


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
    """Edit/composite with reference images via Replicate."""
    client = _replicate_client()
    if not client:
        return error_result("REPLICATE_API_TOKEN is not set in environment or config.")
    if not image_urls:
        return error_result("Edit requires at least one reference image URL.")

    model = _model_id()
    final_prompt = apply_prompt_text_policy(prompt, text_policy)

    try:
        _throttle()
        output = client.run(
            model,
            input=_build_input(
                final_prompt,
                resolution,
                image_urls,
                size=size,
                quality=quality,
            ),
        )
        image_url = _save_replicate_output(output, output_path)
        return success_result(output_path, image_url)
    except Exception as e:
        return error_result(f"Replicate edit failed: {e}")
