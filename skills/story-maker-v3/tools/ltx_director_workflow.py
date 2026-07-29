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


def patch_server_model_names(
    api_workflow: dict[str, dict],
    *,
    available_clip_names: list[str] | None = None,
) -> None:
    """Align DualCLIPLoader filenames with models present on the ComfyUI host.

    Older hosts shipped ``comfy_gemma_3_12B_it.safetensors``; current LTX 2.3
    pods expose ``gemma_3_12B_it_fp4_mixed.safetensors``. Only rewrite when the
    workflow name is missing and a known alias is available.
    """
    clip = api_workflow.get("12")
    if not clip or clip.get("class_type") != "DualCLIPLoader":
        return
    name1 = clip["inputs"].get("clip_name1")
    if not name1:
        return
    available = list(available_clip_names or [])
    if not available:
        try:
            info = curl_json("GET", "/object_info/DualCLIPLoader")
            available = list(
                info["DualCLIPLoader"]["input"]["required"]["clip_name1"][0]
            )
        except Exception:
            return
    if name1 in available:
        return
    aliases = {
        "gemma_3_12B_it_fp4_mixed.safetensors": (
            "comfy_gemma_3_12B_it.safetensors",
        ),
        "comfy_gemma_3_12B_it.safetensors": (
            "gemma_3_12B_it_fp4_mixed.safetensors",
        ),
    }
    for alt in aliases.get(str(name1), ()):
        if alt in available:
            clip["inputs"]["clip_name1"] = alt
            return


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


def patch_negative_prompt(api_workflow: dict[str, dict], negative_prompt: str) -> None:
    """Replace the Hotfix graph's zeroed negative conditioning with real text.

    The stock Hotfix graph has no text negative: every ``negative`` input is
    wired to a ``ConditioningZeroOut`` node (an empty conditioning, since the
    graph runs at low CFG where a real negative has little effect anyway).
    When the AD supplies a non-empty ``negative_prompt`` (e.g. to suppress
    "extra people, duplicated characters, background people running"), inject
    one CLIPTextEncode node sharing the LTXDirector node's CLIP source and
    repoint every ``negative`` link that currently targets a
    ``ConditioningZeroOut`` node onto it — for both the base and upscale
    passes. No-op (leaves the zeroed negative as-is) when ``negative_prompt``
    is empty. Caveat: effect is weak on distilled checkpoints at low CFG;
    this is a secondary defense behind the AD's cast-lock beats/prompts.
    """
    text = str(negative_prompt or "").strip()
    if not text:
        return

    zero_out_ids = {
        nid
        for nid, node in api_workflow.items()
        if node.get("class_type") == "ConditioningZeroOut"
    }
    if not zero_out_ids:
        return

    clip_source = None
    director = api_workflow.get("131")
    if director and director.get("class_type") == "LTXDirector":
        clip_source = director.get("inputs", {}).get("clip")
    if clip_source is None:
        for node in api_workflow.values():
            src = node.get("inputs", {}).get("clip")
            if isinstance(src, list) and len(src) == 2:
                clip_source = src
                break
    if clip_source is None:
        return

    new_id = str(max((int(nid) for nid in api_workflow if nid.isdigit()), default=0) + 1)
    api_workflow[new_id] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": text, "clip": clip_source},
    }

    for node in api_workflow.values():
        neg = node.get("inputs", {}).get("negative")
        if (
            isinstance(neg, list)
            and len(neg) == 2
            and str(neg[0]) in zero_out_ids
        ):
            node["inputs"]["negative"] = [new_id, 0]


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


def patch_save_video_codec(
    api_workflow: dict[str, dict],
    *,
    codec: str = "h264",
    format: str = "mp4",
) -> None:
    """Force software H.264 encode (avoid RunPod NVENC OpenEncodeSessionEx failures)."""
    for node in api_workflow.values():
        if node.get("class_type") != "SaveVideo":
            continue
        inputs = node.setdefault("inputs", {})
        inputs["codec"] = codec
        inputs["format"] = format


def is_aac_nan_error(message: str) -> bool:
    """True when SaveVideo failed because LTX audio contained non-finite samples."""
    m = (message or "").lower()
    return "nan/+-inf" in m or ("aac" in m and "avcodec_send_frame" in m)


# Back-compat alias used in plan / tests
_is_aac_nan_error = is_aac_nan_error

