"""Reference integrity for Grok Edit shot specs."""
import json

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

import config
from ._json_util import clean_json_str


def _scene_bg_modes(scene_assets: dict) -> dict[str, str]:
    modes = {}
    for scene in scene_assets.get("scenes", []):
        if isinstance(scene, dict):
            modes[scene["scene_id"]] = scene.get("background_reference_mode", "style_anchor")
    return modes


def _shot_scene_map(story: dict) -> dict[str, str]:
    mapping = {}
    for scene in story.get("scenes", []):
        for shot in scene.get("shots", []):
            mapping[shot["shot_id"]] = scene["scene_id"]
    return mapping


def _char_priority(slots: list, asset_ref: str) -> int:
    for slot in slots:
        if not isinstance(slot, dict) or slot.get("role") != "character_sheet":
            continue
        aid = slot.get("asset_id", "")
        if aid and aid in asset_ref:
            return int(slot.get("priority", 0))
    return 999


def _truncate_refs(
    refs: list[str],
    slots: list,
    *,
    limit: int,
    reserve_bg: bool,
) -> tuple[list[str], list[str]]:
    """Truncate refs by slot priority; optionally reserve one background slot."""
    if len(refs) <= limit:
        return refs, []

    char_refs = [r for r in refs if "character_sheets" in r]
    bg_refs = [r for r in refs if "backgrounds" in r]
    char_refs.sort(key=lambda r: _char_priority(slots, r))

    kept: list[str] = []
    dropped: list[str] = []

    bg_budget = 1 if reserve_bg and bg_refs else 0
    char_budget = max(0, limit - bg_budget)
    kept_chars = char_refs[:char_budget]
    dropped_chars = char_refs[char_budget:]
    kept.extend(kept_chars)
    dropped.extend(dropped_chars)

    if bg_budget and bg_refs:
        kept.append(bg_refs[0])
        dropped.extend(bg_refs[1:])
    elif bg_refs:
        dropped.extend(bg_refs)

    return kept[:limit], dropped


async def reference_integrity(ctx: Context) -> None:
    story_raw = ctx.state.get("story_plan_content")
    specs_raw = ctx.state.get("generation_specs_content")
    scene_raw = ctx.state.get("scene_assets_content")
    if not story_raw or not specs_raw:
        print("⚠️ [reference_integrity] missing story_plan or generation_specs")
        return

    story = clean_json_str(story_raw) if isinstance(story_raw, str) else story_raw
    specs = clean_json_str(specs_raw) if isinstance(specs_raw, str) else specs_raw
    scene_assets = clean_json_str(scene_raw) if scene_raw else {}
    if isinstance(scene_assets, str):
        scene_assets = clean_json_str(scene_assets)

    ref_limit = config.get_image_ref_limit()
    bg_modes = _scene_bg_modes(scene_assets)
    shot_scenes = _shot_scene_map(story)

    shot_chars = {}
    for scene in story.get("scenes", []):
        for shot in scene.get("shots", []):
            shot_chars[shot["shot_id"]] = shot.get("characters_present", [])

    shot_images = specs.get("shot_images", {})
    repaired = False

    for shot_id, entry in shot_images.items():
        if not isinstance(entry, dict):
            continue
        mode = entry.get("generation_mode", "grok_edit")
        strategy = entry.get("reference_strategy", "char_sheets_only")
        present = shot_chars.get(shot_id, [])
        slots = entry.get("reference_slots", [])
        scene_id = shot_scenes.get(shot_id, "")
        bg_mode = bg_modes.get(scene_id, "style_anchor")

        refs = []
        if mode == "grok_t2i" or strategy == "no_references":
            entry["reference_images"] = []
            entry["generation_mode"] = "grok_t2i"
            entry["reference_strategy"] = "no_references"
            repaired = True
            continue

        for slot in sorted(slots, key=lambda s: s.get("priority", 0)):
            if not isinstance(slot, dict):
                continue
            role = slot.get("role")
            asset_id = slot.get("asset_id")
            if role == "character_sheet" and asset_id in present:
                refs.append(f"{{{{character_sheets.{asset_id}.fal_image_url}}}}")
            elif role == "scene_background" and bg_mode == "full_plate":
                backgrounds = specs.get("backgrounds", {})
                bg_key = asset_id if asset_id in backgrounds else scene_id
                if bg_key in backgrounds:
                    if slot.get("asset_id") != bg_key:
                        slot["asset_id"] = bg_key
                    refs.append(f"{{{{backgrounds.{bg_key}.fal_image_url}}}}")

        if bg_mode == "style_anchor":
            strategy = "char_sheets_only" if present else "no_references"
            slots = [s for s in slots if s.get("role") != "scene_background"]
            entry["reference_slots"] = slots
            refs = [r for r in refs if r.startswith("{{character_sheets.")]

        if strategy == "char_sheets_only":
            refs = [r for r in refs if r.startswith("{{character_sheets.")]
            for cid in present:
                expected = f"{{{{character_sheets.{cid}.fal_image_url}}}}"
                if expected not in refs:
                    refs.append(expected)
            if not present:
                entry["reference_images"] = []
                entry["generation_mode"] = "grok_t2i"
                entry["reference_strategy"] = "no_references"
                repaired = True
                continue
        elif strategy == "char_sheets_and_background":
            char_refs = [r for r in refs if r.startswith("{{character_sheets.")]
            bg_refs = [r for r in refs if r.startswith("{{backgrounds.")]
            if not bg_refs and scene_id in specs.get("backgrounds", {}):
                bg_refs = [f"{{{{backgrounds.{scene_id}.fal_image_url}}}}"]
            for cid in present:
                expected = f"{{{{character_sheets.{cid}.fal_image_url}}}}"
                if expected not in char_refs:
                    char_refs.append(expected)
            refs = char_refs + bg_refs

        reserve_bg = strategy == "char_sheets_and_background" and bg_mode == "full_plate"
        if len(refs) > ref_limit:
            refs, dropped = _truncate_refs(
                refs, slots, limit=ref_limit, reserve_bg=reserve_bg
            )
            print(
                f"⚠️ [reference_integrity] Truncated {shot_id} to {len(refs)}/{ref_limit} refs"
                + (f" (dropped {len(dropped)})" if dropped else "")
            )

        entry["reference_images"] = refs
        entry["reference_strategy"] = strategy
        if not refs:
            entry["generation_mode"] = "grok_t2i"
            entry["reference_strategy"] = "no_references"
        else:
            entry["generation_mode"] = "grok_edit"
        repaired = True

    if repaired:
        specs["shot_images"] = shot_images
        ctx.state["generation_specs_content"] = json.dumps(specs, indent=2, ensure_ascii=False)
        output_dir = ctx.state.get("output_dir")
        if output_dir:
            path = f"{output_dir}/generation_specs.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(specs, f, indent=2, ensure_ascii=False)


reference_integrity_node = FunctionNode(
    func=reference_integrity, name="reference_integrity_node"
)
