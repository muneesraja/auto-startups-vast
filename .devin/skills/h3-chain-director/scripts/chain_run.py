#!/usr/bin/env python3
"""Per-scene orchestrator for the H3 seamless-chain workflow.

Submits ONE scene at a time to ``workflows/comfyui/minimax-h3-seamless-chain-global-refs.json``,
then polls, extracts sample frames, and writes the result back into the ledger.

The outer loop lives here (in Python), not in the graph — this is the
architectural consequence of the checkpoint prefix-hash contract (see
``references/checkpoint-contract.md``): submitting scene_range=k lets us swap
refs, repair the next prompt, and reroll seeds between scenes without losing
prior work.

Usage::

    python3 scripts/chain_run.py --ledger state.json --scene 1
    python3 scripts/chain_run.py --ledger state.json --from 3 --to 5
    python3 scripts/chain_run.py --ledger state.json --scene 1 --dry-run
    python3 scripts/chain_run.py --ledger state.json --scene 1 --width 544 --height 320 --steps 5

Reuses (import by path, does NOT copy):
  - ``story-maker-v3/tools/comfyui_tools.py``  (upload/queue/poll/download)
  - ``story-maker-v3/tools/minimax_workflow.py::ui_workflow_to_api``  (UI→API conversion)
  - ``story-maker-v3/config.py``  (COMFYUI_URL, auth)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[2]
STORY_MAKER = REPO_ROOT / "skills" / "story-maker-v3"

sys.path.insert(0, str(STORY_MAKER))
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import config  # type: ignore  # noqa: E402

from tools.comfyui_tools import (  # type: ignore  # noqa: E402
    curl_json,
    download_output,
    upload_image,
    wait_for_prompt,
)
from tools.minimax_workflow import ui_workflow_to_api  # type: ignore  # noqa: E402

from assets_registry import GlobalAssetRegistry  # noqa: E402

WORKFLOW_PATH = REPO_ROOT / "workflows" / "comfyui" / "minimax-h3-seamless-chain-global-refs.json"


# ---------------------------------------------------------------------------
# Plan generation from ledger
# ---------------------------------------------------------------------------


def ledger_to_plan(ledger: dict) -> dict:
    """Generate the H3 Chain Plan JSON from the continuity ledger.

    The ledger is the single source of truth; plan_json is generated (never
    hand-edited) so the hashed fields of already-rendered clips stay frozen.
    """
    clips = ledger.get("clips", [])
    cast = ledger.get("cast", [])

    # Build prompt_prefix from cast + shared sections
    prefix_parts = []
    # subject_definitions
    sd_lines = []
    for c in cast:
        if isinstance(c, dict):
            label = c.get("label", f"<Subject {c.get('id', '?')}>")
            lock = c.get("appearance_lock", "")
            sd_lines.append(f"{label} is {lock}.")
    if sd_lines:
        prefix_parts.append("subject_definitions:\n" + "\n".join(sd_lines))

    # non_diegetic_music (if present in ledger)
    music = ledger.get("music", "")
    if music:
        prefix_parts.append(f"non_diegetic_music: {music}")

    prompt_prefix = "\n\n".join(prefix_parts)

    shots = []
    for i, clip in enumerate(clips):
        if not isinstance(clip, dict):
            continue
        prompt = ""
        pf = clip.get("prompt_file")
        if pf and Path(pf).is_file():
            prompt = Path(pf).read_text(encoding="utf-8")

        shot: dict[str, Any] = {
            "id": clip.get("id", f"clip_{i+1:02d}"),
            "prompt": prompt,
            "prompt_hash": "sha256:" + hashlib.sha256(prompt.encode()).hexdigest(),
            "seed": int(clip.get("seed", 0)),
            "steps": int(clip.get("steps", 5)),
            "length": int(clip.get("raw_frames", 362)),
        }
        shots.append(shot)

    plan = {
        "run_name": ledger.get("run_name", "h3_chain_run"),
        "compatibility": {
            "width": ledger.get("width", 960),
            "height": ledger.get("height", 544),
            "context_length": ledger.get("context_length", 22),
            "anchor_mode": ledger.get("anchor_mode", "head"),
            "encode_mode": ledger.get("encode_mode", "video"),
            "crop": ledger.get("crop", False),
            "audio_mode": ledger.get("audio_mode", "source_track"),
            "audio_context_length": ledger.get("audio_context_length", 0),
            "generation_fingerprint": ledger.get("generation_fingerprint", ""),
            "segment_crf": ledger.get("segment_crf", 20),
        },
        "defaults": {"duration_seconds": 15, "steps": 5},
        "base_seed": ledger.get("base_seed", 0),
        "prompt_prefix": prompt_prefix,
        "shots": shots,
    }
    return plan


# ---------------------------------------------------------------------------
# Workflow patching
# ---------------------------------------------------------------------------


def _find_nodes(ui_workflow: dict, node_type: str) -> list[dict]:
    return [n for n in ui_workflow.get("nodes", []) if n.get("type") == node_type]


def _find_node(ui_workflow: dict, node_type: str) -> dict | None:
    nodes = _find_nodes(ui_workflow, node_type)
    return nodes[0] if nodes else None


def _next_link_id(ui_workflow: dict) -> int:
    """Return a new link id one greater than the largest existing link id."""
    max_id = 0
    for link in ui_workflow.get("links", []):
        if isinstance(link, dict):
            max_id = max(max_id, link.get("id", 0))
        elif isinstance(link, (list, tuple)) and len(link) >= 1:
            max_id = max(max_id, int(link[0]))
    return max_id + 1


def patch_workflow(
    ui_workflow: dict,
    plan: dict,
    scene: int,
    *,
    song_path: str | None = None,
    ref_image_paths: list[str] | None = None,
    width: int | None = None,
    height: int | None = None,
    steps: int | None = None,
) -> dict:
    """Patch the UI workflow widgets for a single-scene submission.

    Patches:
      - ChainPlan(1700): plan_json + all compatibility widgets
      - LoopStart(1701): start_clip = scene, scene_range = str(scene)
      - LoadImage nodes: upload + set filenames for ref images
      - LoadAudio: set song filename
      - Width/height/steps overrides for low-res dial-in

    ChainPlan widget layout (15 widgets):
      [0]=plan_json, [1]=run_name, [2]=fingerprint, [3]=width, [4]=height,
      [5]=context_length, [6]=encode_mode, [7]=anchor_mode, [8]=crop,
      [9]=audio_mode, [10]=audio_context_length, [11]=default_duration_seconds,
      [12]=default_steps, [13]=base_seed, [14]=segment_crf

    LoopStart widget layout: [0]=start_clip, [1]=scene_range
    """
    compat = plan.get("compatibility", {})
    if width:
        compat["width"] = width
    if height:
        compat["height"] = height
    if steps:
        for shot in plan.get("shots", []):
            shot["steps"] = steps
        compat.setdefault("default_steps", steps)

    # ChainPlan node — patch by known widget index
    plan_node = _find_node(ui_workflow, "MiniMaxH3ChainPlan")
    if plan_node:
        widgets = plan_node.setdefault("widgets_values", [])
        # Ensure we have enough slots
        while len(widgets) < 15:
            widgets.append("")
        widgets[0] = json.dumps(plan, ensure_ascii=False)
        widgets[1] = plan.get("run_name", "h3_chain_run")
        widgets[2] = compat.get("generation_fingerprint", f"{plan.get('run_name', 'run')}-fingerprint")
        widgets[3] = compat.get("width", 960)
        widgets[4] = compat.get("height", 544)
        widgets[5] = compat.get("context_length", 22)
        widgets[6] = compat.get("encode_mode", "video")
        widgets[7] = compat.get("anchor_mode", "head")
        widgets[8] = compat.get("crop", "disabled")
        widgets[9] = compat.get("audio_mode", "source_track")
        widgets[10] = compat.get("audio_context_length", 0)
        widgets[11] = plan.get("defaults", {}).get("duration_seconds", 15)
        widgets[12] = plan.get("defaults", {}).get("steps", 5)
        widgets[13] = plan.get("base_seed", 0)
        widgets[14] = compat.get("segment_crf", 20)

    # LoopStart node — [0]=start_clip, [1]=scene_range
    loop_start = _find_node(ui_workflow, "MiniMaxH3ChainLoopStart")
    if loop_start:
        widgets = loop_start.setdefault("widgets_values", [])
        while len(widgets) < 2:
            widgets.append("")
        widgets[0] = scene
        widgets[1] = str(scene)  # scene_range as string

    # ChainAssemble node — patch run_name (widgets_values[1] for main assemble)
    for node in _find_nodes(ui_workflow, "MiniMaxH3ChainAssemble"):
        if node.get("mode") != 2:
            widgets = node.setdefault("widgets_values", [])
            if len(widgets) >= 2:
                widgets[1] = plan.get("run_name", "h3_chain_run")

    # LoadImage nodes — upload ref images, set filenames, wire to ReferenceToVideo
    if ref_image_paths:
        load_image_nodes = _find_nodes(ui_workflow, "LoadImage")
        ref_node = _find_node(ui_workflow, "MiniMaxH3ReferenceToVideo")
        new_link_id = _next_link_id(ui_workflow)
        for idx, node in enumerate(load_image_nodes):
            if idx >= len(ref_image_paths):
                # Mute any extra LoadImage nodes that won't be used
                node["mode"] = 2
                break
            rpath = ref_image_paths[idx]
            if os.path.isfile(rpath):
                uploaded = upload_image(rpath, config.COMFYUI_URL, config.COMFYUI_AUTH)
                # upload_image returns a dict like {'name': '...', 'subfolder': '', 'type': 'input'}
                uploaded_name = uploaded.get("name") if isinstance(uploaded, dict) else str(uploaded)
                widgets = node.setdefault("widgets_values", [])
                if widgets:
                    widgets[0] = uploaded_name
                else:
                    widgets.append(uploaded_name)
                # The shipped workflow only wires the first LoadImage to
                # ref_images.ref_image_0. Wire the second LoadImage to
                # ref_images.ref_image_1 when a second ref is provided.
                if idx == 1 and ref_node and len(ref_node.get("inputs", [])) > 4:
                    link = [new_link_id, node["id"], 0, ref_node["id"], 4, "IMAGE"]
                    ui_workflow.setdefault("links", []).append(link)
                    # Make sure the input on ReferenceToVideo reflects the link
                    ref_node["inputs"][4]["link"] = new_link_id
                    new_link_id += 1

    # LoadAudio — set song filename, or remove if no song (generated_audio mode)
    load_audio = _find_node(ui_workflow, "LoadAudio")
    if load_audio:
        if song_path and os.path.isfile(song_path):
            # Upload audio to ComfyUI input dir
            widgets = load_audio.setdefault("widgets_values", [])
            fname = os.path.basename(song_path)
            if widgets:
                widgets[0] = fname
            else:
                widgets.append(fname)
        else:
            # No source audio — remove LoadAudio node and its links
            _remove_node(ui_workflow, load_audio["id"])

    # Remove LoadImage nodes that have no valid ref image
    if not ref_image_paths:
        load_image_nodes = _find_nodes(ui_workflow, "LoadImage")
        for node in load_image_nodes:
            _remove_node(ui_workflow, node["id"])

    return ui_workflow


def _remove_node(ui_workflow: dict, node_id: int) -> None:
    """Remove a node and all links referencing it from the UI workflow."""
    # Collect link IDs to remove
    dead_link_ids: set[int] = set()
    for link in ui_workflow.get("links", []):
        if isinstance(link, dict):
            if link.get("origin_id") == node_id or link.get("target_id") == node_id:
                dead_link_ids.add(link.get("id"))
        elif isinstance(link, (list, tuple)) and len(link) >= 4:
            # [link_id, origin_id, origin_slot, target_id, target_slot]
            if link[1] == node_id or link[3] == node_id:
                dead_link_ids.add(link[0])
    # Remove dead links
    ui_workflow["links"] = [
        link for link in ui_workflow.get("links", [])
        if not (
            (isinstance(link, dict) and link.get("id") in dead_link_ids)
            or (isinstance(link, (list, tuple)) and len(link) >= 1 and link[0] in dead_link_ids)
        )
    ]
    # Remove the node
    ui_workflow["nodes"] = [n for n in ui_workflow.get("nodes", []) if n.get("id") != node_id]
    # Clear input link references on remaining nodes
    for node in ui_workflow.get("nodes", []):
        for inp in node.get("inputs") or []:
            if inp.get("link") in dead_link_ids:
                inp["link"] = None


# ---------------------------------------------------------------------------
# Frame extraction (for auto-review)
# ---------------------------------------------------------------------------


def _extract_chain_paths(text: str) -> list[str]:
    """Extract server file paths from chain node text output."""
    import re
    # Match paths like /workspace/ComfyUI/output/.../file.mp4
    return re.findall(r"/workspace/ComfyUI/output/\S+\.(?:mp4|webm|gif|safetensors|json)", text)


def extract_review_frames(video_path: str, output_dir: str) -> dict:
    """Extract first/middle/last frames of a segment for the auto-review."""
    os.makedirs(output_dir, exist_ok=True)
    frames: dict[str, str] = {}

    # Get duration
    try:
        dur_out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            stderr=subprocess.DEVNULL, timeout=10,
        )
        duration = float(dur_out.strip())
    except Exception:
        duration = 0

    for label, t in [("first", 0), ("middle", duration / 2 if duration else 0), ("last", max(0, duration - 0.1))]:
        out = os.path.join(output_dir, f"{label}.png")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(t), "-i", video_path,
                 "-frames:v", "1", out],
                capture_output=True, timeout=15,
            )
            if os.path.isfile(out):
                frames[label] = out
        except Exception:
            pass
    return frames


# ---------------------------------------------------------------------------
# Reroute resolution (Reroute nodes may not be installed on the server)
# ---------------------------------------------------------------------------


def _build_link_map(ui_workflow: dict) -> dict[int, tuple[int, int, int, int, int]]:
    """Build link_id → (link_id, origin_id, origin_slot, target_id, target_slot)."""
    lm: dict[int, tuple[int, int, int, int, int]] = {}
    for link in ui_workflow.get("links", []):
        if isinstance(link, dict):
            lm[link["id"]] = (link["id"], link["origin_id"], link["origin_slot"], link["target_id"], link["target_slot"])
        elif isinstance(link, (list, tuple)) and len(link) >= 5:
            lm[int(link[0])] = (int(link[0]), int(link[1]), int(link[2]), int(link[3]), int(link[4]))
    return lm


def _resolve_reroutes(ui_workflow: dict) -> None:
    """Resolve Reroute nodes by following their input chain to the real source.

    Handles chains: Reroute → Reroute → real source.
    For each Reroute: follow its input link to find the real origin (skipping
    other Reroutes), then patch all output links to point to the real source,
    then remove all Reroute nodes and their links.
    """
    nodes = ui_workflow.get("nodes", [])
    reroute_ids = {n["id"] for n in nodes if n.get("type") == "Reroute"}
    if not reroute_ids:
        return

    # Build a map: node_id → (origin_id, origin_slot) for each node's single input
    # Reroute nodes have exactly one input
    input_of: dict[int, tuple[int, int]] = {}
    # Build a map: node_id → list of (link_id, target_id, target_slot) for outputs
    outputs_of: dict[int, list[tuple[int, int, int]]] = {}

    for link in ui_workflow.get("links", []):
        if isinstance(link, (list, tuple)) and len(link) >= 5:
            lid, oid, oslot, tid, tslot = int(link[0]), int(link[1]), int(link[2]), int(link[3]), int(link[4])
            if tid in reroute_ids:
                input_of[tid] = (oid, oslot)
            if oid in reroute_ids:
                outputs_of.setdefault(oid, []).append((lid, tid, tslot))

    # Follow the chain for each Reroute to find the real source
    def follow_chain(rid: int, visited: set[int] = None) -> tuple[int, int]:
        if visited is None:
            visited = set()
        if rid in visited:
            return (rid, 0)  # cycle protection
        visited.add(rid)
        src = input_of.get(rid)
        if src is None:
            return (rid, 0)
        oid, oslot = src
        if oid in reroute_ids:
            return follow_chain(oid, visited)
        return (oid, oslot)

    # Patch output links: for each Reroute's output, change origin to real source
    new_links = []
    for link in ui_workflow.get("links", []):
        if isinstance(link, (list, tuple)) and len(link) >= 5:
            lid, oid, oslot, tid, tslot = int(link[0]), int(link[1]), int(link[2]), int(link[3]), int(link[4])
            if oid in reroute_ids:
                real_oid, real_oslot = follow_chain(oid)
                oid = real_oid
                oslot = real_oslot
            if tid in reroute_ids:
                continue  # input link to a Reroute — drop
            # Preserve any extra elements in the link (e.g. type string)
            new_link = [lid, oid, oslot, tid, tslot] + list(link[5:])
            new_links.append(new_link)
        else:
            new_links.append(link)

    ui_workflow["links"] = new_links
    ui_workflow["nodes"] = [n for n in nodes if n.get("type") != "Reroute"]


def _resolve_bypassed_nodes(ui_workflow: dict) -> None:
    """Resolve bypassed nodes (mode=4) by passing their input through to outputs.

    Bypassed nodes should be skipped — their input flows directly to their
    output. The UI→API converter doesn't handle this, so we patch output links
    to originate from the bypassed node's input source, then remove the node.
    """
    nodes = ui_workflow.get("nodes", [])
    bypassed_ids = {n["id"] for n in nodes if n.get("mode") == 4}
    if not bypassed_ids:
        return

    # Build input/output maps (same approach as _resolve_reroutes)
    input_of: dict[int, tuple[int, int]] = {}
    for link in ui_workflow.get("links", []):
        if isinstance(link, (list, tuple)) and len(link) >= 5:
            lid, oid, oslot, tid, tslot = int(link[0]), int(link[1]), int(link[2]), int(link[3]), int(link[4])
            if tid in bypassed_ids:
                input_of[tid] = (oid, oslot)

    # Follow chain through other bypassed nodes
    def follow_chain(rid: int, visited: set[int] = None) -> tuple[int, int]:
        if visited is None:
            visited = set()
        if rid in visited:
            return (rid, 0)
        visited.add(rid)
        src = input_of.get(rid)
        if src is None:
            return (rid, 0)
        oid, oslot = src
        if oid in bypassed_ids:
            return follow_chain(oid, visited)
        return (oid, oslot)

    new_links = []
    for link in ui_workflow.get("links", []):
        if isinstance(link, (list, tuple)) and len(link) >= 5:
            lid, oid, oslot, tid, tslot = int(link[0]), int(link[1]), int(link[2]), int(link[3]), int(link[4])
            if oid in bypassed_ids:
                real_oid, real_oslot = follow_chain(oid)
                oid = real_oid
                oslot = real_oslot
            if tid in bypassed_ids:
                continue
            new_links.append([lid, oid, oslot, tid, tslot] + list(link[5:]))
        else:
            new_links.append(link)

    ui_workflow["links"] = new_links
    ui_workflow["nodes"] = [n for n in nodes if n.get("mode") != 4]


def _remove_muted_nodes(ui_workflow: dict) -> None:
    """Remove nodes with mode=2 (muted) from the workflow.

    The UI→API converter doesn't respect the mode field, so muted nodes get
    executed. We remove them (and their links) before conversion.

    mode=4 (bypassed) nodes are left in place — the converter handles them by
    passing through their inputs to their outputs.
    """
    muted_ids = {n["id"] for n in ui_workflow.get("nodes", []) if n.get("mode") == 2}
    if not muted_ids:
        return
    for nid in muted_ids:
        _remove_node(ui_workflow, nid)


def _strip_linked_widget_fields(ui_workflow: dict, object_info: dict) -> None:
    """Fix widget-to-input mapping for nodes with linked widget inputs.

    The UI→API converter maps ``widgets_values[i]`` to ``widget_inputs[i]``,
    where ``widget_inputs`` is the list of node inputs that have a ``widget``
    field. This breaks when a widget input is linked (the converter still
    consumes a widget slot for it, misaligning all subsequent widget values).

    Fix: for each node, add missing widget-only inputs (from object_info) as
    fake input entries with a ``widget`` field, in object_info order, so the
    converter's positional mapping aligns with the actual widget order. For
    linked widget inputs, the converter checks ``linked`` first, so the link
    value takes precedence.
    """
    for node in ui_workflow.get("nodes", []):
        ntype = node.get("type", "")
        if ntype not in object_info:
            continue
        existing_inputs = {inp.get("name") for inp in node.get("inputs") or []}
        obj_inp = object_info[ntype].get("input", {})
        required = obj_inp.get("required", {})
        # Build the new inputs list in object_info order
        new_inputs: list[dict] = []
        existing_by_name = {inp.get("name"): inp for inp in node.get("inputs") or []}
        for rname in required:
            if rname in existing_by_name:
                new_inputs.append(existing_by_name[rname])
            else:
                # Widget-only input not in the node's inputs — add a fake entry
                new_inputs.append({
                    "name": rname,
                    "type": required[rname][0] if isinstance(required[rname], list) else "*",
                    "link": None,
                    "widget": {"name": rname},
                })
        # Preserve any non-required inputs (e.g. optional inputs)
        for inp in node.get("inputs") or []:
            if inp.get("name") not in required:
                new_inputs.append(inp)
        node["inputs"] = new_inputs


# ---------------------------------------------------------------------------
# Scene submission
# ---------------------------------------------------------------------------


def submit_scene(
    ui_workflow: dict,
    object_info: dict,
    plan: dict,
    scene: int,
    *,
    song_path: str | None = None,
    ref_image_paths: list[str] | None = None,
    width: int | None = None,
    height: int | None = None,
    steps: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Submit one scene to ComfyUI and return the result."""
    patched = patch_workflow(
        ui_workflow, plan, scene,
        song_path=song_path,
        ref_image_paths=ref_image_paths,
        width=width, height=height, steps=steps,
    )

    if dry_run and not object_info:
        # No server available — emit the patched UI workflow instead of an API prompt
        return {"dry_run": True, "api_prompt": patched, "scene": scene, "note": "no object_info; patched UI workflow emitted"}

    # Resolve Reroute nodes (the server may not have the Reroute custom node)
    _resolve_reroutes(patched)
    # Resolve bypassed nodes (mode=4) — pass through their input to output
    _resolve_bypassed_nodes(patched)
    # Remove muted nodes (mode=2) — the converter doesn't respect the mode field
    _remove_muted_nodes(patched)
    # Fix widget-to-input mapping for nodes with linked widget inputs
    _strip_linked_widget_fields(patched, object_info)

    api_prompt = ui_workflow_to_api(patched, object_info)

    if dry_run:
        return {"dry_run": True, "api_prompt": api_prompt, "scene": scene}

    # Queue the prompt
    resp = curl_json(
        "POST",
        "/prompt",
        base_url=config.COMFYUI_URL,
        data={"prompt": api_prompt},
        auth=config.COMFYUI_AUTH,
    )
    prompt_id = resp.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"no prompt_id in response: {resp}")

    # Poll for completion
    outputs = wait_for_prompt(prompt_id, base_url=config.COMFYUI_URL, auth=config.COMFYUI_AUTH)

    return {
        "dry_run": False,
        "prompt_id": prompt_id,
        "outputs": outputs,
        "scene": scene,
        "api_prompt": api_prompt,
    }


