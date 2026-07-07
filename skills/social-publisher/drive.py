"""Download files from Google Drive via gws CLI."""

from __future__ import annotations

import os
import re

import config
from gws_cli import download_drive_file


def normalize_drive_file_id(value: str) -> str:
    """Extract raw Drive file ID from plain ID or common URL forms."""
    value = value.strip()
    if not value:
        return ""
    if re.fullmatch(r"[a-zA-Z0-9_-]{10,}", value):
        return value
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"[?&]id=([a-zA-Z0-9_-]+)",
        r"/folders/([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return value


def download_asset(
    drive_file_id: str,
    *,
    dest_dir: str | None = None,
    ext: str = ".mp4",
) -> str:
    file_id = normalize_drive_file_id(drive_file_id)
    if not file_id:
        raise ValueError("drive_file_id is empty")

    out_dir = dest_dir or config.TEMP_DIR
    os.makedirs(out_dir, exist_ok=True)
    if not ext.startswith("."):
        ext = f".{ext}"
    output_path = os.path.join(out_dir, f"{file_id}{ext}")
    return download_drive_file(file_id, output_path)


def download_video(drive_file_id: str, *, dest_dir: str | None = None) -> str:
    return download_asset(drive_file_id, dest_dir=dest_dir, ext=".mp4")
