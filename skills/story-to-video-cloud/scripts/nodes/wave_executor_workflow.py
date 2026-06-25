"""Nested Workflow that executes Wave 1 and Wave 2 of image/video tasks with bounded parallelism.

Uses Grok Imagine (via fal.ai API) for image generation, LTX-2.3 for video,
and handles auto-uploading of locally extracted frames to fal.ai.
"""
import os
import json
import re
import asyncio
import traceback
import fal_client

from google.adk import Workflow
from google.adk.workflow import FunctionNode, JoinNode, START, RetryConfig

from tools.fal_tools import generate_grok_t2i, generate_grok_edit
from tools.comfyui_tools import generate_ltx_video, extract_last_frame

# Lock guarding all writes to prompts.json during wave execution. Lock is process-wide.
_PROMPTS_FILE_LOCK = asyncio.Lock()

# Bound for simultaneous calls.
_MAX_CONCURRENCY = 4

# Retry policy for transient ComfyUI / API failures.
API_RETRY_CONFIG = RetryConfig(
    max_attempts=5,
    initial_delay=1.0,
    max_delay=60.0,
    backoff_factor=2.0,
    jitter=1.0,
    exceptions=[RuntimeError, TimeoutError, OSError, ConnectionError, json.JSONDecodeError],
)

_REF_PATTERN = re.compile(r"\{\{+([^}]+)\}\}+")


def _resolve_ref(ref_str, prompts_data):
    """Resolve references like {{character_sheets.char_01.fal_image_url}} dynamically."""
    if not isinstance(ref_str, str):
        return ref_str
    match = _REF_PATTERN.search(ref_str)
    if not match:
        return ref_str
    parts = match.group(1).strip().split(".")
    if len(parts) != 3:
        return ref_str
    namespace, key, field = parts
    try:
        val = prompts_data[namespace][key][field]
        if val is None:
            raise KeyError(f"Reference value for {ref_str} is currently null.")
        return val
    except (KeyError, TypeError) as e:
        raise KeyError(f"Could not resolve template reference: {ref_str} ({e})")


def _load_prompts(output_dir: str) -> dict:
    prompts_path = os.path.join(output_dir, "prompts.json")
    with open(prompts_path, "r", encoding="utf-8") as f:
        return json.load(f)


async def _save_prompts_locked(output_dir: str, prompts_data: dict) -> None:
    """Atomically write prompts.json under the global asyncio lock."""
    prompts_path = os.path.join(output_dir, "prompts.json")
    async with _PROMPTS_FILE_LOCK:
        tmp_path = prompts_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(prompts_data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, prompts_path)


def _ensure_dirs(output_dir: str) -> dict:
    """Create the standard subdirectories."""
    dirs = {
        "char_sheets": os.path.join(output_dir, "character_sheets"),
        "images": os.path.join(output_dir, "images"),
        "videos": os.path.join(output_dir, "videos"),
    }
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    return dirs


# ----- Per-shot node functions -----

async def _run_char_sheet(ctx, shot_id: str, output_dir: str) -> None:
    """Generate ONE character sheet via Grok T2I. Idempotent."""
    prompts = _load_prompts(output_dir)
    entry = prompts.get("character_sheets", {}).get(shot_id)
    if not entry:
        print(f"   ⚠️ [char_sheet:{shot_id}] No entry in prompts.json; skipping.")
        return
    if entry.get("status") == "generated" and entry.get("output_path") and entry.get("fal_image_url"):
        print(f"   ⏭️ [char_sheet:{shot_id}] Already generated.")
        return

    char_dir = os.path.join(output_dir, "character_sheets")
    os.makedirs(char_dir, exist_ok=True)
    out_path = os.path.join(char_dir, f"{shot_id}_sheet.png")
    print(f"   🎨 [char_sheet:{shot_id}] Generating Grok T2I character sheet...")
    res = generate_grok_t2i(entry["prompt"], out_path)
    if res.get("status") == "success":
        entry["status"] = "generated"
        entry["output_path"] = res["generated_image_path"]
        entry["fal_image_url"] = res["fal_image_url"]
        print(f"   ✅ [char_sheet:{shot_id}] Saved to {res['generated_image_path']}")
    else:
        entry["status"] = "failed"
        raise RuntimeError(f"Char sheet {shot_id} failed: {res.get('message')}")
    await _save_prompts_locked(output_dir, prompts)


