#!/usr/bin/env python3
"""Deterministic artifact validator (the "hands" check Claude Code loops on).

  python3 scripts/validate.py <artifact> --schema {scenes|storyboard|prompts|video_prompt}
      [--target-seconds N] [--scenes-path P] [--run-dir D] [--scene S] [--gen G]

Writes ``<artifact>.validation.json`` (pass/fail + reasons) next to the artifact
and exits nonzero on failure so the SKILL.md write->validate->fix loop can branch.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from tools import validators  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Validate a story-maker-v4c artifact")
    p.add_argument("artifact", help="Path to the artifact file (md/json)")
    p.add_argument("--schema", required=True, choices=("scenes", "storyboard", "prompts", "video_prompt"))
    p.add_argument("--target-seconds", type=int, default=None)
    p.add_argument("--scenes-path", default=None, help="scenes.md (for storyboard cross-check)")
    p.add_argument("--run-dir", default=None, help="run output dir (for prompts/video_prompt schemas)")
    p.add_argument("--scene", default=None, help="scene id (for prompts/video_prompt schemas)")
    p.add_argument("--gen", default=None, help="generation id (for video_prompt schema; inferred from filename if omitted)")
    p.add_argument("--tolerance", type=int, default=15)
    args = p.parse_args()

    artifact = Path(args.artifact).resolve()
    if not artifact.is_file():
        print(f"artifact not found: {artifact}")
        return 2

    res = validators.validate(
        str(artifact),
        args.schema,
        target_seconds=args.target_seconds,
        scenes_path=args.scenes_path,
        run_dir=args.run_dir,
        scene_id=args.scene,
        gen_id=args.gen,
    )

    out_path = artifact.with_suffix(artifact.suffix + ".validation.json")
    out_path.write_text(json.dumps(res.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    if res.ok:
        print(f"PASS: {artifact.name} ({args.schema})" + (f"  warnings={len(res.warnings)}" if res.warnings else ""))
        for w in res.warnings:
            print(f"  ⚠ {w}")
        return 0
    print(f"FAIL: {artifact.name} ({args.schema}) — {len(res.errors)} error(s)")
    for e in res.errors:
        print(f"  ✗ {e}")
    for w in res.warnings:
        print(f"  ⚠ {w}")
    print(f"  wrote {out_path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())