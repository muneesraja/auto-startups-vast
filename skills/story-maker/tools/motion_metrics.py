"""Cheap motion-energy metric via ffmpeg scene detection."""
from __future__ import annotations

import json
import os
import subprocess


def probe_duration_seconds(video_path: str) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            video_path,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    data = json.loads(proc.stdout)
    return float(data["format"]["duration"])


def measure_motion_energy(
    video_path: str,
    *,
    scene_threshold: float = 0.01,
) -> float:
    """Scene-change count per second — higher means more visible motion."""
    if not os.path.isfile(video_path):
        raise FileNotFoundError(video_path)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            video_path,
            "-filter:v",
            f"select='gt(scene,{scene_threshold})',showinfo",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    changes = proc.stderr.count("Parsed_showinfo")
    duration = probe_duration_seconds(video_path)
    return changes / max(duration, 0.5)


def motion_energy_passes(
    video_path: str,
    *,
    min_energy: float | None = None,
    scene_threshold: float = 0.01,
) -> tuple[bool, float]:
    if min_energy is None:
        min_energy = float(os.getenv("VIDEO_QA_MIN_MOTION_ENERGY", "0.15"))
    energy = measure_motion_energy(video_path, scene_threshold=scene_threshold)
    return energy >= min_energy, energy


def strengthen_motion_prompt(prompt: str) -> str:
    """Bias retry prompts toward visible sequential motion."""
    text = (prompt or "").strip()
    if not text.lower().startswith("a cinematic scene"):
        text = f"A cinematic scene of visible motion unfolding. {text}"
    if "natural character animation" not in text.lower():
        text = (
            f"{text} Strong continuous movement throughout the clip. "
            "No static hold or freeze frame. "
            "Natural character animation. Expressive animated motion."
        )
    return text
