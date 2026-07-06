#!/usr/bin/env python3
"""Probe GPT Image 2 multi-reference limits via Replicate.

Collects character + background PNGs from outputs/story-maker and runs
controlled edit calls at 3, 10, and 16 reference counts for comparison.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Allow imports from story-maker package root
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import replicate  # noqa: E402

import config  # noqa: E402
from tools.grok_image_common import (  # noqa: E402
    download_url_to_path,
    ensure_no_text,
    extract_replicate_output_url,
)

_WORKSPACE = _ROOT.parent.parent
_OUTPUTS = _WORKSPACE / "outputs" / "story-maker"
_PROBE_DIR = _OUTPUTS / "ref-limit-probe"
_MODEL = "openai/gpt-image-2"

_PROBE_PROMPT = (
    "Images 1 through {char_end}: distinct character reference sheets — preserve each "
    "character's face, outfit, and proportions. "
    "Images {bg_start} through {bg_end}: environment / classroom background plates. "
    "Compose one 16:9 Pixar-style animated classroom scene: three children (a girl with "
    "dark hair, a boy with glasses, a girl with a red ribbon) in the foreground at their "
    "desks; warm morning light through windows; no text, no captions, no watermark."
)


def _collect_ref_pool() -> list[Path]:
    chars = sorted(_OUTPUTS.glob("*/characters/*.png"))
    bgs = sorted(_OUTPUTS.glob("*/backgrounds/*.png"))
    # Prefer classroom-ish backgrounds from glider-and-rara / baby-star scene_01
    preferred_bgs = [
        p
        for p in bgs
        if "scene_01" in p.name
        and any(s in str(p) for s in ("glider-and-rara", "baby-star", "glider"))
    ]
    other_bgs = [p for p in bgs if p not in preferred_bgs]
    ordered = chars + preferred_bgs + other_bgs
    return ordered


def _build_prompt(n_refs: int, ref_paths: list[Path]) -> str:
    n_chars = sum(1 for p in ref_paths if "/characters/" in str(p))
    n_bgs = n_refs - n_chars
    bg_start = n_chars + 1 if n_bgs else 0
    return _PROBE_PROMPT.format(
        char_end=n_chars,
        bg_start=bg_start,
        bg_end=n_refs if n_bgs else n_chars,
    )


def _open_ref_files(paths: list[Path]) -> list:
    """Return file handles for Replicate input_images (caller must close)."""
    return [open(p, "rb") for p in paths]


def _run_probe(
    client: replicate.Client,
    ref_paths: list[Path],
    out_png: Path,
    out_json: Path,
    *,
    ref_limit: int | None = None,
) -> dict:
    selected = ref_paths[:ref_limit] if ref_limit else ref_paths
    prompt = ensure_no_text(_build_prompt(len(selected), selected))
    handles = _open_ref_files(selected)

    record: dict = {
        "model": _MODEL,
        "ref_count": len(selected),
        "ref_paths": [str(p) for p in selected],
        "prompt": prompt,
        "status": "pending",
        "elapsed_sec": None,
        "error": None,
        "output_url": None,
    }

    t0 = time.monotonic()
    try:
        output = client.run(
            _MODEL,
            input={
                "prompt": prompt,
                "aspect_ratio": "16:9",
                "quality": os.getenv("REPLICATE_IMAGE_QUALITY", config.REPLICATE_IMAGE_QUALITY),
                "number_of_images": 1,
                "output_format": "png",
                "background": "opaque",
                "input_images": handles,
            },
        )
        url = extract_replicate_output_url(output)
        if not url:
            raise RuntimeError(f"No output URL from Replicate: {output!r}")
        download_url_to_path(url, str(out_png))
        record["status"] = "success"
        record["output_url"] = url
    except Exception as e:
        record["status"] = "error"
        record["error"] = str(e)
    finally:
        for h in handles:
            h.close()
        record["elapsed_sec"] = round(time.monotonic() - t0, 2)
        out_json.write_text(json.dumps(record, indent=2), encoding="utf-8")

    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe GPT Image 2 reference limits")
    parser.add_argument(
        "--counts",
        type=str,
        default="3,10,16",
        help="Comma-separated ref counts to test (default: 3,10,16)",
    )
    parser.add_argument(
        "--min-interval",
        type=float,
        default=float(os.getenv("REPLICATE_MIN_INTERVAL_SEC", "12")),
        help="Seconds between Replicate calls",
    )
    args = parser.parse_args()
    counts = [int(c.strip()) for c in args.counts.split(",") if c.strip()]

    token = os.environ.get("REPLICATE_API_TOKEN") or config.REPLICATE_API_TOKEN
    if not token:
        print("ERROR: REPLICATE_API_TOKEN not set", file=sys.stderr)
        return 1

    pool = _collect_ref_pool()
    max_count = max(counts)
    if len(pool) < max_count:
        print(
            f"ERROR: need {max_count} refs but only {len(pool)} PNGs in {_OUTPUTS}",
            file=sys.stderr,
        )
        return 1

    _PROBE_DIR.mkdir(parents=True, exist_ok=True)
    client = replicate.Client(api_token=token)
    summary = []

    print(f"Ref pool: {len(pool)} images ({sum(1 for p in pool if '/characters/' in str(p))} chars)")
    for i, n in enumerate(counts):
        if i > 0:
            time.sleep(args.min_interval)
        label = f"probe_{n}ref"
        out_png = _PROBE_DIR / f"{label}.png"
        out_json = _PROBE_DIR / f"{label}.json"
        print(f"\n--- {n} refs -> {out_png.name} ---")
        record = _run_probe(client, pool, out_png, out_json, ref_limit=n)
        summary.append(
            {
                "ref_count": n,
                "status": record["status"],
                "elapsed_sec": record["elapsed_sec"],
                "output": str(out_png) if record["status"] == "success" else None,
                "error": record.get("error"),
            }
        )
        print(f"  status={record['status']} elapsed={record['elapsed_sec']}s")
        if record.get("error"):
            print(f"  error: {record['error']}")

    summary_path = _PROBE_DIR / "probe_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSummary: {summary_path}")
    return 0 if all(s["status"] == "success" for s in summary) else 2


if __name__ == "__main__":
    raise SystemExit(main())
