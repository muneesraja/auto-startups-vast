"""Video frame extraction helpers for bridge clip generation.

Uses ffmpeg to extract tails, heads, and last frames from rendered clips.
These are used to condition bridge renders (ref_videos) and to build seam
reports.
"""

from __future__ import annotations

import os
import subprocess


def _run_ffmpeg(args: list[str], timeout: int = 60) -> bool:
    try:
        result = subprocess.run(["ffmpeg", "-y", *args], capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0
    except Exception:
        return False


def extract_tail(mp4: str, seconds: float, out_path: str) -> bool:
    """Extract the last N seconds of a video (with audio) to out_path."""
    if not os.path.isfile(mp4):
        return False
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    ok = _run_ffmpeg([
        "-sseof", f"-{seconds}",
        "-i", mp4,
        "-c", "copy",
        out_path,
    ])
    if not ok:
        # Fallback: re-encode if stream copy fails (codec mismatch)
        ok = _run_ffmpeg([
            "-sseof", f"-{seconds}",
            "-i", mp4,
            "-c:v", "libx264",
            "-c:a", "aac",
            out_path,
        ])
    return ok and os.path.isfile(out_path)


def extract_head(mp4: str, seconds: float, out_path: str) -> bool:
    """Extract the first N seconds of a video (with audio) to out_path."""
    if not os.path.isfile(mp4):
        return False
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    ok = _run_ffmpeg([
        "-i", mp4,
        "-t", str(seconds),
        "-c", "copy",
        out_path,
    ])
    if not ok:
        ok = _run_ffmpeg([
            "-i", mp4,
            "-t", str(seconds),
            "-c:v", "libx264",
            "-c:a", "aac",
            out_path,
        ])
    return ok and os.path.isfile(out_path)


def extract_last_frame(mp4: str, out_png: str) -> bool:
    """Extract the final frame of a video to a PNG (for still-frame fallback)."""
    if not os.path.isfile(mp4):
        return False
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    return _run_ffmpeg([
        "-sseof", "-0.1",
        "-i", mp4,
        "-frames:v", "1",
        "-update", "1",
        out_png,
    ]) and os.path.isfile(out_png)


def extract_first_frame(mp4: str, out_png: str) -> bool:
    """Extract the first frame of a video to a PNG."""
    if not os.path.isfile(mp4):
        return False
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    return _run_ffmpeg([
        "-i", mp4,
        "-frames:v", "1",
        "-update", "1",
        out_png,
    ]) and os.path.isfile(out_png)


def extract_frame_at_time(mp4: str, seconds: float, out_path: str) -> bool:
    """Extract a single frame at a specific timestamp (seconds) from a video."""
    if not os.path.isfile(mp4):
        return False
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    # ponytail: fast input seeking via -ss before -i; single frame output
    return _run_ffmpeg([
        "-ss", f"{max(0.0, float(seconds)):.3f}",
        "-i", mp4,
        "-frames:v", "1",
        "-update", "1",
        out_path,
    ]) and os.path.isfile(out_path)


def extract_frames_at_timestamps(
    mp4: str, timestamps: dict[str, float], out_dir: str, ext: str = "webp"
) -> dict[str, str]:
    """Extract frames for multiple named timestamps into out_dir.

    Returns dict of {name: file_path} for all successfully extracted frames.
    """
    results: dict[str, str] = {}
    if not os.path.isfile(mp4):
        return results
    os.makedirs(out_dir, exist_ok=True)
    for name, sec in timestamps.items():
        out_path = os.path.join(out_dir, f"{name}.{ext}")
        if extract_frame_at_time(mp4, sec, out_path):
            results[name] = out_path
    return results


def get_video_duration(mp4: str, default: float = 10.0) -> float:
    """Get video duration in seconds via ffprobe, falling back to default."""
    if not os.path.isfile(mp4):
        return default
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", mp4],
            capture_output=True, text=True, timeout=10,
        )
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip())
    except Exception:
        pass
    return default


