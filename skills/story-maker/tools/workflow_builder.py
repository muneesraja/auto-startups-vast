"""Minimal ComfyUI workflow builder for LTX 2.3 I2V."""

from __future__ import annotations

import copy
import json
import os
import re


def _json_escape(value: str) -> str:
    return json.dumps(value)[1:-1]


def load_workflow_template(template_name: str, templates_dir: str | None = None) -> dict:
    if templates_dir is None:
        templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "workflow-templates")

    template_path = os.path.join(templates_dir, f"{template_name}.json")
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Workflow template not found: {template_path}")

    with open(template_path, encoding="utf-8") as f:
        return json.load(f)


def snap_duration_seconds(requested: int, fps: int = 25) -> int:
    """Snap to valid LTX frame count (8n+1) at given fps."""
    requested = max(1, int(requested))
    frames = requested * fps
    n = max(0, round((frames - 1) / 8))
    snapped_frames = n * 8 + 1
    return max(1, round(snapped_frames / fps))


def _apply_overrides(workflow: dict, overrides: dict, overrides_map: dict) -> dict:
    if not overrides or not overrides_map:
        return workflow

    for name, value in overrides.items():
        mapping = overrides_map.get(name)
        if not mapping:
            continue
        node_id = mapping["node"]
        input_key = mapping["key"]
        if node_id in workflow:
            workflow[node_id]["inputs"][input_key] = value
    return workflow


def build_ltx_i2v_workflow(template: dict, shot_data: dict, global_cfg: dict) -> dict:
    workflow = copy.deepcopy(template)
    overrides_map = template.get("_overrides_map", {})

    prompt_text = shot_data["prompt"]
    negative_prompt = shot_data.get(
        "negative_prompt",
        global_cfg.get(
            "negative_prompt",
            "blurry, low quality, still frame, frames, watermark, overlay, titles",
        ),
    )
    seed = shot_data.get("seed", global_cfg.get("seed_base", 42))
    width = global_cfg.get("width", 1280)
    height = global_cfg.get("height", 720)
    duration = snap_duration_seconds(
        int(shot_data.get("duration", global_cfg.get("duration", 8))),
        fps=int(shot_data.get("fps", global_cfg.get("fps", 25))),
    )
    fps = int(shot_data.get("fps", global_cfg.get("fps", 25)))
    motion_image = shot_data.get("motion_image") or "example.png"
    filename_prefix = shot_data["filename_prefix"]

    overrides = {
        "prompt": prompt_text,
        "negative_prompt": negative_prompt,
        "seed": seed,
        "width": width,
        "height": height,
        "duration": duration,
        "fps": fps,
    }
    workflow = _apply_overrides(workflow, overrides, overrides_map)

    workflow_str = json.dumps(workflow)
    workflow_str = workflow_str.replace("__PROMPT__", _json_escape(prompt_text))
    workflow_str = workflow_str.replace("__NEGATIVE_PROMPT__", _json_escape(negative_prompt))
    workflow_str = workflow_str.replace("__MOTION_IMAGE__", _json_escape(motion_image))
    workflow_str = workflow_str.replace("__FILENAME_PREFIX__", _json_escape(filename_prefix))
    workflow_str = workflow_str.replace('"__SEED__"', str(seed))
    workflow_str = workflow_str.replace("__SEED__", str(seed))
    workflow_str = workflow_str.replace('"__WIDTH__"', str(width))
    workflow_str = workflow_str.replace("__WIDTH__", str(width))
    workflow_str = workflow_str.replace('"__HEIGHT__"', str(height))
    workflow_str = workflow_str.replace("__HEIGHT__", str(height))
    workflow_str = workflow_str.replace('"__DURATION__"', str(duration))
    workflow_str = workflow_str.replace("__DURATION__", str(duration))
    workflow_str = workflow_str.replace('"__FPS__"', str(fps))
    workflow_str = workflow_str.replace("__FPS__", str(fps))

    result = json.loads(workflow_str)
    remaining = re.findall(r"__[A-Z_]+__", workflow_str)
    if remaining:
        print(f"   Warning: unreplaced workflow placeholders: {set(remaining)}")

    return {k: v for k, v in result.items() if not k.startswith("_")}
