"""Storyboard-sheet image pipeline for reel_v2."""
from __future__ import annotations

import asyncio
import json
import os
import shutil

try:
    from google.adk.agents.context import Context
    from google.adk.workflow import FunctionNode
except ImportError:  # pragma: no cover - test fallback without ADK installed
    class Context:  # type: ignore[override]
        pass

    class FunctionNode:  # type: ignore[override]
        def __init__(self, func, name: str):
            self.func = func
            self.name = name

import config
from profiles import get_profile
from tools.grok_tools import generate_grok_edit
from tools.vision_llm import vision_json_from_image
from ._json_util import clean_json_str
from ._shot_image_gen import retry_async, soften_moderation_prompt
from .generation_nodes import (
    _load_specs,
    _only_scenes,
    _save_specs,
    _scene_in_scope,
    _shot_in_scope,
    _url_reachable,
)
from .storyboard_sheet_builder import build_panel_lines, build_storyboard_sheet_prompt as build_template_storyboard_prompt

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MAX_SHEET_CONCURRENCY = int(os.getenv("STORYBOARD_SHEET_CONCURRENCY", "2"))
_MAX_REGEN_CONCURRENCY = int(os.getenv("PANEL_REGEN_CONCURRENCY", "2"))
_PANEL_REGEN_ALLOW_SOFT_FAIL = os.getenv("PANEL_REGEN_ALLOW_SOFT_FAIL", "1").lower() in (
    "1",
    "true",
    "yes",
)


def _load_story(ctx: Context) -> dict:
    raw = ctx.state.get("story_plan_content")
    if not raw:
        path = os.path.join(ctx.state["output_dir"], "story_plan.json")
        with open(path, encoding="utf-8") as f:
            raw = json.dumps(json.load(f))
    return clean_json_str(raw) if isinstance(raw, str) else raw


def _load_prompt_file(name: str) -> str:
    style = (os.getenv("STORY_STYLE") or "").strip().lower()
    candidates: list[str] = []
    if style and style != "cinematic":
        candidates.append(os.path.join(_SKILL_DIR, "prompts", style, f"{name}.md"))
    candidates.append(os.path.join(_SKILL_DIR, "prompts", f"{name}.md"))
    for path in candidates:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
    raise FileNotFoundError(f"Prompt file not found for {name!r}; tried: {candidates}")


def _chunk_shots(shots: list[dict], size: int) -> list[list[dict]]:
    if size <= 0:
        return [shots]
    return [shots[i : i + size] for i in range(0, len(shots), size)]


def _panel_line(shot: dict, index: int) -> str:
    """Backward-compatible single-panel formatter."""
    return build_panel_lines([shot], start_index=index)


def build_storyboard_sheet_prompt(
    scene: dict,
    shots: list[dict],
    *,
    render_style: str,
    template: str | None = None,
    sheet_number: int = 1,
    panels_per_sheet: int = 10,
    story_characters: list[dict] | None = None,
    global_shot_offset: int = 0,
    style_id: str | None = "reel_v2",
) -> str:
    return build_template_storyboard_prompt(
        scene,
        shots,
        sheet_number=sheet_number,
        panels_per_sheet=panels_per_sheet,
        render_style=render_style,
        story_characters=story_characters,
        global_shot_offset=global_shot_offset,
        template=template,
        style_id=style_id,
    )


def _character_ref_urls(specs: dict, character_ids: list[str]) -> list[str]:
    from tools.grok_replicate import upload_local_image

    urls: list[str] = []
    for cid in character_ids:
        entry = specs.get("character_sheets", {}).get(cid, {})
        url = entry.get("fal_image_url") or ""
        local_path = entry.get("output_path")
        needs_upload = (
            not url
            or "replicate.delivery/" in url
            or (
                local_path
                and os.path.isfile(local_path)
                and (
                    "api.replicate.com/v1/files/" not in url
                    and not _url_reachable(url)
                )
            )
        )
        if needs_upload and local_path and os.path.isfile(local_path):
            url = upload_local_image(local_path)
            entry["fal_image_url"] = url
        if url:
            urls.append(url)
    return urls


