#!/usr/bin/env python3
"""Print sha256 hashes the spatial-QA agent pastes into spatial_qa_report.md.

  python3 scripts/sheet_hashes.py --output-dir <run> --scene s1

For each non-bridge generation of the scene prints the sheet file hash; also
prints the spatial_plan_<scene>.md hash. The spatial_qa validator verifies
these values against the real files — the agent must not invent them.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from tools import validators  # noqa: E402


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    p = argparse.ArgumentParser(description="Print sheet + spatial-plan sha256 for the QA report")
    p.add_argument("--output-dir", required=True, help="run output dir")
    p.add_argument("--scene", required=True, help="scene id (e.g. s1)")
    args = p.parse_args()

    run_dir = os.path.abspath(args.output_dir)
    scene_id = args.scene

    sb_path = os.path.join(run_dir, f"storyboard_{scene_id}.md")
    if not os.path.isfile(sb_path):
        print(f"storyboard not found: {sb_path}", file=sys.stderr)
        return 1
    sb = validators.parse_storyboard(open(sb_path, encoding="utf-8").read())

    for gen in sb.get("generations", []):
        if gen.get("is_bridge"):
            continue
        gid = gen["gen_id"]
        for ext in ("webp", "png", "jpg", "jpeg"):
            sheet = os.path.join(run_dir, f"storyboard_sheet_{scene_id}_{gid}.{ext}")
            if os.path.isfile(sheet):
                print(f"{scene_id}/{gid} image_sha256: {_sha256(sheet)}")
                break
        else:
            print(f"{scene_id}/{gid}: sheet file not found", file=sys.stderr)

    plan_path = os.path.join(run_dir, f"spatial_plan_{scene_id}.md")
    if os.path.isfile(plan_path):
        print(f"spatial_plan_sha256: {_sha256(plan_path)}")
    else:
        print(f"no spatial plan for {scene_id} ({plan_path})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
