#!/usr/bin/env python3
"""
Automated Verification Script for story-to-video-cinematic
"""

import json
import os
import sys

# Resolve scripts path
script_dir = os.path.dirname(os.path.abspath(__file__))

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


def test_v2_features(flux_template):
    print("\n⏳ [Test 3] Verifying V2/V3 features (Prompt Composition & Cloning)...")
    
    # 1. Test multi-character edit prompt composition
    from flux_edit_pass import compose_multi_character_edit_prompt
    char_lookup = {
        "pippin": {"edit_prompt_descriptor": "the baby panda with the red scarf"},
        "miko": {"edit_prompt_descriptor": "the brown monkey with the green leaf hat"}
    }
    prompt = compose_multi_character_edit_prompt(
        ["pippin", "miko"],
        char_lookup,
        "Cinematic 3D Pixar-style"
    )
    assert "reference image 1" in prompt, "Missing reference image 1 reference"
    assert "reference image 2" in prompt, "Missing reference image 2 reference"
    assert "the baby panda with the red scarf" in prompt, "Missing Pippin descriptor"
    assert "the brown monkey with the green leaf hat" in prompt, "Missing Miko descriptor"
    print("   ✅ compose_multi_character_edit_prompt composed correctly")

    # 2. Test dynamic workflow cloning (1 ref)
    shot_1 = {
        "prompt": "Test edit",
        "scene_image": "scene.png",
        "character_refs": ["sheet_pippin.png"],
        "filename_prefix": "s01_sh01_ff_edited",
        "_builder_mode": "flux_klein_edit_dynamic"
    }
    w1 = build_dynamic_workflow(flux_template, shot_1, {"seed_base": 42})
    assert "121" in w1
    assert "121_2" not in w1, "121_2 should not be spawned for single character"
    print("   ✅ dynamic cloning correctly skipped cloning for 1 reference")

    # 3. Test dynamic workflow cloning (3 refs)
    shot_3 = {
        "prompt": "Test edit 3",
        "scene_image": "scene.png",
        "character_refs": ["sheet_pippin.png", "sheet_miko.png", "sheet_luna.png"],
        "filename_prefix": "s01_sh01_ff_edited",
        "_builder_mode": "flux_klein_edit_dynamic"
    }
    w3 = build_dynamic_workflow(flux_template, shot_3, {"seed_base": 42})
    assert "121" in w3
    assert "121_2" in w3, "121_2 missing"
    assert "121_3" in w3, "121_3 missing"
    assert "92:131_2" in w3, "ReferenceLatent Positive Ref 2 missing"
    assert "92:131_3" in w3, "ReferenceLatent Positive Ref 3 missing"
    assert w3["92:103"]["inputs"]["positive"][0] == "92:131_3", "CFGGuider positive input not rewired to end of chain"
    print("   ✅ dynamic cloning correctly cloned 3 reference chains and rewired CFGGuider")

    # 4. Test chain resolution in BatchWaveOrchestrator
    from cinematic_orchestrator import BatchWaveOrchestrator
    
    # Load example JSON — path resolved relative to this script's location
    example_json = os.path.join(script_dir, "..", "examples", "06-full-story-dryrun-prompt.json")
    with open(example_json) as f:
        prompts_data = json.load(f)
    
    # Mock class to construct orchestrator
    class MockArgs:
        references_dir = None
        provider = "openrouter"
        shot = None
        fast = False
        interactive = False
        skip_existing = False
    
    orchestrator = BatchWaveOrchestrator(
        prompts_data=prompts_data,
        base_url="http://localhost:8188",
        comfyui_auth=None,
        output_dir="temp",
        args=MockArgs()
    )
    
    # Confirm flat list length
    assert len(orchestrator.all_shots) == 3, f"Expected 3 shots, got {len(orchestrator.all_shots)}"
    
    # Confirm visual depths
    assert orchestrator.all_shots[0]["_depth"] == 0, "Shot 1 should be depth 0"
    assert orchestrator.all_shots[1]["_depth"] == 1, "Shot 2 should be depth 1"
    assert orchestrator.all_shots[2]["_depth"] == 0, "Shot 3 should be depth 0 (due to ##cut)"
    print("   ✅ visual depth calculation and chain boundaries resolved correctly")


