#!/usr/bin/env python3
"""Optional: song → onset grid → cut timestamps for beat-synced cutting.

Uses librosa (if available) or ffmpeg's silencedetect as a fallback to extract
beat onsets from the source audio, then snaps the ledger's micro-shot cut
timestamps to the nearest onset.

This is OPTIONAL — the pipeline works without it (cuts are authored by the
Cutter role based on narrative beats).  When ``source_track`` is used and the
song has a strong beat, beat-synced cutting improves the cut rhythm.

Usage::

    python3 scripts/beat_grid.py --song song.wav --output beat_grid.json
    python3 scripts/beat_grid.py --song song.wav --ledger state.json --apply
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def onsets_librosa(song_path: str) -> list[float]:
    """Extract beat onsets using librosa (preferred)."""
    try:
        import librosa
    except ImportError:
        return []
    y, sr = librosa.load(song_path, sr=22050)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    return librosa.frames_to_time(beats, sr=sr).tolist()


def onsets_ffmpeg(song_path: str) -> list[float]:
    """Fallback: use ffmpeg's silencedetect to find transitions."""
    try:
        out = subprocess.check_output(
            ["ffmpeg", "-i", song_path, "-af", "silencedetect=noise=-30dB:d=0.1",
             "-f", "null", "-"],
            stderr=subprocess.STDOUT, timeout=60,
        )
    except Exception:
        return []
    onsets: list[float] = []
    for line in out.decode("utf-8", errors="replace").splitlines():
        if "silence_start:" in line:
            for part in line.split():
                if part.startswith("silence_start:"):
                    try:
                        onsets.append(float(part.split(":")[1]))
                    except ValueError:
                        pass
    return onsets


def snap_to_beat(timestamp: float, beats: list[float], tolerance: float = 0.08) -> float:
    """Snap a timestamp to the nearest beat within tolerance (±80ms)."""
    if not beats:
        return timestamp
    nearest = min(beats, key=lambda b: abs(b - timestamp))
    if abs(nearest - timestamp) <= tolerance:
        return nearest
    return timestamp


def main() -> int:
    p = argparse.ArgumentParser(description="Beat grid extraction + cut snapping")
    p.add_argument("--song", required=True, help="Path to source audio")
    p.add_argument("--output", default=None, help="Output beat grid JSON")
    p.add_argument("--ledger", default=None, help="Path to state.json (for --apply)")
    p.add_argument("--apply", action="store_true", help="Snap ledger cut timestamps to beats")
    args = p.parse_args()

    song = Path(args.song)
    if not song.is_file():
        print(f"song not found: {song}", file=sys.stderr)
        return 1

    # Try librosa first, fall back to ffmpeg
    beats = onsets_librosa(str(song))
    if not beats:
        print("librosa not available or no beats found, falling back to ffmpeg", file=sys.stderr)
        beats = onsets_ffmpeg(str(song))

    if not beats:
        print("no onsets detected", file=sys.stderr)
        return 1

    print(f"detected {len(beats)} beat onsets")

    if args.apply and args.ledger:
        ledger_path = Path(args.ledger)
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        snapped = 0
        for clip in ledger.get("clips", []):
            if not isinstance(clip, dict):
                continue
            for shot in clip.get("shots", []):
                if not isinstance(shot, dict):
                    continue
                t = shot.get("t", [])
                if len(t) == 2:
                    shot["t"] = [snap_to_beat(float(t[0]), beats), snap_to_beat(float(t[1]), beats)]
                    snapped += 1
                if "on_beat" in shot:
                    shot["on_beat"] = snap_to_beat(float(shot["on_beat"]), beats)
        ledger_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"snapped {snapped} timestamps to beats")

    out_path = Path(args.output) if args.output else Path("beat_grid.json")
    out_path.write_text(json.dumps({"beats": [round(b, 3) for b in beats]}, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
