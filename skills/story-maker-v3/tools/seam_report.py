"""Seam measurement tool: quantify the visual jump between adjacent clips.

For each adjacent clip pair (gK, gK+1) in a run, extracts the last frame of gK
and the first frame of gK+1, writes a side-by-side contact sheet, and computes
simple metrics (mean absolute pixel difference, histogram distance, mean luma
delta). Used to verify that bridge clips reduce the jump.

  python3 -m tools.seam_report <run_dir> [--scene sN] [--out seam_report.json]

No external deps beyond ffmpeg + Pillow (already required by the skill).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
    import numpy as np
except ImportError:
    Image = None  # type: ignore
    np = None  # type: ignore


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(["ffmpeg", "-y", *args], capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-300:]}")


def extract_last_frame(mp4: str, out_png: str) -> bool:
    """Extract the final frame of a video to a PNG."""
    if not os.path.isfile(mp4):
        return False
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    try:
        _run_ffmpeg(["-sseof", "-0.1", "-i", mp4, "-frames:v", "1", "-update", "1", out_png])
        return os.path.isfile(out_png)
    except Exception:
        return False


def extract_first_frame(mp4: str, out_png: str) -> bool:
    """Extract the first frame of a video to a PNG."""
    if not os.path.isfile(mp4):
        return False
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    try:
        _run_ffmpeg(["-i", mp4, "-frames:v", "1", "-update", "1", out_png])
        return os.path.isfile(out_png)
    except Exception:
        return False


def _load_array(png: str) -> "np.ndarray | None":
    if np is None or not os.path.isfile(png):
        return None
    img = Image.open(png).convert("RGB")
    return np.asarray(img, dtype=np.float32)


def _resize_match(a: "np.ndarray", b: "np.ndarray") -> tuple["np.ndarray", "np.ndarray"]:
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    if a.shape[:2] != (h, w):
        a = np.asarray(Image.fromarray(a.astype(np.uint8)).resize((w, h)))
    if b.shape[:2] != (h, w):
        b = np.asarray(Image.fromarray(b.astype(np.uint8)).resize((w, h)))
    return a.astype(np.float32), b.astype(np.float32)


def compute_metrics(png_a: str, png_b: str) -> dict:
    """Compute mean abs diff, histogram distance, mean luma delta between two frames."""
    a = _load_array(png_a)
    b = _load_array(png_b)
    if a is None or b is None:
        return {"status": "missing_frames"}
    a, b = _resize_match(a, b)
    mad = float(np.mean(np.abs(a - b)))
    luma_a = 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]
    luma_b = 0.299 * b[:, :, 0] + 0.587 * b[:, :, 1] + 0.114 * b[:, :, 2]
    luma_delta = float(np.mean(np.abs(luma_a - luma_b)))
    # Histogram distance (per-channel, 32 bins)
    hist_a = np.histogram(a, bins=32, range=(0, 255))[0].astype(np.float32)
    hist_b = np.histogram(b, bins=32, range=(0, 255))[0].astype(np.float32)
    hist_a /= hist_a.sum() + 1e-6
    hist_b /= hist_b.sum() + 1e-6
    hist_dist = float(np.sum(np.abs(hist_a - hist_b)))
    return {
        "status": "ok",
        "mean_abs_diff": round(mad, 2),
        "histogram_distance": round(hist_dist, 4),
        "mean_luma_delta": round(luma_delta, 2),
    }


def _make_contact_sheet(png_a: str, png_b: str, out_path: str) -> None:
    """Write a side-by-side contact sheet of two frames."""
    if Image is None or not os.path.isfile(png_a) or not os.path.isfile(png_b):
        return
    a = Image.open(png_a).convert("RGB")
    b = Image.open(png_b).convert("RGB")
    h = min(a.height, b.height)
    if a.height != h:
        a = a.resize((int(a.width * h / a.height), h))
    if b.height != h:
        b = b.resize((int(b.width * h / b.height), h))
    canvas = Image.new("RGB", (a.width + b.width + 4, h), (0, 0, 0))
    canvas.paste(a, (0, 0))
    canvas.paste(b, (a.width + 4, 0))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    canvas.save(out_path)


def _ordered_clips(run_dir: str, scene_id: str | None) -> list[tuple[str, str]]:
    """Return [(scene_id, clip_path), ...] in concat order, optionally filtered."""
    clips: list[tuple[str, str]] = []
    scene_ids = sorted(
        m.group(1)
        for f in os.listdir(run_dir)
        if (m := __import__("re").fullmatch(r"storyboard_([^.]+)\.md", f))
    )
    if scene_id:
        scene_ids = [s for s in scene_ids if s == scene_id]
    for sid in scene_ids:
        clips_dir = os.path.join(run_dir, "clips", sid)
        if not os.path.isdir(clips_dir):
            continue
        for f in sorted(os.listdir(clips_dir)):
            if f.endswith(".mp4"):
                clips.append((sid, os.path.join(clips_dir, f)))
    return clips


def build_report(run_dir: str, scene_id: str | None = None) -> dict:
    """Build seam report for all adjacent clip pairs in the run."""
    clips = _ordered_clips(run_dir, scene_id)
    report: dict = {"run_dir": run_dir, "seam_count": 0, "seams": []}
    if len(clips) < 2:
        report["status"] = "no_seams"
        return report

    frames_dir = os.path.join(run_dir, "seam_frames")
    os.makedirs(frames_dir, exist_ok=True)

    for i in range(len(clips) - 1):
        sid_a, clip_a = clips[i]
        sid_b, clip_b = clips[i + 1]
        seam_id = f"seam_{i+1:02d}_{os.path.basename(clip_a)[:-4]}_{os.path.basename(clip_b)[:-4]}"
        last_png = os.path.join(frames_dir, f"{seam_id}_last.png")
        first_png = os.path.join(frames_dir, f"{seam_id}_first.png")
        sheet_png = os.path.join(frames_dir, f"{seam_id}_contact.png")

        ok_a = extract_last_frame(clip_a, last_png)
        ok_b = extract_first_frame(clip_b, first_png)
        metrics = compute_metrics(last_png, first_png) if (ok_a and ok_b) else {"status": "extraction_failed"}
        if ok_a and ok_b:
            _make_contact_sheet(last_png, first_png, sheet_png)

        report["seams"].append({
            "seam_id": seam_id,
            "clip_a": clip_a,
            "clip_b": clip_b,
            "scene_a": sid_a,
            "scene_b": sid_b,
            "last_frame": last_png,
            "first_frame": first_png,
            "contact_sheet": sheet_png if os.path.isfile(sheet_png) else None,
            "metrics": metrics,
        })
    report["seam_count"] = len(report["seams"])
    report["status"] = "ok"
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Seam report: quantify jumps between adjacent clips")
    p.add_argument("run_dir", help="run output dir")
    p.add_argument("--scene", default=None, help="limit to one scene")
    p.add_argument("--out", default=None, help="output JSON path (default: <run_dir>/seam_report.json)")
    args = p.parse_args()

    run_dir = os.path.abspath(args.run_dir)
    report = build_report(run_dir, args.scene)
    out_path = args.out or os.path.join(run_dir, "seam_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"seam report: {report['seam_count']} seams -> {out_path}")
    for s in report["seams"]:
        m = s["metrics"]
        if m.get("status") == "ok":
            print(f"  {s['seam_id']}: MAD={m['mean_abs_diff']} luma_delta={m['mean_luma_delta']} hist_dist={m['histogram_distance']}")
        else:
            print(f"  {s['seam_id']}: {m.get('status', 'unknown')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
