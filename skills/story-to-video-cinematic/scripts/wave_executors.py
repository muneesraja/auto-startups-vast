#!/usr/bin/env python3
"""
Wave Executors Mixin: Implements the execution waves for the BatchWaveOrchestrator.
Splits Wave 2 into Wave 2a (FF Klein edits) and Wave 2b (LF derivations from FF) to resolve race conditions.
"""

import os
import sys
import copy
import shutil

# Resolve filmmaking scripts path
script_dir = os.path.dirname(os.path.abspath(__file__))
filmmaking_scripts = os.path.abspath(os.path.join(
    script_dir, "..", "..", "story-to-video-filmmaking", "scripts"
))
if filmmaking_scripts not in sys.path:
    sys.path.append(filmmaking_scripts)

# ComfyUI / filmmaking utilities
from comfyui_api import (
    curl_json,
    wait_for_prompt,
    download_output,
)
from workflow_builder import build_dynamic_workflow
from filmmaking_utils import upload_image_if_needed
from continuation_pipeline import extract_continuation_frame
from fflf_executor import execute_fflf_shot

# Prompt composer & quality gates
from prompt_composer import (
    build_ff_edit_prompt,
    build_lf_derivation_prompt,
)
from quality_gates import (
    evaluate_character_sheet,
    evaluate_scene_composition,
    evaluate_klein_consistency,
    evaluate_lf_delta,
)
from ideogram_generator import (
    compose_character_sheet_prompt,
    compose_scene_prompt,
)


