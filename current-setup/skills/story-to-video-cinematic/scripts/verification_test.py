#!/usr/bin/env python3
"""
Automated Verification Script for story-to-video-cinematic
"""

import json
import os
import sys

# Append filmmaking scripts path
script_dir = os.path.dirname(os.path.abspath(__file__))
filmmaking_scripts = os.path.abspath(os.path.join(
    script_dir, "..", "..", "story-to-video-filmmaking", "scripts"
))
sys.path.append(filmmaking_scripts)

from workflow_builder import build_dynamic_workflow, load_workflow_template


def test_templates_parsing():
    print("⏳ [Test 1] Parsing workflow templates...")
    templates_dir = os.path.abspath(os.path.join(script_dir, "..", "assets", "workflow-templates"))
    
    ideogram_path = os.path.join(templates_dir, "ideogram-4-t2i.json")
    flux_path = os.path.join(templates_dir, "flux-2-klein-image-edit.json")
    
    with open(ideogram_path) as f:
        ideogram = json.load(f)
        print("   ✅ ideogram-4-t2i.json parsed successfully")
        
    with open(flux_path) as f:
        flux = json.load(f)
        print("   ✅ flux-2-klein-image-edit.json parsed successfully")
        
    return ideogram, flux


def test_builder_compilation(ideogram_template, flux_template):
    print("\n⏳ [Test 2] Compiling workflow templates via workflow_builder...")
    
    global_cfg = {
        "width": 1344,
        "height": 768,
        "seed_base": 42
    }
    
    # Test ideogram_t2i builder
    print("   👉 Testing ideogram_t2i builder compilation...")
    shot_data_ideogram = {
        "prompt": "Test Prompt",
        "filename_prefix": "test_ideogram"
    }
    w_ideogram = build_dynamic_workflow(ideogram_template, shot_data_ideogram, global_cfg)
    print(f"      ✅ compiled: {len(w_ideogram)} nodes")
    
    # Test flux_klein_edit builder
    print("   👉 Testing flux_klein_edit builder compilation...")
    shot_data_flux = {
        "prompt": "Test Edit Prompt",
        "scene_image": "raw_still.png",
        "character_ref": "character_sheet.png",
        "filename_prefix": "test_flux_edit"
    }
    w_flux = build_dynamic_workflow(flux_template, shot_data_flux, global_cfg)
    print(f"      ✅ compiled: {len(w_flux)} nodes")


if __name__ == "__main__":
    try:
        ideo_t, flux_t = test_templates_parsing()
        test_builder_compilation(ideo_t, flux_t)
        print("\n🎉 All automated tests passed successfully!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
