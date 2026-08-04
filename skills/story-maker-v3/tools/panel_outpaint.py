"""Deterministic panel outpaint helpers (pure PIL + numpy).

Provides:
  - ``trim_gutter()``          — crop near-white borders from a panel crop.
  - ``prepad_to_aspect()``     — scale + centre a crop on a 16:9 canvas with
                                  plain white side bars.
  - ``center_region_drift()``  — compare only the locked inner box between the
                                  pre-padded crop and the model output.

No LLM calls, no network.  All operations are pixel-deterministic.
"""

from __future__ import annotations

import math
import os
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_size(size: str) -> tuple[int, int]:
    """Parse ``"WxH"`` → ``(W, H)``."""
    w, h = size.lower().split("x")
    return int(w), int(h)


def trim_gutter(
    img: Image.Image,
    *,
    threshold: int = 240,
    margin: int = 2,
) -> Image.Image:
    """Crop near-white borders from *img*.

    Scans rows/columns for pixels where **all** channels ≥ *threshold* and
    trims them.  A small *margin* is kept to avoid cutting into content.
    """
    arr = np.array(img.convert("RGB"))
    h, w, _ = arr.shape

    # Rows / cols that are "white" (all channels ≥ threshold).
    white_rows = np.all(arr >= threshold, axis=(1, 2))  # shape (h,)
    white_cols = np.all(arr >= threshold, axis=(0, 2))  # shape (w,)

    # Find non-white bounding box.
    non_white_rows = np.where(~white_rows)[0]
    non_white_cols = np.where(~white_cols)[0]
    if len(non_white_rows) == 0 or len(non_white_cols) == 0:
        return img  # entirely white — return as-is

    top = max(0, non_white_rows[0] - margin)
    bottom = min(h, non_white_rows[-1] + 1 + margin)
    left = max(0, non_white_cols[0] - margin)
    right = min(w, non_white_cols[-1] + 1 + margin)

    return img.crop((left, top, right, bottom))


def _mirror_fill_bar(
    source: Image.Image,
    bar_width: int,
    side: str,
    *,
    blur_radius: float = 8.0,
    feather: int = 6,
) -> Image.Image:
    """Create a filler bar by mirroring the edge of *source*.

    *side* is ``"left"`` or ``"right"``.  The bar is mirrored horizontally,
    optionally blurred, and feathered at the inner edge so the seam with
    the centre is soft.
    """
    if bar_width <= 0:
        return Image.new("RGBA", (1, source.height), (0, 0, 0, 0))

    # Take a strip from the edge of the source and mirror it.
    strip_w = min(bar_width, source.width)
    if side == "left":
        strip = source.crop((0, 0, strip_w, source.height))
        mirrored = strip.transpose(Image.FLIP_LEFT_RIGHT)
    else:
        strip = source.crop((source.width - strip_w, 0, source.width, source.height))
        mirrored = strip.transpose(Image.FLIP_LEFT_RIGHT)

    # Resize to exact bar width.
    bar = mirrored.resize((bar_width, source.height), Image.LANCZOS)

    # Blur to soften the mirrored content.
    bar = bar.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    # Feather the inner edge so the seam with the centre is soft.
    if feather > 0 and bar.width > feather:
        arr = np.array(bar.convert("RGBA"), dtype=np.float32)
        if side == "left":
            ramp = np.linspace(0, 1, feather)
            arr[:, -feather:, 3] = arr[:, -feather:, 3] * ramp
        else:
            ramp = np.linspace(1, 0, feather)
            arr[:, :feather, 3] = arr[:, :feather, 3] * ramp
        bar = Image.fromarray(arr.astype(np.uint8), mode="RGBA")

    return bar


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prepad_to_aspect(
    crop_path: str,
    out_path: str,
    *,
    size: str | None = None,
    gutter_threshold: int = 240,
    blur_radius: float = 8.0,
    feather: int = 6,
) -> dict[str, Any]:
    """Pre-pad a panel crop to a 16:9 canvas with plain white side bars.

    Steps:
      1. Open the crop and trim white gutters.
      2. Scale the trimmed crop to fit inside the target canvas height
         (preserving aspect ratio).
      3. Centre it on a plain white canvas.
      4. Save as PNG.

    Returns ``{"inner_box": (left, top, right, bottom)}`` — the pixel region
    where the original crop content lives on the canvas.  This is the
    **locked region** that the outpaint model must not alter.
    """
    if size is None:
        size = "2048x1152"
    canvas_w, canvas_h = _parse_size(size)

    img = Image.open(crop_path).convert("RGB")
    img = trim_gutter(img, threshold=gutter_threshold)

    # Scale to fit canvas height (the crop is roughly 1:1, canvas is 16:9).
    scale = canvas_h / img.height
    new_w = int(round(img.width * scale))
    new_h = canvas_h
    # If the scaled width exceeds canvas width, scale by width instead.
    if new_w > canvas_w:
        scale = canvas_w / img.width
        new_w = canvas_w
        new_h = int(round(img.height * scale))

    scaled = img.resize((new_w, new_h), Image.LANCZOS)

    # Centre the scaled crop.
    paste_x = (canvas_w - new_w) // 2
    paste_y = (canvas_h - new_h) // 2

    # Create a plain white RGB canvas and paste the crop in the centre.
    # The white left/right bars are the explicit outpaint target for the model.
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    canvas.paste(scaled, (paste_x, paste_y))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    canvas.save(out_path, "PNG")

    inner_box = (paste_x, paste_y, paste_x + new_w, paste_y + new_h)
    return {"inner_box": inner_box}


