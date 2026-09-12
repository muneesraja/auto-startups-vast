"""Lightweight media verification for rendered clips (ffprobe-based).

Used by render_all.py before promoting a downloaded ``*.part`` file to its
final clip path — a render is not 'rendered' until the bytes are a real
video of approximately the expected duration with an audio stream.
"""

from __future__ import annotations

import json
import subprocess


def probe(path: str) -> dict | None:
    """Return ffprobe format/streams summary, or None if the file is unreadable."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-print_format", "json",
                "-show_format", "-show_streams",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def verify_clip(path: str, expected_seconds: float, *, eps: float = 0.5) -> str | None:
    """Return None when the clip looks valid, else a human-readable problem."""
    info = probe(path)
    if info is None:
        return "ffprobe could not read the file"
    streams = info.get("streams") or []
    if not any(s.get("codec_type") == "video" for s in streams):
        return "no video stream"
    if not any(s.get("codec_type") == "audio" for s in streams):
        return "no audio stream"
    try:
        dur = float(info.get("format", {}).get("duration", 0.0))
    except (TypeError, ValueError):
        dur = 0.0
    if expected_seconds and dur < expected_seconds - eps:
        return f"duration {dur:.2f}s < expected {expected_seconds:.2f}s"
    return None
