"""Nested Workflow that executes Wave 1 and Wave 2 of ComfyUI calls with bounded parallelism.

Replaces the legacy scripts/wave_executor.py sequential execution loop. Improvements:
- Per-shot FunctionNode with `RetryConfig` (fixes ISSUE-004 / ISSUE-005 by raising
  on empty/non-JSON curl responses and retrying transient failures up to 5 times
  with exponential backoff + jitter).
- `max_concurrency=4` on the Workflow bounds parallel ComfyUI calls — the sweet
  spot for the free-tier Cloudflare trycloudflare tunnel.
- Serialized prompts.json writes via an asyncio.Lock (prevents torn writes from
  parallel per-shot nodes).
- Idempotent: if a shot is already `status='generated'` on disk, the node skips
  without making a ComfyUI call (fixes cascading-skip part of ISSUE-002 by
  surfacing still-missing entries at the JOIN).
- Issues A1/B2/C1 fixed upstream by validate_prompts_node; this module just runs
  whatever the prompt JSON says regardless of "should this char be present".
"""
import os
import json
import re
import asyncio
import traceback

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

# Lighter retry policy for vision-review LLM calls (audit-mode, non-blocking).
# Vision reviews must NOT raise — they sink errors silently into review_skipped
# entries. But we still retry transient network failures before giving up.
_REVIEW_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    initial_delay=2.0,
    max_delay=30.0,
    backoff_factor=2.0,
    jitter=0.5,
    exceptions=[RuntimeError, TimeoutError, OSError, ConnectionError],
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
    """Generate ONE character sheet. Idempotent."""
    # Lazy import to avoid hard dependency when unit-testing node construction.
    import sys
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if here not in sys.path:
        sys.path.insert(0, here)
    from tools.comfyui_tools import generate_ideogram_image  # type: ignore

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
    print(f"   🎨 [char_sheet:{shot_id}] Generating...")
    res = generate_ideogram_image(entry["prompt"], out_path, aspect_ratio="16:9")
    if res.get("status") == "success":
        entry["status"] = "generated"
        entry["output_path"] = res["generated_image_path"]
        print(f"   ✅ [char_sheet:{shot_id}] Saved to {res['generated_image_path']}")
    else:
        entry["status"] = "failed"
        raise RuntimeError(f"Char sheet {shot_id} failed: {res.get('message')}")
    await _save_prompts_locked(output_dir, prompts)


async def _run_ff(ctx, shot_id: str, output_dir: str) -> None:
    """Generate ONE first-frame Ideogram image. Idempotent."""
    import sys
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if here not in sys.path:
        sys.path.insert(0, here)
    from tools.comfyui_tools import generate_ideogram_image  # type: ignore

    prompts = _load_prompts(output_dir)
    entry = prompts.get("ff_shots", {}).get(shot_id)
    if not entry:
        return
    if entry.get("prompt_type") == "extracted_frame":
        return  # Wave 2 shot; handled separately.
    if entry.get("status") == "generated" and entry.get("output_path"):
        print(f"   ⏭️ [ff:{shot_id}] Already generated.")
        return

    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    out_path = os.path.join(images_dir, f"{shot_id}_ff.png")
    print(f"   🎨 [ff:{shot_id}] Generating...")
    res = generate_ideogram_image(entry["prompt"], out_path, aspect_ratio="16:9")
    if res.get("status") == "success":
        entry["status"] = "generated"
        entry["output_path"] = res["generated_image_path"]
        print(f"   ✅ [ff:{shot_id}] Saved to {res['generated_image_path']}")
    else:
        entry["status"] = "failed"
        raise RuntimeError(f"FF {shot_id} failed: {res.get('message')}")
    await _save_prompts_locked(output_dir, prompts)