def get_object_info() -> dict:
    """Fetch /object_info from ComfyUI (needed for UI→API conversion)."""
    import httpx

    url = f"{config.COMFYUI_URL}/object_info"
    headers = {}
    if config.COMFYUI_AUTH:
        headers["Authorization"] = f"Bearer {config.COMFYUI_AUTH}"
    resp = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description="Per-scene H3 chain orchestrator")
    p.add_argument("--ledger", required=True, help="Path to state.json (continuity ledger)")
    p.add_argument("--scene", type=int, default=None, help="Single scene number to render")
    p.add_argument("--from", dest="from_scene", type=int, default=None, help="Start scene (range)")
    p.add_argument("--to", dest="to_scene", type=int, default=None, help="End scene (range)")
    p.add_argument("--song", default=None, help="Path to source audio (for source_track)")
    p.add_argument("--refs", default="anchor", choices=("anchor", "anchor+sheet"), help="Reference image mode")
    p.add_argument("--width", type=int, default=None, help="Width override (low-res dial-in)")
    p.add_argument("--height", type=int, default=None, help="Height override (low-res dial-in)")
    p.add_argument("--steps", type=int, default=None, help="Steps override (low-res dial-in)")
    p.add_argument("--dry-run", action="store_true", help="Emit api_prompt.json, no GPU")
    p.add_argument("--max-rerolls", type=int, default=2, help="Max rerolls before escalating")
    p.add_argument("--workflow", default=str(WORKFLOW_PATH), help="Path to the workflow JSON")
    args = p.parse_args()

    ledger_path = Path(args.ledger)
    if not ledger_path.is_file():
        print(f"ledger not found: {ledger_path}", file=sys.stderr)
        return 1
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))

    plan = ledger_to_plan(ledger)

    # Determine scene range
    if args.scene:
        scenes = [args.scene]
    elif args.from_scene:
        end = args.to_scene or args.from_scene
        scenes = list(range(args.from_scene, end + 1))
    else:
        scenes = list(range(1, len(plan["shots"]) + 1))

    # Load workflow
    workflow_path = Path(args.workflow)
    if not workflow_path.is_file():
        print(f"workflow not found: {workflow_path}", file=sys.stderr)
        return 1
    ui_workflow = json.loads(workflow_path.read_text(encoding="utf-8"))

    # Get object_info (try even in dry-run if server is up)
    object_info: dict = {}
    try:
        object_info = get_object_info()
        print(f"object_info: {len(object_info)} node types", file=sys.stderr)
    except Exception as e:
        if not args.dry_run:
            print(f"could not fetch /object_info: {e}", file=sys.stderr)
            return 1
        print(f"could not fetch /object_info (dry-run will emit UI workflow): {e}", file=sys.stderr)

    # Resolve ref images from the registry
    reg = GlobalAssetRegistry()
    ref_paths: list[str] = []
    for c in ledger.get("cast", []):
        if isinstance(c, dict):
            entry = reg.resolve_approved(
                ledger.get("series", ""),
                c.get("id", ""),
                appearance_lock=c.get("appearance_lock"),
                kind="character_plate",
            )
            if entry:
                p = reg.approved_path(entry)
                if p:
                    ref_paths.append(p)

    # Add per-scene sheet if anchor+sheet mode
    if args.refs == "anchor+sheet" and scenes:
        clip = ledger.get("clips", [])[scenes[0] - 1] if scenes[0] <= len(ledger.get("clips", [])) else None
        if clip and clip.get("sheet"):
            ref_paths.append(clip["sheet"])

    for scene in scenes:
        print(f"--- Scene {scene} ---")
        result = submit_scene(
            ui_workflow, object_info, plan, scene,
            song_path=args.song,
            ref_image_paths=ref_paths,
            width=args.width, height=args.height, steps=args.steps,
            dry_run=args.dry_run,
        )

        if args.dry_run:
            out = Path(ledger_path.parent / f"api_prompt_scene_{scene}.json")
            out.write_text(json.dumps(result["api_prompt"], indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  dry-run: wrote {out}")
        else:
            print(f"  prompt_id: {result.get('prompt_id')}")
            out_dir = ledger_path.parent / "output"
            out_dir.mkdir(parents=True, exist_ok=True)
            # wait_for_prompt returns the outputs dict directly (no nested "outputs")
            outputs = result.get("outputs", {})
            # Download standard ComfyUI outputs (images/gifs/videos)
            for node_id, node_output in outputs.items():
                for o in node_output.get("gifs", []) + node_output.get("images", []):
                    fname = o.get("filename", "")
                    subfolder = o.get("subfolder", "")
                    if fname:
                        local_path = out_dir / fname
                        ok = download_output(
                            fname,
                            str(local_path),
                            base_url=config.COMFYUI_URL,
                            subfolder=subfolder,
                            auth=config.COMFYUI_AUTH,
                            is_video=str(fname).endswith((".mp4", ".webm", ".gif")),
                            file_type=o.get("type", "output"),
                        )
                        if ok:
                            print(f"  downloaded: {local_path}")
                            if str(local_path).endswith((".mp4", ".webm", ".gif")):
                                frames = extract_review_frames(
                                    str(local_path),
                                    str(ledger_path.parent / "frames" / f"scene_{scene}"),
                                )
                                print(f"  review frames: {list(frames.keys())}")
                # Chain nodes output text with server file paths — download those files
                for text_item in node_output.get("text", []):
                    if isinstance(text_item, str):
                        for server_path in _extract_chain_paths(text_item):
                            fname = os.path.basename(server_path)
                            subfolder = os.path.dirname(server_path).replace(
                                "/workspace/ComfyUI/output/", ""
                            )
                            local_path = out_dir / fname
                            ok = download_output(
                                fname,
                                str(local_path),
                                base_url=config.COMFYUI_URL,
                                subfolder=subfolder,
                                auth=config.COMFYUI_AUTH,
                                is_video=fname.endswith((".mp4", ".webm", ".gif")),
                                file_type="output",
                            )
                            if ok:
                                print(f"  downloaded: {local_path}")
                                if str(local_path).endswith((".mp4", ".webm", ".gif")):
                                    frames = extract_review_frames(
                                        str(local_path),
                                        str(ledger_path.parent / "frames" / f"scene_{scene}"),
                                    )
                                    print(f"  review frames: {list(frames.keys())}")
                            else:
                                print(f"  chain output: {server_path} (download failed)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
