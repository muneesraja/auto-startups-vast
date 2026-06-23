"""Nested Workflow that executes Wave 1 and Wave 2 of ComfyUI calls with bounded parallelism.

Flux-only architecture (consistency-patch phases removed):
- Wave 1: character_sheets → ff → lf → video
- Wave 2: extract_FF → lf → video

Improvements:
- Per-shot FunctionNode with `RetryConfig` (transient ComfyUI / tunnel failures,
  exponential backoff + jitter, up to 5 attempts).
- `max_concurrency=4` on the Workflow bounds parallel ComfyUI calls.
- Serialized prompts.json writes via an asyncio.Lock.
- Idempotent: if a shot is already `status='generated'` on disk, the node skips
  without making a ComfyUI call.

ADK 2.0 modernization notes:
- Transient ComfyUI / tunnel failures are NOT caught at the wave boundary:
  per the ADK 2.0 migration guide, broad `except Exception` blocks mask the
  framework's automatic RetryConfig mechanism. Exceptions now propagate to
  the workflow runner, which retries via the per-node RetryConfig.
- Imports `Event` from `google.adk` (preferred ADK 2.0 path). The `FunctionNode`
  wrapper is still used here because the per-shot nodes are built dynamically
  via closures (`_make_node`) with per-shot `args` — the `@node` decorator
  cannot express that at module load time.
"""
import os
import json
import re
import asyncio

from google.adk import Workflow
from google.adk.workflow import FunctionNode, JoinNode, START, RetryConfig

# Lock guarding all writes to prompts.json during wave execution. Lock is process-wide.
_PROMPTS_FILE_LOCK = asyncio.Lock()

# Bound for simultaneous ComfyUI calls (free-tier Cloudflare tunnel sweet spot).
_MAX_CONCURRENCY = 4

# Retry policy for transient ComfyUI / tunnel failures.
COMFYUI_RETRY_CONFIG = RetryConfig(
    max_attempts=5,
    initial_delay=1.0,
    max_delay=60.0,
    backoff_factor=2.0,
    jitter=1.0,
    exceptions=[RuntimeError, TimeoutError, OSError, ConnectionError, json.JSONDecodeError],
)


_REF_PATTERN = re.compile(r"\{\{+([^}]+)\}\}+")


def _resolve_ref(ref_str, prompts_data):
    """Resolve references like {{character_sheets.char_01.output_path}} dynamically."""
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


# ----- Per-shot node functions (one FunctionNode per shot+phase) -----

async def _run_char_sheet(ctx, shot_id: str, output_dir: str) -> None:
    """Generate ONE character sheet via Flux Klein 9B pure T2I. Idempotent."""
    import sys
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if here not in sys.path:
        sys.path.insert(0, here)
    from tools.comfyui_tools import generate_flux_image  # type: ignore

    prompts = _load_prompts(output_dir)
    entry = prompts.get("character_sheets", {}).get(shot_id)
    if not entry:
        print(f"   ⚠️ [char_sheet:{shot_id}] No entry in prompts.json; skipping.")
        return
    if entry.get("status") == "generated" and entry.get("output_path"):
        print(f"   ⏭️ [char_sheet:{shot_id}] Already generated.")
        return

    char_dir = os.path.join(output_dir, "character_sheets")
    os.makedirs(char_dir, exist_ok=True)
    out_path = os.path.join(char_dir, f"{shot_id}_sheet.png")
    print(f"   🎨 [char_sheet:{shot_id}] Generating via Flux Klein T2I...")
    res = generate_flux_image(entry["prompt"], out_path, reference_image_paths=[])
    if res.get("status") == "success":
        entry["status"] = "generated"
        entry["output_path"] = res["generated_image_path"]
        print(f"   ✅ [char_sheet:{shot_id}] Saved to {res['generated_image_path']}")
    else:
        entry["status"] = "failed"
        raise RuntimeError(f"Char sheet {shot_id} failed: {res.get('message')}")
    await _save_prompts_locked(output_dir, prompts)