async def _run_consistency_patch(ctx, shot_id: str, output_dir: str) -> None:
    """Apply ONE consistency patch via Flux Klein 9B. Idempotent.

    Now reads `base_image` (FF) as the Flux Klein base; reads `reference_images`
    as the character sheets only (no FF in the refs list — Issue B fix).
    """
    import sys
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if here not in sys.path:
        sys.path.insert(0, here)
    from tools.comfyui_tools import generate_flux_edit  # type: ignore

    prompts = _load_prompts(output_dir)
    entry = prompts.get("consistency_patches", {}).get(shot_id)
    if not entry or entry.get("status") in ("generated", "skipped"):
        return
    if entry.get("status") == "generated" and entry.get("output_path"):
        return

    # Resolve the base_image template (the FF to edit).
    base_image_ref = entry.get("base_image") or ""
    if not base_image_ref:
        # Backward compatibility: if no base_image set, look at legacy reference_images shape
        # where FF was the LAST entry.
        refs = entry.get("reference_images") or []
        if not refs:
            entry["status"] = "skipped"
            await _save_prompts_locked(output_dir, prompts)
            return
        base_image_ref = refs[-1]
        # Decouple FF from reference_images so only char_sheets remain.
        entry["reference_images"] = refs[:-1]
        entry["base_image"] = base_image_ref

    try:
        scene_img = _resolve_ref(base_image_ref, prompts)
        char_refs = [_resolve_ref(r, prompts) for r in (entry.get("reference_images") or [])]
    except KeyError as e:
        entry["status"] = "failed"
        print(f"   ❌ [cp:{shot_id}] Cannot resolve references: {e}")
        await _save_prompts_locked(output_dir, prompts)
        return  # Skip rather than raise — Wave will continue with other shots.

    images_dir = os.path.join(output_dir, "images")
    out_path = os.path.join(images_dir, f"{shot_id}_ff_consistent.png")
    print(f"   🎨 [cp:{shot_id}] Generating consistency patch...")
    res = generate_flux_edit(entry["prompt"], out_path, scene_img, char_refs)
    if res.get("status") == "success":
        entry["status"] = "generated"
        entry["output_path"] = res["generated_image_path"]
        print(f"   ✅ [cp:{shot_id}] Saved to {res['generated_image_path']}")
    else:
        entry["status"] = "failed"
        raise RuntimeError(f"Consistency patch {shot_id} failed: {res.get('message')}")
    await _save_prompts_locked(output_dir, prompts)


async def _run_lf(ctx, shot_id: str, output_dir: str) -> None:
    """Generate ONE last-frame image.

    NEW (Issue A1 fix): LF is now Ideogram 4 T2I (prompt_type == 'ideogram_t2i'),
    with an empty reference_images list. Falls back to Flux edit if a legacy
    entry is encountered (prompt_type == 'flux_edit'), so old prompts.json files
    still work end-to-end.
    """
    import sys
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if here not in sys.path:
        sys.path.insert(0, here)
    from tools.comfyui_tools import generate_ideogram_image, generate_flux_edit  # type: ignore

    prompts = _load_prompts(output_dir)
    entry = prompts.get("lf_shots", {}).get(shot_id)
    if not entry:
        return
    if entry.get("status") == "generated" and entry.get("output_path"):
        print(f"   ⏭️ [lf:{shot_id}] Already generated.")
        return

    images_dir = os.path.join(output_dir, "images")
    out_path = os.path.join(images_dir, f"{shot_id}_lf.png")
    prompt_type = entry.get("prompt_type", "ideogram_t2i")
    prompt = entry.get("prompt")

    if prompt_type == "ideogram_t2i":
        print(f"   🎨 [lf:{shot_id}] Generating via Ideogram T2I...")
        res = generate_ideogram_image(prompt, out_path, aspect_ratio="16:9")
    else:
        # Legacy flux_edit path — kept as a fallback.
        try:
            refs = [_resolve_ref(r, prompts) for r in (entry.get("reference_images") or [])]
            scene_img = refs[0]
            char_refs = refs[1:]
        except (KeyError, IndexError) as e:
            entry["status"] = "failed"
            print(f"   ❌ [lf:{shot_id}] Cannot resolve references: {e}")
            await _save_prompts_locked(output_dir, prompts)
            return
        print(f"   🎨 [lf:{shot_id}] Generating via Flux Klein edit (legacy)...")
        res = generate_flux_edit(prompt, out_path, scene_img, char_refs)

    if res.get("status") == "success":
        entry["status"] = "generated"
        entry["output_path"] = res["generated_image_path"]
        print(f"   ✅ [lf:{shot_id}] Saved to {res['generated_image_path']}")
    else:
        entry["status"] = "failed"
        raise RuntimeError(f"LF {shot_id} failed: {res.get('message')}")
    await _save_prompts_locked(output_dir, prompts)


