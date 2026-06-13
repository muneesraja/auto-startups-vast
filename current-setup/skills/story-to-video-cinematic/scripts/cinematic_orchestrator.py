#!/usr/bin/env python3
"""
Story-to-Video-Cinematic: Batch-Wave Cinematic Orchestrator V2
============================================================
Orchestrates the 3-stage model pipeline using the batch-wave execution model:
  1. Ideogram 4 T2I -> Character sheets + raw scene stills (Wave 0 + Wave 1)
  2. Flux Klein 9B Edit -> Character consistency refinement (Wave 2, Wave 4, Wave 6)
  3. LTX 2.3 FFLF -> Consistent video generation (Wave 3, Wave 5, Wave 7)

This class-based orchestrator minimizes model swaps (max 7 swaps) and supports
dynamic 1-4 character reference sheet injection.
"""

import argparse
import json
import os
import shutil
import sys
import time
import copy

# Resolve and append story-to-video-filmmaking scripts path
script_dir = os.path.dirname(os.path.abspath(__file__))
filmmaking_scripts = os.path.abspath(os.path.join(
    script_dir, "..", "..", "story-to-video-filmmaking", "scripts"
))
sys.path.append(filmmaking_scripts)

# Import ComfyUI and filmmaking helper modules
from comfyui_api import (
    curl_json,
    wait_for_prompt,
    download_output,
    get_available_images,
    upload_image,
    DEFAULT_BASE_URL,
)
from workflow_builder import build_dynamic_workflow, load_workflow_template
from filmmaking_utils import upload_image_if_needed
from continuation_pipeline import extract_continuation_frame
from fflf_executor import execute_fflf_shot
from gemini_eval import evaluate_image_against_reference, resolve_provider

# Import generators/editors
import ideogram_generator
import flux_edit_pass


