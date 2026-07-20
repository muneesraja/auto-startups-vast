#!/usr/bin/env python3
"""Migrate a flat story-maker run into story_root + part-N layout.

Copies (does not move) a live flat folder such as ``story-naila-5m-v2`` into::

    outputs/story-maker/<story-id>/
      characters/ locations/ backgrounds/   # shared
      part-<n>/                             # per-part artifacts

Absolute paths inside generation_specs.json / plan.json / video_shot_plan.json
are rewritten so shared assets point at the story root and everything else at
the part directory.

Example:
  .venv/bin/python scripts/migrate_story_series.py \\
    --source ../../outputs/story-maker/story-naila-5m-v2 \\
    --story-id story-naila --part 1
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

_SKILL_DIR = Path(__file__).resolve().parents[1]
_REPO = _SKILL_DIR.parents[1]
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

SHARED_DIRS = ("characters", "locations", "backgrounds")
PART_FILES = (
    "developed_story.md",
    "scene_paper.md",
    "plan.json",
    "generation_specs.json",
    "video_shot_plan.json",
    "cost_estimate.json",
    "final_film.mp4",
    "final_film_director.mp4",
)
PART_DIRS = (
    "storyboard_sheets",
    "panel_crops",
    "images",
    "videos",
)
ADHOC_VIDEO_DIRS = ("Naila-final-v2-videos",)


def rewrite_series_paths(
    text: str,
    *,
    source_root: str,
    story_root: str,
    part_dir: str,
) -> tuple[str, dict[str, int]]:
    """Rewrite absolute paths from a flat source into series layout.

    Order matters:
    1. shared subdirs under source → story_root
    2. ad-hoc video dump dirs → part_dir/videos
    3. remaining source_root → part_dir
    """
    counts = {"shared": 0, "adhoc_videos": 0, "part": 0}
    # realpath so /var vs /private/var (macOS) still match JSON paths.
    src = os.path.realpath(os.path.abspath(source_root)).rstrip("/")
    story = os.path.realpath(os.path.abspath(story_root)).rstrip("/")
    part = os.path.realpath(os.path.abspath(part_dir)).rstrip("/")
    # Also try non-realpath forms present in older specs.
    src_variants = {src, os.path.abspath(source_root).rstrip("/")}
    if src.startswith("/private/"):
        src_variants.add(src[len("/private") :])
    elif os.path.exists("/private" + src):
        src_variants.add("/private" + src)

    out = text
    for src_form in sorted(src_variants, key=len, reverse=True):
        for name in SHARED_DIRS:
            old = f"{src_form}/{name}/"
            new = f"{story}/{name}/"
            n = out.count(old)
            if n:
                out = out.replace(old, new)
                counts["shared"] += n
            old_bare = f"{src_form}/{name}"
            new_bare = f"{story}/{name}"
            pattern = re.compile(re.escape(old_bare) + r"(?![/\w])")
            matches = list(pattern.finditer(out))
            if matches:
                out = pattern.sub(new_bare, out)
                counts["shared"] += len(matches)

        for adhoc in ADHOC_VIDEO_DIRS:
            old = f"{src_form}/{adhoc}/"
            new = f"{part}/videos/"
            n = out.count(old)
            if n:
                out = out.replace(old, new)
                counts["adhoc_videos"] += n

        n = out.count(src_form + "/")
        if n:
            out = out.replace(src_form + "/", part + "/")
            counts["part"] += n
        pattern = re.compile(re.escape(src_form) + r"(?![/\w])")
        bare = list(pattern.finditer(out))
        if bare:
            out = pattern.sub(part, out)
            counts["part"] += len(bare)

    return out, counts


def rewrite_json_file(
    path: Path,
    *,
    source_root: str,
    story_root: str,
    part_dir: str,
) -> dict[str, int]:
    if not path.is_file():
        return {}
    raw = path.read_text(encoding="utf-8")
    rewritten, counts = rewrite_series_paths(
        raw,
        source_root=source_root,
        story_root=story_root,
        part_dir=part_dir,
    )
    if rewritten != raw:
        # Prefer round-tripping JSON when valid so formatting stays consistent.
        try:
            data = json.loads(rewritten)
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except json.JSONDecodeError:
            path.write_text(rewritten, encoding="utf-8")
    return counts


def _copy_file(src: Path, dst: Path) -> bool:
    if not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _copy_dir(src: Path, dst: Path) -> bool:
    if not src.is_dir():
        return False
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return True


def migrate(
    *,
    source: Path,
    story_root: Path,
    part: int,
) -> dict[str, Any]:
    source = source.resolve()
    story_root = story_root.resolve()
    part_dir = story_root / f"part-{int(part)}"

    if not source.is_dir():
        raise FileNotFoundError(f"Source not found: {source}")

    story_root.mkdir(parents=True, exist_ok=True)
    part_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "source": str(source),
        "story_root": str(story_root),
        "part_dir": str(part_dir),
        "copied_shared": [],
        "copied_part_files": [],
        "copied_part_dirs": [],
        "rewrites": {},
        "missing_assets": [],
    }

    for name in SHARED_DIRS:
        src = source / name
        dst = story_root / name
        if _copy_dir(src, dst):
            summary["copied_shared"].append(name)
            print(f"  shared ← {name}/")
        else:
            dst.mkdir(parents=True, exist_ok=True)
            print(f"  shared mkdir empty {name}/")

    for name in PART_FILES:
        if _copy_file(source / name, part_dir / name):
            summary["copied_part_files"].append(name)
            print(f"  part file ← {name}")

    for name in PART_DIRS:
        if _copy_dir(source / name, part_dir / name):
            summary["copied_part_dirs"].append(name)
            print(f"  part dir ← {name}/")

    # Fold ad-hoc video dumps into part videos/
    videos_dst = part_dir / "videos"
    videos_dst.mkdir(parents=True, exist_ok=True)
    for adhoc in ADHOC_VIDEO_DIRS:
        src = source / adhoc
        if not src.is_dir():
            continue
        for item in src.iterdir():
            if item.is_file() and item.suffix.lower() in (".mp4", ".mov", ".webm"):
                target = videos_dst / item.name
                if not target.exists():
                    shutil.copy2(item, target)
                    print(f"  adhoc video ← {adhoc}/{item.name}")

    for fname in ("generation_specs.json", "plan.json", "video_shot_plan.json"):
        counts = rewrite_json_file(
            part_dir / fname,
            source_root=str(source),
            story_root=str(story_root),
            part_dir=str(part_dir),
        )
        if counts:
            summary["rewrites"][fname] = counts
            print(f"  rewrite {fname}: {counts}")

    # Verify sampled assets exist after rewrite
    specs_path = part_dir / "generation_specs.json"
    if specs_path.is_file():
        specs = json.loads(specs_path.read_text(encoding="utf-8"))
        samples: list[str] = []
        for section in ("character_sheets", "location_sheets", "shot_images"):
            for entry in (specs.get(section) or {}).values():
                if isinstance(entry, dict) and entry.get("output_path"):
                    samples.append(entry["output_path"])
                    if len(samples) >= 12:
                        break
            if len(samples) >= 12:
                break
        for p in samples:
            if not os.path.isfile(p):
                summary["missing_assets"].append(p)
        print(
            f"  asset check: {len(samples) - len(summary['missing_assets'])}/"
            f"{len(samples)} sample paths exist"
        )
        if summary["missing_assets"]:
            for p in summary["missing_assets"][:5]:
                print(f"    missing: {p}")

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        required=True,
        help="Flat source run dir (e.g. outputs/story-maker/story-naila-5m-v2)",
    )
    parser.add_argument("--story-id", required=True, help="Story id (e.g. story-naila)")
    parser.add_argument("--part", type=int, default=1, help="Part number (default 1)")
    parser.add_argument(
        "--base-dir",
        default=None,
        help="Output base (default: STORY_MAKER_OUTPUT_DIR or outputs/story-maker)",
    )
    args = parser.parse_args(argv)

    import config

    base = Path(args.base_dir or config.DEFAULT_OUTPUT_BASE_DIR).resolve()
    source = Path(args.source).expanduser().resolve()
    story_root = base / args.story_id.strip().strip("/")

    print(f"Migrating {source}")
    print(f"  → story_root {story_root}")
    print(f"  → part-{args.part}")
    summary = migrate(source=source, story_root=story_root, part=args.part)
    print("Done.")
    print(json.dumps({k: v for k, v in summary.items() if k != "missing_assets"}, indent=2))
    return 1 if summary.get("missing_assets") else 0


if __name__ == "__main__":
    raise SystemExit(main())
