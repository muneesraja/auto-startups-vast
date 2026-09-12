#!/usr/bin/env python3
"""Series status board + per-episode status writes.

    python3 scripts/episode_status.py --story-dir outputs/story-maker-v5/shiva
        # board: one line per episode from episodes.json

    python3 scripts/episode_status.py --run-dir <run> --set rendering
        # advance a run's status.json and update the series index

Writing stages:    draft | planned | ready
Production stages: planned | assets_approved | render_approved |
                   rendering | qc_pending | complete
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from tools.episode_spec import (  # noqa: E402
    PRODUCTION_STAGES,
    episode_status,
    set_index_production,
    set_production_status,
)


def _board(story_dir: str) -> int:
    path = os.path.join(story_dir, "episodes.json")
    if not os.path.isfile(path):
        print(f"no index: {path}")
        return 1
    with open(path, encoding="utf-8") as f:
        idx = json.load(f)
    episodes = idx.get("episodes") or {}
    if not episodes:
        print("(no episodes tracked yet)")
        return 0
    print(f"{'episode':<10} {'writing':<10} {'production':<16} run")
    for key in sorted(episodes):
        e = episodes[key]
        print(
            f"{key:<10} {e.get('writing', '-'):<10} "
            f"{e.get('production', '-'):<16} {e.get('run_dir', '-')}"
        )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Episode status board / writes")
    p.add_argument("--story-dir", default=None,
                   help="series output dir containing episodes.json")
    p.add_argument("--run-dir", default=None,
                   help="episode run dir for --set")
    p.add_argument("--set", dest="stage", default=None,
                   choices=PRODUCTION_STAGES,
                   help="advance the run's production stage")
    args = p.parse_args()

    if args.stage:
        if not args.run_dir:
            raise SystemExit("--set requires --run-dir")
        run_dir = os.path.abspath(args.run_dir)
        status = set_production_status(run_dir, args.stage)
        # Reflect into the series index if we can infer series+episode.
        spec_path = os.path.join(run_dir, "episode_spec.json")
        if os.path.isfile(spec_path):
            with open(spec_path, encoding="utf-8") as f:
                spec = json.load(f)
            story_dir = os.path.dirname(run_dir)
            set_index_production(
                story_dir, spec.get("episode", 0), args.stage,
                run_dir=run_dir,
            )
        print(f"{run_dir}: production → {args.stage}")
        print(json.dumps(status, indent=2))
        return 0

    if args.run_dir:
        print(json.dumps(episode_status(os.path.abspath(args.run_dir)),
                         indent=2))
        return 0
    if args.story_dir:
        return _board(os.path.abspath(args.story_dir))
    raise SystemExit("pass --story-dir, or --run-dir [--set STAGE]")


if __name__ == "__main__":
    raise SystemExit(main())
