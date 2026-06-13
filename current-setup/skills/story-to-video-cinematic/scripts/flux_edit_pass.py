#!/usr/bin/env python3
"""
Story-to-Video-Cinematic: Flux Klein Edit Pass
=============================================
Performs character consistency editing using Flux Klein 9B Image-to-Image Edit.
Auto-composes specific edit prompts to replace generic characters with reference sheets.
"""

import os
import sys

# Append filmmaking scripts to import comfyui_api and workflow_builder
filmmaking_scripts = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "story-to-video-filmmaking", "scripts"
))
sys.path.append(filmmaking_scripts)

from comfyui_api import curl_json, wait_for_prompt
from workflow_builder import build_dynamic_workflow


def compose_edit_prompt(edit_prompt_descriptor, style):
    """Generate a proper Flux Klein edit prompt for character consistency."""
    return (
        f"Replace the {edit_prompt_descriptor} character in the scene with "
        f"the character from reference 1, matching their exact appearance, "
        f"face, hair, clothing, and proportions. Keep the background, "
        f"lighting, composition, and overall scene identical. "
        f"Maintain the {style} art style throughout."
    )


def execute_flux_klein_edit(scene_image_server_path, character_ref_server_path, edit_prompt,
                             filename, workflow_template, global_cfg, base_url, auth=None):
    """Queue and run a Flux Klein edit pass on ComfyUI."""
    print(f"   🎨 Running Flux Klein Edit:")
    print(f"      Scene Image: {scene_image_server_path}")
    print(f"      Character Ref: {character_ref_server_path}")
    print(f"      Edit Prompt: {edit_prompt[:120]}...")

    shot_for_builder = {
        "prompt": edit_prompt,
        "scene_image": scene_image_server_path,
        "character_ref": character_ref_server_path,
        "filename_prefix": filename.replace(".png", "")
    }

    # Build workflow using builder
    workflow = build_dynamic_workflow(workflow_template, shot_for_builder, global_cfg)

    # Queue workflow
    result = curl_json("POST", "/prompt", base_url,
                       data={"prompt": workflow, "client_id": "story-to-video-cinematic-flux-edit"},
                       auth=auth)

    if "error" in result:
        err = result["error"]
        print(f"      ❌ Queue error: {err.get('type')}: {err.get('message')}")
        return None

    prompt_id = result.get("prompt_id")
    try:
        outputs = wait_for_prompt(prompt_id, base_url, auth=auth)
    except (RuntimeError, TimeoutError) as e:
        print(f"      ❌ {e}")
        return None

    # Download output image
    for nid, out in outputs.items():
        for item in out.get("images", []):
            srv_filename = item["filename"]
            return srv_filename

    return None
