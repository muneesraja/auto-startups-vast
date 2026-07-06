"""Generation FunctionNodes — fal.ai images, ComfyUI videos, ffmpeg concat."""
import asyncio
import json
import os

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from tools.comfyui_tools import generate_ltx_i2v_video
from tools.video_concat import concat_videos
from ._json_util import clean_json_str
from ._shot_image_gen import (
    generate_one_shot_image,
    retry_async,
    soften_moderation_prompt,
)

_MAX_CONCURRENCY = int(os.getenv("GROK_IMAGE_CONCURRENCY", "1"))


def _image_concurrency() -> int:
    try:
        import config

        if config.get_image_provider() == "replicate":
            return _MAX_CONCURRENCY
    except Exception:
        pass
    return 4


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


async def generation_router(ctx: Context) -> None:
    if bool(ctx.state.get("stop_before_generation", False)):
        print(
            "⏸️ [generation_router] stop_before_generation — "
            "images + vision motion prompts only (no LTX video)"
        )
    ctx.route = "generate"


async def generate_backgrounds(ctx: Context) -> None:
    import config
    from tools.fal_tools import generate_grok_t2i
    from .reference_integrity_node import reference_integrity

    # Repair reference_images on resume (planning path already ran this node).
    await reference_integrity(ctx)

    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    only_scenes = _only_scenes(ctx)
    bg_dir = os.path.join(output_dir, "backgrounds")
    os.makedirs(bg_dir, exist_ok=True)

    from tools.grok_replicate import upload_local_image

    for scene_id, entry in specs.get("backgrounds", {}).items():
        if not _scene_in_scope(scene_id, only_scenes):
            continue
        out_path = os.path.join(bg_dir, f"{scene_id}.png")
        local_path = entry.get("output_path") or out_path
        if os.path.isfile(local_path) and os.path.getsize(local_path) > 0:
            url = entry.get("fal_image_url") or ""
            needs_upload = (
                not url
                or "replicate.delivery/" in url
                or (
                    "api.replicate.com/v1/files/" not in url
                    and not _url_reachable(url)
                )
            )
            if needs_upload:
                print(f"  Re-uploading background: {scene_id}")
                url = await asyncio.to_thread(upload_local_image, local_path)
            entry["output_path"] = local_path
            entry["fal_image_url"] = url
            entry["status"] = "completed"
            _save_specs(ctx, specs)
            print(f"  Background skip (on disk): {scene_id}")
            continue
        prompt_box = [entry.get("background_prompt", "")]
        print(f"  Background T2I: {scene_id}")

        def _gen(path=out_path):
            return generate_grok_t2i(
                prompt_box[0], path, size=config.BACKGROUND_IMAGE_SIZE
            )

        def _soften(_err: str, attempt: int) -> None:
            before = prompt_box[0]
            prompt_box[0] = soften_moderation_prompt(before, aggressive=attempt >= 2)
            if prompt_box[0] != before:
                entry["background_prompt"] = prompt_box[0]
                print(f"   Softened background prompt for moderation: {scene_id}")

        result = await retry_async(
            _gen, f"background {scene_id}", on_sensitive=_soften
        )
        entry["output_path"] = result["generated_image_path"]
        entry["fal_image_url"] = result["fal_image_url"]
        if result.get("revised_prompt"):
            entry["revised_prompt"] = result["revised_prompt"]
        entry["status"] = "completed"
        _save_specs(ctx, specs)

    _save_specs(ctx, specs)


def _url_reachable(url: str) -> bool:
    if not url or not str(url).startswith("http"):
        return False
    try:
        import httpx

        resp = httpx.head(url, timeout=15.0, follow_redirects=True)
        if resp.status_code < 400:
            return True
        # Some CDNs reject HEAD; try a tiny GET range.
        resp = httpx.get(url, timeout=15.0, follow_redirects=True, headers={"Range": "bytes=0-0"})
        return resp.status_code < 400
    except Exception:
        return False


