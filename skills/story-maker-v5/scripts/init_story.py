#!/usr/bin/env python3
"""Scaffold a canonical ``stories/<name>/`` input folder.

    python3 scripts/init_story.py lord-shiva-furious-moments
    python3 scripts/init_story.py lord-shiva-furious-moments \
        --stories-root stories --title "Lord Shiva — Furious Moments"

Creates config.json, series.md, episodes/episode-1.md (+ meta sidecar),
audio/, characters/, locations/, objects/, style/, references/, and
README.intake.md. Idempotent — never overwrites existing files.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from tools.story_input import init_story  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Init a stories/ input folder")
    p.add_argument("name", help="folder name (slugified)")
    p.add_argument("--stories-root", default="stories")
    p.add_argument("--title", default="")
    args = p.parse_args()

    sd = init_story(args.stories_root, args.name, title=args.title)
    print(f"initialized {sd}/")
    for name in sorted(os.listdir(sd)):
        print(f"  {name}{'/' if os.path.isdir(os.path.join(sd, name)) else ''}")
    print(f"\nnext: edit {os.path.join(sd, 'episodes', 'episode-1.md')}, "
          "then run prepare_episode.py or use skills/story-intake/cli.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
