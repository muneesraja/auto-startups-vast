#!/usr/bin/env python3
"""Build identity plates + per-clip 3×2 storyboard sheets.

Registry-first: generates MISSES ONLY. Each approved asset in the global
registry is reused without regeneration. Each success writes a new version +
cost to the registry.

Reuses (import by path):
  - ``story-maker-v3/tools/image_pipeline.py``  (Replicate/fal gpt-image-2 dispatch)
  - ``story-maker-v3/tools/char_sheet_builder.py``
  - ``story-maker-v3/config.py``
  - ``h3-chain-director/scripts/assets_registry.py``  (global registry)

Usage::

    python3 scripts/build_sheets.py --ledger state.json --series NAME --episode N
    python3 scripts/build_sheets.py --ledger state.json --clip 3  # rebuild one sheet
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[2]
STORY_MAKER = REPO_ROOT / "skills" / "story-maker-v3"

sys.path.insert(0, str(STORY_MAKER))
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import config  # type: ignore  # noqa: E402

from assets_registry import GlobalAssetRegistry  # noqa: E402


def build_identity_plates(
    ledger: dict,
    reg: GlobalAssetRegistry,
    *,
    series: str,
    episode: int,
    dry_run: bool = False,
) -> list[dict]:
    """Generate missing identity plates for the ledger's cast."""
    built: list[dict] = []
    assets_dir = reg.assets_dir / series / "characters"

    for c in ledger.get("cast", []):
        if not isinstance(c, dict):
            continue
        entity_id = c.get("id", "")
        lock = c.get("appearance_lock", "")
        if not entity_id or not lock:
            continue

        # Registry-first: check for an approved asset
        existing = reg.resolve_approved(series, entity_id, appearance_lock=lock, kind="character_plate")
        if existing:
            built.append({"asset_id": existing["asset_id"], "action": "reused", "path": reg.approved_path(existing)})
            continue

        # Miss — need to generate
        variant = c.get("variant", "base")
        out_dir = assets_dir / entity_id / variant
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "v1.webp"

        if dry_run:
            built.append({"entity_id": entity_id, "action": "would_generate", "path": str(out_path)})
            continue

        # Build the plate prompt from the appearance lock
        prompt = f"Character identity plate: {lock}. Single character, full body, neutral pose, plain background. No text, no captions, no labels, no borders, no watermark."

        # Dispatch via story-maker-v3's image pipeline
        from tools.grok_tools import generate_grok_t2i  # type: ignore

        result = generate_grok_t2i(
            prompt=prompt,
            output_path=str(out_path),
            provider=config.get_image_provider(),
        )

        # Register the new asset
        entry = reg.add(
            kind="character_plate",
            series=series,
            entity_id=entity_id,
            variant=variant,
            appearance_lock=lock,
            path=str(out_path),
            provider=config.get_image_provider(),
            model=getattr(config, "REPLICATE_IMAGE_MODEL", "openai/gpt-image-2"),
            prompt_file="",
            cost_usd=0.24,
            notes="identity plate",
        )
        reg.record_usage(entry["asset_id"], series=series, episode=episode, run=f"epi-{episode}", stage="S8")
        built.append({"asset_id": entry["asset_id"], "action": "generated", "path": str(out_path)})

    return built


