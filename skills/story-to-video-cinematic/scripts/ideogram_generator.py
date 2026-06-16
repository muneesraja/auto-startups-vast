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
    """Compose the structured JSON prompt for Ideogram 4 scene frames.

    Places up to 3 characters using split bounding boxes so the model renders
    them in the correct left/centre/right positions.

    Bbox coordinate system: [y1, x1, y2, x2] in range 0-1000.
    - y: 0 = top, 1000 = bottom
    - x: 0 = left, 1000 = right
    """
    # Character bbox layouts by count
    CHAR_BBOXES = {
        1: [[150, 250, 950, 750]],                        # centred
        2: [[150, 50, 950, 480], [150, 520, 950, 950]],   # left | right
        3: [[100, 30, 950, 333], [100, 350, 950, 640], [100, 660, 950, 970]],  # thirds
    }

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

    present = characters_present or []
    n = min(len(present), 3)
    bboxes = CHAR_BBOXES.get(n, CHAR_BBOXES[1])

    for i, char_id in enumerate(present[:n]):
        char_info = (characters_cfg or {}).get(char_id)
        if char_info:
            desc = char_info.get("description", char_id)
            name = char_info.get("display_name", char_id)
        else:
            desc = char_id
            name = char_id

        prompt_dict["compositional_deconstruction"]["elements"].append({
            "type": "obj",
            "bbox": bboxes[i],
            "desc": f"{name}: {desc}"
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
