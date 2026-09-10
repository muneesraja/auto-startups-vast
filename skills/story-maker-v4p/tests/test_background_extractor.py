"""Unit tests for background source video & wall reference extraction."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

from tools.background_extractor import (
    calculate_angle_timestamp,
    cardinal_wall_timestamps,
    extract_cardinal_walls,
    extract_landmark_walls,
    register_location_walls,
    resolve_facing_wall,
)


def test_calculate_angle_timestamp_uniform():
    duration = 10.0
    assert calculate_angle_timestamp(0.0, duration) == 0.0
    assert calculate_angle_timestamp(90.0, duration) == 2.5
    assert calculate_angle_timestamp(180.0, duration) == 5.0
    assert calculate_angle_timestamp(270.0, duration) == 7.5
    assert calculate_angle_timestamp(360.0, duration) == 0.0
    assert calculate_angle_timestamp(450.0, duration) == 2.5


def test_calculate_angle_timestamp_with_offset():
    duration = 10.0
    start_angle = 90.0
    # At 90 deg, timestamp should be 0
    assert calculate_angle_timestamp(90.0, duration, start_angle=start_angle) == 0.0
    # At 180 deg, delta is 90 -> 2.5s
    assert calculate_angle_timestamp(180.0, duration, start_angle=start_angle) == 2.5
    # At 0 deg, delta is 270 -> 7.5s
    assert calculate_angle_timestamp(0.0, duration, start_angle=start_angle) == 7.5


def test_cardinal_wall_timestamps():
    duration = 12.0
    ts = cardinal_wall_timestamps(duration)
    assert ts["wall_000deg"] == 0.0
    assert ts["wall_090deg"] == 3.0
    assert ts["wall_180deg"] == 6.0
    assert ts["wall_270deg"] == 9.0


def test_resolve_facing_wall():
    walls = {
        "wall_000deg": "/path/to/wall_000deg.webp",
        "wall_090deg": "/path/to/wall_090deg.webp",
        "wall_180deg": "/path/to/wall_180deg.webp",
        "wall_270deg": "/path/to/wall_270deg.webp",
        "wall_bus_upper_deck": "/path/to/wall_bus.webp",
    }
    # Direct match
    assert resolve_facing_wall("wall_090deg", walls) == "/path/to/wall_090deg.webp"
    # toward_<landmark>
    assert resolve_facing_wall("toward_bus_upper_deck", walls) == "/path/to/wall_bus.webp"
    # Numeric shorthand
    assert resolve_facing_wall("180", walls) == "/path/to/wall_180deg.webp"
    # Missing
    assert resolve_facing_wall("toward_unknown", walls) is None


def test_register_location_walls():
    class MockRegistry:
        def __init__(self):
            self.locations = {}
            self.saved = False

        def location(self, lid: str):
            return self.locations.setdefault(lid, {})

        def save(self):
            self.saved = True

    reg = MockRegistry()
    walls = {"wall_000deg": "/test/w0.webp", "wall_090deg": "/test/w90.webp"}
    entry = register_location_walls(reg, "loc_test", walls, video_path="/test/vid.mp4")

    assert entry["walls"]["wall_000deg"] == "/test/w0.webp"
    assert entry["source_video"] == "/test/vid.mp4"
    assert reg.saved is True


@patch("tools.background_extractor.extract_frames_at_timestamps")
def test_extract_cardinal_and_landmark_walls(mock_extract):
    mock_extract.return_value = {
        "wall_000deg": "/out/wall_000deg.webp",
        "wall_090deg": "/out/wall_090deg.webp",
    }
    res = extract_cardinal_walls("/dummy.mp4", 10.0, "/out")
    assert len(res) == 2
    mock_extract.assert_called_once()

    mock_extract.reset_mock()
    mock_extract.return_value = {"wall_lamp_01": "/out/wall_lamp_01.webp"}
    res2 = extract_landmark_walls("/dummy.mp4", 10.0, {"lamp_01": 180.0}, "/out")
    assert "wall_lamp_01" in res2
