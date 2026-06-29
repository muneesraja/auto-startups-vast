"""Generation FunctionNodes — fal.ai images, ComfyUI videos, ffmpeg concat."""
import asyncio
import json
import os
import re

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from tools.comfyui_tools import generate_ltx_i2v_video
from tools.fal_tools import generate_grok_edit, generate_grok_t2i
from tools.video_concat import concat_videos
from ._json_util import clean_json_str

_REF_PATTERN = re.compile(r"\{\{+([^}]+)\}\}+")
_MAX_CONCURRENCY = 4
_MAX_RETRIES = 3


def _only_scenes(ctx: Context) -> list[str] | None:
    scenes = ctx.state.get("only_scenes")
    if not scenes:
        return None
    return [s for s in scenes if s]


def _shot_in_scope(shot_id: str, only_scenes: list[str] | None) -> bool:
    if not only_scenes:
        return True
    return any(shot_id.startswith(f"{scene_id}_") for scene_id in only_scenes)


def _scene_in_scope(scene_id: str, only_scenes: list[str] | None) -> bool:
    if not only_scenes:
        return True
    return scene_id in only_scenes


def _chars_in_scope(specs: dict, only_scenes: list[str] | None) -> set[str]:
    if not only_scenes:
        return set(specs.get("character_sheets", {}).keys())
    char_ids: set[str] = set()
    for shot_id, entry in specs.get("shot_images", {}).items():
        if not _shot_in_scope(shot_id, only_scenes):
            continue
        for slot in entry.get("reference_slots", []):
            if slot.get("role") == "character_sheet":
                char_ids.add(slot["asset_id"])
    return char_ids


def _load_specs(ctx: Context) -> dict:
    raw = ctx.state.get("generation_specs_content")
    if not raw:
        path = os.path.join(ctx.state["output_dir"], "generation_specs.json")
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    return clean_json_str(raw) if isinstance(raw, str) else raw