def center_region_drift(
    crop_path: str,
    upscale_path: str,
    inner_box: tuple[int, int, int, int],
    *,
    threshold: float = 0.25,
    downscale: int = 256,
) -> float:
    """Compare only the locked inner-box region between crop and upscale.

    The *inner_box* is in canvas coordinates (from ``prepad_to_aspect``).
    We extract the corresponding region from both the pre-padded crop and
    the model's upscale output, resize to *downscale* × *downscale*, and
    compute a drift score using normalised MSE + Pearson correlation.

    Raises ``RuntimeError`` if the drift score exceeds *threshold*.
    Returns the drift score (0 = identical, 1 = completely different).
    """
    # The crop_path here is the pre-padded canvas (saved by prepad_to_aspect).
    # We compare the inner_box region of the prepad vs the same region of the upscale.
    a = Image.open(crop_path).convert("RGB")
    b = Image.open(upscale_path).convert("RGB")

    # Both should be the same canvas size, but just in case, resize b to match a.
    if b.size != a.size:
        b = b.resize(a.size, Image.LANCZOS)

    left, top, right, bottom = inner_box
    a_region = a.crop((left, top, right, bottom))
    b_region = b.crop((left, top, right, bottom))

    # Resize to common shape for comparison.
    a_arr = np.array(a_region.resize((downscale, downscale), Image.LANCZOS), dtype=np.float32) / 255.0
    b_arr = np.array(b_region.resize((downscale, downscale), Image.LANCZOS), dtype=np.float32) / 255.0

    # Normalised MSE (0 = identical, 1 = maximally different).
    mse = float(np.mean((a_arr - b_arr) ** 2))

    # Pearson correlation on flattened pixel vectors.
    a_flat = a_arr.flatten()
    b_flat = b_arr.flatten()
    a_mean = a_flat - a_flat.mean()
    b_mean = b_flat - b_flat.mean()
    denom = math.sqrt(float(np.sum(a_mean ** 2)) * float(np.sum(b_mean ** 2)))
    if denom < 1e-8:
        pearson = 0.0
    else:
        pearson = float(np.sum(a_mean * b_mean) / denom)

    # Drift score: combine MSE and (1 - pearson).
    # MSE is already in [0, 1] for normalised floats.
    # (1 - pearson) is in [0, 2] but typically [0, 1] for correlated images.
    drift = mse * 0.5 + (1.0 - pearson) * 0.5

    if drift > threshold:
        raise RuntimeError(
            f"center_region_drift score {drift:.4f} > threshold {threshold:.4f} "
            f"— the model altered the locked centre region"
        )

    return drift
