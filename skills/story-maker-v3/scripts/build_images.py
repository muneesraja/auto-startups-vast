#!/usr/bin/env python3
"""Image media builder (the "hands"). No LLM calls.

Reads prompt files Agent 4 authored under ``<run_dir>/image_prompts/`` and
dispatches deterministic image generation + crop + upscale via the
``image_pipeline`` module.

  python3 scripts/build_images.py --output-dir <run> --assets-only
      # char sheets + location locks (shared, once)

  python3 scripts/build_images.py --output-dir <run> --scene s1
      # one scene: storyboard sheet -> crop 8 panels -> upscale each panel

Resume: existing assets / sheets / crops / upscales are skipped (the SKILL.md
waterfall checks existence before invoking this).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

import config  # noqa: E402
from tools import image_pipeline as ip  # noqa: E402
from tools import validators  # noqa: E402
from tools import duration_budget  # noqa: E402
from tools.char_sheet_builder import load_character_prompt  # noqa: E402
from tools.location_sheet_builder import load_location_prompt  # noqa: E402


def _scenes(run_dir: str) -> dict:
    path = os.path.join(run_dir, "scenes.md")
    if not os.path.isfile(path):
        raise SystemExit(f"scenes.md not found: {path}")
    return validators.parse_scenes(open(path, encoding="utf-8").read())


def _storyboard(run_dir: str, scene_id: str) -> dict:
    path = os.path.join(run_dir, f"storyboard_{scene_id}.md")
    if not os.path.isfile(path):
        raise SystemExit(f"storyboard_{scene_id}.md not found: {path}")
    return validators.parse_storyboard(open(path, encoding="utf-8").read())


def _exists(path: str) -> bool:
    return bool(path) and os.path.isfile(path) and os.path.getsize(path) > 0


def build_assets(reg: ip.AssetRegistry, scenes: dict) -> None:
    """Generate all character sheets + location locks referenced by scenes.md."""
    cids: list[str] = []
    lids: list[str] = []
    for sc in scenes["scenes"]:
        for cid in sc["cast"]:
            if cid and cid not in cids:
                cids.append(cid)
        if sc["location_id"] and sc["location_id"] not in lids:
            lids.append(sc["location_id"])

    for cid in cids:
        if _exists(reg.character_path(cid)):
            print(f"  char sheet {cid}: exists, skip")
            continue
        txt_path = ip.character_prompt_path(reg.run_dir, cid)
        json_path = txt_path[:-4] + ".json"
        prompt_text, fields = load_character_prompt(txt_path)
        if not prompt_text and not fields and os.path.isfile(json_path):
            _, fields = load_character_prompt(json_path)
        if not prompt_text and not fields:
            raise SystemExit(f"missing char prompt for {cid}: {txt_path} (or .json)")
        print(f"  char sheet {cid}: generating ...")
        ip.generate_character_sheet(reg, cid, prompt_text=prompt_text, character_fields=fields)

    for lid in lids:
        if _exists(reg.location_path(lid)):
            print(f"  location lock {lid}: exists, skip")
            continue
        txt_path = ip.location_prompt_path(reg.run_dir, lid)
        json_path = txt_path[:-4] + ".json"
        prompt_text, fields = load_location_prompt(txt_path)
        if not prompt_text and not fields and os.path.isfile(json_path):
            _, fields = load_location_prompt(json_path)
        if not prompt_text and not fields:
            raise SystemExit(f"missing location prompt for {lid}: {txt_path} (or .json)")
        print(f"  location lock {lid}: generating ...")
        ip.generate_location_lock(reg, lid, prompt_text=prompt_text, location_fields=fields)


def build_scene(reg: ip.AssetRegistry, scenes: dict, scene_id: str) -> None:
    """Generate one scene's storyboard sheet, crop, and per-panel upscales."""
    scene_list = scenes["scenes"]
    idx = next((i for i, s in enumerate(scene_list) if s["scene_id"] == scene_id), None)
    if idx is None:
        raise SystemExit(f"scene {scene_id} not in scenes.md")
    prev_scene_id = scene_list[idx - 1]["scene_id"] if idx > 0 else None

    sb = _storyboard(reg.run_dir, scene_id)
    cast = sb["cast"]
    loc = sb["location_ref_id"] or scene_list[idx]["location_id"]

    # 1. Storyboard sheet (edit + refs).
    sheet_path = reg.sheet_path(scene_id)
    if _exists(sheet_path):
        print(f"  sheet {scene_id}: exists, skip")
    else:
        sheet_prompt = ip.read_prompt(ip.sheet_prompt_path(reg.run_dir, scene_id))
        if not sheet_prompt:
            raise SystemExit(f"missing storyboard sheet prompt for {scene_id}")
        print(f"  sheet {scene_id}: generating (refs: loc={loc} prev={prev_scene_id} chars={cast}) ...")
        ip.generate_storyboard_sheet(
            reg, scene_id, prompt_text=sheet_prompt,
            character_ref_ids=cast, location_ref_id=loc, prev_scene_id=prev_scene_id,
        )

    # 2. Crop panels.
    from tools import panel_crop
    crops = []
    have_all_crops = all(
        _exists(reg.panel_path(scene_id, f"panel_{r+1}{c+1}"))
        for r in range(duration_budget.SCENE_ROWS) for c in range(duration_budget.ROW_PANELS)
    )
    if have_all_crops:
        print(f"  panels {scene_id}: all crops exist, skip")
        crops = [
            {"panel_id": f"panel_{r+1}{c+1}", "path": reg.panel_path(scene_id, f"panel_{r+1}{c+1}")}
            for r in range(duration_budget.SCENE_ROWS) for c in range(duration_budget.ROW_PANELS)
        ]
    else:
        print(f"  panels {scene_id}: cropping ...")
        crops = ip.crop_panels(reg, scene_id)
        for c in crops:
            print(f"    {c['panel_id']} ({c['method']}) -> {c['path']}")

    # 3. Upscale each panel (edit: crop + char refs).
    rows = sb["rows"]
    for r in range(duration_budget.SCENE_ROWS):
        for c in range(duration_budget.ROW_PANELS):
            panel_id = f"panel_{r+1}{c+1}"
            up_path = reg.upscale_path(scene_id, panel_id)
            if _exists(up_path):
                print(f"  upscale {scene_id}/{panel_id}: exists, skip")
                continue
            prompt_text = ip.read_prompt(ip.panel_prompt_path(reg.run_dir, scene_id, panel_id))
            if not prompt_text:
                raise SystemExit(f"missing panel prompt for {scene_id}/{panel_id}")
            # characters_present from the storyboard cell.
            cell = rows[r][c] if r < len(rows) and c < len(rows[r]) else {}
            chars = validators.parse_cid_list(cell.get("characters_present", ""))
            print(f"  upscale {scene_id}/{panel_id}: generating (chars={chars}) ...")
            ip.upscale_panel(reg, scene_id, panel_id, prompt_text=prompt_text, character_ref_ids=chars, location_ref_id=loc)


def main() -> int:
    p = argparse.ArgumentParser(description="Build story-maker-v3 image media")
    p.add_argument("--output-dir", required=True, help="run output dir")
    p.add_argument("--assets-dir", default=None, help="shared assets dir (default: <output-dir>/../assets)")
    p.add_argument("--assets-only", action="store_true", help="only char sheets + location locks")
    p.add_argument("--scene", default=None, help="build one scene (sheet + crop + upscale)")
    args = p.parse_args()

    run_dir = os.path.abspath(args.output_dir)
    assets_dir = args.assets_dir or os.path.join(os.path.dirname(run_dir), "assets")
    os.makedirs(run_dir, exist_ok=True)
    os.makedirs(assets_dir, exist_ok=True)

    reg = ip.AssetRegistry(run_dir, assets_dir)
    scenes = _scenes(run_dir)

    if args.assets_only:
        build_assets(reg, scenes)
        print("assets done")
        return 0
    if args.scene:
        build_scene(reg, scenes, args.scene)
        print(f"scene {args.scene} done")
        return 0
    # Default: assets + every scene.
    build_assets(reg, scenes)
    for sc in scenes["scenes"]:
        build_scene(reg, scenes, sc["scene_id"])
    print("all scenes done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())