async def _run_background(ctx, scene_id: str, output_dir: str) -> None:
    """Generate ONE scene background via Grok T2I. Idempotent."""
    prompts = _load_prompts(output_dir)
    entry = prompts.get("backgrounds", {}).get(scene_id)
    if not entry:
        print(f"   ⚠️ [background:{scene_id}] No entry in prompts.json; skipping.")
        return
    if entry.get("status") == "generated" and entry.get("output_path") and entry.get("fal_image_url"):
        print(f"   ⏭️ [background:{scene_id}] Already generated.")
        return

    bg_dir = os.path.join(output_dir, "backgrounds")
    os.makedirs(bg_dir, exist_ok=True)
    out_path = os.path.join(bg_dir, f"{scene_id}_bg.png")
    print(f"   🎨 [background:{scene_id}] Generating Grok T2I background image...")
    res = generate_grok_t2i(entry["prompt"], out_path)
    if res.get("status") == "success":
        entry["status"] = "generated"
        entry["output_path"] = res["generated_image_path"]
        entry["fal_image_url"] = res["fal_image_url"]
        print(f"   ✅ [background:{scene_id}] Saved to {res['generated_image_path']}")
    else:
        entry["status"] = "failed"
        raise RuntimeError(f"Background {scene_id} failed: {res.get('message')}")
    await _save_prompts_locked(output_dir, prompts)


async def _run_ff(ctx, shot_id: str, output_dir: str) -> None:
    """Generate ONE first-frame via Grok Edit. Idempotent."""
    if bool(ctx.state.get("stop_after_char_sheets", False)):
        print(f"   Skip [ff:{shot_id}] (stop_after_char_sheets active).")
        return
    only_shots = ctx.state.get("only_shots")
    if only_shots and shot_id not in only_shots:
        print(f"   Skip [ff:{shot_id}] (not in only_shots).")
        return
    prompts = _load_prompts(output_dir)
    entry = prompts.get("ff_shots", {}).get(shot_id)
    if not entry:
        return
    if entry.get("prompt_type") == "extracted_frame":
        return  # Wave 2 shot; handled separately.
    if entry.get("status") == "generated" and entry.get("output_path") and entry.get("fal_image_url"):
        print(f"   ⏭️ [ff:{shot_id}] Already generated.")
        return

    try:
        resolved_refs = [_resolve_ref(r, prompts) for r in (entry.get("reference_images") or [])]
    except KeyError as e:
        entry["status"] = "failed"
        print(f"   ❌ [ff:{shot_id}] Cannot resolve references: {e}")
        await _save_prompts_locked(output_dir, prompts)
        return

    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    out_path = os.path.join(images_dir, f"{shot_id}_ff.png")
    if not resolved_refs:
        print(f"   🎨 [ff:{shot_id}] Generating Grok T2I First Frame (no references)...")
        res = generate_grok_t2i(entry["prompt"], out_path)
    else:
        print(f"   🎨 [ff:{shot_id}] Generating Grok Edit First Frame...")
        res = generate_grok_edit(entry["prompt"], resolved_refs, out_path)
    if res.get("status") == "success":
        entry["status"] = "generated"
        entry["output_path"] = res["generated_image_path"]
        entry["fal_image_url"] = res["fal_image_url"]
        print(f"   ✅ [ff:{shot_id}] Saved to {res['generated_image_path']}")
    else:
        entry["status"] = "failed"
        raise RuntimeError(f"FF {shot_id} failed: {res.get('message')}")
    await _save_prompts_locked(output_dir, prompts)


