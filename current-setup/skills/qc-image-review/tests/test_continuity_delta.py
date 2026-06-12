"""Test continuity_delta computation.

Bug: review of v2.0 found that the LF gate was documented as requiring
`continuity_delta > 0` (frozen shot detection) but `compute_continuity_delta`
was never implemented. A frozen shot (FF ≈ LF) would silently pass QC.

These tests verify the new function.
"""
import sys
from pathlib import Path

import pytest
import yaml

# Add the scripts dir to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from openrouter_qc import compute_continuity_delta  # noqa: E402


def test_identical_images_have_zero_delta(tmp_path):
    """Two copies of the same image should have delta ≈ 0 (frozen shot)."""
    from PIL import Image
    img = Image.new("RGB", (256, 256), color="red")
    img.save(tmp_path / "a.png")
    img.save(tmp_path / "b.png")
    delta = compute_continuity_delta(str(tmp_path / "a.png"), str(tmp_path / "b.png"))
    assert delta < 0.05, f"Identical images should have delta ≈ 0, got {delta}"


def test_different_images_have_high_delta(tmp_path):
    """Solid red vs solid blue should have a non-trivial delta (good — pass)."""
    from PIL import Image
    red = Image.new("RGB", (256, 256), color="red")
    blue = Image.new("RGB", (256, 256), color="blue")
    red.save(tmp_path / "red.png")
    blue.save(tmp_path / "blue.png")
    delta = compute_continuity_delta(str(tmp_path / "red.png"), str(tmp_path / "blue.png"))
    # Note: in grayscale, red and blue aren't as different as expected.
    # But they MUST be different (delta > 0) — this catches the frozen-shot case.
    assert delta > 0.1, f"Different colors should have non-trivial delta, got {delta}"


def test_slightly_different_images_have_medium_delta(tmp_path):
    """Slightly shifted versions should have medium delta."""
    from PIL import Image
    import numpy as np
    rng = np.random.RandomState(42)
    base = rng.randint(0, 255, (256, 256, 3), dtype=np.uint8)
    shifted = np.roll(base, 10, axis=0)
    Image.fromarray(base).save(tmp_path / "base.png")
    Image.fromarray(shifted).save(tmp_path / "shifted.png")
    delta = compute_continuity_delta(str(tmp_path / "base.png"), str(tmp_path / "shifted.png"))
    assert 0.05 < delta < 0.7, f"Slightly shifted images should have medium delta, got {delta}"


def test_delta_is_bounded_zero_to_one(tmp_path):
    """Delta should always be in [0, 1] regardless of input."""
    from PIL import Image
    # Maximum possible difference: all-white vs all-black
    white = Image.new("RGB", (256, 256), color="white")
    black = Image.new("RGB", (256, 256), color="black")
    white.save(tmp_path / "white.png")
    black.save(tmp_path / "black.png")
    delta = compute_continuity_delta(str(tmp_path / "white.png"), str(tmp_path / "black.png"))
    assert 0.0 <= delta <= 1.0, f"Delta must be bounded [0, 1], got {delta}"