class WaveExecutorMixin:
    """Mixin providing wave execution methods for BatchWaveOrchestrator.
    
    Expects self to have: state, char_lookup, characters, all_shots, 
    global_cfg, base_url, auth, scenes_dir, scenes_edited_dir, videos_dir,
    motion_eval_dir, references_dir, available_images, args, logger,
    ideogram_template, flux_edit_template, ltx_fflf_template, quality_gate_enabled,
    provider_name, api_key
    """

    # ── Wave 0: Character Sheets ───────────────────────────────────

    def wave_0_character_sheets(self):
        """Generate all character sheets in one Ideogram batch.
        Moved from cinematic_orchestrator.py L220-299."""
        self.logger.update_wave("wave_0_character_sheets", "in_progress")
        self.logger.log("════════════════════════════════════════", "INFO")
        self.logger.log("  WAVE 0: Generating Character Sheets (Ideogram 4)", "INFO")
        self.logger.log("════════════════════════════════════════", "INFO")
        
        pending_prompts = []
        
        for char in self.characters:
            char_id = char["id"]
            sheet_filename = f"{char_id}_character_sheet.png"
            local_path = os.path.join(self.references_dir, sheet_filename)
            
            # Check if sheet exists or is pre-defined
            if char.get("character_sheet_path"):
                shutil.copy(char["character_sheet_path"], local_path)
                self.logger.log(f"   📋 Copied predefined character sheet for {char_id}", "INFO")
                srv_name = upload_image_if_needed(local_path, self.base_url, self.available_images, self.auth)
                self.state["character_sheets"][char_id] = srv_name
                self.logger.update_item("wave_0_character_sheets", char_id, "completed", output=sheet_filename)
            elif os.path.exists(local_path) and os.path.getsize(local_path) > 1024:
                self.logger.log(f"   📷 Character sheet for {char_id} already exists locally", "INFO")
                srv_name = upload_image_if_needed(local_path, self.base_url, self.available_images, self.auth)
                self.state["character_sheets"][char_id] = srv_name
                self.logger.update_item("wave_0_character_sheets", char_id, "completed", output=sheet_filename)
            else:
                prompt_text = char["character_sheet_prompt"]
                # Compose Ideogram JSON structured prompt for richer layout control
                style_notes = char.get("style_notes", "")
                ideogram_prompt = compose_character_sheet_prompt(
                    character_name=char.get("display_name", char_id),
                    character_desc=char.get("description", prompt_text),
                    style_notes=style_notes,
                    global_style=self.global_cfg.get("style", "")
                )
                pending_prompts.append((char_id, ideogram_prompt, local_path, sheet_filename))
                self.logger.update_item("wave_0_character_sheets", char_id, "running")

        if not pending_prompts:
            self.logger.log("   ✅ No character sheets need generation.", "INFO")
            self.logger.update_wave("wave_0_character_sheets", "completed")
            return

        # Queue all sheets
        queue_ids = []
        for char_id, prompt, local_path, sheet_filename in pending_prompts:
            self.logger.log(f"   🎨 Queuing character sheet generation for {char_id}...", "INFO")
            shot_for_builder = {
                "prompt": prompt,
                "references": [],
                "filename_prefix": sheet_filename.replace(".png", "")
            }
            workflow = build_dynamic_workflow(self.ideogram_template, shot_for_builder, self.global_cfg)
            res = curl_json("POST", "/prompt", self.base_url, data={"prompt": workflow, "client_id": f"sheet-{char_id}"}, auth=self.auth)
            if "prompt_id" in res:
                queue_ids.append((char_id, res["prompt_id"], local_path, sheet_filename))
            else:
                err_msg = res.get('error', 'unknown error')
                self.logger.log(f"      ❌ Failed to queue character sheet for {char_id}: {err_msg}", "ERROR")
                self.logger.update_item("wave_0_character_sheets", char_id, "failed", error=err_msg)
                self.logger.update_wave("wave_0_character_sheets", "failed")
                raise RuntimeError(f"[Wave 0] Queue failed for character sheet '{char_id}': {err_msg}")

        # Wait and download
        for char_id, prompt_id, local_path, sheet_filename in queue_ids:
            self.logger.log(f"   ⏳ Waiting for character sheet: {char_id}...", "INFO")
            try:
                outputs = wait_for_prompt(prompt_id, self.base_url, auth=self.auth)
                srv_name = None
                for nid, out in outputs.items():
                    for item in out.get("images", []):
                        srv_filename = item["filename"]
                        download_output(srv_filename, local_path, self.base_url, auth=self.auth)
                        srv_name = upload_image_if_needed(local_path, self.base_url, self.available_images, self.auth)
                        self.state["character_sheets"][char_id] = srv_name
                        self.logger.log(f"      ✅ Saved and cached: {char_id} ({srv_name})", "INFO")
                
                if not srv_name:
                    raise RuntimeError("No image output returned from ComfyUI prompt")

                # Evaluate character sheet Quality Gate (Gate 1)
                eval_res = None
                gate_enabled = self.global_cfg.get("quality_gate", {}).get("gates", {}).get("character_sheet", True)
                if self.quality_gate_enabled and gate_enabled:
                    self.logger.log(f"      🛡️ Gate 1: Reviewing character sheet visual quality...", "INFO")
                    char_info = self.char_lookup[char_id]
                    eval_res = evaluate_character_sheet(
                        image_path=local_path,
                        character_info=char_info,
                        global_style=self.global_cfg.get("style", "3D Pixar-style"),
                        provider=self.provider_name,
                        api_key=self.api_key
                    )
                    if eval_res.get("rejected", False) or not eval_res.get("passed", True):
                        self.logger.log(f"         ⚠️ Character sheet failed quality gate: {eval_res.get('rejection_reason', 'low score')}", "WARN")
                    else:
                        self.logger.log(f"         ✅ Passed. Likeness: {eval_res.get('character_likeness')}/10, Style: {eval_res.get('style_match')}/10", "INFO")
                
                score = eval_res.get("overall") if eval_res else None
                self.logger.update_item("wave_0_character_sheets", char_id, "completed", output=sheet_filename, eval_score=score, eval_result=eval_res)
                
            except Exception as e:
                err_msg = str(e)
                self.logger.log(f"      ❌ Error waiting/downloading sheet for {char_id}: {err_msg}", "ERROR")
                self.logger.update_item("wave_0_character_sheets", char_id, "failed", error=err_msg)
                self.logger.update_wave("wave_0_character_sheets", "failed")
                raise RuntimeError(f"[Wave 0] Failed to download character sheet '{char_id}': {err_msg}") from e
                
        self.logger.update_wave("wave_0_character_sheets", "completed")

    # ── Wave 1: First Frames (Depth 0) ─────────────────────────────

    def wave_1_ideogram_ffs(self):
        """Generate all chain_start/##cut FF images in one Ideogram batch.
        Moved from cinematic_orchestrator.py L303-374."""
        self.logger.update_wave("wave_1_ideogram_ffs", "in_progress")
        self.logger.log("════════════════════════════════════════", "INFO")
        self.logger.log("  WAVE 1: Generating Raw Scene stills (Ideogram 4 T2I)", "INFO")
        self.logger.log("════════════════════════════════════════", "INFO")
        
        depth_0_shots = [s for s in self.all_shots if s["_depth"] == 0]
        
        pending_prompts = []
        for shot in depth_0_shots:
            prefix = shot["filename_prefix"]
            
            # FF still (only if ff_source is ideogram)
            if shot.get("ff_source") == "ideogram":
                ff_raw_name = f"{prefix}_ff_raw.png"
                ff_raw_path = os.path.join(self.scenes_dir, ff_raw_name)
                item_id = f"{prefix}_ff_raw"
                
                if os.path.exists(ff_raw_path) and os.path.getsize(ff_raw_path) > 1024:
                    self.logger.log(f"   📷 Raw FF already exists locally: {ff_raw_name}", "INFO")
                    srv_name = upload_image_if_needed(ff_raw_path, self.base_url, self.available_images, self.auth)
                    self.state["ff_images"][prefix] = srv_name
                    self.logger.update_item("wave_1_ideogram_ffs", item_id, "completed", output=ff_raw_name)
                else:
                    self.logger.update_item("wave_1_ideogram_ffs", item_id, "running")
                    # Compose Ideogram JSON structured prompt for layout control
                    ff_prompt_text = shot["ff_prompt"]
                    ideogram_ff_prompt = compose_scene_prompt(
                        prompt_text=ff_prompt_text,
                        global_style=self.global_cfg.get("style", ""),
                        characters_present=shot.get("characters_present", []),
                        characters_cfg=self.char_lookup
                    )
                    pending_prompts.append((prefix, "ff", ideogram_ff_prompt, ff_raw_path, ff_raw_name, item_id, shot))

            # LF still (only if lf_source is ideogram_fresh)
            if shot.get("lf_source") == "ideogram_fresh":
                lf_raw_name = f"{prefix}_lf_raw.png"
                lf_raw_path = os.path.join(self.scenes_dir, lf_raw_name)
                item_id = f"{prefix}_lf_raw"
                
                if os.path.exists(lf_raw_path) and os.path.getsize(lf_raw_path) > 1024:
                    self.logger.log(f"   📷 Raw LF already exists locally: {lf_raw_name}", "INFO")
                    srv_name = upload_image_if_needed(lf_raw_path, self.base_url, self.available_images, self.auth)
                    self.state["lf_images"][prefix] = srv_name
                    self.logger.update_item("wave_1_ideogram_ffs", item_id, "completed", output=lf_raw_name)
                else:
                    lf_prompt_text = shot.get("lf_prompt") or shot.get("narrative", "")
                    # Compose Ideogram JSON structured prompt for layout control
                    ideogram_lf_prompt = compose_scene_prompt(
                        prompt_text=lf_prompt_text,
                        global_style=self.global_cfg.get("style", ""),
                        characters_present=shot.get("characters_present", []),
                        characters_cfg=self.char_lookup
                    )
                    self.logger.update_item("wave_1_ideogram_ffs", item_id, "running")
                    pending_prompts.append((prefix, "lf", ideogram_lf_prompt, lf_raw_path, lf_raw_name, item_id, shot))

        if not pending_prompts:
            self.logger.log("   ✅ No raw frames need generation.", "INFO")
            self.logger.update_wave("wave_1_ideogram_ffs", "completed")
            return

        # Queue all stills
        queue_ids = []
        for prefix, role, prompt, local_path, raw_name, item_id, shot in pending_prompts:
            self.logger.log(f"   🎨 Queuing raw {role.upper()} for {prefix}...", "INFO")
            shot_for_builder = {
                "prompt": prompt,
                "references": [],
                "filename_prefix": raw_name.replace(".png", "")
            }
            workflow = build_dynamic_workflow(self.ideogram_template, shot_for_builder, self.global_cfg)
            res = curl_json("POST", "/prompt", self.base_url, data={"prompt": workflow, "client_id": f"{prefix}-{role}"}, auth=self.auth)
            if "prompt_id" in res:
                queue_ids.append((prefix, role, res["prompt_id"], local_path, raw_name, item_id, shot))
            else:
                err_msg = res.get('error', 'unknown error')
                self.logger.log(f"      ❌ Failed to queue raw still for {prefix}: {err_msg}", "ERROR")
                self.logger.update_item("wave_1_ideogram_ffs", item_id, "failed", error=err_msg)

        # Wait and download
        for prefix, role, prompt_id, local_path, raw_name, item_id, shot in queue_ids:
            self.logger.log(f"   ⏳ Waiting for raw {role.upper()}: {prefix}...", "INFO")
            try:
                outputs = wait_for_prompt(prompt_id, self.base_url, auth=self.auth)
                srv_name = None
                for nid, out in outputs.items():
                    for item in out.get("images", []):
                        srv_filename = item["filename"]
                        download_output(srv_filename, local_path, self.base_url, auth=self.auth)
                        srv_name = upload_image_if_needed(local_path, self.base_url, self.available_images, self.auth)
                        
                        if role == "ff":
                            self.state["ff_images"][prefix] = srv_name
                        else:
                            self.state["lf_images"][prefix] = srv_name
                        self.logger.log(f"      ✅ Saved raw {role}: {prefix} ({srv_name})", "INFO")
                
                if not srv_name:
                    raise RuntimeError(f"No output image returned for raw {role}")

                # Evaluate scene composition (Gate 2)
                eval_res = None
                gate_enabled = self.global_cfg.get("quality_gate", {}).get("gates", {}).get("scene_composition", True)
                if self.quality_gate_enabled and gate_enabled and role == "ff":
                    self.logger.log(f"      🛡️ Gate 2: Reviewing FF scene composition quality...", "INFO")
                    ref_paths = [os.path.join(self.references_dir, f"{cid}_character_sheet.png") for cid in shot.get("characters_present", [])]
                    char_desc = "; ".join(self.char_lookup[cid]["description"] for cid in shot.get("characters_present", []) if cid in self.char_lookup)
                    eval_res = evaluate_scene_composition(
                        image_path=local_path,
                        character_sheet_paths=[p for p in ref_paths if os.path.exists(p)],
                        ff_prompt=shot["ff_prompt"],
                        characters_desc=char_desc,
                        global_style=self.global_cfg.get("style", "3D Pixar-style"),
                        provider=self.provider_name,
                        api_key=self.api_key,
                        model=self.global_cfg.get("quality_gate", {}).get("model_image")
                    )
                    if eval_res.get("rejected", False) or not eval_res.get("passed", True):
                        self.logger.log(f"         ⚠️ Scene composition failed quality gate: {eval_res.get('rejection_reason', 'low score')}", "WARN")
                    else:
                        self.logger.log(f"         ✅ Passed. Score: {eval_res.get('overall') or eval_res.get('overall_score') or 0}/10", "INFO")
                
                score = eval_res.get("overall") if eval_res else None
                self.logger.update_item("wave_1_ideogram_ffs", item_id, "completed", output=raw_name, eval_score=score, eval_result=eval_res)

            except Exception as e:
                err_msg = str(e)
                self.logger.log(f"      ❌ Error downloading raw still for {prefix}: {err_msg}", "ERROR")
                self.logger.update_item("wave_1_ideogram_ffs", item_id, "failed", error=err_msg)

        self.logger.update_wave("wave_1_ideogram_ffs", "completed")

    # ── Wave 2a: Flux Klein FF Edits (Depth 0) ─────────────────────

    def wave_2a_klein_ff_edits(self):
        """Run Klein FF consistency edits ONLY for depth 0 shots.
        Split from the original wave_2_klein_edits().
        Queue all FF edits → wait/download all → update state["ff_images"]."""
        self.logger.update_wave("wave_2a_klein_ff_edits", "in_progress")
        self.logger.log("════════════════════════════════════════", "INFO")
        self.logger.log("  WAVE 2a: Running Flux Klein FF Edits (Depth 0)", "INFO")
        self.logger.log("════════════════════════════════════════", "INFO")

        depth_0_shots = [s for s in self.all_shots if s["_depth"] == 0]
        pending_edits = []

        for shot in depth_0_shots:
            prefix = shot["filename_prefix"]
            chars_present = shot.get("characters_present", [])
            has_characters = len(chars_present) > 0
            item_id = f"{prefix}_ff_edit"

            if shot.get("ff_source") == "ideogram":
                raw_ff_name = f"{prefix}_ff_raw.png"
                raw_ff_path = os.path.join(self.scenes_dir, raw_ff_name)
                edited_ff_name = f"{prefix}_ff_edited.png"
                edited_ff_path = os.path.join(self.scenes_edited_dir, edited_ff_name)

                if os.path.exists(edited_ff_path) and os.path.getsize(edited_ff_path) > 1024:
                    self.logger.log(f"   📷 Edited FF already exists locally: {edited_ff_name}", "INFO")
                    srv_name = upload_image_if_needed(edited_ff_path, self.base_url, self.available_images, self.auth)
                    self.state["ff_images"][prefix] = srv_name
                    self.logger.update_item("wave_2a_klein_ff_edits", item_id, "completed", output=edited_ff_name)
                elif not has_characters:
                    self.logger.log(f"   ⏭️  No character consistency needed for {prefix} FF — copying raw file.", "INFO")
                    shutil.copy(raw_ff_path, edited_ff_path)
                    srv_name = upload_image_if_needed(edited_ff_path, self.base_url, self.available_images, self.auth)
                    self.state["ff_images"][prefix] = srv_name
                    self.logger.update_item("wave_2a_klein_ff_edits", item_id, "completed", output=edited_ff_name)
                else:
                    self.logger.update_item("wave_2a_klein_ff_edits", item_id, "running")
                    edit_prompt = build_ff_edit_prompt(shot, self.char_lookup, self.global_cfg.get("style", ""))
                    char_refs = [self.state["character_sheets"][cid] for cid in chars_present if cid in self.state["character_sheets"]]
                    pending_edits.append((prefix, item_id, self.state["ff_images"][prefix], char_refs, edit_prompt, edited_ff_path, edited_ff_name, chars_present, shot))

        if not pending_edits:
            self.logger.log("   ✅ No Klein FF edits need processing.", "INFO")
            self.logger.update_wave("wave_2a_klein_ff_edits", "completed")
            return

        # Queue
        queue_ids = []
        for prefix, item_id, input_scene, char_refs, edit_prompt, local_path, edited_name, chars, shot in pending_edits:
            self.logger.log(f"   🎨 Queuing Klein FF edit for {prefix}...", "INFO")
            shot_for_builder = {
                "prompt": edit_prompt,
                "scene_image": input_scene,
                "character_refs": char_refs,
                "filename_prefix": edited_name.replace(".png", ""),
                "_builder_mode": "flux_klein_edit_dynamic"
            }
            workflow = build_dynamic_workflow(self.flux_edit_template, shot_for_builder, self.global_cfg)
            res = curl_json("POST", "/prompt", self.base_url, data={"prompt": workflow, "client_id": f"{prefix}-ff-edit"}, auth=self.auth)
            if "prompt_id" in res:
                queue_ids.append((prefix, item_id, res["prompt_id"], local_path, edited_name, chars, shot))
            else:
                err_msg = res.get('error', 'unknown error')
                self.logger.log(f"      ❌ Failed to queue Klein FF edit for {prefix}: {err_msg}", "ERROR")
                self.logger.update_item("wave_2a_klein_ff_edits", item_id, "failed", error=err_msg)

        # Wait and download
        for prefix, item_id, prompt_id, local_path, edited_name, chars, shot in queue_ids:
            self.logger.log(f"   ⏳ Waiting for Klein FF edit: {prefix}...", "INFO")
            try:
                outputs = wait_for_prompt(prompt_id, self.base_url, auth=self.auth)
                srv_name = None
                for nid, out in outputs.items():
                    for item in out.get("images", []):
                        srv_filename = item["filename"]
                        download_output(srv_filename, local_path, self.base_url, auth=self.auth)
                        srv_name = upload_image_if_needed(local_path, self.base_url, self.available_images, self.auth)
                        self.state["ff_images"][prefix] = srv_name
                        self.logger.log(f"      ✅ Saved edited still: {prefix} ({srv_name})", "INFO")
                
                if not srv_name:
                    raise RuntimeError("No output image from Klein FF edit ComfyUI prompt")

                # Run Gate 3: Klein Consistency Check
                eval_res = None
                gate_enabled = self.global_cfg.get("quality_gate", {}).get("gates", {}).get("klein_consistency", True)
                if self.quality_gate_enabled and gate_enabled:
                    self.logger.log(f"      🛡️ Gate 3: Reviewing edited character consistency likeness/neutrality...", "INFO")
                    ref_paths = [os.path.join(self.references_dir, f"{cid}_character_sheet.png") for cid in chars]
                    raw_ff_path = os.path.join(self.scenes_dir, f"{prefix}_ff_raw.png")
                    eval_res = evaluate_klein_consistency(
                        edited_path=local_path,
                        raw_path=raw_ff_path,
                        character_sheet_paths=[p for p in ref_paths if os.path.exists(p)],
                        provider=self.provider_name,
                        api_key=self.api_key,
                        model=self.global_cfg.get("quality_gate", {}).get("model_image")
                    )
                    if eval_res.get("rejected", False) or not eval_res.get("passed", True):
                        self.logger.log(f"         ⚠️ Edited still failed quality gate: {eval_res.get('rejection_reason', 'low score')}", "WARN")
                    else:
                        self.logger.log(f"         ✅ Passed. Likeness: {eval_res.get('character_likeness')}/10, background preservation: {eval_res.get('background_preservation')}/10", "INFO")

                score = eval_res.get("overall") if eval_res else None
                self.logger.update_item("wave_2a_klein_ff_edits", item_id, "completed", output=edited_name, eval_score=score, eval_result=eval_res)

            except Exception as e:
                err_msg = str(e)
                self.logger.log(f"      ❌ Error waiting/downloading Klein FF edit: {err_msg}", "ERROR")
                self.logger.update_item("wave_2a_klein_ff_edits", item_id, "failed", error=err_msg)

        self.logger.update_wave("wave_2a_klein_ff_edits", "completed")

    # ── Wave 2b: Flux Klein LF Derivations (Depth 0) ───────────────

    def wave_2b_klein_lf_derivations(self):
        """Run Klein LF derivations ONLY for depth 0 shots.
        Split from the original wave_2_klein_edits().
        Uses state["ff_images"] which is now guaranteed to have edited FF paths.
        Queue all LF derivations → wait/download all → update state["lf_images"].
        
        THIS IS THE FIX FOR THE RACE CONDITION."""
        self.logger.update_wave("wave_2b_klein_lf_derivations", "in_progress")
        self.logger.log("════════════════════════════════════════", "INFO")
        self.logger.log("  WAVE 2b: Running Flux Klein LF Derivations (Depth 0)", "INFO")
        self.logger.log("════════════════════════════════════════", "INFO")

        depth_0_shots = [s for s in self.all_shots if s["_depth"] == 0]
        pending_edits = []

        for shot in depth_0_shots:
            prefix = shot["filename_prefix"]
            chars_present = shot.get("characters_present", [])
            item_id = f"{prefix}_lf_derivation"

            if shot.get("lf_source") == "klein_from_ff":
                edited_lf_name = f"{prefix}_lf_edited.png"
                edited_lf_path = os.path.join(self.scenes_edited_dir, edited_lf_name)

                if os.path.exists(edited_lf_path) and os.path.getsize(edited_lf_path) > 1024:
                    self.logger.log(f"   📷 Derived LF already exists locally: {edited_lf_name}", "INFO")
                    srv_name = upload_image_if_needed(edited_lf_path, self.base_url, self.available_images, self.auth)
                    self.state["lf_images"][prefix] = srv_name
                    self.logger.update_item("wave_2b_klein_lf_derivations", item_id, "completed", output=edited_lf_name)
                else:
                    self.logger.update_item("wave_2b_klein_lf_derivations", item_id, "running")
                    edit_prompt = build_lf_derivation_prompt(shot, self.global_cfg.get("style", ""))
                    lf_refs = shot.get("lf_edit_references", chars_present)
                    char_refs = [self.state["character_sheets"][cid] for cid in lf_refs if cid in self.state["character_sheets"]]
                    
                    # Ensure the edited FF image is ready on ComfyUI server
                    ff_srv_name = self.state["ff_images"].get(prefix)
                    if not ff_srv_name:
                        self.logger.log(f"      ❌ Missing edited FF server image for {prefix}. Cannot derive LF.", "ERROR")
                        self.logger.update_item("wave_2b_klein_lf_derivations", item_id, "failed", error="Missing edited FF")
                        continue

                    pending_edits.append((prefix, item_id, ff_srv_name, char_refs, edit_prompt, edited_lf_path, edited_lf_name, lf_refs, shot))

        if not pending_edits:
            self.logger.log("   ✅ No Klein LF derivations need processing.", "INFO")
            self.logger.update_wave("wave_2b_klein_lf_derivations", "completed")
            return

        # Queue
        queue_ids = []
        for prefix, item_id, scene_image, char_refs, edit_prompt, local_path, edited_name, chars, shot in pending_edits:
            self.logger.log(f"   🎨 Queuing Klein LF derivation for {prefix}...", "INFO")
            shot_for_builder = {
                "prompt": edit_prompt,
                "scene_image": scene_image,
                "character_refs": char_refs,
                "filename_prefix": edited_name.replace(".png", ""),
                "_builder_mode": "flux_klein_edit_dynamic"
            }
            workflow = build_dynamic_workflow(self.flux_edit_template, shot_for_builder, self.global_cfg)
            res = curl_json("POST", "/prompt", self.base_url, data={"prompt": workflow, "client_id": f"{prefix}-lf-derivation"}, auth=self.auth)
            if "prompt_id" in res:
                queue_ids.append((prefix, item_id, res["prompt_id"], local_path, edited_name, chars, shot))
            else:
                err_msg = res.get('error', 'unknown error')
                self.logger.log(f"      ❌ Failed to queue Klein LF derivation for {prefix}: {err_msg}", "ERROR")
                self.logger.update_item("wave_2b_klein_lf_derivations", item_id, "failed", error=err_msg)

        # Wait and download
        for prefix, item_id, prompt_id, local_path, edited_name, chars, shot in queue_ids:
            self.logger.log(f"   ⏳ Waiting for Klein LF derivation: {prefix}...", "INFO")
            try:
                outputs = wait_for_prompt(prompt_id, self.base_url, auth=self.auth)
                srv_name = None
                for nid, out in outputs.items():
                    for item in out.get("images", []):
                        srv_filename = item["filename"]
                        download_output(srv_filename, local_path, self.base_url, auth=self.auth)
                        srv_name = upload_image_if_needed(local_path, self.base_url, self.available_images, self.auth)
                        self.state["lf_images"][prefix] = srv_name
                        self.logger.log(f"      ✅ Saved edited still: {prefix} ({srv_name})", "INFO")

                if not srv_name:
                    raise RuntimeError("No output image from ComfyUI prompt")

                # Run Gate 4: LF Delta Verification (Compare FF vs LF)
                eval_res = None
                gate_enabled = self.global_cfg.get("quality_gate", {}).get("gates", {}).get("lf_delta", True)
                if self.quality_gate_enabled and gate_enabled:
                    self.logger.log(f"      🛡️ Gate 4: Reviewing LF delta verification quality...", "INFO")
                    ff_edited_path = os.path.join(self.scenes_edited_dir, f"{prefix}_ff_edited.png")
                    eval_res = evaluate_lf_delta(
                        ff_path=ff_edited_path,
                        lf_path=local_path,
                        lf_edit_instruction=shot.get("lf_edit_instruction", ""),
                        provider=self.provider_name,
                        api_key=self.api_key,
                        model=self.global_cfg.get("quality_gate", {}).get("model_image")
                    )
                    if eval_res.get("rejected", False) or not eval_res.get("passed", True):
                        self.logger.log(f"         ⚠️ LF delta failed quality gate: {eval_res.get('rejection_reason', 'low score')}", "WARN")
                    else:
                        self.logger.log(f"         ✅ Passed. Delta accuracy: {eval_res.get('delta_accuracy')}/10, Identity preserved: {eval_res.get('identity_preserved')}/10", "INFO")

                score = eval_res.get("overall") if eval_res else None
                self.logger.update_item("wave_2b_klein_lf_derivations", item_id, "completed", output=edited_name, eval_score=score, eval_result=eval_res)

            except Exception as e:
                err_msg = str(e)
                self.logger.log(f"      ❌ Error waiting/downloading Klein LF derivation: {err_msg}", "ERROR")
                self.logger.update_item("wave_2b_klein_lf_derivations", item_id, "failed", error=err_msg)

        self.logger.update_wave("wave_2b_klein_lf_derivations", "completed")

    # ── Wave 3: FFLF Video (Depth 0) ───────────────────────────────

    def wave_3_fflf_batch_1(self):
        """Run FFLF video generation for depth 0 shots, then extract tail frames."""
        self.logger.update_wave("wave_3_fflf_batch", "in_progress")
        self.logger.log("════════════════════════════════════════", "INFO")
        self.logger.log("  WAVE 3: Executing LTX FFLF Video Gen (Depth 0)", "INFO")
        self.logger.log("════════════════════════════════════════", "INFO")
        depth_0_shots = [s for s in self.all_shots if s["_depth"] == 0]

        for shot in depth_0_shots:
            prefix = shot["filename_prefix"]
            item_id = f"{prefix}_video"
            
            # Skip if we only targeted a specific shot
            if self.args.shot and prefix != self.args.shot:
                continue

            self.logger.update_item("wave_3_fflf_batch", item_id, "running")

            # Skip existing videos if requested
            if self.args.skip_existing:
                existing = sorted(
                    f for f in os.listdir(self.videos_dir)
                    if f.startswith(prefix) and f.endswith(('.mp4', '.webm', '.gif'))
                    and os.path.getsize(os.path.join(self.videos_dir, f)) > 1024 * 100
                )
                if existing:
                    existing_path = os.path.join(self.videos_dir, existing[-1])
                    self.logger.log(f"   ⏭️ Skipping video gen for {prefix} (exists: {existing[-1]})", "INFO")
                    self.state["videos"][prefix] = existing_path
                    self._extract_and_cache_tail(existing_path, shot, prefix)
                    self.logger.update_item("wave_3_fflf_batch", item_id, "completed", output=existing[-1])
                    continue

            # Run FFLF execution
            shot_data_for_fflf = copy.deepcopy(shot)
            shot_data_for_fflf["first_frame_image"] = f"{prefix}_ff_edited.png"
            shot_data_for_fflf["last_frame_image"] = f"{prefix}_lf_edited.png"

            self.logger.log(f"   🎥 Running FFLF video generation for {prefix}...", "INFO")
            try:
                video_path = execute_fflf_shot(
                    shot_data=shot_data_for_fflf,
                    global_cfg=self.global_cfg,
                    workflow_template=self.ltx_fflf_template,
                    base_url=self.base_url,
                    videos_dir=self.videos_dir,
                    scenes_dir=self.scenes_edited_dir,
                    motion_eval_dir=self.motion_eval_dir,
                    available_images=self.available_images,
                    mode="fast" if self.args.fast else ("interactive" if self.args.interactive else "auto"),
                    auth=self.auth
                )

                if video_path and os.path.exists(video_path):
                    self.state["videos"][prefix] = video_path
                    self._extract_and_cache_tail(video_path, shot, prefix)
                    self.logger.update_item("wave_3_fflf_batch", item_id, "completed", output=os.path.basename(video_path))
                else:
                    self.logger.log(f"   ❌ FFLF video generation failed for {prefix}.", "ERROR")
                    self.logger.update_item("wave_3_fflf_batch", item_id, "failed", error="Generation failed")
            except Exception as e:
                err_msg = str(e)
                self.logger.log(f"   ❌ FFLF video generation error: {err_msg}", "ERROR")
                self.logger.update_item("wave_3_fflf_batch", item_id, "failed", error=err_msg)

        self.logger.update_wave("wave_3_fflf_batch", "completed")

    # ── Wave N: Continuation Waves (Depth >= 1) ────────────────────

    def wave_n_klein_continuation(self, depth):
        """Generate LFs for continuation shots at a specific depth using predecessor tail frames."""
        wave_name = f"wave_N_continuations_depth_{depth}_klein"
        self.logger.update_wave(wave_name, "in_progress")
        self.logger.log(f"   🎨 WAVE {4 + (depth-1)*2}: Generating Continuation LFs (Depth {depth})", "INFO")
        depth_shots = [s for s in self.all_shots if s["_depth"] == depth]

        pending_edits = []
        for shot in depth_shots:
            prefix = shot["filename_prefix"]
            pred_prefix = shot["continues_from"]
            chars_present = shot.get("characters_present", [])
            item_id = f"{prefix}_lf_continuation"

            # First frame of this shot is the predecessor's tail frame
            pred_tail_srv = self.state["tail_frames"].get(pred_prefix)
            if not pred_tail_srv:
                self.logger.log(f"      ⚠️ Predecessor tail frame not found for {prefix} — skipping LF derivation.", "WARN")
                self.logger.update_item(wave_name, item_id, "skipped", error="Missing predecessor tail frame")
                continue

            edited_lf_name = f"{prefix}_lf_edited.png"
            edited_lf_path = os.path.join(self.scenes_edited_dir, edited_lf_name)

            if os.path.exists(edited_lf_path) and os.path.getsize(edited_lf_path) > 1024:
                self.logger.log(f"      📷 Continuation LF already exists locally: {edited_lf_name}", "INFO")
                srv_name = upload_image_if_needed(edited_lf_path, self.base_url, self.available_images, self.auth)
                self.state["lf_images"][prefix] = srv_name
                self.logger.update_item(wave_name, item_id, "completed", output=edited_lf_name)
            else:
                self.logger.update_item(wave_name, item_id, "running")
                edit_prompt = build_lf_derivation_prompt(shot, self.global_cfg.get("style", ""))
                lf_refs = shot.get("lf_edit_references", chars_present)
                char_refs = [self.state["character_sheets"][cid] for cid in lf_refs if cid in self.state["character_sheets"]]
                pending_edits.append((prefix, item_id, pred_tail_srv, char_refs, edit_prompt, edited_lf_path, edited_lf_name, lf_refs, shot))

        if not pending_edits:
            self.logger.update_wave(wave_name, "completed")
            return

        # Queue
        queue_ids = []
        for prefix, item_id, pred_tail_srv, char_refs, edit_prompt, local_path, edited_name, chars, shot in pending_edits:
            self.logger.log(f"      🎨 Queuing Klein LF edit for {prefix} from tail...", "INFO")
            shot_for_builder = {
                "prompt": edit_prompt,
                "scene_image": pred_tail_srv,
                "character_refs": char_refs,
                "filename_prefix": edited_name.replace(".png", ""),
                "_builder_mode": "flux_klein_edit_dynamic"
            }
            workflow = build_dynamic_workflow(self.flux_edit_template, shot_for_builder, self.global_cfg)
            res = curl_json("POST", "/prompt", self.base_url, data={"prompt": workflow, "client_id": f"{prefix}-continuation-lf"}, auth=self.auth)
            if "prompt_id" in res:
                queue_ids.append((prefix, item_id, res["prompt_id"], local_path, edited_name, chars, shot))
            else:
                err_msg = res.get('error', 'unknown error')
                self.logger.log(f"         ❌ Failed to queue Klein edit for {prefix}: {err_msg}", "ERROR")
                self.logger.update_item(wave_name, item_id, "failed", error=err_msg)

        # Wait and download
        for prefix, item_id, prompt_id, local_path, edited_name, chars, shot in queue_ids:
            self.logger.log(f"      ⏳ Waiting for Klein LF: {prefix}...", "INFO")
            try:
                outputs = wait_for_prompt(prompt_id, self.base_url, auth=self.auth)
                srv_name = None
                for nid, out in outputs.items():
                    for item in out.get("images", []):
                        srv_filename = item["filename"]
                        download_output(srv_filename, local_path, self.base_url, auth=self.auth)
                        srv_name = upload_image_if_needed(local_path, self.base_url, self.available_images, self.auth)
                        self.state["lf_images"][prefix] = srv_name
                        self.logger.log(f"         ✅ Saved continuation LF: {prefix} ({srv_name})", "INFO")

                if not srv_name:
                    raise RuntimeError("No output image from ComfyUI prompt")

                # Run Quality Gate review (Gate 4 for continuation LF)
                eval_res = None
                gate_enabled = self.global_cfg.get("quality_gate", {}).get("gates", {}).get("lf_delta", True)
                if self.quality_gate_enabled and gate_enabled:
                    self.logger.log(f"         🛡️ Reviewing edited character consistency likeness/neutrality...", "INFO")
                    pred_prefix = shot["continues_from"]
                    ff_path = os.path.join(self.scenes_edited_dir, f"{pred_prefix}_tail_frame.png")
                    eval_res = evaluate_lf_delta(
                        ff_path=ff_path,
                        lf_path=local_path,
                        lf_edit_instruction=shot.get("lf_edit_instruction", ""),
                        provider=self.provider_name,
                        api_key=self.api_key,
                        model=self.global_cfg.get("quality_gate", {}).get("model_image")
                    )
                    if eval_res.get("rejected", False) or not eval_res.get("passed", True):
                        self.logger.log(f"            ⚠️ Continuation LF failed quality gate: {eval_res.get('rejection_reason', 'low score')}", "WARN")
                    else:
                        self.logger.log(f"            ✅ Passed. Delta accuracy: {eval_res.get('delta_accuracy')}/10, Identity preserved: {eval_res.get('identity_preserved')}/10", "INFO")

                score = eval_res.get("overall") if eval_res else None
                self.logger.update_item(wave_name, item_id, "completed", output=edited_name, eval_score=score, eval_result=eval_res)

            except Exception as e:
                err_msg = str(e)
                self.logger.log(f"         ❌ Error waiting/downloading Klein LF edit: {err_msg}", "ERROR")
                self.logger.update_item(wave_name, item_id, "failed", error=err_msg)

        self.logger.update_wave(wave_name, "completed")

    def wave_n_fflf_continuation(self, depth):
        """Run FFLF video generation for continuation shots at a specific depth, then extract tail frames."""
        wave_name = f"wave_N_continuations_depth_{depth}_fflf"
        self.logger.update_wave(wave_name, "in_progress")
        self.logger.log(f"   🎥 WAVE {5 + (depth-1)*2}: Executing LTX FFLF Video Gen (Depth {depth})", "INFO")
        depth_shots = [s for s in self.all_shots if s["_depth"] == depth]

        for shot in depth_shots:
            prefix = shot["filename_prefix"]
            pred_prefix = shot["continues_from"]
            item_id = f"{prefix}_video"

            # Skip if we targeted a single shot
            if self.args.shot and prefix != self.args.shot:
                continue

            self.logger.update_item(wave_name, item_id, "running")

            # Skip existing
            if self.args.skip_existing:
                existing = sorted(
                    f for f in os.listdir(self.videos_dir)
                    if f.startswith(prefix) and f.endswith(('.mp4', '.webm', '.gif'))
                    and os.path.getsize(os.path.join(self.videos_dir, f)) > 1024 * 100
                )
                if existing:
                    existing_path = os.path.join(self.videos_dir, existing[-1])
                    self.logger.log(f"      Skip video gen for {prefix}", "INFO")
                    self.state["videos"][prefix] = existing_path
                    self._extract_and_cache_tail(existing_path, shot, prefix)
                    self.logger.update_item(wave_name, item_id, "completed", output=existing[-1])
                    continue

            # FF image is the local filename of the predecessor's tail frame
            pred_tail_local_name = f"{pred_prefix}_tail_frame.png"
            
            shot_data_for_fflf = copy.deepcopy(shot)
            shot_data_for_fflf["first_frame_image"] = pred_tail_local_name
            shot_data_for_fflf["last_frame_image"] = f"{prefix}_lf_edited.png"

            self.logger.log(f"      🎥 Running FFLF video generation for {prefix}...", "INFO")
            try:
                video_path = execute_fflf_shot(
                    shot_data=shot_data_for_fflf,
                    global_cfg=self.global_cfg,
                    workflow_template=self.ltx_fflf_template,
                    base_url=self.base_url,
                    videos_dir=self.videos_dir,
                    scenes_dir=self.scenes_edited_dir,
                    motion_eval_dir=self.motion_eval_dir,
                    available_images=self.available_images,
                    mode="fast" if self.args.fast else ("interactive" if self.args.interactive else "auto"),
                    auth=self.auth
                )

                if video_path and os.path.exists(video_path):
                    self.state["videos"][prefix] = video_path
                    self._extract_and_cache_tail(video_path, shot, prefix)
                    self.logger.update_item(wave_name, item_id, "completed", output=os.path.basename(video_path))
                else:
                    self.logger.log(f"      ❌ FFLF video generation failed for {prefix}.", "ERROR")
                    self.logger.update_item(wave_name, item_id, "failed", error="Generation failed")
            except Exception as e:
                err_msg = str(e)
                self.logger.log(f"      ❌ FFLF video generation error: {err_msg}", "ERROR")
                self.logger.update_item(wave_name, item_id, "failed", error=err_msg)

        self.logger.update_wave(wave_name, "completed")

    def _extract_and_cache_tail(self, video_path, shot, prefix):
        """Helper to extract tail frame and upload it to ComfyUI for continuation use."""
        overlap_seconds = shot.get("overrides", {}).get("overlap_seconds") or self.global_cfg.get("overlap_seconds", 1.0)
        fps = shot.get("overrides", {}).get("fps") or self.global_cfg.get("fps", 25)
        target_image_name = f"{prefix}_tail_frame.png"
        target_image_path = os.path.join(self.scenes_edited_dir, target_image_name)

        try:
            extracted = extract_continuation_frame(
                video_path=video_path,
                overlap_seconds=overlap_seconds,
                fps=fps,
                output_path=target_image_path
            )
            if extracted and os.path.exists(extracted):
                srv_name = upload_image_if_needed(target_image_path, self.base_url, self.available_images, self.auth)
                self.state["tail_frames"][prefix] = srv_name
                self.logger.log(f"   🎞️ Extracted and uploaded tail frame to ComfyUI: {srv_name}", "INFO")
        except Exception as e:
            self.logger.log(f"   ⚠️ Tail frame extraction error for {prefix}: {e}", "WARN")
