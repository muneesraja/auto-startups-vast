#!/usr/bin/env python3
"""
Story-to-Video-Cinematic: Ideogram 4 Generator
==============================================
Generates character sheets and raw scene still frames using Ideogram 4 T2I.
Composes structured JSON prompts automatically.
"""

import json
import os
import sys

# Append filmmaking scripts to import comfyui_api and workflow_builder
filmmaking_scripts = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "story-to-video-filmmaking", "scripts"
))
sys.path.append(filmmaking_scripts)

from comfyui_api import curl_json, wait_for_prompt, download_output
from workflow_builder import build_dynamic_workflow


def compose_character_sheet_prompt(character_name, character_desc, style_notes, global_style):
    """Compose the structured JSON prompt for Ideogram 4 character sheets."""
    prompt_dict = {
        "high_level_description": f"Professional character reference sheet showing {character_name} from front, 3/4, and side views.",
        "style_description": {
            "medium": "illustration",
            "aesthetics": f"Model-sheet character design, white background. {global_style}. {style_notes or ''}".strip(),
            "lighting": "flat studio lighting, even illumination"
        },
        "compositional_deconstruction": {
            "background": "clean white background, isolated illustration, no shadows, no distractions",
            "elements": [
                {
                    "type": "obj",
                    "bbox": [50, 50, 950, 350],
                    "desc": f"{character_name} front view. {character_desc}"
                },
                {
                    "type": "obj",
                    "bbox": [50, 380, 950, 650],
                    "desc": f"{character_name} 3/4 view. {character_desc}"
                },
                {
                    "type": "obj",
                    "bbox": [50, 680, 950, 950],
                    "desc": f"{character_name} side view. {character_desc}"
                }
            ]
        }
    }
    return json.dumps(prompt_dict)


def compose_scene_prompt(prompt_text, global_style, characters_present, characters_cfg):
    """Compose the structured JSON prompt for Ideogram 4 scene frames."""
    prompt_dict = {
        "high_level_description": prompt_text,
        "style_description": {
            "medium": "cinematic_still",
            "aesthetics": global_style,
            "lighting": "cinematic lighting, dramatic composition"
        },
        "compositional_deconstruction": {
            "background": "detailed cinematic background matching the scene description",
            "elements": []
        }
    }
    
    # Place character in center if present
    if characters_present and characters_cfg:
        # Use primary character or first character present
        primary_char = characters_present[0]
        char_info = characters_cfg.get(primary_char)
        if char_info:
            desc = char_info.get("description", "")
            prompt_dict["compositional_deconstruction"]["elements"].append({
                "type": "obj",
                "bbox": [200, 250, 900, 750], # Centered
                "desc": f"{primary_char}, {desc}"
            })
            
    return json.dumps(prompt_dict)


def generate_ideogram_image(prompt_text, filename, workflow_template, global_cfg, base_url, auth=None):
    """Queue and download an Ideogram 4.0 generation."""
    print(f"   🎨 Generating Ideogram image: {filename}")
    
    shot_for_builder = {
        "prompt": prompt_text,
        "references": [],
        "filename_prefix": filename.replace(".png", "")
    }

    # Build workflow using builder
    workflow = build_dynamic_workflow(workflow_template, shot_for_builder, global_cfg)

    # Queue workflow
    result = curl_json("POST", "/prompt", base_url,
                       data={"prompt": workflow, "client_id": "story-to-video-cinematic-ideogram"},
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