_AAC_NAN_MAX_RETRIES = 2


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
    clip_choices = None
    dual = object_info.get("DualCLIPLoader")
    if dual:
        try:
            clip_choices = list(
                dual["input"]["required"]["clip_name1"][0]
            )
        except Exception:
            clip_choices = None
    patch_server_model_names(api_workflow, available_clip_names=clip_choices)
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
    negative_prompt: str = "",
    client_id: str = "story-maker-director-v2",
    max_aac_nan_retries: int = _AAC_NAN_MAX_RETRIES,
) -> dict[str, Any]:
    """Patch Hotfix with a timeline payload, queue, wait, and download.

    On SaveVideo AAC NaN/+-Inf failures (intermittent LTX AudioVAE), re-queues
    the same graph with a bumped seed up to ``max_aac_nan_retries`` times.
    """
    base_seed = int(seed)
    last_error: dict[str, Any] | None = None

    for attempt in range(max_aac_nan_retries + 1):
        attempt_seed = base_seed + (1000 * attempt)
        if attempt > 0:
            print(
                f"  AAC NaN SaveVideo — retrying seed={attempt_seed} "
                f"(attempt {attempt}/{max_aac_nan_retries})",
                flush=True,
            )
        result = _queue_director_timeline_once(
            timeline_payload=timeline_payload,
            output_path=output_path,
            global_prompt=global_prompt,
            cfg=cfg,
            width=width,
            height=height,
            seed=attempt_seed,
            negative_prompt=negative_prompt,
            client_id=client_id,
        )
        if result.get("status") == "success":
            result["seed"] = attempt_seed
            if attempt > 0:
                result["aac_nan_retries"] = attempt
            return result
        last_error = result
        message = str(result.get("message") or "")
        if attempt < max_aac_nan_retries and is_aac_nan_error(message):
            continue
        if last_error is not None:
            last_error["seed"] = attempt_seed
        return last_error

    assert last_error is not None
    last_error["seed"] = base_seed + (1000 * max_aac_nan_retries)
    return last_error


def _queue_director_timeline_once(
    *,
    timeline_payload: dict,
    output_path: str,
    global_prompt: str = "",
    cfg: float = 1.0,
    width: int | None = None,
    height: int | None = None,
    seed: int = 42,
    negative_prompt: str = "",
    client_id: str = "story-maker-director-v2",
) -> dict[str, Any]:
    """Single Hotfix queue attempt (no AAC-NaN retry)."""
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
        patch_negative_prompt(api_workflow, negative_prompt)
        sanitize_workflow_inputs(api_workflow)

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        patch_save_prefix(api_workflow, f"director_v2/{out_path.stem}")
        patch_save_video_codec(api_workflow)

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
    guide_frame_paths: dict[str, str] | None = None,
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
    guides = list(clip.get("guide_frames") or [])
    if workflow in ("i2v_hold", "i2v") or start_id == end_id:
        if any(bool(g.get("is_end_frame") or g.get("placement") == "end") for g in guides if isinstance(g, dict)) and len(guides) > 1:
            workflow = "flf2v"
        else:
            workflow = "i2v"
    else:
        workflow = "flf2v"
    resolved_global = (global_prompt or clip.get("global_prompt") or "").strip()
    width = int(
        width
        if width is not None
        else getattr(config, "DIRECTOR_VIDEO_WIDTH", config.VIDEO_WIDTH)
    )
    height = int(
        height
        if height is not None
        else getattr(config, "DIRECTOR_VIDEO_HEIGHT", config.VIDEO_HEIGHT)
    )

    try:
        guide_paths = dict(guide_frame_paths or {})
        if start_id and first_frame_path:
            guide_paths.setdefault(str(start_id), first_frame_path)
        if end_id and last_frame_path:
            guide_paths.setdefault(str(end_id), last_frame_path)
        for g in guides:
            if not isinstance(g, dict):
                continue
            pid = str(g.get("panel_id") or "").strip()
            if pid and pid not in guide_paths:
                # Caller should pass all paths via guide_frame_paths; skip missing.
                continue

        uploaded: dict[str, str] = {}
        for panel_id, path in guide_paths.items():
            if path:
                uploaded[panel_id] = _upload_image_file(path)

        first_file = uploaded.get(str(start_id or "")) or (
            _upload_image_file(first_frame_path) if first_frame_path else ""
        )
        last_file = uploaded.get(str(end_id or ""))
        if workflow == "flf2v" and not last_file and last_frame_path:
            last_file = _upload_image_file(last_frame_path)
        if workflow == "flf2v" and not guides and not last_file:
            return {
                "status": "error",
                "message": "FLF clip requires last_frame_path",
            }

        timeline_payload = build_timeline_from_director_clip(
            clip,
            first_image_file=first_file,
            last_image_file=last_file,
            guide_image_files=uploaded,
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
            negative_prompt=str(clip.get("negative_prompt") or "").strip(),
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
                    "width": width,
                    "height": height,
                }
            )
        return result
    except Exception as e:
        return {"status": "error", "message": f"LTX Director clip failed: {e}"}
