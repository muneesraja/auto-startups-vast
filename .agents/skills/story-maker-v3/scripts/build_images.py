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


def _exists(path: str) -> bool:
    return bool(path) and os.path.isfile(path) and os.path.getsize(path) > 0


def _inspiration_urls(reg: ip.AssetRegistry, filter_keyword: str | None = None) -> list[str]:
    urls: list[str] = []
    for iid in sorted(reg.data.get("inspirations", {})):
        if filter_keyword and filter_keyword.lower() not in iid.lower():
            continue
        url = ip.ensure_asset_url(reg.inspiration_asset(iid))
        if url and url not in urls:
            urls.append(url)
    return urls


def _build_character_asset(reg: ip.AssetRegistry, cid: str) -> None:
    c_path = reg.character_path(cid)
    if _exists(c_path):
        entry = reg.character(cid)
        entry["output_path"] = c_path
        print(f"  char sheet {cid}: exists, skip")
        return
    txt_path = ip.character_prompt_path(reg.run_dir, cid)
    json_path = txt_path[:-4] + ".json"
    prompt_text, fields = load_character_prompt(txt_path)
    if not prompt_text and not fields and os.path.isfile(json_path):
        _, fields = load_character_prompt(json_path)
    if not prompt_text and not fields:
        raise SystemExit(f"missing char prompt for {cid}: {txt_path} (or .json)")
    ref_urls = _inspiration_urls(reg)
    print(f"  char sheet {cid}: generating (refs={len(ref_urls)}) ...")
    ip.generate_character_sheet(reg, cid, prompt_text=prompt_text, character_fields=fields, ref_image_urls=ref_urls or None)


def _build_location_asset(reg: ip.AssetRegistry, lid: str) -> None:
    l_path = reg.location_path(lid)
    if _exists(l_path):
        entry = reg.location(lid)
        entry["output_path"] = l_path
        print(f"  location lock {lid}: exists, skip")
        return
    txt_path = ip.location_prompt_path(reg.run_dir, lid)
    json_path = txt_path[:-4] + ".json"
    prompt_text, fields = load_location_prompt(txt_path)
    if not prompt_text and not fields and os.path.isfile(json_path):
        _, fields = load_location_prompt(json_path)
    if not prompt_text and not fields:
        raise SystemExit(f"missing location prompt for {lid}: {txt_path} (or .json)")
    ref_urls = _inspiration_urls(reg, filter_keyword="style")
    print(f"  location lock {lid}: generating (refs={len(ref_urls)}) ...")
    ip.generate_location_lock(reg, lid, prompt_text=prompt_text, location_fields=fields, ref_image_urls=ref_urls or None)


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
    jobs = [
        *(lambda cid=cid: _build_character_asset(reg, cid) for cid in cids),
        *(lambda lid=lid: _build_location_asset(reg, lid) for lid in lids),
    ]
    ip.run_image_jobs(list(jobs))
    reg.save()