async def _run_ff(ctx, shot_id: str, output_dir: str) -> None:
    """Generate ONE first-frame image via Flux Klein 9B with char-sheet refs. Idempotent.

    For continuation shots (prompt_type == 'extracted_frame'), this is a no-op —
    the FF image is set by _run_extract_last_frame during Wave 2.
    """
    import sys
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if here not in sys.path:
        sys.path.insert(0, here)
    from tools.comfyui_tools import generate_flux_image  # type: ignore

    prompts = _load_prompts(output_dir)
    entry = prompts.get("ff_shots", {}).get(shot_id)
    if not entry:
        return
    if entry.get("prompt_type") == "extracted_frame":
        return  # Wave 2 shot; FF set by extract_last_frame.
    if entry.get("status") == "generated" and entry.get("output_path"):
        print(f"   ⏭️ [ff:{shot_id}] Already generated.")
        return

    # Resolve char-sheet reference templates
    try:
        char_refs = [_resolve_ref(r, prompts) for r in (entry.get("reference_images") or [])]
    except KeyError as e:
        entry["status"] = "failed"
        print(f"   ❌ [ff:{shot_id}] Cannot resolve references: {e}")
        await _save_prompts_locked(output_dir, prompts)
        return

    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    out_path = os.path.join(images_dir, f"{shot_id}_ff.png")
    print(f"   🎨 [ff:{shot_id}] Generating via Flux Klein with {len(char_refs)} ref(s)...")
    res = generate_flux_image(entry["prompt"], out_path, reference_image_paths=char_refs)
    if res.get("status") == "success":
        entry["status"] = "generated"
        entry["output_path"] = res["generated_image_path"]
        print(f"   ✅ [ff:{shot_id}] Saved to {res['generated_image_path']}")
    else:
        entry["status"] = "failed"
        raise RuntimeError(f"FF {shot_id} failed: {res.get('message')}")
    await _save_prompts_locked(output_dir, prompts)


async def _run_lf(ctx, shot_id: str, output_dir: str) -> None:
    """Generate ONE last-frame image via Flux Klein 9B with char sheets + FF as refs.

    Reference image order: char sheets first, then FF image (per
    lf_shots.reference_images convention; FF is the last entry).
    """
    import sys
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if here not in sys.path:
        sys.path.insert(0, here)
    from tools.comfyui_tools import generate_flux_image  # type: ignore

    prompts = _load_prompts(output_dir)
    entry = prompts.get("lf_shots", {}).get(shot_id)
    if not entry:
        return
    if entry.get("status") == "generated" and entry.get("output_path"):
        print(f"   ⏭️ [lf:{shot_id}] Already generated.")
        return

    # Resolve all reference templates (char sheets + FF)
    try:
        refs = [_resolve_ref(r, prompts) for r in (entry.get("reference_images") or [])]
    except KeyError as e:
        entry["status"] = "failed"
        print(f"   ❌ [lf:{shot_id}] Cannot resolve references: {e}")
        await _save_prompts_locked(output_dir, prompts)
        return

    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    out_path = os.path.join(images_dir, f"{shot_id}_lf.png")
    print(f"   🎨 [lf:{shot_id}] Generating via Flux Klein with {len(refs)} ref(s)...")
    res = generate_flux_image(entry["prompt"], out_path, reference_image_paths=refs)
    if res.get("status") == "success":
        entry["status"] = "generated"
        entry["output_path"] = res["generated_image_path"]
        print(f"   ✅ [lf:{shot_id}] Saved to {res['generated_image_path']}")
    else:
        entry["status"] = "failed"
        raise RuntimeError(f"LF {shot_id} failed: {res.get('message')}")
    await _save_prompts_locked(output_dir, prompts)


