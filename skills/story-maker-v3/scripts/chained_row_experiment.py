"""Experiment: generate a row of 4 shots sequentially with Replicate gpt-image-2.

Flow:
  shot_1: medium quality 2048x1152, refs = character sheets + location.
  shot_2..4: low quality 2048x1152, refs = previous shot + character sheets + location,
             with an explicit "2 seconds after previous frame" motion instruction.

All outputs live in a dedicated experiment folder (no overwrite of the main run).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow importing from the skill package root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from tools import grok_replicate  # noqa: E402


DEFAULT_OUTPUT_DIR = os.path.join(
    config.DEFAULT_OUTPUT_BASE_DIR, "naila-ep1-chained-row2"
)

# Row 2 of scene s1 from the current Naila storyboard.
SHOTS = [
    {
        "shot_id": "row2_shot_1",
        "characters_present": ["char_02", "char_03"],
        "prompt": (
            "A cinematic 16:9 animation still: a tall kind-faced father stands beside a wooden feed trough "
            "in a far left paddock of a forest shelter, turning toward a golden dog that has just arrived "
            "barking at his feet. An elephant is visible only in the deep background. Warm dappled afternoon "
            "light, medium shot. Match the attached character sheets for the father and the golden dog, and "
            "the location lock for the forest shelter. "
            "No Naila, no parrot, no horse in foreground, no elephant close. "
            "no text, no labels, no captions, no watermarks, no frame numbers, no timeline."
        ),
        "quality": "medium",
    },
    {
        "shot_id": "row2_shot_2",
        "characters_present": ["char_02", "char_05"],
        "prompt": (
            "A cinematic 16:9 animation still showing the moment 2 seconds after the previous frame: "
            "the father is now mounted on a chestnut horse, riding rightward across the yard toward the "
            "distant swing, receding into mid-ground. The golden dog is no longer in this frame. "
            "Warm dappled afternoon light, wide shot. Match the attached character sheets for the father and "
            "the chestnut horse, and the location lock. "
            "No Naila, no parrot, no dog, no elephant close. "
            "no text, no labels, no captions, no watermarks, no frame numbers, no timeline."
        ),
        "quality": "low",
    },
    {
        "shot_id": "row2_shot_3",
        "characters_present": ["char_01", "char_02", "char_05"],
        "prompt": (
            "A cinematic 16:9 animation still showing the moment 2 seconds after the previous frame: "
            "the chestnut horse has stopped a few steps to the left of the wooden swing between two big trees; "
            "the father remains seated in the saddle, leaning his upper body only slightly toward the "
            "6-year-old girl; Naila sits on the swing seat, her feet dangling, tears still wet on her cheeks, "
            "her mouth just beginning to turn into a small surprised smile. Warm dappled afternoon light, "
            "two-shot framing. Match the attached character sheets for the father, Naila, and the chestnut "
            "horse, and the location lock. "
            "Negative constraints: no body contact, no fully resolved smile, no horse touching swing ropes, "
            "no father dismounted, no dog, no parrot. "
            "no text, no labels, no captions, no watermarks, no frame numbers, no timeline."
        ),
        "quality": "low",
    },
    {
        "shot_id": "row2_shot_4",
        "characters_present": ["char_01", "char_02"],
        "prompt": (
            "A cinematic 16:9 animation still showing the moment 2 seconds after the previous frame: "
            "the father is now standing firmly on the ground, lifting Naila up onto his shoulders; Naila is "
            "high above, arms slightly out, looking out over the shelter; the dog and parrot are visible below "
            "and around them. Warm dappled afternoon light, low-angle joyful shot. Match the attached character "
            "sheets for the father and Naila, and the location lock. "
            "No horse in immediate foreground, no elephant close, father must be standing not riding. "
            "no text, no labels, no captions, no watermarks, no frame numbers, no timeline."
        ),
        "quality": "low",
    },
]


def _asset_path(kind: str, cid: str) -> str:
    return os.path.join(config.DEFAULT_OUTPUT_BASE_DIR, "naila", "assets", kind, f"{cid}.png")


def _ensure_replicate_url(path: str) -> str:
    """Return a Replicate-usable URL for a local asset, uploading if needed."""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return grok_replicate.upload_local_image(path)


def _collect_refs(shot: dict, previous_url: str | None) -> list[str]:
    """Build reference image list: previous frame first (if any), then chars, then location."""
    refs: list[str] = []
    if previous_url:
        refs.append(previous_url)
    for cid in shot["characters_present"]:
        refs.append(_ensure_replicate_url(_asset_path("characters", cid)))
    refs.append(_ensure_replicate_url(_asset_path("locations", "loc_forest_shelter")))
    return refs


def main() -> int:
    parser = argparse.ArgumentParser(description="Chained 4-shot Replicate experiment")
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Folder to write all generated frames into",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print prompts and refs without calling Replicate",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    previous_url: str | None = None

    for i, shot in enumerate(SHOTS, start=1):
        refs = _collect_refs(shot, previous_url)
        output_path = str(out_dir / f"{shot['shot_id']}.png")
        manifest.append(
            {
                "index": i,
                "shot_id": shot["shot_id"],
                "quality": shot["quality"],
                "prompt": shot["prompt"],
                "refs": refs,
                "output_path": output_path,
            }
        )

        print(f"\n[{i}/4] {shot['shot_id']} — quality={shot['quality']}")
        print(f"  refs: {len(refs)}")
        print(f"  output: {output_path}")

        if args.dry_run:
            print("  (dry run — skipping Replicate)")
            continue

        result = grok_replicate.generate_grok_edit(
            prompt=shot["prompt"],
            image_urls=refs,
            output_path=output_path,
            size="2048x1152",
            quality=shot["quality"],
        )

        if result.get("status") != "success":
            print(f"  ERROR: {result.get('message')}")
            return 1

        # The returned URL is the local file URL; we can re-upload the local PNG
        # for the next shot so Replicate gets a fresh public URL.
        previous_url = _ensure_replicate_url(result["generated_image_path"])
        print(f"  done -> {result['generated_image_path']}")

    manifest_path = out_dir / "manifest.json"
    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"\nmanifest written: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