async def _run_lf(ctx, shot_id: str, output_dir: str) -> None:
    """Generate ONE last-frame via Grok Edit. Idempotent."""
    if bool(ctx.state.get("stop_after_char_sheets", False)):
        print(f"   Skip [lf:{shot_id}] (stop_after_char_sheets active).")
        return
    only_shots = ctx.state.get("only_shots")
    if only_shots and shot_id not in only_shots:
        print(f"   Skip [lf:{shot_id}] (not in only_shots).")
        return
    prompts = _load_prompts(output_dir)
    entry = prompts.get("lf_shots", {}).get(shot_id)
    if not entry:
        return
    if entry.get("status") == "generated" and entry.get("output_path") and entry.get("fal_image_url"):
        print(f"   ⏭️ [lf:{shot_id}] Already generated.")
        return

    try:
        resolved_refs = [_resolve_ref(r, prompts) for r in (entry.get("reference_images") or [])]
    except KeyError as e:
        entry["status"] = "failed"
        print(f"   ❌ [lf:{shot_id}] Cannot resolve references: {e}")
        await _save_prompts_locked(output_dir, prompts)
        return

    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    out_path = os.path.join(images_dir, f"{shot_id}_lf.png")
    if not resolved_refs:
        print(f"   🎨 [lf:{shot_id}] Generating Grok T2I Last Frame (no references)...")
        res = generate_grok_t2i(entry["prompt"], out_path)
    else:
        print(f"   🎨 [lf:{shot_id}] Generating Grok Edit Last Frame...")
        res = generate_grok_edit(entry["prompt"], resolved_refs, out_path)
    if res.get("status") == "success":
        entry["status"] = "generated"
        entry["output_path"] = res["generated_image_path"]
        entry["fal_image_url"] = res["fal_image_url"]
        print(f"   ✅ [lf:{shot_id}] Saved to {res['generated_image_path']}")
    else:
        entry["status"] = "failed"
        raise RuntimeError(f"LF {shot_id} failed: {res.get('message')}")
    await _save_prompts_locked(output_dir, prompts)


async def _run_video(ctx, shot_id: str, output_dir: str) -> None:
    """Generate ONE LTX FLF2V video. Idempotent."""
    if bool(ctx.state.get("stop_after_char_sheets", False)):
        print(f"   Skip [video:{shot_id}] (stop_after_char_sheets active).")
        return
    if bool(ctx.state.get("skip_video", False)):
        print(f"   Skip [video:{shot_id}] (skip_video active).")
        return
    only_shots = ctx.state.get("only_shots")
    if only_shots and shot_id not in only_shots:
        print(f"   Skip [video:{shot_id}] (not in only_shots).")
        return
    prompts = _load_prompts(output_dir)
    entry = prompts.get("motion_prompts", {}).get(shot_id)
    if not entry:
        return
    if entry.get("status") == "generated" and entry.get("output_path"):
        print(f"   ⏭️ [video:{shot_id}] Already generated.")
        return

    try:
        ff_ref = entry.get("ff_image")
        lf_ref = entry.get("lf_image")
        ff_img = _resolve_ref(ff_ref, prompts) if ff_ref else None
        lf_img = _resolve_ref(lf_ref, prompts) if lf_ref else None
    except KeyError as e:
        entry["status"] = "failed"
        print(f"   ❌ [video:{shot_id}] Cannot resolve image refs: {e}")
        await _save_prompts_locked(output_dir, prompts)
        return

    videos_dir = os.path.join(output_dir, "videos")
    os.makedirs(videos_dir, exist_ok=True)
    out_path = os.path.join(videos_dir, f"{shot_id}.mp4")
    duration = entry.get("duration_seconds", 8)
    print(f"   🎬 [video:{shot_id}] Generating Video ({duration}s)...")
    res = generate_ltx_video(ff_img, lf_img, entry["prompt"], out_path, duration_seconds=duration)
    if res.get("status") == "success":
        entry["status"] = "generated"
        entry["output_path"] = res["video_path"]
        print(f"   ✅ [video:{shot_id}] Saved to {res['video_path']}")
    else:
        entry["status"] = "failed"
        raise RuntimeError(f"Video {shot_id} failed: {res.get('message')}")
    await _save_prompts_locked(output_dir, prompts)


def _get_chars_for_shot(shot_id: str, blueprint: dict) -> list[str]:
    for scene in blueprint.get("scenes", []):
        for shot in scene.get("shots", []):
            if shot.get("shot_id") == shot_id:
                return shot.get("characters_present", [])
    return []


