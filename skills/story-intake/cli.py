#!/usr/bin/env python3
"""story-intake — CLI for managing ``stories/`` input folders.

    python3 skills/story-intake/cli.py init olli --title "Olli"
    python3 skills/story-intake/cli.py episode olli 2 --title "The Dive"
    python3 skills/story-intake/cli.py add-asset olli characters ./ollie.png
    python3 skills/story-intake/cli.py add-audio olli ./v.mp3 \
        --role voice --speaker S1 --episode 2
    python3 skills/story-intake/cli.py check olli       # input warnings
    python3 skills/story-intake/cli.py status olli      # episodes + stages
    python3 skills/story-intake/cli.py prepare olli 1   # → prepare_episode.py
    python3 skills/story-intake/cli.py list             # all stories

Thin wrapper over story-maker-v5's input contract (``tools/story_input.py``,
``tools/episode_spec.py``, imported by path). Files stay the source of
truth — every command is plain file writes under ``stories/``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent
V5_ROOT = SKILL_ROOT.parent / "story-maker-v5"
sys.path.insert(0, str(V5_ROOT))

from tools import audio_refs as ar  # noqa: E402
from tools import episode_spec as es  # noqa: E402
from tools import story_input as si  # noqa: E402


def _story_dir(args, name: str) -> str:
    sd = si.story_dir(args.stories_root, name)
    root = os.path.realpath(args.stories_root)
    if not os.path.realpath(sd).startswith(root + os.sep):
        raise SystemExit(f"bad story name: {name}")
    return sd


def _print_warnings(warn: list[str]) -> None:
    for w in warn:
        print(f"  warning: {w}", file=sys.stderr)


def cmd_init(args) -> int:
    sd = si.init_story(args.stories_root, args.name, title=args.title)
    print(f"initialized {sd}/")
    for n in sorted(os.listdir(sd)):
        p = os.path.join(sd, n)
        print(f"  {n}{'/' if os.path.isdir(p) else ''}")
    print("\nnext: write episodes/episode-1/episode-1.md, then "
          "`cli.py prepare " + os.path.basename(sd) + " 1`")
    return 0


def cmd_episode(args) -> int:
    sd = _story_dir(args, args.name)
    if not os.path.isdir(sd):
        raise SystemExit(f"story not found: {sd} — run `init {args.name}`")
    ep_dir = si.episode_dir(sd, args.number)
    md_path = os.path.join(ep_dir, f"episode-{args.number}.md")
    for alt in (md_path,
                os.path.join(sd, "episodes", f"episode-{args.number}.md"),
                os.path.join(sd, f"episode-{args.number}.md")):
        if os.path.isfile(alt):
            raise SystemExit(f"episode {args.number} already exists: {alt}")
    os.makedirs(os.path.join(ep_dir, "audio"), exist_ok=True)
    os.makedirs(os.path.join(ep_dir, "references"), exist_ok=True)
    title = args.title or "<title>"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Episode {args.number} — {title}\n\n")
    es._atomic_write(os.path.join(ep_dir, "meta.json"),
                     dict(si._EPISODE_META, title=title))
    print(f"created {os.path.relpath(ep_dir, sd)}/")
    return 0


def cmd_add_asset(args) -> int:
    sd = _story_dir(args, args.name)
    rel = si.import_file(sd, args.kind, args.file, entity=args.entity or "",
                         episode=args.episode)
    print(f"imported → {rel}")
    stem = rel.rpartition("/")[2].rpartition(".")[0]
    if args.kind in ("characters", "locations", "objects") \
            and not si._ENTITY_RE.match(stem):
        print(f"  note: '{stem}' isn't canonical (char_NN/loc_NN/obj_NN) — "
              "map it in config cast[] or rename", file=sys.stderr)
    return 0


def cmd_add_audio(args) -> int:
    sd = _story_dir(args, args.name)
    rel = si.import_file(
        sd, "audio", args.file, role=args.role, speaker=args.speaker,
        scene=args.scene or "", gen=args.gen or "", episode=args.episode)
    print(f"imported → {rel}")
    return 0


def cmd_check(args) -> int:
    sd = _story_dir(args, args.name)
    warn = si.story_warnings(sd)
    if warn:
        _print_warnings(warn)
        print(f"{len(warn)} warning(s) for {os.path.basename(sd)}")
        return 1
    print(f"{os.path.basename(sd)}: clean")
    return 0


def cmd_status(args) -> int:
    sd = _story_dir(args, args.name)
    cfg = si.load_story_config(sd)
    idx = es._load_json(os.path.join(args.outputs_root,
                                     os.path.basename(sd), "episodes.json"))
    print(f"{os.path.basename(sd)} — {cfg.get('title') or '(untitled)'} "
          f"[{cfg.get('style')}]")
    for e in si.list_episode_files(sd):
        st = (idx.get("episodes") or {}).get(f"epi-{e['episode']}") or {}
        w = st.get("writing", "—")
        p = st.get("production", "—")
        empty = ""
        try:
            if not open(e["path"], encoding="utf-8").read().strip():
                empty = " (empty)"
        except OSError:
            pass
        print(f"  epi-{e['episode']}: writing={w} production={p}{empty}  "
              f"{os.path.relpath(e['path'], sd)}")
    warn = si.story_warnings(sd)
    _print_warnings(warn)
    return 0


def cmd_prepare(args) -> int:
    cmd = [
        sys.executable,
        str(V5_ROOT / "scripts" / "prepare_episode.py"),
        "--stories-root", args.stories_root,
        "--outputs-root", args.outputs_root,
        "--series", si.slugify(args.name),
        "--episode", str(args.number),
    ]
    res = subprocess.run(cmd)
    return res.returncode


def cmd_list(args) -> int:
    if not os.path.isdir(args.stories_root):
        print("(no stories/ root)")
        return 0
    for n in sorted(os.listdir(args.stories_root)):
        sd = os.path.join(args.stories_root, n)
        if not os.path.isdir(sd):
            continue
        cfg = si.load_story_config(sd)
        eps = si.list_episode_files(sd)
        print(f"{n:30} {len(eps):>2} ep  {cfg.get('title') or ''}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stories-root", default="stories")
    p.add_argument("--outputs-root", default="outputs/story-maker-v5")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="scaffold a story folder")
    s.add_argument("name")
    s.add_argument("--title", default="")
    s.set_defaults(f=cmd_init)

    s = sub.add_parser("episode", help="create episodes/episode-N/ folder")
    s.add_argument("name")
    s.add_argument("number", type=int)
    s.add_argument("--title", default="")
    s.set_defaults(f=cmd_episode)

    s = sub.add_parser("add-asset", help="import an image with entity naming")
    s.add_argument("name")
    s.add_argument("kind",
                   choices=("characters", "locations", "objects",
                            "style", "references"))
    s.add_argument("file")
    s.add_argument("--entity", default="",
                   help="canonical id (char_01/loc_01/obj_01) or 'new' "
                        "(default: next free)")
    s.add_argument("--episode", type=int, default=None,
                   help="references only: route into episodes/episode-N/")
    s.set_defaults(f=cmd_add_asset)

    s = sub.add_parser("add-audio", help="import audio with role naming")
    s.add_argument("name")
    s.add_argument("file")
    s.add_argument("--role", required=True,
                   choices=list(ar.VALID_ROLES))
    s.add_argument("--speaker", default="", help="required for role=voice")
    s.add_argument("--episode", type=int, default=None,
                   help="route into episodes/episode-N/audio/")
    s.add_argument("--scene", default="")
    s.add_argument("--gen", default="")
    s.set_defaults(f=cmd_add_audio)

    s = sub.add_parser("check", help="input warnings for a story")
    s.add_argument("name")
    s.set_defaults(f=cmd_check)

    s = sub.add_parser("status", help="episodes + writing/production stages")
    s.add_argument("name")
    s.set_defaults(f=cmd_status)

    s = sub.add_parser("prepare", help="run prepare_episode.py")
    s.add_argument("name")
    s.add_argument("number", type=int)
    s.set_defaults(f=cmd_prepare)

    s = sub.add_parser("list", help="all stories")
    s.set_defaults(f=cmd_list)

    args = p.parse_args()
    try:
        return args.f(args)
    except (ValueError, FileNotFoundError) as e:
        raise SystemExit(f"error: {e}")


if __name__ == "__main__":
    raise SystemExit(main())
