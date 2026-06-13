#!/usr/bin/env python3
"""
Story-to-Video-Cinematic: Flux Klein Edit Pass (Multi-Character Support)
=============================================
Performs character consistency editing using Flux Klein 9B Image-to-Image Edit.
Auto-composes specific edit prompts to replace generic characters with reference sheets.
Supports multiple character references per shot.
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


def compose_multi_character_edit_prompt(characters_present, char_lookup, global_style):
    """
    Auto-compose a Klein edit prompt for N characters.
    
    Reference image numbering:
      "reference image 1" = first character in characters_present
      "reference image 2" = second character
      etc.
    """
    if not characters_present:
        return f"Keep the background, lighting, composition, and overall scene identical. Maintain the {global_style} art style throughout."

    parts = []
    for i, char_id in enumerate(characters_present, start=1):
        char = char_lookup.get(char_id)
        if not char:
            continue
        desc = char.get("edit_prompt_descriptor", f"the {char_id}")
        parts.append(
            f"Make {desc} match the character from reference image {i} "
            f"exactly — same face, body, clothing, and proportions."
        )
    
    preservation = (
        "Keep the background, lighting, composition, and overall scene identical. "
        f"Maintain the {global_style} art style throughout."
    )
    
    return " ".join(parts) + " " + preservation


def execute_flux_klein_edit_multi(
    scene_image_server_path,
    character_ref_server_paths,  # list of server filenames, ordered by characters_present
    edit_prompt,
    filename,
    workflow_template,
    global_cfg,
    base_url,
    auth=None
):
    """
    Execute a Flux Klein edit with N character references.
    Uses the dynamic workflow builder.
    """
    print(f"   🎨 Running Flux Klein Edit Multi:")
    print(f"      Scene Image: {scene_image_server_path}")
    print(f"      Character Refs: {character_ref_server_paths}")
    print(f"      Edit Prompt: {edit_prompt[:120]}...")

    shot_for_builder = {
        "prompt": edit_prompt,
        "scene_image": scene_image_server_path,
        "character_refs": character_ref_server_paths,
        "filename_prefix": filename.replace(".png", ""),
        "_builder_mode": "flux_klein_edit_dynamic"
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


def execute_flux_klein_edit(scene_image_server_path, character_ref_server_path, edit_prompt,
                             filename, workflow_template, global_cfg, base_url, auth=None):
    """Legacy/Single wrapper pointing to execute_flux_klein_edit_multi."""
    return execute_flux_klein_edit_multi(
        scene_image_server_path=scene_image_server_path,
        character_ref_server_paths=[character_ref_server_path] if character_ref_server_path else [],
        edit_prompt=edit_prompt,
        filename=filename,
        workflow_template=workflow_template,
        global_cfg=global_cfg,
        base_url=base_url,
        auth=auth
    )