async def _run_extract_last_frame(ctx, shot_id: str, prev_shot_id: str, output_dir: str) -> None:
    """Extract the FF for a Wave 2 continuation shot, restore its quality via Grok Edit, and upload to fal.ai CDN."""
    only_shots = ctx.state.get("only_shots")
    if only_shots and shot_id not in only_shots:
        print(f"   Skip [extract_ff:{shot_id}] (not in only_shots).")
        return
    prompts = _load_prompts(output_dir)
    ff_entry = prompts.get("ff_shots", {}).get(shot_id)
    if ff_entry and ff_entry.get("status") == "generated" and ff_entry.get("output_path") and ff_entry.get("fal_image_url"):
        print(f"   ⏭️ [extract_ff:{shot_id}] Already extracted and uploaded.")
        return

    prev_video_entry = prompts.get("motion_prompts", {}).get(prev_shot_id)
    if not prev_video_entry or not prev_video_entry.get("output_path"):
        raise RuntimeError(
            f"Cannot extract FF for {shot_id}: preceding video for {prev_shot_id} did not generate."
        )

    prev_video_path = prev_video_entry["output_path"]
    images_dir = os.path.join(output_dir, "images")
    raw_output_path = os.path.join(images_dir, f"{shot_id}_ff_raw.png")
    out_path = os.path.join(images_dir, f"{shot_id}_ff.png")

    print(f"   🎞️ [extract_ff:{shot_id}] Extracting from {prev_shot_id} video to raw file...")
    res = extract_last_frame(prev_video_path, raw_output_path)
    if res.get("status") != "success":
        raise RuntimeError(f"FF extraction for {shot_id} failed: {res.get('message')}")

    # Upload raw to fal.ai so it can be used as reference
    try:
        if not os.environ.get("FAL_KEY"):
            import config
            os.environ["FAL_KEY"] = config.FAL_KEY or ""
        print(f"   ☁️ [extract_ff:{shot_id}] Uploading extracted raw FF frame to fal.ai CDN...")
        raw_fal_url = fal_client.upload_file(raw_output_path)
    except Exception as e:
        raise RuntimeError(f"Uploading extracted raw FF to fal.ai failed: {e}")

    # Now, restore the quality of the blurry frame via Grok Edit using previous shot's LF prompt and character sheets.
    lf_prompt = prompts.get("lf_shots", {}).get(prev_shot_id, {}).get("prompt")
    restored = False
    fal_url = raw_fal_url

    if lf_prompt:
        try:
            print(f"   ✨ [extract_ff:{shot_id}] Found preceding LF prompt. Performing Grok Edit quality restoration...")
            # Load blueprint
            blueprint_path = os.path.join(output_dir, "director_visual_blueprint.json")
            if os.path.exists(blueprint_path):
                with open(blueprint_path, "r", encoding="utf-8") as f:
                    blueprint = json.load(f)
                
                # Get characters present in shot
                chars_present = _get_chars_for_shot(shot_id, blueprint)
                char_refs = []
                for char_id in chars_present:
                    cs_url = prompts.get("character_sheets", {}).get(char_id, {}).get("fal_image_url")
                    if cs_url:
                        char_refs.append(cs_url)

                ref_urls = [raw_fal_url] + char_refs
                print(f"   🎨 [extract_ff:{shot_id}] Grok Edit refs: {ref_urls}")
                
                res_grok = generate_grok_edit(lf_prompt, ref_urls, out_path)
                if res_grok.get("status") == "success":
                    fal_url = res_grok["fal_image_url"]
                    restored = True
                    print(f"   ✅ [extract_ff:{shot_id}] Grok Edit restoration successful. URL: {fal_url}")
                else:
                    print(f"   ⚠️ [extract_ff:{shot_id}] Grok Edit restoration failed: {res_grok.get('message')}. Falling back to raw.")
            else:
                print(f"   ⚠️ [extract_ff:{shot_id}] Blueprint not found at {blueprint_path}. Skipping restoration.")
        except Exception as e:
            print(f"   ⚠️ [extract_ff:{shot_id}] Grok Edit restoration errored: {e}. Falling back to raw.")

    if not restored:
        import shutil
        shutil.copy2(raw_output_path, out_path)
        print(f"   ℹ️ [extract_ff:{shot_id}] Using raw frame as-is.")

    ff_entry = prompts.setdefault("ff_shots", {}).setdefault(shot_id, {})
    ff_entry["status"] = "generated"
    ff_entry["prompt_type"] = "extracted_frame_restored" if restored else "extracted_frame"
    ff_entry["source"] = "extracted_from_previous_video"
    ff_entry["output_path"] = out_path
    ff_entry["fal_image_url"] = fal_url
    ff_entry["raw_output_path"] = raw_output_path
    ff_entry["raw_fal_url"] = raw_fal_url
    ff_entry.setdefault("prompt", None)
    ff_entry.setdefault("reference_images", [])
    ff_entry.setdefault("generated_by", "wave2_extract_last_frame")
    await _save_prompts_locked(output_dir, prompts)
    print(f"   ✅ [extract_ff:{shot_id}] Saved and uploaded to {fal_url}")


