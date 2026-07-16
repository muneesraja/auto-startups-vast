"""Headless LTX Director Hotfix workflow helpers for ComfyUI /prompt."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import config
from tools.comfyui_tools import (
    curl_json,
    download_output,
    upload_image,
    wait_for_prompt,
)
from tools.ltx_director_timeline import (
    build_flf_timeline,
    build_i2v_timeline,
    build_timeline_from_director_clip,
    snap_ltx_frames,
)
from tools.ltx_render_params import resolve_clip_render_params

DECORATIVE = {"MarkdownNote", "Note", "Comment"}
_SKIP_WIDGET = {"fixed", "randomize", "increment", "decrement"}

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_HOTFIX_UI = (
    _REPO_ROOT / "workflows" / "comfyui" / "LTX_Director_2_Workflow_Hotfix.json"
)
DIRECTOR_FPS = 24
_UPLOAD_SUBFOLDER = "whatdreamscost"

# Cached UI→API conversion for the current process
_API_WORKFLOW_CACHE: dict[str, dict] | None = None


def hotfix_workflow_path() -> Path:
    override = os.getenv("LTX_DIRECTOR_HOTFIX_WORKFLOW")
    if override:
        return Path(override)
    return DEFAULT_HOTFIX_UI


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
    """Convert a ComfyUI UI graph export into an API prompt dict."""
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
        api[str(node["id"])] = {"class_type": ntype, "inputs": inputs}
    return api


def sanitize_workflow_inputs(api_workflow: dict[str, dict]) -> None:
    """Drop API inputs that picked up wrong types during UI conversion."""
    director = api_workflow.get("131")
    if director and director.get("class_type") == "LTXDirector":
        opt = director["inputs"].get("optional_latent")
        if not isinstance(opt, list):
            director["inputs"].pop("optional_latent", None)


def patch_server_model_names(api_workflow: dict[str, dict]) -> None:
    """Align loader filenames with models present on the ComfyUI host."""
    clip = api_workflow.get("12")
    if clip and clip.get("class_type") == "DualCLIPLoader":
        if clip["inputs"].get("clip_name1") == "gemma_3_12B_it_fp4_mixed.safetensors":
            clip["inputs"]["clip_name1"] = "comfy_gemma_3_12B_it.safetensors"


def patch_director_node(
    api_workflow: dict,
    *,
    director_node_id: str = "131",
    timeline_payload: dict,
    global_prompt: str,
    custom_width: int,
    custom_height: int,
) -> None:
    node = api_workflow[director_node_id]
    node["inputs"].update(
        {
            "timeline_data": timeline_payload["timeline_data"],
            "local_prompts": timeline_payload["local_prompts"],
            "segment_lengths": timeline_payload["segment_lengths"],
            "guide_strength": timeline_payload["guide_strength"],
            "start_frame": timeline_payload["start_frame"],
            "end_frame": timeline_payload["end_frame"],
            "duration_frames": timeline_payload["duration_frames"],
            "start_second": 0.0,
            "end_second": timeline_payload["duration_seconds"],
            "duration_seconds": timeline_payload["duration_seconds"],
            "frame_rate": timeline_payload["frame_rate"],
            "global_prompt": global_prompt,
            "custom_width": int(custom_width),
            "custom_height": int(custom_height),
            "resize_method": "maintain aspect ratio",
            "divisible_by": 32,
            "img_compression": 18,
            "display_mode": "seconds",
            "use_custom_audio": False,
            "use_custom_motion": False,
            "inpaint_audio": True,
        }
    )


def patch_cfg_guiders(api_workflow: dict[str, dict], cfg: float) -> None:
    """Apply AD guidance CFG to every CFGGuider node in the Hotfix graph."""
    value = float(cfg)
    for node in api_workflow.values():
        if node.get("class_type") != "CFGGuider":
            continue
        node.setdefault("inputs", {})["cfg"] = value


def patch_seed(api_workflow: dict[str, dict], seed: int) -> None:
    for node in api_workflow.values():
        if node.get("class_type") == "RandomNoise":
            node.setdefault("inputs", {})["noise_seed"] = int(seed)


def patch_save_prefix(api_workflow: dict[str, dict], prefix: str) -> None:
    for node in api_workflow.values():
        if node.get("class_type") == "SaveVideo":
            node.setdefault("inputs", {})["filename_prefix"] = prefix
            return
    # Hotfix SaveVideo node id is usually 37
    if "37" in api_workflow:
        api_workflow["37"].setdefault("inputs", {})["filename_prefix"] = prefix


def load_hotfix_api_workflow(*, refresh: bool = False) -> dict[str, dict]:
    """Load Hotfix UI JSON, convert via live object_info, cache in-process."""
    global _API_WORKFLOW_CACHE
    if _API_WORKFLOW_CACHE is not None and not refresh:
        return json.loads(json.dumps(_API_WORKFLOW_CACHE))

    path = hotfix_workflow_path()
    ui_workflow = json.loads(path.read_text(encoding="utf-8"))
    node_types = sorted(
        {n["type"] for n in ui_workflow["nodes"] if n["type"] not in DECORATIVE}
    )
    object_info: dict = {}
    for ntype in node_types:
        object_info.update(curl_json("GET", f"/object_info/{ntype}"))
    api_workflow = ui_workflow_to_api(ui_workflow, object_info)
    patch_server_model_names(api_workflow)
    sanitize_workflow_inputs(api_workflow)
    _API_WORKFLOW_CACHE = api_workflow
    return json.loads(json.dumps(api_workflow))


def _upload_image_file(path: str) -> str:
    up = upload_image(path, subfolder=_UPLOAD_SUBFOLDER)
    if not up or not up.get("name"):
        raise RuntimeError(f"Failed to upload image: {path}")
    sub = up.get("subfolder") or ""
    return f"{sub}/{up['name']}" if sub else up["name"]


def _extract_video_ref(outputs: dict) -> tuple[str | None, str]:
    for _nid, out in outputs.items():
        for key in ("videos", "gifs", "images"):
            for item in out.get(key, []):
                if item.get("type") == "temp":
                    continue
                return item["filename"], item.get("subfolder", "") or ""
    return None, ""


def queue_director_timeline(
    *,
    timeline_payload: dict,
    output_path: str,
    global_prompt: str = "",
    cfg: float = 1.0,
    width: int | None = None,
    height: int | None = None,
    seed: int = 42,
    client_id: str = "story-maker-director-v2",
) -> dict[str, Any]:
    """Patch Hotfix with a timeline payload, queue, wait, and download."""
    try:
        api_workflow = load_hotfix_api_workflow()
        patch_director_node(
            api_workflow,
            timeline_payload=timeline_payload,
            global_prompt=global_prompt or "",
            custom_width=int(width if width is not None else config.VIDEO_WIDTH),
            custom_height=int(height if height is not None else config.VIDEO_HEIGHT),
        )
        patch_cfg_guiders(api_workflow, cfg)
        patch_seed(api_workflow, seed)
        sanitize_workflow_inputs(api_workflow)

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        patch_save_prefix(api_workflow, f"director_v2/{out_path.stem}")

        result = curl_json(
            "POST",
            "/prompt",
            data={"prompt": api_workflow, "client_id": client_id},
            timeout=120,
        )
        if result.get("error"):
            return {"status": "error", "message": f"Queue error: {result['error']}"}
        if result.get("node_errors"):
            return {
                "status": "error",
                "message": f"Node errors: {result['node_errors']}",
            }

        prompt_id = result.get("prompt_id")
        outputs = wait_for_prompt(prompt_id, max_wait=3600)
        srv_filename, srv_subfolder = _extract_video_ref(outputs)
        if not srv_filename:
            return {
                "status": "error",
                "message": "No video output in ComfyUI history",
                "outputs": outputs,
            }

        ok = download_output(
            srv_filename,
            str(out_path),
            subfolder=srv_subfolder,
            is_video=True,
        )
        if ok:
            return {
                "status": "success",
                "video_path": str(out_path),
                "prompt_id": prompt_id,
                "duration_frames": timeline_payload.get("duration_frames"),
                "duration_seconds": timeline_payload.get("duration_seconds"),
                "guide_strength": timeline_payload.get("guide_strength"),
            }
        return {"status": "error", "message": "Failed to download generated video"}
    except Exception as e:
        return {"status": "error", "message": f"LTX Director failed: {e}"}


def generate_ltx_director_video(
    *,
    first_frame_path: str,
    output_path: str,
    motion_prompt: str,
    duration_seconds: float = 6,
    last_frame_path: str | None = None,
    workflow: str = "i2v",
    global_prompt: str = "",
    first_guide_strength: float = 0.7,
    last_guide_strength: float = 0.85,
    cfg: float = 1.0,
    fps: int = DIRECTOR_FPS,
    width: int | None = None,
    height: int | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """Upload panels, build an I2V/FLF Director timeline, queue Hotfix."""
    try:
        first_file = _upload_image_file(first_frame_path)
        duration_frames = snap_ltx_frames(duration_seconds, fps=fps)
        mode = (workflow or "i2v").lower()
        if mode in ("flf", "flf2v") and last_frame_path:
            last_file = _upload_image_file(last_frame_path)
            timeline_payload = build_flf_timeline(
                first_image_file=first_file,
                last_image_file=last_file,
                motion_prompt=motion_prompt,
                global_prompt=global_prompt,
                duration_frames=duration_frames,
                first_guide_strength=first_guide_strength,
                last_guide_strength=last_guide_strength,
                fps=fps,
            )
        else:
            timeline_payload = build_i2v_timeline(
                image_file=first_file,
                motion_prompt=motion_prompt,
                global_prompt=global_prompt,
                duration_frames=duration_frames,
                guide_strength=first_guide_strength,
                fps=fps,
            )
        return queue_director_timeline(
            timeline_payload=timeline_payload,
            output_path=output_path,
            global_prompt=global_prompt,
            cfg=cfg,
            width=width,
            height=height,
            seed=seed,
        )
    except Exception as e:
        return {"status": "error", "message": f"LTX Director failed: {e}"}


def generate_ltx_director_from_clip(
    clip: dict,
    *,
    first_frame_path: str,
    output_path: str,
    last_frame_path: str | None = None,
    global_prompt: str = "",
    fps: int = DIRECTOR_FPS,
    width: int | None = None,
    height: int | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """Render one Assistant Director clip via LTX Director Hotfix."""
    render = resolve_clip_render_params(clip, prefer_stored=True)
    start_id = clip.get("start_panel_id") or clip.get("first_panel_id")
    end_id = clip.get("end_panel_id") or clip.get("last_panel_id") or start_id
    workflow = (clip.get("workflow") or clip.get("mode") or "i2v").lower()
    if workflow in ("i2v_hold", "i2v") or start_id == end_id:
        workflow = "i2v"
    else:
        workflow = "flf2v"
    resolved_global = (global_prompt or clip.get("global_prompt") or "").strip()

    try:
        first_file = _upload_image_file(first_frame_path)
        last_file = None
        if workflow == "flf2v":
            if not last_frame_path:
                return {
                    "status": "error",
                    "message": "FLF clip requires last_frame_path",
                }
            last_file = _upload_image_file(last_frame_path)

        timeline_payload = build_timeline_from_director_clip(
            clip,
            first_image_file=first_file,
            last_image_file=last_file,
            global_prompt=resolved_global,
            fps=fps,
            render=render,
        )
        result = queue_director_timeline(
            timeline_payload=timeline_payload,
            output_path=output_path,
            global_prompt=resolved_global,
            cfg=float(render["cfg"]),
            width=width,
            height=height,
            seed=seed,
        )
        if result.get("status") == "success":
            result.update(
                {
                    "workflow": workflow,
                    "motion_class": render["motion_class"],
                    "guidance": render["guidance"],
                    "i2v_strength": render["i2v_strength"],
                    "cfg": render["cfg"],
                    "last_frame_strength": render["last_frame_strength"],
                }
            )
        return result
    except Exception as e:
        return {"status": "error", "message": f"LTX Director clip failed: {e}"}
