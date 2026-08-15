#!/usr/bin/env python3
"""S13 QC: audit actual cut rhythm vs planned cadence.

Uses ffmpeg scene detection to measure how many cuts actually landed in each
rendered segment, then compares against the ledger's planned micro-shot count.

This is the R1 experiment: does H3 honour 6–9 cuts inside one 14s generation?

Usage::

    python3 scripts/audit_cuts.py --ledger state.json --run-dir output/h3_chains/<run>/
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def detect_scenes(video_path: str, threshold: float = 0.3) -> list[float]:
    """Run ffmpeg scene detection and return cut timestamps."""
    try:
        out = subprocess.check_output(
            [
                "ffmpeg", "-i", video_path,
                "-filter:v", f"select='gt(scene,{threshold})',showinfo",
                "-f", "null", "-",
            ],
            stderr=subprocess.STDOUT,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return []
    except FileNotFoundError:
        return []

    cuts: list[float] = []
    for line in out.decode("utf-8", errors="replace").splitlines():
        if "pts_time:" in line:
            # Parse pts_time from showinfo
            for part in line.split():
                if part.startswith("pts_time:"):
                    try:
                        cuts.append(float(part.split(":")[1]))
                    except ValueError:
                        pass
    return cuts


def main() -> int:
    p = argparse.ArgumentParser(description="Audit actual cut rhythm vs planned cadence")
    p.add_argument("--ledger", required=True, help="Path to state.json")
    p.add_argument("--run-dir", required=True, help="Output directory with rendered segments")
    p.add_argument("--threshold", type=float, default=0.3, help="Scene detection threshold")
    args = p.parse_args()

    ledger_path = Path(args.ledger)
    if not ledger_path.is_file():
        print(f"ledger not found: {ledger_path}", file=sys.stderr)
        return 1
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"run dir not found: {run_dir}", file=sys.stderr)
        return 1

    report: list[dict] = []
    clips = ledger.get("clips", [])

    for i, clip in enumerate(clips):
        if not isinstance(clip, dict):
            continue
        clip_id = clip.get("id", f"clip_{i+1}")
        planned_shots = len(clip.get("shots", []))

        # Find the segment file
        segment_files = sorted(run_dir.glob(f"*{clip_id}*.mp4")) + sorted(run_dir.glob(f"*segment_{i+1:02d}*.mp4"))
        if not segment_files:
            report.append({"clip": clip_id, "planned": planned_shots, "detected": None, "status": "missing"})
            continue

        video = str(segment_files[0])
        cuts = detect_scenes(video, threshold=args.threshold)
        detected = len(cuts)

        status = "match" if abs(detected - planned_shots) <= 1 else "drift"
        report.append({
            "clip": clip_id,
            "planned": planned_shots,
            "detected": detected,
            "cuts_at": [round(c, 2) for c in cuts],
            "status": status,
        })

        print(f"  {clip_id}: planned={planned_shots} detected={detected} → {status}")

    # Summary
    total_planned = sum(r["planned"] for r in report if r["planned"])
    total_detected = sum(r["detected"] for r in report if r["detected"] is not None)
    matches = sum(1 for r in report if r["status"] == "match")
    drifts = sum(1 for r in report if r["status"] == "drift")
    missing = sum(1 for r in report if r["status"] == "missing")

    summary = {
        "clips": report,
        "summary": {
            "total_planned_cuts": total_planned,
            "total_detected_cuts": total_detected,
            "match_rate": round(matches / max(1, len(report) - missing), 2),
            "matches": matches,
            "drifts": drifts,
            "missing": missing,
        },
    }

    out_path = ledger_path.parent / "qc_cuts_audit.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsummary: {matches} match, {drifts} drift, {missing} missing")
    print(f"  total: planned={total_planned} detected={total_detected}")
    print(f"  wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
