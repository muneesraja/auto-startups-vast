#!/usr/bin/env python3
"""Image media builder (the "hands"). No LLM calls.

Reads prompt files Agent 4 authored under ``<run_dir>/image_prompts/`` and
dispatches deterministic image generation + crop + outpaint via the
``image_pipeline`` module.

  python3 scripts/build_images.py --output-dir <run> --assets-only
      # char sheets + location locks (shared, once)

  python3 scripts/build_images.py --output-dir <run> --sheet-only --scene s1
      # one scene: storyboard sheet only (→ GATE 1)

  python3 scripts/build_images.py --output-dir <run> --crop-only --scene s1
      # one scene: crop 9 panels from the sheet (free PIL, no API)

  python3 scripts/build_images.py --output-dir <run> --upscale-only --scene s1
      # one scene: upscale each crop to 16:9 (→ GATE 2)

  python3 scripts/build_images.py --output-dir <run> --scene s1
      # one scene: sheet + crop + upscale in one shot (legacy / one-shot rerun)

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
        c_path = reg.character_path(cid)
        if _exists(c_path):
            entry = reg.character(cid)
            entry["output_path"] = c_path
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
        l_path = reg.location_path(lid)
        if _exists(l_path):
            entry = reg.location(lid)
            entry["output_path"] = l_path
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
    reg.save()


def _scene_meta(scenes: dict, scene_id: str) -> tuple[int, str | None]:
    """Return (index, prev_scene_id) for a scene_id."""
    scene_list = scenes["scenes"]
    idx = next((i for i, s in enumerate(scene_list) if s["scene_id"] == scene_id), None)
    if idx is None:
        raise SystemExit(f"scene {scene_id} not in scenes.md")
    prev = scene_list[idx - 1]["scene_id"] if idx > 0 else None
    return idx, prev


def build_sheet(reg: ip.AssetRegistry, scenes: dict, scene_id: str) -> None:
    """Generate one scene's storyboard sheet (edit + refs)."""
    idx, prev_scene_id = _scene_meta(scenes, scene_id)
    sb = _storyboard(reg.run_dir, scene_id)
    cast = sb["cast"]
    loc = sb["location_ref_id"] or scenes["scenes"][idx]["location_id"]

    sheet_path = reg.sheet_path(scene_id)
    if _exists(sheet_path):
        print(f"  sheet {scene_id}: exists, skip")
        return
    sheet_prompt = ip.read_prompt(ip.sheet_prompt_path(reg.run_dir, scene_id))
    if not sheet_prompt:
        raise SystemExit(f"missing storyboard sheet prompt for {scene_id}")
    print(f"  sheet {scene_id}: generating (refs: loc={loc} prev={prev_scene_id} chars={cast}) ...")
    ip.generate_storyboard_sheet(
        reg, scene_id, prompt_text=sheet_prompt,
        character_ref_ids=cast, location_ref_id=loc, prev_scene_id=prev_scene_id,
    )


def build_crops(reg: ip.AssetRegistry, scenes: dict, scene_id: str) -> None:
    """Crop one scene's storyboard sheet into 9 panel PNGs (free PIL, no API)."""
    have_all = all(
        _exists(reg.panel_path(scene_id, f"panel_{r+1}{c+1}"))
        for r in range(duration_budget.SCENE_ROWS) for c in range(duration_budget.ROW_PANELS)
    )
    if have_all:
        print(f"  panels {scene_id}: all crops exist, skip")
        return
    print(f"  panels {scene_id}: cropping ...")
    crops = ip.crop_panels(reg, scene_id)
    for c in crops:
        print(f"    {c['panel_id']} ({c['method']}) -> {c['path']}")


def build_upscales(reg: ip.AssetRegistry, scenes: dict, scene_id: str) -> None:
    """Upscale each 16:9 panel crop to PANEL_IMAGE_SIZE."""
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
            print(f"  upscale {scene_id}/{panel_id}: generating ...")
            ip.upscale_panel(reg, scene_id, panel_id, prompt_text=prompt_text)


def build_scene(reg: ip.AssetRegistry, scenes: dict, scene_id: str) -> None:
    """Legacy: sheet + crop + upscale in one shot."""
    build_sheet(reg, scenes, scene_id)
    build_crops(reg, scenes, scene_id)
    build_upscales(reg, scenes, scene_id)


def main() -> int:
    p = argparse.ArgumentParser(description="Build story-maker-v3 image media")
    p.add_argument("--output-dir", required=True, help="run output dir")
    p.add_argument("--assets-dir", default=None, help="shared assets dir (default: <output-dir>/../assets)")
    p.add_argument("--assets-only", action="store_true", help="only char sheets + location locks")
    p.add_argument("--scene", default=None, help="scene id to build")
    p.add_argument("--sheet-only", action="store_true", help="generate storyboard sheet only (→ GATE 1)")
    p.add_argument("--crop-only", action="store_true", help="crop panels from sheet only (free PIL)")
    p.add_argument("--upscale-only", action="store_true", help="upscale panel crops only (→ GATE 2)")
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

    scene_id = args.scene
    if not scene_id and (args.sheet_only or args.crop_only or args.upscale_only):
        p.error("--sheet-only/--crop-only/--upscale-only require --scene")

    if args.sheet_only:
        build_sheet(reg, scenes, scene_id)
        print(f"sheet {scene_id} done")
        return 0
    if args.crop_only:
        build_crops(reg, scenes, scene_id)
        print(f"crops {scene_id} done")
        return 0
    if args.upscale_only:
        build_upscales(reg, scenes, scene_id)
        print(f"upscales {scene_id} done")
        return 0
    if scene_id:
        build_scene(reg, scenes, scene_id)
        print(f"scene {scene_id} done")
        return 0
    # Default: assets + every scene.
    build_assets(reg, scenes)
    for sc in scenes["scenes"]:
        build_scene(reg, scenes, sc["scene_id"])
    print("all scenes done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())