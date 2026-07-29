"""Shared Grok image generation helpers (provider-agnostic)."""
from __future__ import annotations

import os

import httpx

NO_TEXT_CLAUSE = (
    " No text, no captions, no subtitles, no title cards, no watermark, "
    "no logos, no letters, no words, no numbers, no UI overlays."
)


def cap_ref_urls(urls: list[str], limit: int) -> list[str]:
    """Return at most ``limit`` reference URLs, preserving order."""
    if limit < 1:
        raise ValueError(f"ref limit must be >= 1, got {limit}")
    return list(urls[:limit])


def grok_resolution() -> str:
    return os.getenv("GROK_IMAGE_RESOLUTION", "1k")


def ensure_no_text(prompt: str) -> str:
    lower = prompt.lower()
    if "no text" in lower or "no captions" in lower or "no subtitles" in lower:
        return prompt
    return prompt.rstrip() + NO_TEXT_CLAUSE


PRODUCTION_LABELS_CLAUSE = (
    " Include clean professional model-sheet typography, section headers, and view labels only. "
    "No watermarks, no logos, no subtitle captions, no dialogue text."
)


STORYBOARD_LABELS_CLAUSE = (
    " Include clean professional storyboard typography, shot numbers, section headers, "
    "and camera labels only. No watermarks, no logos, no subtitle captions, no dialogue text."
)


def apply_prompt_text_policy(prompt: str, text_policy: str = "default") -> str:
    """Adjust prompt for text rendering policy before image generation."""
    policy = (text_policy or "default").strip().lower()
    if policy == "production_labels":
        text = (prompt or "").rstrip()
        lower = text.lower()
        if (
            "production-sheet typography" not in lower
            and "storyboard typography" not in lower
        ):
            if "storyboard sheet" in lower:
                text += STORYBOARD_LABELS_CLAUSE
            else:
                text += PRODUCTION_LABELS_CLAUSE
        return text
    return ensure_no_text(prompt)


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


def check_upscale_drift(
    crop_path: str,
    upscale_path: str,
    threshold: float = 0.55,
    size: int = 256,
) -> float:
    """Return a 0..1 drift score between a crop and its upscale.

    Higher score means the upscale deviates more from the crop. The comparison
    uses a center-cropped square, then resized to ``size``, to be tolerant of
    aspect-ratio differences between the 9:16 crop and the 16:9 output.
    """
    import os

    import numpy as np
    from PIL import Image

    if not os.path.isfile(crop_path):
        raise FileNotFoundError(f"crop missing for drift check: {crop_path}")
    if not os.path.isfile(upscale_path):
        raise FileNotFoundError(f"upscale missing for drift check: {upscale_path}")

    def _center_square(img: Image.Image) -> Image.Image:
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        return img.crop((left, top, left + side, top + side))

    a = Image.open(crop_path).convert("RGB")
    b = Image.open(upscale_path).convert("RGB")
    a = _center_square(a).resize((size, size), Image.Resampling.LANCZOS)
    b = _center_square(b).resize((size, size), Image.Resampling.LANCZOS)

    a_arr = np.array(a, dtype=np.float32)
    b_arr = np.array(b, dtype=np.float32)

    # Normalized MSE (0 = identical, 1 = maximum possible)
    mse = float(np.mean((a_arr - b_arr) ** 2))
    mse_score = mse / (255.0 * 255.0)

    # Pearson correlation of the RGB pixel vectors (1 = identical)
    a_flat = a_arr.ravel()
    b_flat = b_arr.ravel()
    a_mean = a_flat - a_flat.mean()
    b_mean = b_flat - b_flat.mean()
    denom = np.sqrt(np.sum(a_mean ** 2) * np.sum(b_mean ** 2))
    if denom == 0:
        corr = 0.0
    else:
        corr = float(np.clip(np.sum(a_mean * b_mean) / denom, -1.0, 1.0))
    corr_score = 1.0 - (corr + 1.0) / 2.0  # rescale to 0..1

    drift = max(mse_score, corr_score)
    if drift > threshold:
        raise RuntimeError(
            f"Upscale drift too high: {drift:.3f} > {threshold:.3f} "
            f"(crop={crop_path}, upscale={upscale_path}). "
            "Delete the bad upscale, improve the panel prompt, and re-run."
        )
    return drift