def test_pipeline_logger():
    print("\n⏳ [Test 4] Verifying PipelineLogger and JSON output...")
    import shutil
    from pipeline_logger import PipelineLogger
    
    test_dir = "temp_logger_test"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
    waves_plan = {
        "wave_0_character_sheets": ["pippin"],
        "wave_1_ideogram_ffs": ["s01_sh01_ff_raw"]
    }
    
    logger = PipelineLogger(
        output_dir=test_dir,
        run_id="test_run",
        total_shots=1,
        total_characters=1,
        waves_plan=waves_plan
    )
    
    # Verify initial json file
    status_path = os.path.join(test_dir, "pipeline_status.json")
    assert os.path.exists(status_path), "pipeline_status.json should exist"
    
    with open(status_path) as f:
        data = json.load(f)
    assert data["run_id"] == "test_run"
    assert data["waves"]["wave_0_character_sheets"]["items"]["pippin"]["status"] == "pending"
    
    # Update item
    logger.update_item("wave_0_character_sheets", "pippin", "completed", output="pippin.png", eval_score=8.5)
    with open(status_path) as f:
        data = json.load(f)
    assert data["waves"]["wave_0_character_sheets"]["items"]["pippin"]["status"] == "completed"
    assert data["waves"]["wave_0_character_sheets"]["items"]["pippin"]["output"] == "pippin.png"
    assert data["waves"]["wave_0_character_sheets"]["items"]["pippin"]["eval_score"] == 8.5
    
    # Clean up
    shutil.rmtree(test_dir)
    print("   ✅ PipelineLogger tests passed")


def test_prompt_composer():
    print("\n⏳ [Test 5] Verifying Prompt Composer utilities...")
    from prompt_composer import build_ff_edit_prompt, build_lf_derivation_prompt
    
    shot = {
        "filename_prefix": "s01_sh01",
        "characters_present": ["pippin"],
        "ff_edit_instructions": {
            "pippin": "Make Pippin wear a small bowler hat."
        }
    }
    char_lookup = {
        "pippin": {"edit_prompt_descriptor": "baby panda"}
    }
    
    prompt = build_ff_edit_prompt(shot, char_lookup, "3D cartoon")
    assert "bowler hat" in prompt
    assert "identical" in prompt
    
    shot_no_override = {
        "filename_prefix": "s01_sh01",
        "characters_present": ["pippin"]
    }
    prompt_no_override = build_ff_edit_prompt(shot_no_override, char_lookup, "3D cartoon")
    assert "Replace the baby panda" in prompt_no_override
    
    shot_lf = {
        "lf_edit_instruction": "The baby panda waves."
    }
    prompt_lf = build_lf_derivation_prompt(shot_lf, "3D cartoon")
    assert "waves" in prompt_lf
    assert "identical" in prompt_lf
    
    print("   ✅ Prompt composer tests passed")


def test_wave_2_split():
    print("\n⏳ [Test 6] Verifying BatchWaveOrchestrator splits Wave 2...")
    from cinematic_orchestrator import BatchWaveOrchestrator
    
    # Check that both wave_2a_klein_ff_edits and wave_2b_klein_lf_derivations are present
    assert hasattr(BatchWaveOrchestrator, "wave_2a_klein_ff_edits"), "wave_2a_klein_ff_edits method missing"
    assert hasattr(BatchWaveOrchestrator, "wave_2b_klein_lf_derivations"), "wave_2b_klein_lf_derivations method missing"
    print("   ✅ Wave 2 split method checks passed")


if __name__ == "__main__":
    try:
        ideo_t, flux_t = test_templates_parsing()
        test_builder_compilation(ideo_t, flux_t)
        test_v2_features(flux_t)
        test_pipeline_logger()
        test_prompt_composer()
        test_wave_2_split()
        print("\n🎉 All automated tests passed successfully!")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