# ----- Workflow builders -----

def _make_node(func, *args, name_suffix: str):
    """Create a curried FunctionNode that injects per-shot args via closure."""
    async def _wrapped(ctx):
        await func(ctx, *args)
    return FunctionNode(
        func=_wrapped,
        name=f"{args[0]}_{name_suffix}",  # args[0] is shot_id
        retry_config=API_RETRY_CONFIG,
    )


def _build_wave1_workflow(output_dir: str, wave1_shot_ids: list[str], wave2_shot_ids: list[str], eager_video: bool = False) -> Workflow:
    """Wire a Workflow that runs Wave 1: char_sheets + backgrounds -> FF -> LF -> video."""
    prompts = _load_prompts(output_dir)
    char_sheet_ids = list(prompts.get("character_sheets", {}).keys())
    bg_ids = list(prompts.get("backgrounds", {}).keys())

    cs_nodes = [_make_node(_run_char_sheet, sid, output_dir, name_suffix="cs") for sid in char_sheet_ids]
    bg_nodes = [_make_node(_run_background, bid, output_dir, name_suffix="bg") for bid in bg_ids]
    ff_nodes = [_make_node(_run_ff, sid, output_dir, name_suffix="ff") for sid in wave1_shot_ids]
    lf_nodes = [_make_node(_run_lf, sid, output_dir, name_suffix="lf") for sid in wave1_shot_ids]
    video_nodes = [_make_node(_run_video, sid, output_dir, name_suffix="video") for sid in wave1_shot_ids]

    edges: list = []
    cs_join = JoinNode(name="cs_join")
    ff_join = JoinNode(name="ff_join")
    lf_join = JoinNode(name="lf_join")

    # 1. Char sheets + backgrounds phase
    if cs_nodes or bg_nodes:
        for n in cs_nodes:
            edges.append((START, n))
            edges.append((n, cs_join))
        for n in bg_nodes:
            edges.append((START, n))
            edges.append((n, cs_join))
        
        # Char sheets + backgrounds -> FF phase
        if eager_video:
            for i, sid in enumerate(wave1_shot_ids):
                edges.append((cs_join, ff_nodes[i]))
                edges.append((ff_nodes[i], lf_nodes[i]))
                edges.append((lf_nodes[i], video_nodes[i]))
        else:
            for n in ff_nodes:
                edges.append((cs_join, n))
    else:
        # No char_sheets or backgrounds; FF nodes connect directly to START
        if eager_video:
            for i, sid in enumerate(wave1_shot_ids):
                edges.append((START, ff_nodes[i]))
                edges.append((ff_nodes[i], lf_nodes[i]))
                edges.append((lf_nodes[i], video_nodes[i]))
        else:
            for n in ff_nodes:
                edges.append((START, n))

    if not eager_video:
        for n in ff_nodes:
            edges.append((n, ff_join))

        # 2. LF phase
        for n in lf_nodes:
            edges.append((ff_join, n))
            edges.append((n, lf_join))

        # 3. Video phase
        for n in video_nodes:
            edges.append((lf_join, n))

    return Workflow(
        name="wave1_executor",
        edges=edges,
        max_concurrency=_MAX_CONCURRENCY,
    )


def _build_wave2_workflow(output_dir: str, wave2_shot_ids: list[str], blueprint: dict) -> Workflow:
    """Wire Wave 2 continuation chain sequentially (extract FF -> LF -> video for shot N)."""
    ordered: list[tuple[str, str]] = []  # (shot_id, prev_shot_id)
    wave2_set = set(wave2_shot_ids)
    for scene in blueprint.get("scenes", []):
        shots = scene.get("shots", [])
        for i, shot in enumerate(shots):
            sid = shot.get("shot_id")
            if sid not in wave2_set:
                continue
            prev = shots[i - 1] if i > 0 else None
            if prev and prev.get("shot_id"):
                ordered.append((sid, prev["shot_id"]))

    edges: list = []
    previous_video_node = None
    for sid, prev_sid in ordered:
        extract_node = _make_node(_run_extract_last_frame, sid, prev_sid, output_dir, name_suffix="extract_ff")
        lf_node = _make_node(_run_lf, sid, output_dir, name_suffix="lf")
        video_node = _make_node(_run_video, sid, output_dir, name_suffix="video")

        edges.append(((previous_video_node or START), extract_node))
        edges.append((extract_node, lf_node))
        edges.append((lf_node, video_node))
        previous_video_node = video_node

    return Workflow(
        name="wave2_executor",
        edges=edges,
        max_concurrency=1,
    )


