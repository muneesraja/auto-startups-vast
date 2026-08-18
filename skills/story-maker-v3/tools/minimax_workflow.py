"""Headless Minimax H3 R2V workflow helpers for ComfyUI /prompt.

Drives the repo-root ``workflows/comfyui/Minimax H3 R2V - Final.json`` graph
with a storyboard sheet as the ONLY reference image plus a timeline prompt.
The UI export is converted to an API prompt, then simplified so no optional
custom nodes are required:

  - the storyboard sheet is uploaded and wired into ``ref_images.ref_image_0``;
  - every other reference input (extra images, ref videos, ref audios) is
    dropped, along with the loader nodes that fed them;
  - prompt / width / height / length are written as literal values on the
    ``MiniMaxH3ReferenceToVideo`` node (the PrimitiveFloat / math /
    ResolutionSelector helper nodes are inlined and removed);
  - ``PathchSageAttentionKJ`` is bypassed when the server does not have it.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any

import config
from tools.comfyui_tools import (
    curl_json,
    download_output,
    has_node_type,
    upload_image,
    upload_video,
    wait_for_prompt,
)
from tools.duration_budget import GEN_MAX, GEN_MIN, minimax_frames

DECORATIVE = {"MarkdownNote", "Note", "Comment"}
_SKIP_WIDGET = {"fixed", "randomize", "increment", "decrement"}

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MINIMAX_UI = (
    _REPO_ROOT / "workflows" / "comfyui" / "Minimax H3 R2V - Final - v2.json"
)
_UPLOAD_SUBFOLDER = "story-maker-v3"

MINIMAX_NODE = "MiniMaxH3ReferenceToVideo"

# Cached UI->API conversion for the current process
_API_WORKFLOW_CACHE: dict[str, dict] | None = None


def minimax_workflow_path() -> Path:
    override = os.getenv("MINIMAX_H3_WORKFLOW")
    if override:
        return Path(override)
    return DEFAULT_MINIMAX_UI


def resolution_for(megapixels: float, aspect: str = "16:9", multiple: int = 32) -> tuple[int, int]:
    """Compute (width, height) like the workflow's ResolutionSelector.

    Ceil each side to the next multiple of ``multiple`` (0.6MP 16:9 -> 1056x608).
    """
    aw, ah = (float(x) for x in aspect.split(":"))
    px = megapixels * 1_000_000
    w = math.sqrt(px * aw / ah)
    h = math.sqrt(px * ah / aw)
    snap = lambda v: int(math.ceil(v / multiple) * multiple)
    return snap(w), snap(h)


# ---------------------------------------------------------------------------
# UI -> API conversion (generic; keeps dynamic inputs like ref_images.*)
# ---------------------------------------------------------------------------

def _input_order(object_info: dict, class_type: str) -> list[str]:
    inp = object_info[class_type]["input"]
    return list(inp.get("required", {}).keys()) + list(inp.get("optional", {}).keys())


def _build_link_map(links: list) -> dict[int, tuple[int, int]]:
    link_map: dict[int, tuple[int, int]] = {}
    for link in links or []:
        if isinstance(link, dict):
            link_map[link["id"]] = (link["origin_id"], link["origin_slot"])
        elif isinstance(link, (list, tuple)) and len(link) >= 3:
            link_map[int(link[0])] = (int(link[1]), int(link[2]))
    return link_map


def ui_workflow_to_api(ui_workflow: dict, object_info: dict) -> dict[str, dict]:
    """Convert a ComfyUI UI graph export into an API prompt dict.

    Unlike the classic converter, linked inputs whose names are NOT in
    object_info (dynamic/autogrow inputs such as ``ref_images.ref_image_0``)
    are preserved verbatim — the Minimax node relies on them.
    """
    link_map = _build_link_map(ui_workflow.get("links"))
    api: dict[str, dict] = {}
    for node in ui_workflow.get("nodes", []):
        ntype = node["type"]
        if ntype in DECORATIVE:
            continue
        if ntype not in object_info:
            raise KeyError(f"Unknown node type on server: {ntype}")
        order = _input_order(object_info, ntype)
        linked: dict[str, list] = {}
        widget_by_name: dict[str, object] = {}
        widget_inputs = [
            inp["name"]
            for inp in (node.get("inputs") or [])
            if inp.get("widget") is not None and inp.get("name")
        ]
        widgets = list(node.get("widgets_values") or [])
        if isinstance(node.get("widgets_values"), dict):
            widget_by_name.update(node["widgets_values"])
            widgets = []
        for i, wname in enumerate(widget_inputs):
            if i >= len(widgets):
                break
            if widgets[i] in _SKIP_WIDGET:
                continue
            widget_by_name[wname] = widgets[i]
        for inp in node.get("inputs") or []:
            name = inp.get("name")
            link_id = inp.get("link")
            if link_id is not None and link_id in link_map:
                origin_id, origin_slot = link_map[link_id]
                linked[name] = [str(origin_id), int(origin_slot)]
        wi_extra = len(widget_inputs)
        inputs: dict = {}
        for key in order:
            if key in linked:
                inputs[key] = linked[key]
                continue
            if key in widget_by_name:
                inputs[key] = widget_by_name[key]
                continue
            while wi_extra < len(widgets) and widgets[wi_extra] in _SKIP_WIDGET:
                wi_extra += 1
            if wi_extra < len(widgets):
                inputs[key] = widgets[wi_extra]
                wi_extra += 1
        # Preserve dynamic linked inputs not present in object_info order.
        for key, val in linked.items():
            if key not in inputs:
                inputs[key] = val
        api[str(node["id"])] = {"class_type": ntype, "inputs": inputs}
    return api


# ---------------------------------------------------------------------------
# Graph simplification + patching
# ---------------------------------------------------------------------------

def _find_node(api: dict[str, dict], class_type: str) -> str:
    for nid, node in api.items():
        if node.get("class_type") == class_type:
            return nid
    raise KeyError(f"workflow has no {class_type} node")


def _link_target(val: Any) -> str | None:
    if isinstance(val, list) and len(val) == 2:
        return str(val[0])
    return None


def _prune_unreachable(api: dict[str, dict], roots: set[str]) -> None:
    """Drop every node not reachable (via input links) from ``roots``."""
    keep: set[str] = set()
    stack = [r for r in roots if r in api]
    while stack:
        nid = stack.pop()
        if nid in keep:
            continue
        keep.add(nid)
        for val in api[nid]["inputs"].values():
            tgt = _link_target(val)
            if tgt and tgt in api and tgt not in keep:
                stack.append(tgt)
    for nid in list(api):
        if nid not in keep:
            del api[nid]


def simplify_minimax_graph(api: dict[str, dict], object_info: dict) -> None:
    """Reduce the graph to: storyboard ref image + literal prompt/size/length.

    ref_videos.* / ref_audios.* slots are kept when the server has the
    corresponding loader nodes (VHS_LoadVideo / LoadAudio), so bridge clips
    can wire them dynamically. They are pruned per-call in patch_generation
    when not used, keeping existing single-sheet renders byte-identical.
    """
    mm_id = _find_node(api, MINIMAX_NODE)
    mm = api[mm_id]["inputs"]

    has_vhs = "VHS_LoadVideo" in object_info
    has_load_audio = "LoadAudio" in object_info

    # 1. Keep ref_image_* slots; keep ref_videos.* if VHS_LoadVideo is present,
    #    keep ref_audios.* if LoadAudio is present; always drop ref_video_audios.
    for key in list(mm.keys()):
        if key.startswith("ref_video_audios."):
            del mm[key]
        elif key.startswith("ref_videos.") and not has_vhs:
            del mm[key]
        elif key.startswith("ref_audios.") and not has_load_audio:
            del mm[key]

    # 2. Inline linked prompt / width / height / length into literal values
    #    (patched per generation later); drop the helper nodes via pruning.
    for key, default in (("prompt", ""), ("width", 1056), ("height", 608), ("length", 125)):
        if _link_target(mm.get(key)):
            mm[key] = default

    # 3. Bypass PathchSageAttentionKJ if the server lacks it.
    if "PathchSageAttentionKJ" not in object_info:
        for node in api.values():
            for key, val in node["inputs"].items():
                tgt = _link_target(val)
                if tgt and api.get(tgt, {}).get("class_type") == "PathchSageAttentionKJ":
                    node["inputs"][key] = api[tgt]["inputs"]["model"]

    # 4. Prune everything no longer reachable from the save nodes.
    #    Note: ref_video/ref_audio loader nodes are only reachable if their
    #    slot is still wired on the Minimax node, so unused ones get pruned.
    roots = {
        nid for nid, node in api.items()
        if node.get("class_type") in ("SaveVideo", "VHS_VideoCombine", "SaveAnimatedWEBP")
    }
    if not roots:
        raise KeyError("workflow has no SaveVideo node")
    _prune_unreachable(api, roots)


def load_api_workflow() -> dict[str, dict]:
    """Load + convert + simplify the Minimax UI workflow (cached per process)."""
    global _API_WORKFLOW_CACHE
    if _API_WORKFLOW_CACHE is not None:
        return json.loads(json.dumps(_API_WORKFLOW_CACHE))
    path = minimax_workflow_path()
    if not path.is_file():
        raise FileNotFoundError(f"Minimax workflow not found: {path}")
    ui = json.loads(path.read_text(encoding="utf-8"))
    object_info = curl_json("GET", "/object_info")
    # Drop node types the server lacks IF they are bypassable/prunable.
    missing = {n["type"] for n in ui.get("nodes", []) if n["type"] not in DECORATIVE and n["type"] not in object_info}
    prunable = {"VHS_LoadVideo", "LoadAudio", "PathchSageAttentionKJ", "ResolutionSelector", "ComfyMathExpression", "PrimitiveFloat", "PrimitiveStringMultiline"}
    hard_missing = missing - prunable
    if hard_missing:
        raise RuntimeError(f"ComfyUI host is missing required node types: {sorted(hard_missing)}")
    if missing:
        # Temporarily register empty stubs so conversion succeeds; the nodes
        # get pruned by simplify_minimax_graph.
        for m in missing:
            object_info[m] = {"input": {"required": {}, "optional": {}}}
    api = ui_workflow_to_api(ui, object_info)
    simplify_minimax_graph(api, object_info)
    _API_WORKFLOW_CACHE = json.loads(json.dumps(api))
    return api


def _collect_ref_slots(mm: dict, prefix: str, slot_prefix: str) -> list[tuple[int, str]]:
    """Collect and sort (index, slot_name) for a ref_* input group."""
    slots: list[tuple[int, str]] = []
    for key in list(mm.keys()):
        if not key.startswith(prefix):
            continue
        suffix = key.split(".")[-1]
        if not suffix.startswith(slot_prefix):
            continue
        try:
            slots.append((int(suffix.split("_")[-1]), key))
        except ValueError:
            continue
    slots.sort()
    return slots


def _wire_ref_slots(
    api: dict[str, dict],
    mm: dict,
    ref_slots: list[tuple[int, str]],
    names: list[str],
    loader_class: str,
    slot_prefix: str,
    group_prefix: str,
    default_inputs: dict,
) -> list[tuple[int, str]]:
    """Wire reference names into loader nodes, adding loaders dynamically.

    Returns the updated ref_slots list. Mirrors the ref_images pattern:
    grow loaders when more names than slots, set filenames, delete unused.
    """
    if not ref_slots and not names:
        return ref_slots

    if len(names) > len(ref_slots):
        needed = len(names) - len(ref_slots)
        numeric_ids = [int(k) for k in api.keys() if k.isdigit()]
        next_id = max(numeric_ids) + 1 if numeric_ids else 1
        next_idx = ref_slots[-1][0] + 1 if ref_slots else 0
        for _ in range(needed):
            new_id = str(next_id)
            new_slot = f"{group_prefix}.{slot_prefix}_{next_idx}"
            api[new_id] = {
                "class_type": loader_class,
                "inputs": dict(default_inputs),
            }
            mm[new_slot] = [new_id, 0]
            ref_slots.append((next_idx, new_slot))
            next_id += 1
            next_idx += 1
        ref_slots.sort()

    for (_, slot), name in zip(ref_slots, names):
        load_id = _link_target(mm.get(slot))
        if not load_id or api.get(load_id, {}).get("class_type") != loader_class:
            raise KeyError(f"{slot} is not fed by a {loader_class} node")
        # Set the primary filename widget (image for LoadImage, video for VHS_LoadVideo)
        if loader_class == "VHS_LoadVideo":
            api[load_id]["inputs"]["video"] = name
        elif loader_class == "LoadAudio":
            api[load_id]["inputs"]["audio"] = name
        else:
            api[load_id]["inputs"]["image"] = name

    # Drop unused slots and their loader nodes
    for _, slot in ref_slots[len(names):]:
        del mm[slot]

    return ref_slots


def patch_generation(
    api: dict[str, dict],
    *,
    reference_image_names: list[str],
    prompt: str,
    duration_seconds: float,
    width: int,
    height: int,
    seed: int,
    filename_prefix: str,
    reference_video_names: list[str] | None = None,
    reference_audio_names: list[str] | None = None,
) -> None:
    mm_id = _find_node(api, MINIMAX_NODE)
    mm = api[mm_id]["inputs"]

    # --- Reference images (existing behaviour) ---
    ref_slots = _collect_ref_slots(mm, "ref_images.ref_image_", "ref_image_")

    if not ref_slots:
        raise KeyError("no ref_images slots found on Minimax H3 node")

    if len(reference_image_names) > len(ref_slots):
        needed = len(reference_image_names) - len(ref_slots)
        numeric_ids = [int(k) for k in api.keys() if k.isdigit()]
        next_id = max(numeric_ids) + 1 if numeric_ids else 1
        next_idx = ref_slots[-1][0] + 1 if ref_slots else 0
        for _ in range(needed):
            new_id = str(next_id)
            new_slot = f"ref_images.ref_image_{next_idx}"
            api[new_id] = {
                "class_type": "LoadImage",
                "inputs": {"image": "", "upload": "image"},
            }
            mm[new_slot] = [new_id, 0]
            ref_slots.append((next_idx, new_slot))
            next_id += 1
            next_idx += 1
        ref_slots.sort()

    for (_, slot), name in zip(ref_slots, reference_image_names):
        load_id = _link_target(mm.get(slot))
        if not load_id or api.get(load_id, {}).get("class_type") != "LoadImage":
            raise KeyError(f"{slot} is not fed by a LoadImage node")
        api[load_id]["inputs"]["image"] = name

    for _, slot in ref_slots[len(reference_image_names):]:
        del mm[slot]

    # --- Reference videos (dynamic, like ref_images) ---
    video_names = reference_video_names or []
    video_slots = _collect_ref_slots(mm, "ref_videos.ref_video_", "ref_video_")
    if video_names:
        vhs_inputs = {
            "video": "", "force_rate": 0, "custom_width": 0, "custom_height": 0,
            "frame_load_cap": 0, "skip_first_frames": 0, "select_every_nth": 1,
            "format": "AnimateDiff",
        }
        _wire_ref_slots(
            api, mm, video_slots, video_names,
            loader_class="VHS_LoadVideo",
            slot_prefix="ref_video_",
            group_prefix="ref_videos",
            default_inputs=vhs_inputs,
        )
    else:
        # No video refs: drop all video slots so the graph is clean
        for _, slot in video_slots:
            del mm[slot]

    # --- Reference audios (dynamic, like ref_images) ---
    audio_names = reference_audio_names or []
    audio_slots = _collect_ref_slots(mm, "ref_audios.ref_audio_", "ref_audio_")
    if audio_names:
        _wire_ref_slots(
            api, mm, audio_slots, audio_names,
            loader_class="LoadAudio",
            slot_prefix="ref_audio_",
            group_prefix="ref_audios",
            default_inputs={"audio": "", "upload": "audio"},
        )
    else:
        for _, slot in audio_slots:
            del mm[slot]

    roots = {
        nid for nid, node in api.items()
        if node.get("class_type") in ("SaveVideo", "VHS_VideoCombine", "SaveAnimatedWEBP")
    }
    if not roots:
        raise KeyError("workflow has no SaveVideo node")
    _prune_unreachable(api, roots)

    dur = max(GEN_MIN, min(GEN_MAX, float(duration_seconds)))
    mm["prompt"] = prompt
    mm["width"] = int(width)
    mm["height"] = int(height)
    mm["length"] = minimax_frames(dur)

    for node in api.values():
        if node["class_type"] == "RandomNoise":
            node["inputs"]["noise_seed"] = int(seed)
        elif node["class_type"] == "SaveVideo":
            node["inputs"]["filename_prefix"] = filename_prefix


def _collect_video_outputs(outputs: dict) -> list[dict]:
    files: list[dict] = []
    for node_output in (outputs or {}).values():
        for key in ("videos", "images", "gifs"):
            for f in node_output.get(key, []) or []:
                name = f.get("filename", "")
                if name.lower().endswith((".mp4", ".webm", ".mov", ".mkv")):
                    files.append(f)
    return files


def render_generation(
    *,
    sheet_path: str,
    prompt: str,
    duration_seconds: float,
    output_path: str,
    seed: int = 42,
    megapixels: float | None = None,
    aspect: str | None = None,
    extra_reference_paths: list[str] | None = None,
    extra_reference_video_paths: list[str] | None = None,
    extra_reference_audio_paths: list[str] | None = None,
    max_wait: int = 7200,
) -> dict:
    """Render one <=15s Minimax H3 generation from a storyboard sheet.

    Video/audio references are uploaded and wired into ref_videos/ref_audios
    dynamically, exactly like image references. When none are passed, the
    graph is pruned to the same shape as before (single sheet ref image).
    """
    if not os.path.isfile(sheet_path):
        return {"status": "error", "message": f"storyboard sheet missing: {sheet_path}"}

    mp = megapixels if megapixels is not None else config.MINIMAX_MEGAPIXELS
    asp = aspect or config.MINIMAX_ASPECT
    width, height = resolution_for(mp, asp)

    up = upload_image(sheet_path, subfolder=_UPLOAD_SUBFOLDER)
    if not up or "name" not in up:
        return {"status": "error", "message": f"sheet upload failed: {sheet_path}"}
    server_name = f"{up.get('subfolder')}/{up['name']}" if up.get("subfolder") else up["name"]
    reference_image_names = [server_name]

    for ref_path in (extra_reference_paths or []):
        up2 = upload_image(ref_path, subfolder=_UPLOAD_SUBFOLDER)
        if not up2 or "name" not in up2:
            return {"status": "error", "message": f"reference upload failed: {ref_path}"}
        name2 = f"{up2.get('subfolder')}/{up2['name']}" if up2.get("subfolder") else up2["name"]
        reference_image_names.append(name2)

    # Upload video references (for bridge clips conditioned on rendered tails/heads)
    reference_video_names: list[str] = []
    for vid_path in (extra_reference_video_paths or []):
        upv = upload_video(vid_path, subfolder=_UPLOAD_SUBFOLDER)
        if not upv or "name" not in upv:
            return {"status": "error", "message": f"video reference upload failed: {vid_path}"}
        vname = f"{upv.get('subfolder')}/{upv['name']}" if upv.get("subfolder") else upv["name"]
        reference_video_names.append(vname)

    # Upload audio references (for audio carry-over across seams)
    reference_audio_names: list[str] = []
    for aud_path in (extra_reference_audio_paths or []):
        upa = upload_image(aud_path, subfolder=_UPLOAD_SUBFOLDER)
        if not upa or "name" not in upa:
            return {"status": "error", "message": f"audio reference upload failed: {aud_path}"}
        aname = f"{upa.get('subfolder')}/{upa['name']}" if upa.get("subfolder") else upa["name"]
        reference_audio_names.append(aname)

    api = load_api_workflow()
    stem = Path(output_path).stem
    patch_generation(
        api,
        reference_image_names=reference_image_names,
        prompt=prompt,
        duration_seconds=duration_seconds,
        width=width,
        height=height,
        seed=seed,
        filename_prefix=f"story-maker-v3/{stem}",
        reference_video_names=reference_video_names or None,
        reference_audio_names=reference_audio_names or None,
    )

    queued = curl_json("POST", "/prompt", data={"prompt": api}, timeout=120)
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        return {"status": "error", "message": f"queue failed: {json.dumps(queued)[:400]}"}

    t0 = time.time()
    outputs = wait_for_prompt(prompt_id, max_wait=max_wait, poll_interval=10)
    videos = _collect_video_outputs(outputs)
    if not videos:
        return {"status": "error", "message": f"no video output in history for {prompt_id}"}
    f = videos[0]
    ok = download_output(
        f["filename"], output_path,
        subfolder=f.get("subfolder", ""), is_video=True,
        file_type=f.get("type", "output"),
    )
    if not ok:
        return {"status": "error", "message": f"download failed: {f['filename']}"}
    return {
        "status": "success",
        "output_path": output_path,
        "prompt_id": prompt_id,
        "width": width,
        "height": height,
        "frames": minimax_frames(max(GEN_MIN, min(GEN_MAX, float(duration_seconds)))),
        "elapsed_seconds": round(time.time() - t0, 1),
    }