async def _run_lf_consistency_patch(ctx, shot_id: str, output_dir: str) -> None:
    """Apply ONE LF consistency patch via Flux Klein 9B. Idempotent.

    Mirrors _run_consistency_patch but uses the LF (not FF) as the Flux Klein
    base image. Char sheets are loaded as the reference images.

    CRITICAL: The prompt for an LF patch must preserve the LF delta from the FF
    (pose/expression/camera shift). It must NOT revert the LF to FF's state.
    Enforced by the lf_consistency_prompter system prompt + validate_prompts_node.

    Skip behavior:
    - status == 'skipped' (continuation shot or empty characters_present): skip silently.
    - status == 'generated' && output_path: skip idempotent.
    - LF base image not yet generated: mark failed and skip (video phase will
      also skip this shot).
    """
    import sys
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if here not in sys.path:
        sys.path.insert(0, here)
    from tools.comfyui_tools import generate_flux_edit  # type: ignore

    prompts = _load_prompts(output_dir)
    entry = prompts.get("lf_consistency_patches", {}).get(shot_id)
    if not entry:
        return  # No LF consistency patch in prompts.json — not an error (chars empty).
    if entry.get("status") in ("skipped", "generated"):
        return
    if entry.get("status") == "generated" and entry.get("output_path"):
        return

    base_image_ref = entry.get("base_image") or ""
    if not base_image_ref:
        # LF consistency patch was skipped upstream — hasn't been marked 'skipped' yet.
        entry["status"] = "skipped"
        await _save_prompts_locked(output_dir, prompts)
        return

    try:
        scene_img = _resolve_ref(base_image_ref, prompts)
        char_refs = [_resolve_ref(r, prompts) for r in (entry.get("reference_images") or [])]
    except KeyError as e:
        entry["status"] = "failed"
        print(f"   ❌ [lf_cp:{shot_id}] Cannot resolve references: {e}")
        await _save_prompts_locked(output_dir, prompts)
        return  # Skip rather than raise — the LF base may not be generated yet.

    images_dir = os.path.join(output_dir, "images")
    out_path = os.path.join(images_dir, f"{shot_id}_lf_consistent.png")
    print(f"   🎨 [lf_cp:{shot_id}] Generating LF consistency patch...")
    res = generate_flux_edit(entry["prompt"], out_path, scene_img, char_refs)
    if res.get("status") == "success":
        entry["status"] = "generated"
        entry["output_path"] = res["generated_image_path"]
        print(f"   ✅ [lf_cp:{shot_id}] Saved to {res['generated_image_path']}")
    else:
        entry["status"] = "failed"
        raise RuntimeError(f"LF consistency patch {shot_id} failed: {res.get('message')}")
    await _save_prompts_locked(output_dir, prompts)