def _normalize_panels(data: dict, expected: int) -> list[dict]:
    panels = data.get("panels")
    if not isinstance(panels, list):
        raise ValueError(f"Crop analyzer JSON missing panels list: {data!r}")
    if len(panels) != expected:
        raise ValueError(
            f"Crop analyzer returned {len(panels)} panels, expected {expected}"
        )
    normalized: list[dict] = []
    for idx, panel in enumerate(panels):
        if not isinstance(panel, dict):
            raise ValueError(f"Panel {idx} is not an object: {panel!r}")
        try:
            x = float(panel["x"])
            y = float(panel["y"])
            w = float(panel["w"])
            h = float(panel["h"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid bbox for panel {idx}: {panel!r}") from exc
        normalized.append({"x": x, "y": y, "w": w, "h": h})
    return normalized


def _grid_bbox_row_major(panel_index: int, *, cols: int = 5, rows: int = 2) -> dict[str, float]:
    """Deterministic 2×5 row-major fallback when vision crop bboxes are invalid."""
    col = panel_index % cols
    row = panel_index // cols
    w = 1.0 / cols
    h = 1.0 / rows
    return {"x": col * w, "y": row * h, "w": w, "h": h}


def _sanitize_panel_bboxes(bboxes: list[dict]) -> list[dict]:
    """Replace zero-area vision bboxes with grid fallbacks."""
    fixed: list[dict] = []
    for idx, bbox in enumerate(bboxes):
        w = float(bbox.get("w", 0))
        h = float(bbox.get("h", 0))
        if w <= 0 or h <= 0:
            fallback = _grid_bbox_row_major(idx)
            print(
                f"  ⚠️ Panel {idx + 1} bbox invalid ({bbox}) — using grid fallback {fallback}"
            )
            fixed.append(fallback)
        else:
            fixed.append(bbox)
    return fixed


def _load_video_shot_plan(ctx: Context) -> dict:
    raw = ctx.state.get("video_shot_plan_content")
    if not raw:
        path = os.path.join(ctx.state["output_dir"], "video_shot_plan.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                raw = f.read()
    if not raw:
        return {"scenes": []}
    return clean_json_str(raw) if isinstance(raw, str) else raw


def _crop_panel(image_path: str, bbox: dict, out_path: str) -> None:
    from PIL import Image

    with Image.open(image_path) as img:
        width, height = img.size
        left = max(0, int(bbox["x"] * width))
        top = max(0, int(bbox["y"] * height))
        right = min(width, int((bbox["x"] + bbox["w"]) * width))
        bottom = min(height, int((bbox["y"] + bbox["h"]) * height))
        if right <= left or bottom <= top:
            raise ValueError(f"Invalid crop box {bbox} for image {width}x{height}")
        crop = img.crop((left, top, right, bottom))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        crop.save(out_path)


def build_panel_regen_prompt(shot: dict, *, render_style: str) -> str:
    from .save_artifact_nodes import _apply_render_style
    characters = ", ".join(shot.get("characters_present", [])) or "as shown"
    description = shot.get("description", "").strip()
    motion_arc = (shot.get("video_motion_arc") or "").strip()
    camera = shot.get("camera_intent") or shot.get("frame_strategy") or "medium shot"
    prompt = (
        "Recreate this storyboard panel as a single full-frame cinematic animation still "
        "at high resolution. Preserve exact composition, camera angle, character poses, "
        "screen direction, and environment layout from the reference panel. "
        f"Camera: {camera}. Action: {description}. "
        f"Motion arc: {motion_arc}. "
        f"Characters present: {characters}. "
        "No text, labels, captions, shot numbers, or watermarks."
    )
    return _apply_render_style(prompt, render_style)


def _build_safe_panel_regen_prompt(shot: dict, *, render_style: str) -> str:
    from .save_artifact_nodes import _apply_render_style

    description = (shot.get("description") or "").strip()
    camera = shot.get("camera_intent") or shot.get("frame_strategy") or "medium shot"
    prompt = (
        "Recreate this single storyboard panel as a family-friendly stylized animated still. "
        "Preserve composition, framing, screen direction, and environment from the provided panel crop. "
        f"Camera: {camera}. Scene action: {description}. "
        "No text, labels, captions, or watermarks."
    )
    softened = soften_moderation_prompt(prompt, aggressive=True)
    return _apply_render_style(softened, render_style)


async def storyboard_sheet_planner(ctx: Context) -> None:
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    story = _load_story(ctx)
    only_scenes = _only_scenes(ctx)
    panels_per_sheet = int(ctx.state.get("panels_per_sheet") or 10)
    style_id = (ctx.state.get("style_id") or "reel_v2").strip().lower()
    profile = get_profile(style_id)
    render_style = profile.render_style
    story_characters = [
        ch for ch in story.get("characters", []) if isinstance(ch, dict)
    ]
    global_shot_offset = 0

    storyboard_sheets: dict[str, dict] = {}
    for scene in story.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        scene_id = scene.get("scene_id")
        if not scene_id or not _scene_in_scope(scene_id, only_scenes):
            continue
        shots = [
            shot
            for shot in scene.get("shots", [])
            if isinstance(shot, dict)
            and shot.get("shot_id")
            and _shot_in_scope(shot["shot_id"], only_scenes)
        ]
        if not shots:
            continue
        for sheet_index, chunk in enumerate(_chunk_shots(shots, panels_per_sheet), start=1):
            sheet_id = f"{scene_id}_sheet_{sheet_index:02d}"
            char_ids: list[str] = []
            for shot in chunk:
                for cid in shot.get("characters_present", []):
                    if cid and cid not in char_ids:
                        char_ids.append(cid)
            sheet_prompt = build_storyboard_sheet_prompt(
                scene,
                chunk,
                render_style=render_style,
                sheet_number=sheet_index,
                panels_per_sheet=panels_per_sheet,
                story_characters=story_characters,
                global_shot_offset=global_shot_offset,
                style_id=style_id,
            )
            global_shot_offset += len(chunk)
            storyboard_sheets[sheet_id] = {
                "sheet_id": sheet_id,
                "scene_id": scene_id,
                "panel_shot_ids": [shot["shot_id"] for shot in chunk],
                "character_ref_ids": char_ids,
                "panel_count": len(chunk),
                "grid": "2x5",
                "sheet_prompt": sheet_prompt,
                "output_path": os.path.join(
                    output_dir, "storyboard_sheets", f"{sheet_id}.png"
                ),
                "fal_image_url": None,
                "panel_bboxes": [],
                "status": "pending",
            }

    specs["storyboard_sheets"] = storyboard_sheets
    _save_specs(ctx, specs)
    print(
        f"📋 [storyboard_sheet_planner] Planned {len(storyboard_sheets)} storyboard sheet(s)"
    )


async def storyboard_sheet_generator(ctx: Context) -> None:
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    only_scenes = _only_scenes(ctx)
    sheets_dir = os.path.join(output_dir, "storyboard_sheets")
    os.makedirs(sheets_dir, exist_ok=True)
    sem = asyncio.Semaphore(_MAX_SHEET_CONCURRENCY)

    async def _one(sheet_id: str, entry: dict) -> None:
        scene_id = entry.get("scene_id")
        if not _scene_in_scope(scene_id, only_scenes):
            return
        out_path = entry.get("output_path") or os.path.join(sheets_dir, f"{sheet_id}.png")
        if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
            entry["output_path"] = out_path
            entry["status"] = "completed"
            return

        ref_urls = _character_ref_urls(specs, entry.get("character_ref_ids", []))
        if not ref_urls:
            raise RuntimeError(f"No character references available for sheet {sheet_id}")

        prompt_box = [entry.get("sheet_prompt", "")]
        model_id = config.GROK_REPLICATE_MODEL
        print(
            f"  Storyboard sheet: {sheet_id} ({len(ref_urls)} char ref(s)) "
            f"model={model_id} quality=medium text_policy=production_labels"
        )

        def _soften(_err: str, attempt: int) -> None:
            before = prompt_box[0]
            prompt_box[0] = soften_moderation_prompt(before, aggressive=attempt >= 2)
            if prompt_box[0] != before:
                entry["sheet_prompt"] = prompt_box[0]

        async with sem:
            def _gen():
                return generate_grok_edit(
                    prompt_box[0],
                    ref_urls,
                    out_path,
                    size=config.STORYBOARD_SHEET_SIZE,
                    quality="medium",
                    text_policy="production_labels",
                )

            result = await retry_async(
                _gen, f"storyboard sheet {sheet_id}", on_sensitive=_soften
            )

        entry["output_path"] = result["generated_image_path"]
        entry["fal_image_url"] = result["fal_image_url"]
        if result.get("revised_prompt"):
            entry["revised_prompt"] = result["revised_prompt"]
        entry["status"] = "completed"

    sheets = specs.get("storyboard_sheets", {})
    await asyncio.gather(*[_one(sid, entry) for sid, entry in sheets.items()])
    _save_specs(ctx, specs)
    print("✅ [storyboard_sheet_generator] Storyboard sheet generation complete")


def _fallback_panel_bboxes(expected: int) -> list[dict[str, float]]:
    return [_grid_bbox_row_major(i) for i in range(expected)]


async def panel_crop(ctx: Context) -> None:
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    only_scenes = _only_scenes(ctx)
    crops_dir = os.path.join(output_dir, "panel_crops")
    os.makedirs(crops_dir, exist_ok=True)
    analyzer_prompt = _load_prompt_file("storyboard_crop_analyzer")
    crop_model, crop_key, crop_base = config.get_crop_analysis_model_config()

    for sheet_id, entry in specs.get("storyboard_sheets", {}).items():
        scene_id = entry.get("scene_id")
        if not _scene_in_scope(scene_id, only_scenes):
            continue
        sheet_path = entry.get("output_path")
        if not sheet_path or not os.path.isfile(sheet_path):
            raise FileNotFoundError(f"Storyboard sheet image missing for {sheet_id}")

        shot_ids = entry.get("panel_shot_ids", [])
        expected = int(entry.get("panel_count") or len(shot_ids))
        crop_map = entry.get("panel_crops") or {}
        if (
            entry.get("panel_bboxes")
            and len(entry.get("panel_bboxes", [])) == expected
            and all(
                os.path.isfile(crop_map.get(sid, "")) and os.path.getsize(crop_map.get(sid, "")) > 0
                for sid in shot_ids
            )
        ):
            print(f"  Panel crop skip (on disk): {sheet_id}")
            continue

        user_text = json.dumps(
            {
                "expected_panels": expected,
                "grid": "2 rows x 5 columns, row-major order",
                "sheet_id": sheet_id,
            },
            ensure_ascii=False,
        )
        print(f"  Panel crop analyze: {sheet_id} ({expected} panels)")
        try:
            data = await vision_json_from_image(
                sheet_path,
                analyzer_prompt,
                user_text,
                model=crop_model,
                api_key=crop_key,
                api_base=crop_base,
            )
            bboxes = _sanitize_panel_bboxes(_normalize_panels(data, expected))
        except Exception as exc:
            print(
                f"  ⚠️ Panel crop vision failed for {sheet_id} ({exc}) — using 2×5 grid fallback"
            )
            bboxes = _fallback_panel_bboxes(expected)
        entry["panel_bboxes"] = bboxes
        panel_crops: dict[str, str] = {}
        for shot_id, bbox in zip(shot_ids, bboxes, strict=True):
            crop_path = os.path.join(crops_dir, f"{shot_id}.png")
            _crop_panel(sheet_path, bbox, crop_path)
            panel_crops[shot_id] = crop_path
            shot_entry = specs.get("shot_images", {}).get(shot_id, {})
            if isinstance(shot_entry, dict):
                shot_entry["panel_crop_path"] = crop_path
                shot_entry["storyboard_sheet_id"] = sheet_id
        entry["panel_crops"] = panel_crops
        entry["status"] = "cropped"

    _save_specs(ctx, specs)
    print("✅ [panel_crop] Panel cropping complete")


async def panel_regen(ctx: Context) -> None:
    from tools.grok_replicate import upload_local_image

    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    story = _load_story(ctx)
    video_shot_plan = _load_video_shot_plan(ctx)
    only_scenes = _only_scenes(ctx)
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    style_id = (ctx.state.get("style_id") or "reel_v2").strip().lower()
    render_style = get_profile(style_id).render_style
    story_shots: dict[str, dict] = {}
    for scene in story.get("scenes", []):
        for shot in scene.get("shots", []):
            story_shots[shot["shot_id"]] = shot

    anchor_to_motion_arc: dict[str, str] = {}
    if video_shot_plan.get("scenes"):
        for scene in video_shot_plan.get("scenes", []):
            for vshot in scene.get("video_shots", []):
                anchor = vshot.get("anchor_panel_id")
                if anchor:
                    anchor_to_motion_arc[anchor] = str(vshot.get("motion_arc") or "").strip()

    sem = asyncio.Semaphore(_MAX_REGEN_CONCURRENCY)
    shot_failures: list[tuple[str, str]] = []

    async def _one(shot_id: str, entry: dict) -> None:
        if not _shot_in_scope(shot_id, only_scenes):
            return
        if anchor_to_motion_arc and shot_id not in anchor_to_motion_arc:
            entry["status"] = "skipped_non_anchor"
            return
        out_path = os.path.join(images_dir, f"{shot_id}.png")
        if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
            entry["output_path"] = out_path
            entry["status"] = "completed"
            return

        crop_path = entry.get("panel_crop_path")
        if not crop_path or not os.path.isfile(crop_path):
            raise FileNotFoundError(f"Panel crop missing for {shot_id}")

        shot = dict(story_shots.get(shot_id, {}))
        shot["video_motion_arc"] = anchor_to_motion_arc.get(shot_id, "")
        char_ids = shot.get("characters_present", entry.get("characters_present", []))
        char_urls = _character_ref_urls(specs, char_ids)
        crop_url = await asyncio.to_thread(upload_local_image, crop_path)
        ref_urls = [crop_url, *char_urls]
        prompt_box = [build_panel_regen_prompt(shot, render_style=render_style)]
        print(f"  Panel regen: {shot_id} ({len(ref_urls)} ref(s))")

        def _soften(_err: str, attempt: int) -> None:
            before = prompt_box[0]
            prompt_box[0] = soften_moderation_prompt(before, aggressive=attempt >= 2)
            if prompt_box[0] != before:
                entry["image_prompt"] = prompt_box[0]

        try:
            async with sem:
                def _gen():
                    return generate_grok_edit(
                        prompt_box[0],
                        ref_urls,
                        out_path,
                        quality="low",
                    )

                result = await retry_async(
                    _gen, f"panel regen {shot_id}", on_sensitive=_soften
                )
        except Exception as first_exc:
            # Moderation recovery ladder:
            # 1) use an aggressively safety-softened prompt
            # 2) drop character refs (use panel crop only)
            # 3) final fallback: copy panel crop so pipeline keeps producing outputs
            prompt_box[0] = _build_safe_panel_regen_prompt(shot, render_style=render_style)
            entry["image_prompt"] = prompt_box[0]
            print(
                f"  ⚠️ Panel regen primary failed for {shot_id}; "
                "retrying with safe prompt + crop-only reference"
            )
            try:
                async with sem:
                    def _gen_safe():
                        return generate_grok_edit(
                            prompt_box[0],
                            [crop_url],
                            out_path,
                            quality="low",
                            text_policy="no_text",
                        )

                    result = await retry_async(
                        _gen_safe,
                        f"panel regen safe fallback {shot_id}",
                        on_sensitive=_soften,
                    )
            except Exception as safe_exc:
                if not _PANEL_REGEN_ALLOW_SOFT_FAIL:
                    raise
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                shutil.copy2(crop_path, out_path)
                entry["output_path"] = out_path
                entry["fal_image_url"] = None
                entry["panel_crop_url"] = crop_url
                entry["status"] = "completed"
                entry["fallback_mode"] = "copied_panel_crop_after_moderation_failure"
                entry["fallback_reason"] = str(safe_exc)
                shot_failures.append((shot_id, str(safe_exc)))
                print(
                    f"  ⚠️ Panel regen fallback copy used for {shot_id} "
                    "(provider moderation persisted)."
                )
                return

        entry["image_prompt"] = prompt_box[0]
        entry["output_path"] = result["generated_image_path"]
        entry["fal_image_url"] = result["fal_image_url"]
        entry["panel_crop_url"] = crop_url
        if result.get("revised_prompt"):
            entry["revised_prompt"] = result["revised_prompt"]
        entry["status"] = "completed"

    tasks = [
        _one(sid, entry)
        for sid, entry in specs.get("shot_images", {}).items()
        if isinstance(entry, dict)
    ]
    await asyncio.gather(*tasks)
    _save_specs(ctx, specs)
    if shot_failures:
        print(
            f"⚠️ [panel_regen] Used crop fallback for {len(shot_failures)} shot(s): "
            + ", ".join(sid for sid, _ in shot_failures)
        )
    print("✅ [panel_regen] Panel regeneration complete")


storyboard_sheet_planner_node = FunctionNode(
    func=storyboard_sheet_planner, name="storyboard_sheet_planner_node"
)
storyboard_sheet_generator_node = FunctionNode(
    func=storyboard_sheet_generator, name="storyboard_sheet_generator_node"
)
panel_crop_node = FunctionNode(func=panel_crop, name="panel_crop_node")
panel_regen_node = FunctionNode(func=panel_regen, name="panel_regen_node")
