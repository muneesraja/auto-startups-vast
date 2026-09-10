#!/usr/bin/env python3
"""Build an immutable, content-addressed render_manifest.json before Minimax H3 rendering.

Scans the run directory for storyboard sheets, video prompts, and optional audio references.
Computes sha256 checksums to guarantee that what was reviewed and approved is precisely
what gets rendered on the GPU.

Usage:
  python3 scripts/build_manifest.py --run-dir <run_dir> [--approve] [--approved-by <name>]
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from tools import image_pipeline as ip
from tools import validators


def sha256_file(filepath: str) -> str:
    """Compute sha256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def find_sheet(run_dir: str, scene_id: str, gen_id: str) -> str | None:
    """Find the storyboard sheet image for a generation."""
    for ext in ("webp", "png", "jpg", "jpeg"):
        scene_sheet = os.path.join(run_dir, f"storyboard_sheet_{scene_id}.{ext}")
        if os.path.isfile(scene_sheet) and os.path.getsize(scene_sheet) > 0:
            return scene_sheet
        sheet_path = os.path.join(run_dir, f"storyboard_sheet_{scene_id}_{gen_id}.{ext}")
        if os.path.isfile(sheet_path) and os.path.getsize(sheet_path) > 0:
            return sheet_path
    return None


def find_audio_ref(run_dir: str, scene_id: str, gen_id: str) -> str | None:
    """Find optional audio reference attachment for a generation."""
    audio_dir = os.path.join(run_dir, "audio")
    if not os.path.isdir(audio_dir):
        return None
    for ext in ("mp3", "wav", "m4a", "aac", "flac"):
        for candidate in (
            f"{scene_id}_{gen_id}.{ext}",
            f"{gen_id}.{ext}",
            f"{scene_id}.{ext}",
        ):
            p = os.path.join(audio_dir, candidate)
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                return p
    return None


def build_manifest(
    run_dir: str,
    *,
    approve: bool = False,
    approved_by: str = "director",
) -> dict:
    run_path = Path(run_dir).resolve()
    scenes_path = run_path / "scenes.md"
    if not scenes_path.is_file():
        raise FileNotFoundError(f"scenes.md not found in {run_dir}")

    scenes_data = validators.parse_scenes(scenes_path.read_text(encoding="utf-8"))
    scenes = scenes_data.get("scenes", [])
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    manifest = {
        "manifest_version": "1.0",
        "run_dir": str(run_path),
        "created_at": now_iso,
        "status": "approved" if approve else "pending",
        "approved_by": approved_by if approve else None,
        "approved_at": now_iso if approve else None,
        "generations": [],
    }

    total_generations = 0

    for sc in scenes:
        sid = sc["scene_id"]
        sb_path = run_path / f"storyboard_{sid}.md"
        if not sb_path.is_file():
            continue
        sb_data = validators.parse_storyboard(sb_path.read_text(encoding="utf-8"))
        generations = [g for g in sb_data.get("generations", []) if not g.get("is_bridge")]

        for gen in generations:
            gid = gen["gen_id"]
            total_generations += 1

            sheet_file = find_sheet(str(run_path), sid, gid)
            prompt_file = ip.video_prompt_path(str(run_path), sid, gid)
            audio_file = find_audio_ref(str(run_path), sid, gid)

            sheet_rel = os.path.relpath(sheet_file, str(run_path)) if sheet_file else None
            prompt_rel = os.path.relpath(prompt_file, str(run_path)) if os.path.isfile(prompt_file) else None
            audio_rel = os.path.relpath(audio_file, str(run_path)) if audio_file else None

            sheet_hash = sha256_file(sheet_file) if sheet_file else None
            prompt_hash = sha256_file(prompt_file) if os.path.isfile(prompt_file) else None
            audio_hash = sha256_file(audio_file) if audio_file else None

            duration = (gen.get("end") or 0.0) - (gen.get("start") or 0.0)

            gen_entry = {
                "scene_id": sid,
                "gen_id": gid,
                "duration_seconds": round(duration, 2),
                "sheet_path": sheet_rel,
                "sheet_sha256": sheet_hash,
                "video_prompt_path": prompt_rel,
                "video_prompt_sha256": prompt_hash,
                "audio_ref_path": audio_rel,
                "audio_ref_sha256": audio_hash,
                "status": "approved" if approve else "pending",
                "clip_path": None,
            }
            manifest["generations"].append(gen_entry)

    out_file = run_path / "render_manifest.json"
    out_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote render manifest with {total_generations} generation(s) -> {out_file}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build approved render manifest with sha256 checksums")
    parser.add_argument("--run-dir", required=True, help="Path to run directory")
    parser.add_argument("--approve", action="store_true", help="Set status to approved")
    parser.add_argument("--approved-by", default="director", help="Name/role of approver")
    args = parser.parse_args()

    try:
        build_manifest(args.run_dir, approve=args.approve, approved_by=args.approved_by)
        return 0
    except Exception as exc:
        print(f"Error building manifest: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