def _save_specs(ctx: Context, specs: dict) -> None:
    ctx.state["generation_specs_content"] = json.dumps(specs, indent=2, ensure_ascii=False)
    path = os.path.join(ctx.state["output_dir"], "generation_specs.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(specs, f, indent=2, ensure_ascii=False)


def _resolve_ref(ref_str: str, specs: dict) -> str:
    if not isinstance(ref_str, str):
        return ref_str
    match = _REF_PATTERN.search(ref_str)
    if not match:
        return ref_str
    parts = match.group(1).strip().split(".")
    if len(parts) != 3:
        return ref_str
    namespace, key, field = parts
    val = specs.get(namespace, {}).get(key, {}).get(field)
    if not val:
        raise KeyError(f"Unresolved reference: {ref_str}")
    return val


async def _retry(fn, label: str):
    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        result = await asyncio.to_thread(fn)
        if result.get("status") == "success":
            return result
        last_err = result.get("message", "unknown error")
        print(f"   Retry {attempt}/{_MAX_RETRIES} {label}: {last_err}")
        await asyncio.sleep(2 * attempt)
    raise RuntimeError(f"{label} failed: {last_err}")


async def generation_router(ctx: Context) -> None:
    if bool(ctx.state.get("stop_before_generation", False)):
        print("⏸️ [generation_router] stop_before_generation — skipping generation")
        ctx.route = "stop"
        return
    ctx.route = "generate"


async def generate_backgrounds(ctx: Context) -> None:
    if bool(ctx.state.get("stop_before_generation", False)):
        return
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    only_scenes = _only_scenes(ctx)
    bg_dir = os.path.join(output_dir, "backgrounds")
    os.makedirs(bg_dir, exist_ok=True)

    for scene_id, entry in specs.get("backgrounds", {}).items():
        if not _scene_in_scope(scene_id, only_scenes):
            continue
        out_path = os.path.join(bg_dir, f"{scene_id}.png")
        if entry.get("fal_image_url") and os.path.isfile(entry.get("output_path") or ""):
            continue
        prompt = entry.get("background_prompt", "")
        print(f"  Background T2I: {scene_id}")

        def _gen(p=prompt, path=out_path):
            return generate_grok_t2i(p, path)

        result = await _retry(_gen, f"background {scene_id}")
        entry["output_path"] = result["generated_image_path"]
        entry["fal_image_url"] = result["fal_image_url"]
        entry["status"] = "completed"

    _save_specs(ctx, specs)


async def generate_character_sheets(ctx: Context) -> None:
    if bool(ctx.state.get("stop_before_generation", False)):
        return
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    only_scenes = _only_scenes(ctx)
    chars_in_scope = _chars_in_scope(specs, only_scenes)
    chars_dir = os.path.join(output_dir, "characters")
    os.makedirs(chars_dir, exist_ok=True)

    for cid, entry in specs.get("character_sheets", {}).items():
        if cid not in chars_in_scope:
            continue
        out_path = os.path.join(chars_dir, f"{cid}.png")
        if entry.get("fal_image_url") and os.path.isfile(entry.get("output_path") or ""):
            continue
        prompt = entry.get("sheet_prompt", "")
        print(f"  Character sheet: {cid}")

        def _gen(p=prompt, path=out_path):
            return generate_grok_t2i(p, path)

        result = await _retry(_gen, f"char sheet {cid}")
        entry["output_path"] = result["generated_image_path"]
        entry["fal_image_url"] = result["fal_image_url"]
        entry["status"] = "completed"

    _save_specs(ctx, specs)


async def generate_shot_images(ctx: Context) -> None:
    if bool(ctx.state.get("stop_before_generation", False)):
        return
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    only_scenes = _only_scenes(ctx)
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    for shot_id, entry in specs.get("shot_images", {}).items():
        if not _shot_in_scope(shot_id, only_scenes):
            continue
        out_path = os.path.join(images_dir, f"{shot_id}.png")
        if entry.get("fal_image_url") and os.path.isfile(entry.get("output_path") or ""):
            continue
        mode = entry.get("generation_mode", "grok_edit")
        prompt = entry.get("image_prompt", "")
        print(f"  Shot image: {shot_id} ({mode})")

        if mode == "grok_t2i":
            def _gen(p=prompt, path=out_path):
                return generate_grok_t2i(p, path)

            result = await _retry(_gen, f"shot t2i {shot_id}")
        else:
            ref_urls = []
            for ref in entry.get("reference_images", []):
                ref_urls.append(_resolve_ref(ref, specs))

            def _gen(p=prompt, urls=ref_urls, path=out_path):
                return generate_grok_edit(p, urls, path)

            result = await _retry(_gen, f"shot edit {shot_id}")

        entry["output_path"] = result["generated_image_path"]
        entry["fal_image_url"] = result["fal_image_url"]
        entry["status"] = "completed"

    _save_specs(ctx, specs)


async def generate_videos(ctx: Context) -> None:
    if bool(ctx.state.get("stop_before_generation", False)):
        return
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    videos_dir = os.path.join(output_dir, "videos")
    os.makedirs(videos_dir, exist_ok=True)
    sem = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _one(shot_id: str, entry: dict):
        out_path = os.path.join(videos_dir, f"{shot_id}.mp4")
        if entry.get("output_path") and os.path.isfile(entry["output_path"]):
            return
        motion = specs.get("motion", {}).get(shot_id, {})
        image_entry = specs.get("shot_images", {}).get(shot_id, {})
        image_path = image_entry.get("output_path")
        if not image_path or not os.path.isfile(image_path):
            raise RuntimeError(f"Missing image for {shot_id}")

        async with sem:
            print(f"  Video I2V: {shot_id}")
            motion_prompt = motion.get("motion_prompt", "")
            duration = motion.get("duration_seconds", 8)

            def _gen():
                return generate_ltx_i2v_video(
                    image_path, motion_prompt, out_path, duration_seconds=duration
                )

            result = await _retry(_gen, f"video {shot_id}")
            entry["output_path"] = result["video_path"]
            entry["status"] = "completed"

    tasks = []
    only_scenes = _only_scenes(ctx)
    for shot_id, entry in specs.get("motion", {}).items():
        if not isinstance(entry, dict):
            continue
        if not _shot_in_scope(shot_id, only_scenes):
            continue
        tasks.append(_one(shot_id, entry))
    await asyncio.gather(*tasks)
    _save_specs(ctx, specs)


async def concat_final_film(ctx: Context) -> None:
    if bool(ctx.state.get("stop_before_generation", False)):
        return
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    story_raw = ctx.state.get("story_plan_content")
    if not story_raw:
        with open(os.path.join(output_dir, "story_plan.json"), encoding="utf-8") as f:
            story_raw = json.dumps(json.load(f))
    story = clean_json_str(story_raw)
    only_scenes = _only_scenes(ctx)

    video_paths = []
    for scene in story.get("scenes", []):
        scene_id = scene.get("scene_id")
        if not _scene_in_scope(scene_id, only_scenes):
            continue
        for shot in scene.get("shots", []):
            sid = shot["shot_id"]
            motion = specs.get("motion", {}).get(sid, {})
            path = motion.get("output_path")
            if not path or not os.path.isfile(path):
                raise RuntimeError(f"Missing video for {sid}")
            video_paths.append(path)

    if only_scenes:
        final_name = f"{'_'.join(only_scenes)}_film.mp4"
    else:
        final_name = "final_film.mp4"
    final_path = os.path.join(output_dir, final_name)
    if os.path.isfile(final_path):
        print(f"  Skip existing {final_path}")
        return

    print(f"  Concat {len(video_paths)} videos")
    result = await asyncio.to_thread(concat_videos, video_paths, final_path)
    if result.get("status") != "success":
        raise RuntimeError(result.get("message", "concat failed"))


generation_router_node = FunctionNode(func=generation_router, name="generation_router_node")
background_generator_node = FunctionNode(
    func=generate_backgrounds, name="background_generator_node"
)
character_sheet_generator_node = FunctionNode(
    func=generate_character_sheets, name="character_sheet_generator_node"
)
shot_image_generator_node = FunctionNode(
    func=generate_shot_images, name="shot_image_generator_node"
)
video_generator_node = FunctionNode(func=generate_videos, name="video_generator_node")
concat_videos_node = FunctionNode(func=concat_final_film, name="concat_videos_node")
