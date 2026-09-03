"""Background source video and contradiction-free wall reference extractor.

Implements the MiniMax H3 360° background video and wall frame extraction technique:
1. Generates or ingests a 360° pan/orbit video of the room/environment.
2. Extracts clean, contradiction-free single frames for each camera facing/wall.
3. Registers them as targeted reference plates for storyboard sheets and Ref2VA prompts.
"""

from __future__ import annotations

import os
from typing import Any

from .video_frames import extract_frames_at_timestamps


def calculate_angle_timestamp(
    angle_deg: float, total_duration: float, start_angle: float = 0.0
) -> float:
    """Map a camera azimuth (0-360 degrees) to a timestamp in a 360-degree pan video.

    Assumes uniform rotation speed across ``total_duration`` seconds.
    """
    if total_duration <= 0:
        return 0.0
    # ponytail: normalized modulo arithmetic handles any degree wrap cleanly
    normalized_deg = (angle_deg - start_angle) % 360.0
    return round((normalized_deg / 360.0) * total_duration, 3)


def cardinal_wall_timestamps(
    total_duration: float, start_angle: float = 0.0
) -> dict[str, float]:
    """Return timestamps for the 4 cardinal room walls (Front, Right, Back, Left)."""
    return {
        "wall_000deg": calculate_angle_timestamp(0.0, total_duration, start_angle),
        "wall_090deg": calculate_angle_timestamp(90.0, total_duration, start_angle),
        "wall_180deg": calculate_angle_timestamp(180.0, total_duration, start_angle),
        "wall_270deg": calculate_angle_timestamp(270.0, total_duration, start_angle),
    }


def extract_cardinal_walls(
    video_path: str,
    duration: float,
    out_dir: str,
    start_angle: float = 0.0,
    ext: str = "webp",
) -> dict[str, str]:
    """Extract standard 4 cardinal wall reference plates from a 360° pan video."""
    ts_map = cardinal_wall_timestamps(duration, start_angle=start_angle)
    return extract_frames_at_timestamps(video_path, ts_map, out_dir, ext=ext)


def extract_landmark_walls(
    video_path: str,
    duration: float,
    landmark_angles: dict[str, float],
    out_dir: str,
    start_angle: float = 0.0,
    ext: str = "webp",
) -> dict[str, str]:
    """Extract wall reference plates aligned to specific landmarks.

    ``landmark_angles`` maps landmark_id -> azimuth in degrees (0-360).
    """
    ts_map = {
        f"wall_{lid}": calculate_angle_timestamp(deg, duration, start_angle)
        for lid, deg in landmark_angles.items()
    }
    return extract_frames_at_timestamps(video_path, ts_map, out_dir, ext=ext)


def register_location_walls(
    registry: Any,
    lid: str,
    wall_paths: dict[str, str],
    video_path: str | None = None,
) -> dict[str, Any]:
    """Register extracted wall frames and optional 360 source video in AssetRegistry."""
    entry = registry.location(lid)
    existing_walls = entry.setdefault("walls", {})
    existing_walls.update(wall_paths)
    if video_path:
        entry["source_video"] = video_path
    registry.save()
    return entry


def resolve_facing_wall(camera_facing: str, walls: dict[str, str]) -> str | None:
    """Match a camera facing expression to an extracted wall reference plate path.

    Supports:
      - direct keys ("wall_090deg", "wall_180deg")
      - landmark facings ("toward_lamp_01" -> matches "wall_lamp_01")
      - cardinal azimuth shortcuts ("0", "90", "180", "270")
    """
    if not walls:
        return None
    facing = camera_facing.strip().lower()

    # 1. Exact key match
    if facing in walls:
        return walls[facing]

    # 2. toward_<landmark> -> wall_<landmark>
    if facing.startswith("toward_"):
        target_landmark = facing[len("toward_") :]
        target_key = f"wall_{target_landmark}"
        if target_key in walls:
            return walls[target_key]

    # 3. Numeric degree shorthand ("90" -> "wall_090deg")
    if facing.isdigit():
        deg = int(facing) % 360
        deg_key = f"wall_{deg:03d}deg"
        if deg_key in walls:
            return walls[deg_key]

    # 4. Keyword containment
    for key, path in walls.items():
        if key in facing or facing in key:
            return path

    return None
