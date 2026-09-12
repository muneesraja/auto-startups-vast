#!/usr/bin/env python3
"""Episode intake: normalize a story file or ``stories/<series>/`` folder
into an explicit run directory.

    python3 scripts/prepare_episode.py --stories-root stories \
        --series shiva --episode 6
    python3 scripts/prepare_episode.py --story-file stories/shiva/episode-6.md

Writes:

  outputs/story-maker-v5/<series>/epi-N/episode_spec.json
  outputs/story-maker-v5/<series>/epi-N/story_source.md   (provenance copy)
  outputs/story-maker-v5/<series>/epi-N/audio/…           (materialized refs)
  outputs/story-maker-v5/<series>/epi-N/status.json       (stage: planned)
  stories/<series>/episodes.json                          (index, writing=planned)

The ``stories/`` folder stays user-managed input — read by path only, never
treated as production state. Ambiguous or missing episodes fail loudly with
a list of what was searched.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from tools.episode_spec import (  # noqa: E402
    EpisodeNotFoundError,
    build_episode_spec,
    find_episode_number,
    find_episode_story,
    load_meta,
    materialize_audio,
    materialize_user_assets,
    set_index_production,
    set_writing_status,
    write_episode_spec,
)
from tools.story_input import load_story_config  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Prepare an episode run dir")
    p.add_argument("--stories-root", default="stories")
    p.add_argument("--outputs-root", default="outputs/story-maker-v5")
    p.add_argument("--series", default=None)
    p.add_argument("--episode", type=int, default=None)
    p.add_argument("--story-file", default=None,
                   help="explicit story file (series inferred from parent dir)")
    args = p.parse_args()

    if args.story_file:
        story_path = os.path.abspath(args.story_file)
        if not os.path.isfile(story_path):
            raise SystemExit(f"story file not found: {story_path}")
        story_dir = os.path.dirname(story_path)
        base = os.path.basename(story_dir)
        if (re.match(r"episode[-\s_]?\d+$", base, re.IGNORECASE)
                and os.path.basename(os.path.dirname(story_dir))
                == "episodes"):
            story_dir = os.path.dirname(os.path.dirname(story_dir))
        elif base == "episodes":
            story_dir = os.path.dirname(story_dir)
        series = args.series or os.path.basename(story_dir)
        episode = args.episode or find_episode_number(
            args.stories_root, series, story_path
        )
        if episode is None:
            raise SystemExit(
                "cannot infer episode number from filename "
                f"'{os.path.basename(story_path)}' — pass --episode"
            )
        stories_root = os.path.dirname(story_dir) or args.stories_root
    else:
        if not args.series:
            raise SystemExit("pass --series or --story-file")
        series = args.series
        story_dir = os.path.join(args.stories_root, series)
        try:
            story_path = find_episode_story(
                args.stories_root, series, args.episode
            )
        except EpisodeNotFoundError as exc:
            raise SystemExit(str(exc))
        episode = args.episode or find_episode_number(
            args.stories_root, series, story_path
        )
        if episode is None:
            raise SystemExit(
                f"story '{os.path.basename(story_path)}' carries no episode "
                "number — pass --episode"
            )
        stories_root = args.stories_root

    meta = load_meta(story_dir, episode)
    config = load_story_config(story_dir)
    spec = build_episode_spec(
        series=series,
        episode=episode,
        story_path=story_path,
        meta=meta,
        stories_root=stories_root,
        outputs_root=args.outputs_root,
        story_file_arg=args.story_file,
        config=config,
    )
    run_dir = spec["run_dir"]

    # Provenance copy of the source story.
    os.makedirs(run_dir, exist_ok=True)
    shutil.copy2(story_path, os.path.join(run_dir, "story_source.md"))

    audio_files = materialize_audio(spec, run_dir, story_dir)
    spec["audio"]["materialized"] = [
        os.path.relpath(a, run_dir) for a in audio_files
    ]

    # User-supplied images → shared assets dir, registered approved.
    assets_dir = os.path.join(args.outputs_root, series, "assets")
    result = materialize_user_assets(spec, run_dir, story_dir, assets_dir)
    spec["user_assets"] = result
    for w in result["warnings"]:
        print(f"warning: {w}", file=sys.stderr)

    spec_path = write_episode_spec(spec, run_dir)

    # Status: writing 'planned' → the index; production 'planned' → run.
    story_dir_out = os.path.join(args.outputs_root, series)
    set_writing_status(story_dir_out, episode, "planned", run_dir=run_dir)
    set_index_production(
        story_dir_out, episode, "planned", run_dir=run_dir
    )
    from tools.episode_spec import set_production_status

    set_production_status(run_dir, "planned",
                          extra={"series": series, "episode": episode,
                                 "source": spec["source"]})

    print(f"prepared {series}/epi-{episode}")
    print(f"  spec:   {spec_path}")
    print(f"  source: {story_path}")
    for a in audio_files:
        print(f"  audio:  {a}")
    for item in result["imported"]:
        print(f"  {item['section']}: {item['entity']} → {item['dest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