async def _run_video(ctx, shot_id: str, output_dir: str) -> None:
    """Generate ONE LTX-2.3 FLF2V video. Idempotent.

    The motion_prompts entry holds:
        ff_image = {{ff_shots.SHOT.output_path}}
        lf_image = {{lf_shots.SHOT.output_path}}
        prompt, duration_seconds
    """
    import sys
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if here not in sys.path:
        sys.path.insert(0, here)
    from tools.comfyui_tools import generate_ltx_video  # type: ignore

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
    duration = entry.get("duration_seconds", 3)
    print(f"   🎬 [video:{shot_id}] Generating ({duration}s)...")
    res = generate_ltx_video(ff_img, lf_img, entry["prompt"], out_path, duration_seconds=duration)
    if res.get("status") == "success":
        entry["status"] = "generated"
        entry["output_path"] = res["video_path"]
        print(f"   ✅ [video:{shot_id}] Saved to {res['video_path']}")
    else:
        entry["status"] = "failed"
        raise RuntimeError(f"Video {shot_id} failed: {res.get('message')}")
    await _save_prompts_locked(output_dir, prompts)


async def _run_extract_last_frame(ctx, shot_id: str, prev_shot_id: str, output_dir: str) -> None:
    """Extract the first frame for a Wave 2 continuation shot from the previous shot's video."""
    import sys
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if here not in sys.path:
        sys.path.insert(0, here)
    from tools.comfyui_tools import extract_last_frame  # type: ignore

    prompts = _load_prompts(output_dir)
    ff_entry = prompts.get("ff_shots", {}).get(shot_id)
    if ff_entry and ff_entry.get("status") == "generated" and ff_entry.get("output_path"):
        print(f"   ⏭️ [extract_ff:{shot_id}] Already extracted.")
        return

    prev_video_entry = prompts.get("motion_prompts", {}).get(prev_shot_id)
    if not prev_video_entry or not prev_video_entry.get("output_path"):
        raise RuntimeError(
            f"Cannot extract FF for {shot_id}: preceding video for {prev_shot_id} did not generate."
        )

    prev_video_path = prev_video_entry["output_path"]
    images_dir = os.path.join(output_dir, "images")
    out_path = os.path.join(images_dir, f"{shot_id}_ff.png")
    print(f"   🎞️ [extract_ff:{shot_id}] Extracting from {prev_shot_id} video...")
    res = extract_last_frame(prev_video_path, out_path)
    if res.get("status") == "success":
        ff_entry = prompts.setdefault("ff_shots", {}).setdefault(shot_id, {})
        ff_entry["status"] = "generated"
        ff_entry["prompt_type"] = "extracted_frame"
        ff_entry["source"] = "extracted_from_previous_video"
        ff_entry["output_path"] = res["extracted_frame_path"]
        ff_entry.setdefault("prompt", None)
        ff_entry.setdefault("reference_images", [])
        ff_entry.setdefault("generated_by", "wave2_extract_last_frame")
        await _save_prompts_locked(output_dir, prompts)
        print(f"   ✅ [extract_ff:{shot_id}] Saved to {res['extracted_frame_path']}")
    else:
        raise RuntimeError(f"FF extraction for {shot_id} failed: {res.get('message')}")


# ----- Workflow builders -----

def _make_node(func, *args, name_suffix: str):
    """Create a curried FunctionNode that injects per-shot args via closure.

    `func` will be called as `await func(ctx, *args)`. Args typically include the
    shot_id and output_dir (and for extraction nodes, the prev_shot_id too).
    """
    async def _wrapped(ctx):
        await func(ctx, *args)
    return FunctionNode(
        func=_wrapped,
        name=f"{args[0]}_{name_suffix}",  # args[0] assumed to be shot_id
        retry_config=COMFYUI_RETRY_CONFIG,
    )