async def _run_video(ctx, shot_id: str, output_dir: str) -> None:
    """Generate ONE LTX FFLF video. Idempotent.
    Note on Issue ISSUE-003: LTX video model accepts 0 ref images but builder sends
    2 → silently truncated. generate_ltx_video now gracefully handles null/empty
    ff_image_path (see tools/comfyui_tools.py update below).
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
        return  # Skip rather than crash; Wave-2 FF/LF chain breakdown is a known ISSUE-008.

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


def _make_review_node(func, *args, name_suffix: str):
    """Curried FunctionNode for vision-review LLM calls. Uses the lighter
    _REVIEW_RETRY_CONFIG (3 attempts vs 5). Args[0] is shot_id.

    Vision review functions themselves NEVER raise on review failures — they
    sink errors into review_skipped entries. RetryConfig only catches transient
    network / file-system errors during the multimodal call.
    """
    async def _wrapped(ctx):
        await func(ctx, *args)
    return FunctionNode(
        func=_wrapped,
        name=f"{args[0]}_{name_suffix}",
        retry_config=_REVIEW_RETRY_CONFIG,
    )


def _build_wave1_workflow(output_dir: str, wave1_shot_ids: list[str], wave2_shot_ids: list[str]) -> Workflow:
    """Wire a Workflow that runs Wave 1: char_sheets -> FF -> CP -> LF -> LF_CP -> review -> video.

    Phase order rationale:
    - cs (char sheets) must finish before FF so the char sheet output_paths exist
      for the CP and LF_CP phases to reference.
    - FF must finish before CP (CP base image is the FF).
    - LF (Ideogram T2I) is independent of CP in principle; runs after CP only to
      keep the phase pipeline simpler and to bound ComfyUI concurrency.
    - LF_CP (LF consistency patch) base image is the LF; must wait on LF.
    - ff_review + lf_review are audit-mode LLM calls that read char sheets +
      patched FF + patched LF; run after LF_CP so all images are on disk.
    - video phase uses both consistency_patches (FF) and lf_consistency_patches
      (LF) output_paths; must wait on review_join (which waits on LF_CP).
    """
    # Lazy import of vision-review per-shot node functions. Avoids a circular
    # import: vision_review_nodes imports _resolve_ref / _load_prompts from this
    # module, so we defer the reverse import to function-call time.
    from .vision_review_nodes import _run_ff_vision_review, _run_lf_vision_review

    prompts = _load_prompts(output_dir)
    char_sheet_ids = list(prompts.get("character_sheets", {}).keys())

    cs_nodes = [_make_node(_run_char_sheet, sid, output_dir, name_suffix="cs") for sid in char_sheet_ids]
    ff_nodes = [_make_node(_run_ff, sid, output_dir, name_suffix="ff") for sid in wave1_shot_ids]
    cp_nodes = [_make_node(_run_consistency_patch, sid, output_dir, name_suffix="cp") for sid in wave1_shot_ids]
    lf_nodes = [_make_node(_run_lf, sid, output_dir, name_suffix="lf") for sid in wave1_shot_ids]
    # LF_CP nodes — one per Wave 1 shot. Skips internally if entry is missing or skipped.
    lf_cp_nodes = [_make_node(_run_lf_consistency_patch, sid, output_dir, name_suffix="lf_cp") for sid in wave1_shot_ids]
    # Vision review nodes (audit, non-blocking) — review the FF + LF consistency patches.
    # They use a separate lighter RetryConfig since these are LLM calls, not ComfyUI.
    ff_review_nodes = [
        _make_review_node(_run_ff_vision_review, sid, output_dir, name_suffix="ff_rev")
        for sid in wave1_shot_ids
    ]
    lf_review_nodes = [
        _make_review_node(_run_lf_vision_review, sid, output_dir, name_suffix="lf_rev")
        for sid in wave1_shot_ids
    ]
    video_nodes = [_make_node(_run_video, sid, output_dir, name_suffix="video") for sid in wave1_shot_ids]

    edges: list = []
    cs_join = JoinNode(name="cs_join")
    ff_join = JoinNode(name="ff_join")
    cp_join = JoinNode(name="cp_join")
    lf_join = JoinNode(name="lf_join")
    lf_cp_join = JoinNode(name="lf_cp_join")
    review_join = JoinNode(name="review_join")

    # 1. Char sheets phase
    if cs_nodes:
        for n in cs_nodes:
            edges.append((START, n))
            edges.append((n, cs_join))
        # Char sheets -> FF phase
        for n in ff_nodes:
            edges.append((cs_join, n))
    else:
        # No char_sheets; FF nodes connect directly to START
        for n in ff_nodes:
            edges.append((START, n))

    for n in ff_nodes:
        edges.append((n, ff_join))

    # 3. Consistency patches phase (FF -> CP)
    for n in cp_nodes:
        edges.append((ff_join, n))
        edges.append((n, cp_join))

    # 4. LF phase (CP -> LF)
    for n in lf_nodes:
        edges.append((cp_join, n))
        edges.append((n, lf_join))

    # 5. LF consistency patch phase (LF -> LF_CP)
    for n in lf_cp_nodes:
        edges.append((lf_join, n))
        edges.append((n, lf_cp_join))

    # 6. Vision review phase (LF_CP -> ff_review + lf_review in parallel -> review_join)
    #    Both review phase types run concurrently; all feed into review_join.
    for n in ff_review_nodes:
        edges.append((lf_cp_join, n))
        edges.append((n, review_join))
    for n in lf_review_nodes:
        edges.append((lf_cp_join, n))
        edges.append((n, review_join))

    # 7. Video phase (review_join -> video)
    for n in video_nodes:
        edges.append((review_join, n))

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
    extract FF -> LF -> video for shot N, then move to shot N+1. The nodes remain
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

    wave1_wf = _build_wave1_workflow(output_dir, wave1_shot_ids, wave2_shot_ids)
    ss1 = InMemorySessionService()
    s1 = await ss1.create_session(app_name="wave1", user_id="director", state={"output_dir": output_dir})
    runner1 = Runner(agent=wave1_wf, app_name="wave1", session_service=ss1)
    msg = types.Content(parts=[types.Part(text="run wave 1")])
    try:
        async for ev in runner1.run_async(user_id="director", session_id=s1.id, new_message=msg):
            pass
    except Exception as e:
        print(f"⚠️ Wave 1 workflow raised (continuing to Wave 2 with surviving artifacts): {e}")
        traceback.print_exc()

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
    try:
        async for ev in runner2.run_async(user_id="director", session_id=s2.id, new_message=msg2):
            pass
    except Exception as e:
        print(f"⚠️ Wave 2 workflow raised: {e}")
        traceback.print_exc()