def build_storyboard_sheets(
    ledger: dict,
    reg: GlobalAssetRegistry,
    *,
    series: str,
    episode: int,
    clip_index: int | None = None,
    dry_run: bool = False,
) -> list[dict]:
    """Generate per-clip 3×2 storyboard sheets from sheet prompts."""
    built: list[dict] = []
    sheets_dir = reg.assets_dir / series / "sheets"
    sheets_dir.mkdir(parents=True, exist_ok=True)

    clips = ledger.get("clips", [])
    indices = [clip_index] if clip_index is not None else range(len(clips))

    for i in indices:
        if i < 0 or i >= len(clips):
            continue
        clip = clips[i]
        if not isinstance(clip, dict):
            continue

        sheet_prompt_path = clip.get("sheet_prompt")
        if not sheet_prompt_path:
            continue

        spath = Path(sheet_prompt_path)
        if not spath.is_file():
            built.append({"clip": clip.get("id"), "action": "skipped", "reason": f"sheet prompt not found: {spath}"})
            continue

        prompt_text = spath.read_text(encoding="utf-8")
        out_path = sheets_dir / f"{clip.get('id', f'clip_{i+1}')}_sheet.webp"

        if dry_run:
            built.append({"clip": clip.get("id"), "action": "would_generate", "path": str(out_path)})
            continue

        # Assemble reference images: anchor (identity plate) + previous sheet
        ref_urls: list[str] = []
        for c in clip.get("cast", []):
            # Find the cast member
            for cm in ledger.get("cast", []):
                if isinstance(cm, dict) and cm.get("id") == c:
                    entry = reg.resolve_approved(series, c, appearance_lock=cm.get("appearance_lock"), kind="character_plate")
                    if entry:
                        p = reg.approved_path(entry)
                        if p and os.path.isfile(p):
                            ref_urls.append(p)
                    break

        # Previous sheet (anchor+previous chaining)
        if i > 0:
            prev_clip = clips[i - 1]
            if isinstance(prev_clip, dict) and prev_clip.get("sheet"):
                prev_sheet = prev_clip["sheet"]
                if os.path.isfile(prev_sheet):
                    ref_urls.append(prev_sheet)

        # Cap refs at 6
        ref_urls = ref_urls[:6]

        # Dispatch via story-maker-v3's image pipeline (edit mode with refs)
        from tools.grok_tools import generate_grok_edit  # type: ignore

        result = generate_grok_edit(
            prompt=prompt_text,
            output_path=str(out_path),
            ref_images=ref_urls,
            provider=config.get_image_provider(),
        )

        # Register the sheet
        entity_id = clip.get("id", f"clip_{i+1}")
        entry = reg.add(
            kind="storyboard_sheet",
            series=series,
            entity_id=entity_id,
            variant=f"epi-{episode}",
            appearance_lock=prompt_text[:200],  # use the sheet prompt as the lock
            path=str(out_path),
            provider=config.get_image_provider(),
            model=getattr(config, "REPLICATE_IMAGE_MODEL", "openai/gpt-image-2"),
            prompt_file=str(spath),
            cost_usd=0.24,
            notes=f"3×2 storyboard sheet for {entity_id}",
            derived_from=[c.get("id", "") for c in ledger.get("cast", []) if isinstance(c, dict)],
        )
        clip["sheet"] = str(out_path)
        built.append({"clip": clip.get("id"), "action": "generated", "path": str(out_path)})

    # Save the updated ledger
    return built


def main() -> int:
    p = argparse.ArgumentParser(description="Build identity plates + storyboard sheets (registry-first)")
    p.add_argument("--ledger", required=True, help="Path to state.json")
    p.add_argument("--series", required=True)
    p.add_argument("--episode", type=int, required=True)
    p.add_argument("--clip", type=int, default=None, help="Rebuild only this clip's sheet (0-indexed)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--plates-only", action="store_true")
    p.add_argument("--sheets-only", action="store_true")
    args = p.parse_args()

    ledger_path = Path(args.ledger)
    if not ledger_path.is_file():
        print(f"ledger not found: {ledger_path}", file=sys.stderr)
        return 1
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))

    reg = GlobalAssetRegistry()

    if not args.sheets_only:
        plates = build_identity_plates(ledger, reg, series=args.series, episode=args.episode, dry_run=args.dry_run)
        print(f"identity plates: {len(plates)}")
        for p_ in plates:
            print(f"  {p_['action']}: {p_.get('asset_id') or p_.get('entity_id')} -> {p_['path']}")

    if not args.plates_only:
        sheets = build_storyboard_sheets(ledger, reg, series=args.series, episode=args.episode, clip_index=args.clip, dry_run=args.dry_run)
        print(f"storyboard sheets: {len(sheets)}")
        for s in sheets:
            print(f"  {s['action']}: {s.get('clip')} -> {s.get('path', s.get('reason', ''))}")

        # Save updated ledger (sheet paths written back)
        if not args.dry_run:
            ledger_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