def _build_wave1_workflow(output_dir: str, wave1_shot_ids: list[str]) -> Workflow:
    """Wire Wave 1: char_sheets → ff → lf → video.

    Flux-only architecture (no consistency patches).
    """
    prompts = _load_prompts(output_dir)
    char_sheet_ids = list(prompts.get("character_sheets", {}).keys())

    cs_nodes = [_make_node(_run_char_sheet, sid, output_dir, name_suffix="cs") for sid in char_sheet_ids]
    ff_nodes = [_make_node(_run_ff, sid, output_dir, name_suffix="ff") for sid in wave1_shot_ids]
    lf_nodes = [_make_node(_run_lf, sid, output_dir, name_suffix="lf") for sid in wave1_shot_ids]
    video_nodes = [_make_node(_run_video, sid, output_dir, name_suffix="video") for sid in wave1_shot_ids]

    edges: list = []
    cs_join = JoinNode(name="cs_join")
    ff_join = JoinNode(name="ff_join")
    lf_join = JoinNode(name="lf_join")

    # 1. Char sheets phase
    if cs_nodes:
        for n in cs_nodes:
            edges.append((START, n))
            edges.append((n, cs_join))
        # Char sheets → FF phase
        for n in ff_nodes:
            edges.append((cs_join, n))
    else:
        # No char_sheets; FF nodes connect directly to START
        for n in ff_nodes:
            edges.append((START, n))

    for n in ff_nodes:
        edges.append((n, ff_join))

    # 2. LF phase (FF → LF)
    for n in lf_nodes:
        edges.append((ff_join, n))
        edges.append((n, lf_join))

    # 3. Video phase (LF → video)
    for n in video_nodes:
        edges.append((lf_join, n))

    return Workflow(
        name="wave1_executor",
        edges=edges,
        max_concurrency=_MAX_CONCURRENCY,
    )


def _build_wave2_workflow(output_dir: str, wave2_shot_ids: list[str], blueprint: dict) -> Workflow:
    """Wire Wave 2 as an ordered continuation chain.

    Wave 2 shots are continuation shots whose FF is extracted from the previous
    shot's video. Some continuations follow another continuation (e.g.
    shot_03 extracts from shot_02), so parallel fan-out is unsafe: a later
    extraction can start before the previous continuation video exists.

    To keep correctness simple, execute all Wave 2 shots in blueprint order:
    extract FF → lf → video for shot N, then move to shot N+1. The nodes remain
    idempotent, so resumes skip previously extracted/generated artifacts.
    """
    ordered: list[tuple[str, str]] = []  # (shot_id, prev_shot_id)
    wave2_set = set(wave2_shot_ids)
    for scene in blueprint.get("scenes", []) or []:
        shots = scene.get("shots", []) or []
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
        # Ordered continuation chain must run one dependency chain at a time.
        max_concurrency=1,
    )


def _wave_shot_ids(blueprint: dict, continuation_flag: bool) -> list[str]:
    """Return shot_id list filtered by `continuation_from_previous == continuation_flag`."""
    ids = []
    for scene in blueprint.get("scenes", []) or []:
        for shot in scene.get("shots", []) or []:
            if bool(shot.get("continuation_from_previous")) == continuation_flag:
                ids.append(shot["shot_id"])
    return ids


async def run_wave_executor(output_dir: str) -> None:
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

    wave1_wf = _build_wave1_workflow(output_dir, wave1_shot_ids)
    ss1 = InMemorySessionService()
    s1 = await ss1.create_session(app_name="wave1", user_id="director", state={"output_dir": output_dir})
    runner1 = Runner(agent=wave1_wf, app_name="wave1", session_service=ss1)
    msg = types.Content(parts=[types.Part(text="run wave 1")])
    # Let transient ComfyUI / tunnel failures propagate so per-node RetryConfig
    # (COMFYUI_RETRY_CONFIG: max_attempts=5, exponential backoff) actually fires.
    # Per ADK 2.0 migration guide, broad except-Exception blocks mask the
    # framework's automatic retry mechanism and disable it permanently for
    # that step.
    async for ev in runner1.run_async(user_id="director", session_id=s1.id, new_message=msg):
        pass

    print(f"\n✅ Wave 1 complete. Proceeding to Wave 2.")

    # Run Wave 2
    if not wave2_shot_ids:
        print("ℹ️ No Wave 2 shots to process.")
        return
    print(f"\n🌊 Running Wave 2 Executor ({len(wave2_shot_ids)} shots)...")
    wave2_wf = _build_wave2_workflow(output_dir, wave2_shot_ids, blueprint)
    ss2 = InMemorySessionService()
    s2 = await ss2.create_session(app_name="wave2", user_id="director", state={"output_dir": output_dir})
    runner2 = Runner(agent=wave2_wf, app_name="wave2", session_service=ss2)
    msg2 = types.Content(parts=[types.Part(text="run wave 2")])
    async for ev in runner2.run_async(user_id="director", session_id=s2.id, new_message=msg2):
        pass
