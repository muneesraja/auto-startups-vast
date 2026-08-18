#!/usr/bin/env python3
"""Image media builder (the "hands"). No LLM calls.

Reads prompt files Agent 4 authored under ``<run_dir>/image_prompts/`` and
dispatches deterministic image generation via the ``image_pipeline`` module.

  python3 scripts/build_images.py --output-dir <run> --assets-only
      # char sheets + location locks (shared, once)

  python3 scripts/build_images.py --output-dir <run> --scene s1
      # one scene: one clean-panel storyboard sheet per generation (→ GATE 1)

There is no crop or upscale stage: each generation's sheet is attached
verbatim as the Minimax H3 reference image at render time.

Resume: existing assets / sheets are skipped (the SKILL.md waterfall checks
existence before invoking this).
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
from tools.char_sheet_builder import load_character_prompt  # noqa: E402
from tools.location_sheet_builder import load_location_prompt  # noqa: E402
from tools.object_sheet_builder import load_object_prompt  # noqa: E402


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


def _spatial_plan(run_dir: str, scene_id: str) -> dict | None:
    """Load the spatial plan for a scene, or None if no plan exists (legacy)."""
    from tools.spatial_validator import parse_spatial_plan
    path = os.path.join(run_dir, f"spatial_plan_{scene_id}.md")
    if not os.path.isfile(path):
        return None
    return parse_spatial_plan(open(path, encoding="utf-8").read())


def _exists(path: str) -> bool:
    return bool(path) and os.path.isfile(path) and os.path.getsize(path) > 0


def build_assets(reg: ip.AssetRegistry, scenes: dict) -> None:
    """Generate all character sheets + location locks + object sheets referenced by scenes.md."""
    cids: list[str] = []
    lids: list[str] = []
    oids: list[str] = []
    for sc in scenes["scenes"]:
        for cid in sc["cast"]:
            if cid and cid not in cids:
                cids.append(cid)
        if sc["location_id"] and sc["location_id"] not in lids:
            lids.append(sc["location_id"])
        for oid in sc.get("objects", []):
            if oid and oid not in oids:
                oids.append(oid)

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
        ref_names, prompt_text = ip.parse_ref_images(prompt_text)
        ref_urls = ip.resolve_ref_names(reg, ref_names) if ref_names else None
        print(f"  char sheet {cid}: generating (refs: {ref_names}) ...")
        ip.generate_character_sheet(reg, cid, prompt_text=prompt_text, character_fields=fields, ref_urls=ref_urls)

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
        ref_names, prompt_text = ip.parse_ref_images(prompt_text)
        ref_urls = ip.resolve_ref_names(reg, ref_names) if ref_names else None
        print(f"  location lock {lid}: generating (refs: {ref_names}) ...")
        ip.generate_location_lock(reg, lid, prompt_text=prompt_text, location_fields=fields, ref_urls=ref_urls)

    for oid in oids:
        o_path = reg.object_path(oid)
        if _exists(o_path):
            entry = reg.object(oid)
            entry["output_path"] = o_path
            print(f"  object sheet {oid}: exists, skip")
            continue
        txt_path = ip.object_prompt_path(reg.run_dir, oid)
        json_path = txt_path[:-4] + ".json"
        prompt_text, fields = load_object_prompt(txt_path)
        if not prompt_text and not fields and os.path.isfile(json_path):
            _, fields = load_object_prompt(json_path)
        if not prompt_text and not fields:
            raise SystemExit(f"missing object prompt for {oid}: {txt_path} (or .json)")
        ref_names, prompt_text = ip.parse_ref_images(prompt_text)
        ref_urls = ip.resolve_ref_names(reg, ref_names) if ref_names else None
        print(f"  object sheet {oid}: generating (refs: {ref_names}) ...")
        ip.generate_object_sheet(reg, oid, prompt_text=prompt_text, object_fields=fields, ref_urls=ref_urls)
    reg.save()


def _scene_meta(scenes: dict, scene_id: str) -> tuple[int, str | None]:
    """Return (index, prev_scene_id) for a scene_id."""
    scene_list = scenes["scenes"]
    idx = next((i for i, s in enumerate(scene_list) if s["scene_id"] == scene_id), None)
    if idx is None:
        raise SystemExit(f"scene {scene_id} not in scenes.md")
    prev = scene_list[idx - 1]["scene_id"] if idx > 0 else None
    return idx, prev


def build_sheets(reg: ip.AssetRegistry, scenes: dict, scene_id: str) -> None:
    """Generate one storyboard sheet per generation for one scene (edit + refs).

    For normal story generations with a spatial plan: a deterministic spatial
    continuity block is materialized into the sheet prompt text before the
    paid image call. Location panorama attachment is controlled by the
    spatial plan's ``location_reference`` field (attach for g1, omit for later
    generations unless explicitly marked re-establishing).

    Bridge generations (bK) are no longer supported and are skipped.
    Continuity between adjacent generations is handled at render time by
    conditioning each generation on the previous generation's rendered tail.
    """
    idx, prev_scene_id = _scene_meta(scenes, scene_id)
    sb = _storyboard(reg.run_dir, scene_id)
    cast = sb["cast"]
    loc = sb["location_ref_id"] or scenes["scenes"][idx]["location_id"]
    gens = sb["generations"]
    if not gens:
        raise SystemExit(f"storyboard_{scene_id}.md has no generations")

    spatial = _spatial_plan(reg.run_dir, scene_id)
    spatial_gens = spatial["generations"] if spatial else {}

    # Materialize spatial continuity blocks into sheet prompts before generation
    if spatial:
        from tools.spatial_prompt_builder import materialize_sheet_prompt
        for gen in gens:
            if gen.get("is_bridge"):
                continue
            gid = gen["gen_id"]
            if gid not in spatial_gens:
                continue
            sheet_prompt_path = ip.sheet_prompt_path(reg.run_dir, scene_id, gid)
            if not os.path.isfile(sheet_prompt_path):
                continue
            prompt_text = ip.read_prompt(sheet_prompt_path)
            if not prompt_text:
                continue
            materialized = materialize_sheet_prompt(prompt_text, spatial, sb, gid)
            with open(sheet_prompt_path, "w", encoding="utf-8") as f:
                f.write(materialized)
            print(f"  {scene_id}/{gid}: materialized spatial bible")

    # Previous sheet for the FIRST generation = last sheet of the previous scene.
    prev_sheet_id: str | None = None
    if prev_scene_id:
        prev_sb_path = os.path.join(reg.run_dir, f"storyboard_{prev_scene_id}.md")
        if os.path.isfile(prev_sb_path):
            prev_sb = validators.parse_storyboard(open(prev_sb_path, encoding="utf-8").read())
            # Find the last non-bridge generation of the previous scene
            for g in reversed(prev_sb["generations"]):
                if not g.get("is_bridge"):
                    prev_sheet_id = f"{prev_scene_id}_{g['gen_id']}"
                    break

    # Pass 1: story generations (skip bridges)
    is_first_story_gen = True
    for gen in gens:
        if gen.get("is_bridge"):
            continue
        gid = gen["gen_id"]
        sheet_path = reg.sheet_path(scene_id, gid)
        if _exists(sheet_path):
            print(f"  sheet {scene_id}_{gid}: exists, skip")
            prev_sheet_id = f"{scene_id}_{gid}"
            is_first_story_gen = False
            continue

        # Determine location attachment policy from spatial plan
        attach_location = True
        if spatial and gid in spatial_gens:
            sg = spatial_gens[gid]
            loc_ref = sg.get("location_reference", "")
            # g1 always attaches; later gens attach only if explicitly marked
            attach_location = (loc_ref == "attach") if not is_first_story_gen else True
        is_first_story_gen = False

        sheet_prompt = ip.read_prompt(ip.sheet_prompt_path(reg.run_dir, scene_id, gid))
        if not sheet_prompt:
            raise SystemExit(f"missing storyboard sheet prompt for {scene_id}/{gid}")
        ref_names, sheet_prompt = ip.parse_ref_images(sheet_prompt)
        extra_ref_urls = ip.resolve_ref_names(reg, ref_names) if ref_names else []
        print(f"  sheet {scene_id}_{gid}: generating "
              f"(refs: loc={'yes' if attach_location else 'no'} prev={prev_sheet_id} "
              f"chars={cast} extra={ref_names}) ...")
        ip.generate_storyboard_sheet(
            reg, scene_id, gid, prompt_text=sheet_prompt,
            character_ref_ids=cast, location_ref_id=loc, prev_sheet_id=prev_sheet_id,
            extra_ref_urls=extra_ref_urls,
            attach_location=attach_location,
        )
        prev_sheet_id = f"{scene_id}_{gid}"



def main() -> int:
    p = argparse.ArgumentParser(description="Build story-maker-v3 image media")
    p.add_argument("--output-dir", required=True, help="run output dir")
    p.add_argument("--assets-dir", default=None, help="shared assets dir (default: <output-dir>/../assets)")
    p.add_argument("--assets-only", action="store_true", help="only char sheets + location locks")
    p.add_argument("--scene", default=None, help="scene id to build sheets for (→ GATE 1)")
    args = p.parse_args()

    run_dir = os.path.abspath(args.output_dir)
    assets_dir = args.assets_dir or os.path.join(os.path.dirname(run_dir), "assets")
    os.makedirs(run_dir, exist_ok=True)
    os.makedirs(assets_dir, exist_ok=True)

    reg = ip.AssetRegistry(run_dir, assets_dir)
    scenes = _scenes(run_dir)

    if args.assets_only:
        build_assets(reg, scenes)
        return 0
    if not args.scene:
        raise SystemExit("pass --assets-only or --scene <id>")
    build_sheets(reg, scenes, args.scene)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
