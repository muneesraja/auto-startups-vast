#!/usr/bin/env python3
"""Build an immutable, content-addressed render_manifest.json before Minimax H3 rendering.

Scans the run directory for storyboard sheets, video prompts, and optional audio
references. Computes sha256 checksums so that what was reviewed and approved is
precisely what gets rendered on the GPU. The manifest also records the resolved
boundary policy per generation (continuation vs fresh cut), the expected frame
count, and hashes of the storyboard/scenes source documents — any post-approval
edit to those documents invalidates the manifest.

Usage:
  python3 scripts/build_manifest.py --run-dir <run_dir> [--approve] [--approved-by <name>]

Exits nonzero when required inputs are missing; ``--approve`` refuses to approve
an incomplete manifest.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from tools import boundary, image_pipeline as ip, validators  # noqa: E402
from tools.audio_refs import find_audio_refs  # noqa: E402
from tools.duration_budget import minimax_frames  # noqa: E402
from tools import minimax_workflow as mw  # noqa: E402


def sha256_file(filepath: str) -> str:
    """Compute sha256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def find_sheet(run_dir: str, scene_id: str, gen_id: str) -> str | None:
    """Find the per-generation storyboard sheet image (canonical convention)."""
    for ext in ("webp", "png", "jpg", "jpeg"):
        sheet_path = os.path.join(run_dir, f"storyboard_sheet_{scene_id}_{gen_id}.{ext}")
        if os.path.isfile(sheet_path) and os.path.getsize(sheet_path) > 0:
            return sheet_path
    return None


def _atomic_write_json(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


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
    scene_ids = [s["scene_id"] for s in scenes]
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Parse all storyboards up front (needed for boundary policy + hashing).
    storyboards: dict[str, dict] = {}
    storyboard_hashes: dict[str, str] = {}
    missing_storyboards: list[str] = []
    for sid in scene_ids:
        sb_path = run_path / f"storyboard_{sid}.md"
        if not sb_path.is_file():
            missing_storyboards.append(sid)
            continue
        storyboards[sid] = validators.parse_storyboard(sb_path.read_text(encoding="utf-8"))
        storyboard_hashes[sid] = sha256_file(str(sb_path))
    if missing_storyboards:
        raise FileNotFoundError(
            f"storyboard files missing for scenes: {', '.join(missing_storyboards)}"
        )

    workflow_path = mw.minimax_workflow_path()
    manifest = {
        "manifest_version": "1.1",
        "run_dir": str(run_path),
        "created_at": now_iso,
        "status": "approved" if approve else "pending",
        "approved_by": approved_by if approve else None,
        "approved_at": now_iso if approve else None,
        "scenes_sha256": sha256_file(str(scenes_path)),
        "storyboard_sha256": storyboard_hashes,
        "workflow": {
            "path": str(workflow_path),
            "sha256": sha256_file(str(workflow_path)) if workflow_path.is_file() else None,
        },
        "generations": [],
    }

    missing_inputs: list[str] = []
    prev_storyboard = None
    for sc in scenes:
        sid = sc["scene_id"]
        sb_data = storyboards[sid]
        generations = [g for g in sb_data.get("generations", []) if not g.get("is_bridge")]

        for gen in generations:
            gid = gen["gen_id"]

            sheet_file = find_sheet(str(run_path), sid, gid)
            prompt_file = ip.video_prompt_path(str(run_path), sid, gid)
            audio_refs = find_audio_refs(str(run_path), sid, gid)

            sheet_rel = os.path.relpath(sheet_file, str(run_path)) if sheet_file else None
            prompt_rel = (
                os.path.relpath(prompt_file, str(run_path))
                if os.path.isfile(prompt_file) else None
            )

            if not sheet_file:
                missing_inputs.append(f"{sid}/{gid}: storyboard sheet")
            if not prompt_rel:
                missing_inputs.append(f"{sid}/{gid}: video prompt")

            audio_entries = [
                {
                    "path": os.path.relpath(r["path"], str(run_path)),
                    "role": r["role"],
                    "sha256": sha256_file(r["path"]),
                }
                for r in audio_refs
            ]

            duration = (gen.get("end") or 0.0) - (gen.get("start") or 0.0)
            has_tail = boundary.needs_tail_ref(
                scene_ids, sid, sb_data, gid, prev_storyboard=prev_storyboard
            )

            gen_entry = {
                "scene_id": sid,
                "gen_id": gid,
                "duration_seconds": round(duration, 2),
                "expected_frames": minimax_frames(duration),
                "boundary": "continuation" if has_tail else "fresh_cut",
                "sheet_path": sheet_rel,
                "sheet_sha256": sha256_file(sheet_file) if sheet_file else None,
                "video_prompt_path": prompt_rel,
                "video_prompt_sha256": sha256_file(prompt_file) if prompt_rel else None,
                "audio_refs": audio_entries,
                # Back-compat single-ref fields (first attached audio ref).
                "audio_ref_path": audio_entries[0]["path"] if audio_entries else None,
                "audio_ref_sha256": audio_entries[0]["sha256"] if audio_entries else None,
                "status": "approved" if approve else "pending",
            }
            manifest["generations"].append(gen_entry)

        prev_storyboard = sb_data

    n = len(manifest["generations"])
    if missing_inputs:
        detail = "\n  ".join(missing_inputs)
        raise FileNotFoundError(
            f"cannot build a complete manifest — missing inputs:\n  {detail}"
        )
    if n == 0:
        raise FileNotFoundError("no generations found — nothing to render")

    out_file = run_path / "render_manifest.json"
    _atomic_write_json(out_file, manifest)
    print(f"Wrote render manifest with {n} generation(s) -> {out_file}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build approved render manifest with sha256 checksums")
    parser.add_argument("--run-dir", required=True, help="Path to run directory")
    parser.add_argument("--approve", action="store_true", help="Set status to approved")
    parser.add_argument("--approved-by", default="director", help="Name/role of approver")
    args = parser.parse_args()

    try:
        build_manifest(args.run_dir, approve=args.approve, approved_by=args.approved_by)
        if args.approve:
            # GATE 2 → render_approved status transition.
            import json as _json
            from tools.episode_spec import (
                set_index_production,
                set_production_status,
            )
            run_dir = os.path.abspath(args.run_dir)
            set_production_status(run_dir, "render_approved")
            spec_path = os.path.join(run_dir, "episode_spec.json")
            if os.path.isfile(spec_path):
                with open(spec_path, encoding="utf-8") as f:
                    spec = _json.load(f)
                set_index_production(
                    os.path.dirname(run_dir), spec.get("episode", 0),
                    "render_approved", run_dir=run_dir,
                )
        return 0
    except Exception as exc:
        print(f"Error building manifest: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