async def generate_character_sheets(ctx: Context) -> None:
    from tools.fal_tools import generate_grok_t2i
    from tools.grok_replicate import upload_local_image

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
        local_path = entry.get("output_path") or out_path
        if os.path.isfile(local_path) and os.path.getsize(local_path) > 0:
            url = entry.get("fal_image_url") or ""
            # replicate.delivery URLs expire; prefer durable Files API URLs.
            needs_upload = (
                not url
                or "replicate.delivery/" in url
                or (
                    "api.replicate.com/v1/files/" not in url
                    and not _url_reachable(url)
                )
            )
            if needs_upload:
                print(f"  Re-uploading character sheet: {cid}")
                url = await asyncio.to_thread(upload_local_image, local_path)
            entry["output_path"] = local_path
            entry["fal_image_url"] = url
            entry["status"] = "completed"
            _save_specs(ctx, specs)
            continue
        prompt_box = [entry.get("sheet_prompt", "")]
        # Pre-soften infant language — GPT Image 2 often flags "baby" sheets.
        prompt_box[0] = soften_moderation_prompt(prompt_box[0])
        entry["sheet_prompt"] = prompt_box[0]
        print(f"  Character sheet: {cid}")

        def _gen(path=out_path):
            return generate_grok_t2i(prompt_box[0], path)

        def _soften(_err: str, attempt: int) -> None:
            before = prompt_box[0]
            prompt_box[0] = soften_moderation_prompt(before, aggressive=attempt >= 2)
            if prompt_box[0] != before:
                entry["sheet_prompt"] = prompt_box[0]
                print(f"   Softened sheet prompt for moderation: {cid}")

        result = await retry_async(
            _gen, f"char sheet {cid}", on_sensitive=_soften
        )
        entry["output_path"] = result["generated_image_path"]
        entry["fal_image_url"] = result["fal_image_url"]
        if result.get("revised_prompt"):
            entry["revised_prompt"] = result["revised_prompt"]
        entry["status"] = "completed"
        _save_specs(ctx, specs)

    _save_specs(ctx, specs)


async def generate_shot_images(ctx: Context) -> None:
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    only_scenes = _only_scenes(ctx)
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    sem = asyncio.Semaphore(_image_concurrency())

    async def _one(shot_id: str, entry: dict):
        if not _shot_in_scope(shot_id, only_scenes):
            return
        out_path = os.path.join(images_dir, f"{shot_id}.png")
        if (
            entry.get("image_qa_status") == "passed"
            and entry.get("fal_image_url")
            and os.path.isfile(entry.get("output_path") or out_path)
        ):
            return
        if entry.get("fal_image_url") and os.path.isfile(entry.get("output_path") or out_path):
            return
        async with sem:
            await generate_one_shot_image(shot_id, entry, specs, images_dir)

    tasks = [
        _one(shot_id, entry)
        for shot_id, entry in specs.get("shot_images", {}).items()
        if isinstance(entry, dict)
    ]
    await asyncio.gather(*tasks)
    _save_specs(ctx, specs)


async def generate_videos(ctx: Context) -> None:
    if bool(ctx.state.get("stop_before_generation", False)):
        return
    output_dir = ctx.state["output_dir"]
    specs = _load_specs(ctx)
    videos_dir = os.path.join(output_dir, "videos")
    os.makedirs(videos_dir, exist_ok=True)
    sem = asyncio.Semaphore(_image_concurrency())

    async def _one(shot_id: str, entry: dict):
        out_path = os.path.join(videos_dir, f"{shot_id}.mp4")
        if (
            entry.get("motion_qa_status") == "passed"
            and entry.get("output_path")
            and os.path.isfile(entry["output_path"])
        ):
            return
        if entry.get("output_path") and os.path.isfile(entry["output_path"]):
            return
        motion = specs.get("motion", {}).get(shot_id, {})
        image_entry = specs.get("shot_images", {}).get(shot_id, {})
        image_path = image_entry.get("output_path")
        if not image_path or not os.path.isfile(image_path):
            raise RuntimeError(f"Missing image for {shot_id}")

        motion_prompt = (motion.get("motion_prompt") or "").strip()
        if not motion_prompt:
            raise RuntimeError(
                f"Missing motion_prompt for {shot_id} — run vision_motion_prompter first"
            )
        duration = motion.get("duration_seconds", 8)

        async with sem:
            print(f"  Video I2V: {shot_id}")

            def _gen():
                return generate_ltx_i2v_video(
                    image_path, motion_prompt, out_path, duration_seconds=duration
                )

            result = await retry_async(_gen, f"video {shot_id}")
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
