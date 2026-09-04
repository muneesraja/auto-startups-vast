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
    upload_image,
    wait_for_prompt,
)
from tools.duration_budget import GEN_MAX, GEN_MIN, minimax_frames

DECORATIVE = {"MarkdownNote", "Note", "Comment"}
_SKIP_WIDGET = {"fixed", "randomize", "increment", "decrement"}

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MINIMAX_UI = (
    _REPO_ROOT / "workflows" / "comfyui" / "Minimax H3 R2V - Final - v2.json"
)
_UPLOAD_SUBFOLDER = "story-maker-v4c"

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
    """Reduce the graph to: storyboard ref image + literal prompt/size/length."""
    mm_id = _find_node(api, MINIMAX_NODE)
    mm = api[mm_id]["inputs"]

    # 1. Keep all wired ref_image_* slots; drop video/audio references.
    for key in list(mm.keys()):
        if key.startswith(("ref_videos.", "ref_audios.", "ref_video_audios.")):
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
) -> None:
    mm_id = _find_node(api, MINIMAX_NODE)
    mm = api[mm_id]["inputs"]

    ref_slots: list[tuple[int, str]] = []
    for key in list(mm.keys()):
        if not key.startswith("ref_images.ref_image_"):
            continue
        suffix = key.split(".")[-1]
        if not suffix.startswith("ref_image_"):
            continue
        try:
            ref_slots.append((int(suffix.split("_")[-1]), key))
        except ValueError:
            continue
    ref_slots.sort()

    if not ref_slots:
        raise KeyError("no ref_images slots found on Minimax H3 node")
    if len(reference_image_names) > len(ref_slots):
        raise ValueError(
            f"more reference images ({len(reference_image_names)}) than wired slots ({len(ref_slots)})"
        )

    for (_, slot), name in zip(ref_slots, reference_image_names):
        load_id = _link_target(mm.get(slot))
        if not load_id or api.get(load_id, {}).get("class_type") != "LoadImage":
            raise KeyError(f"{slot} is not fed by a LoadImage node")
        api[load_id]["inputs"]["image"] = name

    # Drop unused ref image slots and their loader nodes so the graph
    # works when fewer than the wired number of references are supplied.
    for _, slot in ref_slots[len(reference_image_names):]:
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
    max_wait: int = 7200,
) -> dict:
    """Render one <=15s Minimax H3 generation from a storyboard sheet."""
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
        filename_prefix=f"story-maker-v4c/{stem}",
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