class BatchWaveOrchestrator:
    """Batch-wave execution engine for the cinematic pipeline."""

    def __init__(self, prompts_data, base_url, comfyui_auth, output_dir, args):
        self.prompts_data = prompts_data
        self.version = prompts_data.get("version", "3.0")
        self.characters = prompts_data.get("characters", [])  # list of characters
        self.director_plan = prompts_data.get("director_plan", {})
        self.global_cfg = prompts_data.get("global", {})
        self.max_continuous = self.global_cfg.get("max_continuous_shots", 3)
        self.base_url = base_url
        self.auth = comfyui_auth
        self.output_dir = output_dir
        self.args = args

        # Establish folders
        self.scenes_dir = os.path.join(output_dir, "scenes")
        self.scenes_edited_dir = os.path.join(output_dir, "scenes_edited")
        self.videos_dir = os.path.join(output_dir, "videos")
        self.motion_eval_dir = os.path.join(output_dir, "motion_eval")
        self.references_dir = args.references_dir or os.path.join(output_dir, "character_sheets")

        for d in [self.scenes_dir, self.scenes_edited_dir, self.videos_dir, self.motion_eval_dir, self.references_dir]:
            os.makedirs(d, exist_ok=True)

        # Build character lookup: id → character object
        self.char_lookup = {c["id"]: c for c in self.characters}

        # Flatten all shots with scene context
        self.all_shots = self._flatten_shots()

        # Calculate visual depths for continuation waves
        self._assign_depths()

        # Resolve chain topology
        self.chains = self._resolve_chains()

        # Track generated assets
        self.state = {
            "character_sheets": {},   # char_id → ComfyUI server filename
            "ff_images": {},          # "sNN_shNN" → ComfyUI server filename
            "lf_images": {},          # "sNN_shNN" → ComfyUI server filename
            "videos": {},             # "sNN_shNN" → local path
            "tail_frames": {},        # "sNN_shNN" → ComfyUI server filename
        }

        # Load workflow templates
        cinematic_templates_dir = os.path.abspath(os.path.join(script_dir, "..", "assets", "workflow-templates"))
        filmmaking_templates_dir = os.path.abspath(os.path.join(script_dir, "..", "..", "story-to-video-filmmaking", "assets", "workflow-templates"))

        self.ideogram_template = load_workflow_template("ideogram-4-t2i", templates_dir=cinematic_templates_dir)
        self.flux_edit_template = load_workflow_template("flux-2-klein-image-edit", templates_dir=cinematic_templates_dir)
        self.ltx_fflf_template = load_workflow_template("ltx-23-fflf-seed-hunter", templates_dir=filmmaking_templates_dir)

        # Quality gates setup
        self.quality_gate_enabled = self.global_cfg.get("quality_gate", {}).get("enabled", False)
        self.provider_name = None
        self.api_key = None
        if self.quality_gate_enabled:
            try:
                self.provider_name = self.global_cfg.get("quality_gate", {}).get("provider") or args.provider
                self.provider_name, self.api_key, _ = resolve_provider(self.provider_name)
                print(f"🛡️ Quality Gate enabled using provider: {self.provider_name}")
            except Exception as e:
                print(f"⚠️ Could not initialize Quality Gate provider: {e}. Disabling quality gates.")
                self.quality_gate_enabled = False

        # ComfyUI available files discovery
        try:
            self.available_images = get_available_images(self.base_url, auth=self.auth)
            print(f"📷 Found {len(self.available_images)} files in ComfyUI input directory")
        except Exception as e:
            print(f"⚠️ Could not fetch ComfyUI input directory files: {e}")
            self.available_images = set()

    def _flatten_shots(self):
        """Flatten director_plan.scenes[].shots[] into a flat list with scene context."""
        shots = []
        for scene in self.director_plan.get("scenes", []):
            for shot in scene.get("shots", []):
                shot_copy = copy.deepcopy(shot)
                # Map compatibility keys for filmmaker skill executor
                shot_copy["scene"] = scene["scene_id"]
                shot_copy["shot"] = shot["shot_id"]
                shot_copy["_scene_id"] = scene["scene_id"]
                shot_copy["_scene_title"] = scene.get("scene_title", "")
                shot_copy["filename_prefix"] = f"s{scene['scene_id']:02d}_sh{shot['shot_id']:02d}"
                shots.append(shot_copy)
        return shots

    def _assign_depths(self):
        """Assign visual depth to each shot to schedule continuation waves."""
        prefix_to_shot = {shot["filename_prefix"]: shot for shot in self.all_shots}
        for shot in self.all_shots:
            depth = 0
            curr = shot
            # A fresh ideogram start breaks any visual continuity chain
            while curr.get("continues_from") and curr.get("ff_source") != "ideogram":
                pred = prefix_to_shot.get(curr["continues_from"])
                if not pred or pred == curr:
                    break
                depth += 1
                curr = pred
            shot["_depth"] = depth

    def _resolve_chains(self):
        """Group shots into continuation chains, enforcing max_continuous_shots."""
        chains = []
        current_chain = []
        for shot in self.all_shots:
            cont = shot.get("continuity", "start")
            # Force a cut if the visual continuation chain gets too long
            if cont in ("start", "##cut") or len(current_chain) >= self.max_continuous:
                if current_chain:
                    chains.append(current_chain)
                current_chain = [shot]
            elif cont == "##continue":
                current_chain.append(shot)
        if current_chain:
            chains.append(current_chain)
        return chains

    def print_plan(self):
        """Print resolved wave schedule."""
        print(f"\n📋 Batch-Wave Plan (Total: {len(self.all_shots)} shot(s))")
        print("=" * 80)
        print("  Characters Registry:")
        for char in self.characters:
            print(f"    - {char['id']}: {char['display_name']} (descriptor: {char['edit_prompt_descriptor']})")
        
        print("\n  Wave Execution Visual Depths:")
        depth_map = {}
        for shot in self.all_shots:
            d = shot["_depth"]
            depth_map.setdefault(d, []).append(shot["filename_prefix"])
        for d, prefixes in sorted(depth_map.items()):
            print(f"    Depth {d} shots: {', '.join(prefixes)}")
        print("=" * 80)

    def execute(self):
        """Orchestrate the batch-wave pipeline execution."""
        self.print_plan()

        # Wave 0: Generate all character sheets in batch
        self.wave_0_character_sheets()

        # Wave 1: Generate all raw FFs for depth 0 shots
        self.wave_1_ideogram_ffs()

        # Wave 2: Klein FF edits + LF derivations (depth 0)
        self.wave_2_klein_edits()

        # Wave 3: FFLF Video Gen (depth 0) + Tail Frame Extraction
        self.wave_3_fflf_batch_1()

        # Continuation Waves (Depth 1, 2, ...)
        depth = 1
        while self._has_pending_depth(depth):
            print(f"\n\n{'═'*80}\n  WAVES {4 + (depth-1)*2} & {5 + (depth-1)*2}: Continuation Depth {depth}\n{'═'*80}")
            self.wave_n_klein_continuation(depth)
            self.wave_n_fflf_continuation(depth)
            depth += 1

        self.generate_stitch_metadata()

    def _has_pending_depth(self, depth):
        """Check if any shot is registered at this continuation depth."""
        return any(shot["_depth"] == depth for shot in self.all_shots)

    # ── Wave 0: Character Sheets ───────────────────────────────────

    def wave_0_character_sheets(self):
        """Generate all character sheets in one Ideogram batch."""
        print(f"\n\n{'═'*80}\n  WAVE 0: Generating Character Sheets (Ideogram 4)\n{'═'*80}")
        pending_prompts = []
        
        for char in self.characters:
            char_id = char["id"]
            sheet_filename = f"{char_id}_character_sheet.png"
            local_path = os.path.join(self.references_dir, sheet_filename)
            
            # Check if sheet exists or is pre-defined
            if char.get("character_sheet_path"):
                shutil.copy(char["character_sheet_path"], local_path)
                print(f"   📋 Copied predefined character sheet for {char_id}")
                srv_name = upload_image_if_needed(local_path, self.base_url, self.available_images, self.auth)
                self.state["character_sheets"][char_id] = srv_name
            elif os.path.exists(local_path) and os.path.getsize(local_path) > 1024:
                print(f"   📷 Character sheet for {char_id} already exists locally")
                srv_name = upload_image_if_needed(local_path, self.base_url, self.available_images, self.auth)
                self.state["character_sheets"][char_id] = srv_name
            else:
                prompt = char["character_sheet_prompt"]
                pending_prompts.append((char_id, prompt, local_path, sheet_filename))

        if not pending_prompts:
            print("   ✅ No character sheets need generation.")
            return

        # Queue all sheets
        queue_ids = []
        for char_id, prompt, local_path, sheet_filename in pending_prompts:
            print(f"   🎨 Queuing character sheet generation for {char_id}...")
            shot_for_builder = {
                "prompt": prompt,
                "references": [],
                "filename_prefix": sheet_filename.replace(".png", "")
            }
            workflow = build_dynamic_workflow(self.ideogram_template, shot_for_builder, self.global_cfg)
            res = curl_json("POST", "/prompt", self.base_url, data={"prompt": workflow, "client_id": f"sheet-{char_id}"}, auth=self.auth)
            if "prompt_id" in res:
                queue_ids.append((char_id, res["prompt_id"], local_path))
            else:
                print(f"      ❌ Failed to queue character sheet for {char_id}: {res.get('error')}")
                sys.exit(1)

        # Wait and download
        for char_id, prompt_id, local_path in queue_ids:
            print(f"   ⏳ Waiting for character sheet: {char_id}...")
            try:
                outputs = wait_for_prompt(prompt_id, self.base_url, auth=self.auth)
                # Find output image node
                for nid, out in outputs.items():
                    for item in out.get("images", []):
                        srv_filename = item["filename"]
                        download_output(srv_filename, local_path, self.base_url, auth=self.auth)
                        # Upload to sync available cache
                        srv_name = upload_image_if_needed(local_path, self.base_url, self.available_images, self.auth)
                        self.state["character_sheets"][char_id] = srv_name
                        print(f"      ✅ Saved and cached: {char_id} ({srv_name})")
                        
                        # Evaluate character sheet Quality Gate
                        if self.quality_gate_enabled:
                            print(f"      🛡️ Reviewing character sheet visual quality...")
                            char_info = self.char_lookup[char_id]
                            eval_res = evaluate_image_against_reference(
                                image_path=local_path,
                                reference_images=[],
                                character_name=char_info["display_name"],
                                character_spec=char_info["description"],
                                style_description=self.global_cfg.get("style", "3D Pixar-style"),
                                provider=self.provider_name,
                                api_key=self.api_key
                            )
                            if eval_res.get("rejected", False):
                                print(f"         ⚠️ Character sheet failed quality gate: {eval_res.get('rejection_reason')}")
                            else:
                                print(f"         ✅ Passed. Likeness: {eval_res.get('character_likeness')}/10, Style: {eval_res.get('style_match')}/10")
            except Exception as e:
                print(f"      ❌ Error waiting/downloading sheet for {char_id}: {e}")
                sys.exit(1)

    # ── Wave 1: First Frames (Depth 0) ─────────────────────────────

    def wave_1_ideogram_ffs(self):
        """Generate all chain_start/##cut FF images in one Ideogram batch."""
        print(f"\n\n{'═'*80}\n  WAVE 1: Generating Raw Scene stills (Ideogram 4 T2I)\n{'═'*80}")
        depth_0_shots = [s for s in self.all_shots if s["_depth"] == 0]
        
        pending_prompts = []
        for shot in depth_0_shots:
            prefix = shot["filename_prefix"]
            # FF still (only if ff_source is ideogram)
            if shot.get("ff_source") == "ideogram":
                ff_raw_name = f"{prefix}_ff_raw.png"
                ff_raw_path = os.path.join(self.scenes_dir, ff_raw_name)
                
                if os.path.exists(ff_raw_path) and os.path.getsize(ff_raw_path) > 1024:
                    print(f"   📷 Raw FF already exists locally: {ff_raw_name}")
                    srv_name = upload_image_if_needed(ff_raw_path, self.base_url, self.available_images, self.auth)
                    self.state["ff_images"][prefix] = srv_name
                else:
                    pending_prompts.append((prefix, "ff", shot["ff_prompt"], ff_raw_path, ff_raw_name))

            # LF still (only if lf_source is ideogram_fresh)
            if shot.get("lf_source") == "ideogram_fresh":
                lf_raw_name = f"{prefix}_lf_raw.png"
                lf_raw_path = os.path.join(self.scenes_dir, lf_raw_name)
                
                if os.path.exists(lf_raw_path) and os.path.getsize(lf_raw_path) > 1024:
                    print(f"   📷 Raw LF already exists locally: {lf_raw_name}")
                    srv_name = upload_image_if_needed(lf_raw_path, self.base_url, self.available_images, self.auth)
                    self.state["lf_images"][prefix] = srv_name
                else:
                    # Look for lf_prompt override or fall back to narrative
                    lf_prompt = shot.get("lf_prompt") or shot.get("narrative")
                    pending_prompts.append((prefix, "lf", lf_prompt, lf_raw_path, lf_raw_name))

        if not pending_prompts:
            print("   ✅ No raw frames need generation.")
            return

        # Queue all stills
        queue_ids = []
        for prefix, role, prompt, local_path, raw_name in pending_prompts:
            print(f"   🎨 Queuing raw {role.upper()} for {prefix}...")
            shot_for_builder = {
                "prompt": prompt,
                "references": [],
                "filename_prefix": raw_name.replace(".png", "")
            }
            workflow = build_dynamic_workflow(self.ideogram_template, shot_for_builder, self.global_cfg)
            res = curl_json("POST", "/prompt", self.base_url, data={"prompt": workflow, "client_id": f"{prefix}-{role}"}, auth=self.auth)
            if "prompt_id" in res:
                queue_ids.append((prefix, role, res["prompt_id"], local_path))
            else:
                print(f"      ❌ Failed to queue raw still for {prefix}: {res.get('error')}")

        # Wait and download
        for prefix, role, prompt_id, local_path in queue_ids:
            print(f"   ⏳ Waiting for raw {role.upper()}: {prefix}...")
            try:
                outputs = wait_for_prompt(prompt_id, self.base_url, auth=self.auth)
                for nid, out in outputs.items():
                    for item in out.get("images", []):
                        srv_filename = item["filename"]
                        download_output(srv_filename, local_path, self.base_url, auth=self.auth)
                        srv_name = upload_image_if_needed(local_path, self.base_url, self.available_images, self.auth)
                        
                        if role == "ff":
                            self.state["ff_images"][prefix] = srv_name
                        else:
                            self.state["lf_images"][prefix] = srv_name
                        print(f"      ✅ Saved raw {role}: {prefix} ({srv_name})")
            except Exception as e:
                print(f"      ❌ Error downloading raw still for {prefix}: {e}")

    # ── Wave 2: Flux Klein Consistency (Depth 0) ───────────────────

    def wave_2_klein_edits(self):
        """Run all Klein edits for depth 0 shots: FF edits + LF derivations."""
        print(f"\n\n{'═'*80}\n  WAVE 2: Running Flux Klein Edit Pass (Depth 0)\n{'═'*80}")
        depth_0_shots = [s for s in self.all_shots if s["_depth"] == 0]

        pending_edits = []
        for shot in depth_0_shots:
            prefix = shot["filename_prefix"]
            chars_present = shot.get("characters_present", [])
            has_characters = len(chars_present) > 0

            # 1. Edit FF (for shots where ff_source is ideogram)
            if shot.get("ff_source") == "ideogram":
                raw_ff_name = f"{prefix}_ff_raw.png"
                raw_ff_path = os.path.join(self.scenes_dir, raw_ff_name)
                edited_ff_name = f"{prefix}_ff_edited.png"
                edited_ff_path = os.path.join(self.scenes_edited_dir, edited_ff_name)

                if os.path.exists(edited_ff_path) and os.path.getsize(edited_ff_path) > 1024:
                    print(f"   📷 Edited FF already exists locally: {edited_ff_name}")
                    srv_name = upload_image_if_needed(edited_ff_path, self.base_url, self.available_images, self.auth)
                    self.state["ff_images"][prefix] = srv_name
                elif not has_characters:
                    print(f"   ⏭️  No character consistency needed for {prefix} FF — copying raw file.")
                    shutil.copy(raw_ff_path, edited_ff_path)
                    srv_name = upload_image_if_needed(edited_ff_path, self.base_url, self.available_images, self.auth)
                    self.state["ff_images"][prefix] = srv_name
                else:
                    # Composing prompt matching characters_present ordered list
                    edit_prompt = self._build_ff_edit_prompt(shot)
                    char_refs = [self.state["character_sheets"][cid] for cid in chars_present if cid in self.state["character_sheets"]]
                    pending_edits.append((prefix, "ff", self.state["ff_images"][prefix], char_refs, edit_prompt, edited_ff_path, edited_ff_name, chars_present))

            # 2. Derive LF from FF
            if shot.get("lf_source") == "klein_from_ff":
                edited_lf_name = f"{prefix}_lf_edited.png"
                edited_lf_path = os.path.join(self.scenes_edited_dir, edited_lf_name)

                if os.path.exists(edited_lf_path) and os.path.getsize(edited_lf_path) > 1024:
                    print(f"   📷 Derived LF already exists locally: {edited_lf_name}")
                    srv_name = upload_image_if_needed(edited_lf_path, self.base_url, self.available_images, self.auth)
                    self.state["lf_images"][prefix] = srv_name
                else:
                    # LF derivation takes the edited FF as input scene image
                    edit_prompt = shot["lf_edit_instruction"] + f" Keep character identity and background identical. Maintain the {self.global_cfg.get('style', '')} art style throughout."
                    lf_refs = shot.get("lf_edit_references", chars_present)
                    char_refs = [self.state["character_sheets"][cid] for cid in lf_refs if cid in self.state["character_sheets"]]
                    pending_edits.append((prefix, "lf_from_ff", prefix, char_refs, edit_prompt, edited_lf_path, edited_lf_name, lf_refs))

        if not pending_edits:
            print("   ✅ No Klein edits need processing.")
            return

        # Queue all edits
        queue_ids = []
        for prefix, role, input_scene, char_refs, edit_prompt, local_path, edited_name, chars in pending_edits:
            print(f"   🎨 Queuing Klein {role.upper()} edit for {prefix}...")
            # If lf_from_ff, we must resolve input_scene to the newly edited FF server path
            scene_srv_path = input_scene
            if role == "lf_from_ff":
                scene_srv_path = self.state["ff_images"][prefix]

            shot_for_builder = {
                "prompt": edit_prompt,
                "scene_image": scene_srv_path,
                "character_refs": char_refs,
                "filename_prefix": edited_name.replace(".png", ""),
                "_builder_mode": "flux_klein_edit_dynamic"
            }
            workflow = build_dynamic_workflow(self.flux_edit_template, shot_for_builder, self.global_cfg)
            res = curl_json("POST", "/prompt", self.base_url, data={"prompt": workflow, "client_id": f"{prefix}-{role}"}, auth=self.auth)
            if "prompt_id" in res:
                queue_ids.append((prefix, role, res["prompt_id"], local_path, char_refs, chars))
            else:
                print(f"      ❌ Failed to queue Klein edit for {prefix}: {res.get('error')}")

        # Wait and download
        for prefix, role, prompt_id, local_path, char_refs, chars in queue_ids:
            print(f"   ⏳ Waiting for Klein {role.upper()} edit: {prefix}...")
            try:
                outputs = wait_for_prompt(prompt_id, self.base_url, auth=self.auth)
                for nid, out in outputs.items():
                    for item in out.get("images", []):
                        srv_filename = item["filename"]
                        download_output(srv_filename, local_path, self.base_url, auth=self.auth)
                        srv_name = upload_image_if_needed(local_path, self.base_url, self.available_images, self.auth)
                        
                        if role == "ff":
                            self.state["ff_images"][prefix] = srv_name
                        else:
                            self.state["lf_images"][prefix] = srv_name
                        print(f"      ✅ Saved edited still: {prefix} ({srv_name})")

                        # Run Quality Gate review
                        if self.quality_gate_enabled:
                            print(f"      🛡️ Reviewing edited character consistency likeness/neutrality...")
                            ref_paths = [os.path.join(self.references_dir, f"{cid}_character_sheet.png") for cid in chars]
                            eval_res = evaluate_image_against_reference(
                                image_path=local_path,
                                reference_images=[p for p in ref_paths if os.path.exists(p)],
                                character_name=", ".join(chars),
                                character_spec="; ".join(self.char_lookup[cid]["description"] for cid in chars if cid in self.char_lookup),
                                style_description=self.global_cfg.get("style", "3D Pixar-style"),
                                provider=self.provider_name,
                                api_key=self.api_key
                            )
                            if eval_res.get("rejected", False):
                                print(f"         ⚠️ Edited still failed quality gate: {eval_res.get('rejection_reason')}")
                            else:
                                print(f"         ✅ Passed. Likeness: {eval_res.get('character_likeness')}/10, Style: {eval_res.get('style_match')}/10")
            except Exception as e:
                print(f"      ❌ Error waiting/downloading Klein edit: {e}")

    def _build_ff_edit_prompt(self, shot):
        """Build concatenated FF edit instructions for characters present."""
        instructions = []
        for i, cid in enumerate(shot.get("characters_present", []), start=1):
            if shot.get("ff_edit_instructions") and cid in shot["ff_edit_instructions"]:
                instructions.append(shot["ff_edit_instructions"][cid])
            else:
                char = self.char_lookup.get(cid)
                if char:
                    desc = char.get("edit_prompt_descriptor", cid)
                    instructions.append(
                        f"Replace the {desc} in the scene with the character from reference image {i} exactly — "
                        f"same face, body, clothing, and proportions."
                    )
        
        preservation = (
            "Keep the background, lighting, composition, and overall scene identical. "
            f"Maintain the {self.global_cfg.get('style', '')} art style throughout."
        )
        return " ".join(instructions) + " " + preservation

    # ── Wave 3: FFLF Video (Depth 0) ───────────────────────────────

    def wave_3_fflf_batch_1(self):
        """Run FFLF video generation for depth 0 shots, then extract tail frames."""
        print(f"\n\n{'═'*80}\n  WAVE 3: Executing LTX FFLF Video Gen (Depth 0)\n{'═'*80}")
        depth_0_shots = [s for s in self.all_shots if s["_depth"] == 0]

        for shot in depth_0_shots:
            prefix = shot["filename_prefix"]
            
            # Skip if we only targeted a specific shot
            if self.args.shot and prefix != self.args.shot:
                continue

            # Skip existing videos if requested
            if self.args.skip_existing:
                existing = sorted(
                    f for f in os.listdir(self.videos_dir)
                    if f.startswith(prefix) and f.endswith(('.mp4', '.webm', '.gif'))
                    and os.path.getsize(os.path.join(self.videos_dir, f)) > 1024 * 100
                )
                if existing:
                    existing_path = os.path.join(self.videos_dir, existing[-1])
                    print(f"   ⏭️ Skipping video gen for {prefix} (exists: {existing[-1]})")
                    self.state["videos"][prefix] = existing_path
                    self._extract_and_cache_tail(existing_path, shot, prefix)
                    continue

            # Run FFLF execution
            shot_data_for_fflf = copy.deepcopy(shot)
            shot_data_for_fflf["first_frame_image"] = f"{prefix}_ff_edited.png"
            shot_data_for_fflf["last_frame_image"] = f"{prefix}_lf_edited.png"

            print(f"\n   🎥 Running FFLF video generation for {prefix}...")
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

            if video_path:
                self.state["videos"][prefix] = video_path
                self._extract_and_cache_tail(video_path, shot, prefix)
            else:
                print(f"   ❌ FFLF video generation failed for {prefix}.")

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
                print(f"   🎞️ Extracted and uploaded tail frame to ComfyUI: {srv_name}")
        except Exception as e:
            print(f"   ⚠️ Tail frame extraction error for {prefix}: {e}")

    # ── Wave N: Continuation Waves (Depth >= 1) ─────────────────────

    def wave_n_klein_continuation(self, depth):
        """Generate LFs for continuation shots at a specific depth using predecessor tail frames."""
        print(f"   🎨 WAVE {4 + (depth-1)*2}: Generating Continuation LFs (Depth {depth})")
        depth_shots = [s for s in self.all_shots if s["_depth"] == depth]

        pending_edits = []
        for shot in depth_shots:
            prefix = shot["filename_prefix"]
            pred_prefix = shot["continues_from"]
            chars_present = shot.get("characters_present", [])

            # First frame of this shot is the predecessor's tail frame
            pred_tail_srv = self.state["tail_frames"].get(pred_prefix)
            if not pred_tail_srv:
                print(f"      ⚠️ Predecessor tail frame not found for {prefix} — skipping LF derivation.")
                continue

            edited_lf_name = f"{prefix}_lf_edited.png"
            edited_lf_path = os.path.join(self.scenes_edited_dir, edited_lf_name)

            if os.path.exists(edited_lf_path) and os.path.getsize(edited_lf_path) > 1024:
                print(f"      📷 Continuation LF already exists locally: {edited_lf_name}")
                srv_name = upload_image_if_needed(edited_lf_path, self.base_url, self.available_images, self.auth)
                self.state["lf_images"][prefix] = srv_name
            else:
                edit_prompt = shot["lf_edit_instruction"] + f" Keep character identity and background identical. Maintain the {self.global_cfg.get('style', '')} art style throughout."
                lf_refs = shot.get("lf_edit_references", chars_present)
                char_refs = [self.state["character_sheets"][cid] for cid in lf_refs if cid in self.state["character_sheets"]]
                pending_edits.append((prefix, pred_tail_srv, char_refs, edit_prompt, edited_lf_path, edited_lf_name, lf_refs))

        if not pending_edits:
            return

        # Queue
        queue_ids = []
        for prefix, pred_tail_srv, char_refs, edit_prompt, local_path, edited_name, chars in pending_edits:
            print(f"      🎨 Queuing Klein LF edit for {prefix} from tail...")
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
                queue_ids.append((prefix, res["prompt_id"], local_path, chars))
            else:
                print(f"         ❌ Failed to queue Klein edit for {prefix}: {res.get('error')}")

        # Wait and download
        for prefix, prompt_id, local_path, chars in queue_ids:
            print(f"      ⏳ Waiting for Klein LF: {prefix}...")
            try:
                outputs = wait_for_prompt(prompt_id, self.base_url, auth=self.auth)
                for nid, out in outputs.items():
                    for item in out.get("images", []):
                        srv_filename = item["filename"]
                        download_output(srv_filename, local_path, self.base_url, auth=self.auth)
                        srv_name = upload_image_if_needed(local_path, self.base_url, self.available_images, self.auth)
                        self.state["lf_images"][prefix] = srv_name
                        print(f"         ✅ Saved continuation LF: {prefix} ({srv_name})")

                        # Run Quality Gate review
                        if self.quality_gate_enabled:
                            print(f"         🛡️ Reviewing edited character consistency likeness/neutrality...")
                            ref_paths = [os.path.join(self.references_dir, f"{cid}_character_sheet.png") for cid in chars]
                            eval_res = evaluate_image_against_reference(
                                image_path=local_path,
                                reference_images=[p for p in ref_paths if os.path.exists(p)],
                                character_name=", ".join(chars),
                                character_spec="; ".join(self.char_lookup[cid]["description"] for cid in chars if cid in self.char_lookup),
                                style_description=self.global_cfg.get("style", "3D Pixar-style"),
                                provider=self.provider_name,
                                api_key=self.api_key
                            )
                            if eval_res.get("rejected", False):
                                print(f"            ⚠️ Continuation LF failed quality gate: {eval_res.get('rejection_reason')}")
                            else:
                                print(f"            ✅ Passed. Likeness: {eval_res.get('character_likeness')}/10, Style: {eval_res.get('style_match')}/10")
            except Exception as e:
                print(f"         ❌ Error waiting/downloading Klein LF edit: {e}")

    def wave_n_fflf_continuation(self, depth):
        """Run FFLF video generation for continuation shots at a specific depth, then extract tail frames."""
        print(f"   🎥 WAVE {5 + (depth-1)*2}: Executing LTX FFLF Video Gen (Depth {depth})")
        depth_shots = [s for s in self.all_shots if s["_depth"] == depth]

        for shot in depth_shots:
            prefix = shot["filename_prefix"]
            pred_prefix = shot["continues_from"]

            # Skip if we targeted a single shot
            if self.args.shot and prefix != self.args.shot:
                continue

            # Skip existing
            if self.args.skip_existing:
                existing = sorted(
                    f for f in os.listdir(self.videos_dir)
                    if f.startswith(prefix) and f.endswith(('.mp4', '.webm', '.gif'))
                    and os.path.getsize(os.path.join(self.videos_dir, f)) > 1024 * 100
                )
                if existing:
                    existing_path = os.path.join(self.videos_dir, existing[-1])
                    print(f"      Skip video gen for {prefix}")
                    self.state["videos"][prefix] = existing_path
                    self._extract_and_cache_tail(existing_path, shot, prefix)
                    continue

            # FF image is the local filename of the predecessor's tail frame
            pred_tail_local_name = f"{pred_prefix}_tail_frame.png"
            
            shot_data_for_fflf = copy.deepcopy(shot)
            shot_data_for_fflf["first_frame_image"] = pred_tail_local_name
            shot_data_for_fflf["last_frame_image"] = f"{prefix}_lf_edited.png"

            print(f"\n      🎥 Running FFLF video generation for {prefix}...")
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

            if video_path:
                self.state["videos"][prefix] = video_path
                self._extract_and_cache_tail(video_path, shot, prefix)
            else:
                print(f"      ❌ FFLF video generation failed for {prefix}.")

    # ── Stitch Metadata generation ─────────────────────────────────

    def generate_stitch_metadata(self):
        """Generate a JSON manifest file listing all generated videos in order."""
        stitch_list = []
        for shot in self.all_shots:
            prefix = shot["filename_prefix"]
            video_path = self.state["videos"].get(prefix)
            if video_path and os.path.exists(video_path):
                stitch_list.append({
                    "shot_id": prefix,
                    "local_path": os.path.abspath(video_path),
                    "filename": os.path.basename(video_path)
                })
        
        output_path = os.path.join(self.output_dir, "stitch_list.json")
        with open(output_path, "w") as f:
            json.dump(stitch_list, f, indent=2)
            
        print(f"\n🎬 Stitch metadata saved successfully to: {output_path}")
        print(f"   Order of files to stitch: {', '.join(x['shot_id'] for x in stitch_list)}")