def build_objects(reg: ip.AssetRegistry, obj_ids: list[str] | None = None) -> None:
    """Generate object/prop sheets (4K)."""
    prompts_dir = os.path.join(reg.run_dir, "image_prompts", "objects")
    assets_obj_dir = os.path.join(reg.assets_dir, "objects")
    candidates: list[str] = []
    if obj_ids:
        candidates = list(obj_ids)
    else:
        for sdir in (prompts_dir, assets_obj_dir):
            if os.path.isdir(sdir):
                for fname in os.listdir(sdir):
                    if fname.endswith((".txt", ".json")) and not fname.startswith("."):
                        base = os.path.splitext(fname)[0]
                        oid = base[:-7] if base.endswith("_prompt") else base
                        if oid not in candidates:
                            candidates.append(oid)
    if not candidates:
        return

    def build_one(oid: str) -> None:
        o_path = reg.object_path(oid)
        if _exists(o_path):
            entry = reg.object_asset(oid)
            entry["output_path"] = o_path
            print(f"  object sheet {oid}: exists, skip")
            return
        prompt_text = ""
        fields = None
        for ppath in (
            os.path.join(prompts_dir, f"{oid}.txt"),
            os.path.join(prompts_dir, f"{oid}.json"),
            os.path.join(assets_obj_dir, f"{oid}_prompt.txt"),
            os.path.join(assets_obj_dir, f"{oid}.txt"),
            os.path.join(reg.run_dir, "image_prompts", f"{oid}.txt"),
        ):
            if os.path.isfile(ppath):
                prompt_text, fields = load_object_prompt(ppath)
                if prompt_text or fields:
                    break
        if not prompt_text and not fields:
            print(f"  object sheet {oid}: no prompt found, skip")
            return
        print(f"  object sheet {oid}: generating (4K) ...")
        ip.generate_object_sheet(reg, oid, prompt_text=prompt_text, object_fields=fields)

    ip.run_image_jobs([lambda oid=oid: build_one(oid) for oid in candidates])
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
    """Generate one storyboard sheet per generation for one scene (edit + refs)."""
    idx, prev_scene_id = _scene_meta(scenes, scene_id)
    sb = _storyboard(reg.run_dir, scene_id)
    cast = sb["cast"]
    loc = sb["location_ref_id"] or scenes["scenes"][idx]["location_id"]
    gens = sb["generations"]
    if not gens:
        raise SystemExit(f"storyboard_{scene_id}.md has no generations")

    # Previous sheet for the FIRST generation = last sheet of the previous scene.
    prev_sheet_id: str | None = None
    if prev_scene_id:
        prev_sb_path = os.path.join(reg.run_dir, f"storyboard_{prev_scene_id}.md")
        if os.path.isfile(prev_sb_path):
            prev_sb = validators.parse_storyboard(open(prev_sb_path, encoding="utf-8").read())
            if prev_sb["generations"]:
                prev_sheet_id = f"{prev_scene_id}_{prev_sb['generations'][-1]['gen_id']}"

    for gen in gens:
        gid = gen["gen_id"]
        sheet_path = reg.sheet_path(scene_id, gid)
        if _exists(sheet_path):
            print(f"  sheet {scene_id}_{gid}: exists, skip")
            prev_sheet_id = f"{scene_id}_{gid}"
            continue
        sheet_prompt = ip.read_prompt(ip.sheet_prompt_path(reg.run_dir, scene_id, gid))
        if not sheet_prompt:
            raise SystemExit(f"missing storyboard sheet prompt for {scene_id}/{gid}")
        print(f"  sheet {scene_id}_{gid}: generating (refs: loc={loc} prev={prev_sheet_id} chars={cast}) ...")
        ip.generate_storyboard_sheet(
            reg, scene_id, gid, prompt_text=sheet_prompt,
            character_ref_ids=cast, location_ref_id=loc, prev_sheet_id=prev_sheet_id,
        )
        prev_sheet_id = f"{scene_id}_{gid}"


def main() -> int:
    p = argparse.ArgumentParser(description="Build story-maker-v3 image media")
    p.add_argument("--output-dir", required=True, help="run output dir")
    p.add_argument("--assets-dir", default=None, help="shared assets dir (default: <output-dir>/../assets)")
    p.add_argument("--assets-only", action="store_true", help="only char sheets + location locks")
    p.add_argument("--objects", action="store_true", help="build object/prop asset sheets")
    p.add_argument("--scene", default=None, help="scene id to build sheets for (→ GATE 1)")
    args = p.parse_args()

    run_dir = os.path.abspath(args.output_dir)
    assets_dir = args.assets_dir or os.path.join(os.path.dirname(run_dir), "assets")
    os.makedirs(run_dir, exist_ok=True)
    os.makedirs(assets_dir, exist_ok=True)

    reg = ip.AssetRegistry(run_dir, assets_dir)
    scenes = _scenes(run_dir)

    if args.objects:
        build_objects(reg)
        return 0
    if args.assets_only:
        build_assets(reg, scenes)
        build_objects(reg)
        return 0
    if not args.scene:
        raise SystemExit("pass --assets-only or --scene <id>")
    build_sheets(reg, scenes, args.scene)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