def _wave_shot_ids(blueprint: dict, continuation_flag: bool) -> list[str]:
    """Return shot_id list filtered by continuation_from_previous."""
    ids = []
    for scene in blueprint.get("scenes", []):
        for shot in scene.get("shots", []):
            if bool(shot.get("continuation_from_previous")) == continuation_flag:
                ids.append(shot["shot_id"])
    return ids


async def run_wave_executor(
    output_dir: str,
    stop_after_char_sheets: bool = False,
    only_shots: list[str] = None,
    skip_video: bool = False,
    eager_video: bool = False,
) -> None:
    """Build and run Wave 1 then Wave 2 nested Workflows."""
    blueprint_path = os.path.join(output_dir, "director_visual_blueprint.json")
    wave1_path = os.path.join(output_dir, "generator_wave_1.json")
    wave2_path = os.path.join(output_dir, "generator_wave_2.json")

    if not os.path.exists(blueprint_path):
        raise FileNotFoundError(f"Missing blueprint: {blueprint_path}")
    if not os.path.exists(wave1_path) or not os.path.exists(wave2_path):
        raise FileNotFoundError(f"Missing generator_wave_1.json or _2.json in {output_dir}")

    with open(blueprint_path, "r", encoding="utf-8") as f:
        blueprint = json.load(f)
    wave1_shot_ids = _wave_shot_ids(blueprint, continuation_flag=False)
    wave2_shot_ids = _wave_shot_ids(blueprint, continuation_flag=True)

    # Run Wave 1
    print(f"\n🌊 Running Wave 1 Executor ({len(wave1_shot_ids)} shots; max_concurrency={_MAX_CONCURRENCY})...")
    _ensure_dirs(output_dir)
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    wave1_wf = _build_wave1_workflow(output_dir, wave1_shot_ids, wave2_shot_ids, eager_video=eager_video)
    ss1 = InMemorySessionService()
    s1 = await ss1.create_session(
        app_name="wave1",
        user_id="director",
        state={
            "output_dir": output_dir,
            "stop_after_char_sheets": stop_after_char_sheets,
            "only_shots": only_shots,
            "skip_video": skip_video,
        }
    )
    runner1 = Runner(agent=wave1_wf, app_name="wave1", session_service=ss1)
    msg = types.Content(parts=[types.Part(text="run wave 1")])
    try:
        async for ev in runner1.run_async(user_id="director", session_id=s1.id, new_message=msg):
            pass
    except Exception as e:
        print(f"⚠️ Wave 1 workflow raised (continuing to Wave 2): {e}")
        traceback.print_exc()

    print(f"\n✅ Wave 1 complete. Proceeding to Wave 2.")

    # Run Wave 2
    if stop_after_char_sheets:
        print("ℹ️ Wave 2 skipped (stop_after_char_sheets active).")
        return
    if not wave2_shot_ids:
        print("ℹ️ No Wave 2 shots to process.")
        return
    print(f"\n🌊 Running Wave 2 Executor ({len(wave2_shot_ids)} shots)...")
    wave2_wf = _build_wave2_workflow(output_dir, wave2_shot_ids, blueprint)
    ss2 = InMemorySessionService()
    s2 = await ss2.create_session(
        app_name="wave2",
        user_id="director",
        state={
            "output_dir": output_dir,
            "only_shots": only_shots,
            "skip_video": skip_video,
        }
    )
    runner2 = Runner(agent=wave2_wf, app_name="wave2", session_service=ss2)
    msg2 = types.Content(parts=[types.Part(text="run wave 2")])
    try:
        async for ev in runner2.run_async(user_id="director", session_id=s2.id, new_message=msg2):
            pass
    except Exception as e:
        print(f"⚠️ Wave 2 workflow raised: {e}")
        traceback.print_exc()