def main():
    parser = argparse.ArgumentParser(
        description="Story-to-Video-Cinematic: Batch-Wave Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--prompts", default="cinematic_prompt.json",
                        help="Path to cinematic_prompt.json (default: cinematic_prompt.json)")
    parser.add_argument("--url", default=os.environ.get("COMFYUI_URL", DEFAULT_BASE_URL),
                        help=f"ComfyUI base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--output-dir", default=None,
                        help="Output directory (defaults to sibling directory of --prompts)")
    parser.add_argument("--shot", type=str, default=None,
                        help="Process only a specific shot (matches filename_prefix)")
    parser.add_argument("--fast", action="store_true",
                        help="Skip LTX seed hunting, use Stage 2+3 directly")
    parser.add_argument("--interactive", action="store_true",
                        help="Prompt user in terminal to select Stage 1 preview index")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip shots whose videos already exist in videos/")
    parser.add_argument("--dry-run", action="store_true",
                        help="Resolve chains and print execution plan without generating anything")
    parser.add_argument("--auth", type=str, default=None,
                        help="ComfyUI Basic Auth in username:password format")
    parser.add_argument("--api-key", default=os.environ.get("GEMINI_API_KEY", ""),
                        help="API key for motion evaluation / quality gates")
    parser.add_argument("--provider", choices=["openrouter", "gemini"], default=None,
                        help="Vision provider for quality gates")
    parser.add_argument("--references-dir", type=str, default=None,
                        help="Character reference sheets folder")

    args = parser.parse_args()
    base_url = args.url

    # Resolve output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = os.path.dirname(os.path.abspath(args.prompts))

    # Parse auth credentials
    comfyui_auth = None
    if args.auth:
        parts = args.auth.split(":", 1)
        if len(parts) == 2:
            comfyui_auth = (parts[0], parts[1])
        else:
            print("❌ Invalid auth format. Use username:password")
            sys.exit(1)

    # Load prompts
    if not os.path.exists(args.prompts):
        print(f"❌ Cinematic prompts file not found: {args.prompts}")
        sys.exit(1)

    with open(args.prompts) as f:
        prompts_data = json.load(f)

    # Validate version is V3
    version = prompts_data.get("version", "")
    if version != "3.0":
        print(f"❌ Error: This orchestrator requires schema version '3.0' (found '{version}').")
        sys.exit(1)

    # Instantiate and execute orchestrator
    orchestrator = BatchWaveOrchestrator(
        prompts_data=prompts_data,
        base_url=base_url,
        comfyui_auth=comfyui_auth,
        output_dir=output_dir,
        args=args
    )

    if args.dry_run:
        orchestrator.print_plan()
        print("\n✅ Dry-run complete — no queue operations executed.")
        return

    orchestrator.execute()


if __name__ == "__main__":
    main()
