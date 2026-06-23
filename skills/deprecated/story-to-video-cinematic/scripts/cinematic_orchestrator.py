#!/usr/bin/env python3
"""
Story-to-Video-Cinematic: Batch-Wave Cinematic Orchestrator V3
============================================================
Orchestrates the 3-stage model pipeline using the batch-wave execution model:
  1. Ideogram 4 T2I -> Character sheets + raw scene stills (Wave 0 + Wave 1)
  2. Flux Klein 9B Edit -> Character consistency refinement (Wave 2a, Wave 2b, etc.)
  3. LTX 2.3 FFLF -> Consistent video generation (Wave 3, Wave 5, etc.)

Supports modular execution, dual-output logging, pipeline status tracker,
quality gates (Image & Video) via Gemini/OpenRouter, and dynamic character cloning.
"""

import argparse
import json
import os
import shlex
import shutil
import sys
import time
import copy
import datetime
import subprocess

script_dir = os.path.dirname(os.path.abspath(__file__))
# Load environment variables from workspace root .env
env_path = os.path.abspath(os.path.join(script_dir, "..", "..", "..", ".env"))
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

# Import ComfyUI and filmmaking helper modules
from comfyui_api import (
    get_available_images,
    DEFAULT_BASE_URL,
)
from workflow_builder import load_workflow_template
from gemini_eval import resolve_provider

# Import V3 modular dependencies
from wave_executors import WaveExecutorMixin
from pipeline_logger import PipelineLogger


class BatchWaveOrchestrator(WaveExecutorMixin):
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
        self.story_name = os.path.basename(os.path.abspath(output_dir))
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
        self.ltx_fflf_template = load_workflow_template("ltx-23-fflf-seed-hunter", templates_dir=cinematic_templates_dir)

        # ── Initialize logger ──
        run_id = f"run_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        waves_plan = self._build_waves_plan()
        self.logger = PipelineLogger(
            output_dir=self.output_dir,
            run_id=run_id,
            total_shots=len(self.all_shots),
            total_characters=len(self.characters),
            waves_plan=waves_plan
        )

        # Quality gates setup
        self.quality_gate_enabled = self.global_cfg.get("quality_gate", {}).get("enabled", False)
        self.provider_name = None
        self.api_key = None
        if self.quality_gate_enabled:
            try:
                self.provider_name = self.global_cfg.get("quality_gate", {}).get("provider") or args.provider
                self.provider_name, self.api_key, _ = resolve_provider(self.provider_name)
                self.logger.log(f"🛡️ Quality Gate enabled using provider: {self.provider_name}")
            except Exception as e:
                self.logger.log(f"⚠️ Could not initialize Quality Gate provider: {e}. Disabling quality gates.", "WARN")
                self.quality_gate_enabled = False

        # ComfyUI available files discovery
        try:
            self.available_images = get_available_images(self.base_url, auth=self.auth)
            self.logger.log(f"📷 Found {len(self.available_images)} files in ComfyUI input directory")
        except Exception as e:
            self.logger.log(f"⚠️ Could not fetch ComfyUI input directory files: {e}", "WARN")
            self.available_images = set()

    def _build_waves_plan(self):
        """Constructs waves plan dictionary mapping wave names to list of expected item IDs."""
        waves_plan = {
            "wave_0_character_sheets": [char["id"] for char in self.characters],
            "wave_1_ideogram_ffs": [],
            "wave_2a_klein_ff_edits": [],
            "wave_2b_klein_lf_derivations": [],
            "wave_3_fflf_batch": [],
        }
        
        depth_0_shots = [s for s in self.all_shots if s["_depth"] == 0]
        for shot in depth_0_shots:
            prefix = shot["filename_prefix"]
            if shot.get("ff_source") == "ideogram":
                waves_plan["wave_1_ideogram_ffs"].append(f"{prefix}_ff_raw")
            if shot.get("lf_source") == "ideogram_fresh":
                waves_plan["wave_1_ideogram_ffs"].append(f"{prefix}_lf_raw")
            
            if shot.get("ff_source") == "ideogram":
                waves_plan["wave_2a_klein_ff_edits"].append(f"{prefix}_ff_edit")
                
            if shot.get("lf_source") == "klein_from_ff":
                waves_plan["wave_2b_klein_lf_derivations"].append(f"{prefix}_lf_derivation")
                
            waves_plan["wave_3_fflf_batch"].append(f"{prefix}_video")
            
        depth = 1
        while self._has_pending_depth(depth):
            depth_shots = [s for s in self.all_shots if s["_depth"] == depth]
            klein_items = []
            fflf_items = []
            for shot in depth_shots:
                prefix = shot["filename_prefix"]
                klein_items.append(f"{prefix}_lf_continuation")
                fflf_items.append(f"{prefix}_video")
                
            waves_plan[f"wave_N_continuations_depth_{depth}_klein"] = klein_items
            waves_plan[f"wave_N_continuations_depth_{depth}_fflf"] = fflf_items
            depth += 1
            
        waves_plan["wave_final_video_eval"] = ["final_stitched_video"]
        return waves_plan

    def _flatten_shots(self):
        """Flatten director_plan.scenes[].shots[] into a flat list with scene context."""
        shots = []
        for scene in self.director_plan.get("scenes", []):
            for shot in scene.get("shots", []):
                shot_copy = copy.deepcopy(shot)
                shot_copy["scene"] = scene["scene_id"]
                shot_copy["shot"] = shot["shot_id"]
                shot_copy["_scene_id"] = scene["scene_id"]
                shot_copy["_scene_title"] = scene.get("scene_title", "")
                shot_copy["filename_prefix"] = f"{self.story_name}_s{scene['scene_id']:02d}_sh{shot['shot_id']:02d}"
                
                cont_from = shot_copy.get("continues_from")
                if cont_from:
                    if not cont_from.startswith(f"{self.story_name}_"):
                        shot_copy["continues_from"] = f"{self.story_name}_{cont_from}"
                        
                shots.append(shot_copy)
        return shots

    def _assign_depths(self):
        """Assign visual depth to each shot to schedule continuation waves."""
        prefix_to_shot = {shot["filename_prefix"]: shot for shot in self.all_shots}
        for shot in self.all_shots:
            depth = 0
            curr = shot
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
        self.logger.log(f"\n📋 Batch-Wave Plan (Total: {len(self.all_shots)} shot(s))")
        self.logger.log("=" * 80)
        self.logger.log("  Characters Registry:")
        for char in self.characters:
            self.logger.log(f"    - {char['id']}: {char['display_name']} (descriptor: {char['edit_prompt_descriptor']})")
        
        self.logger.log("\n  Wave Execution Visual Depths:")
        depth_map = {}
        for shot in self.all_shots:
            d = shot["_depth"]
            depth_map.setdefault(d, []).append(shot["filename_prefix"])
        for d, prefixes in sorted(depth_map.items()):
            self.logger.log(f"    Depth {d} shots: {', '.join(prefixes)}")
        self.logger.log("=" * 80)

    def execute(self):
        """Orchestrate the batch-wave pipeline execution."""
        self.print_plan()

        try:
            # Wave 0: Generate all character sheets in batch
            self.wave_0_character_sheets()

            # Wave 1: Generate all raw FFs for depth 0 shots
            self.wave_1_ideogram_ffs()

            # Wave 2a/2b: Klein FF edits + LF derivations (depth 0)
            self.wave_2a_klein_ff_edits()
            self.wave_2b_klein_lf_derivations()

            # Wave 3: FFLF Video Gen (depth 0) + Tail Frame Extraction
            self.wave_3_fflf_batch_1()

            # Continuation Waves (Depth 1, 2, ...)
            depth = 1
            while self._has_pending_depth(depth):
                self.logger.log(f"\n\n{'═'*80}\n  WAVES {4 + (depth-1)*2} & {5 + (depth-1)*2}: Continuation Depth {depth}\n{'═'*80}")
                self.wave_n_klein_continuation(depth)
                self.wave_n_fflf_continuation(depth)
                depth += 1

            self.generate_stitch_metadata()

            # Gate 5: Final Video Evaluation
            gate_enabled = self.global_cfg.get("quality_gate", {}).get("gates", {}).get("final_video", True)
            stitched_video_path = self.state.get("stitched_video")
            if self.quality_gate_enabled and gate_enabled and stitched_video_path and os.path.exists(stitched_video_path):
                self.logger.update_wave("wave_final_video_eval", "in_progress")
                self.logger.log("════════════════════════════════════════", "INFO")
                self.logger.log("  WAVE 8: Evaluating Stitched Final Video (Gate 5)", "INFO")
                self.logger.log("════════════════════════════════════════", "INFO")

                story_summary = self.director_plan.get("story_summary", "")
                char_list = [c["display_name"] for c in self.characters]
                self.logger.update_item("wave_final_video_eval", "final_stitched_video", "running")

                try:
                    from quality_gates import evaluate_final_video
                    eval_res = evaluate_final_video(
                        video_path=stitched_video_path,
                        story_summary=story_summary,
                        characters_list=char_list,
                        provider=self.provider_name,
                        api_key=self.api_key,
                        model=self.global_cfg.get("quality_gate", {}).get("model_video")
                    )
                    if eval_res.get("rejected", False) or not eval_res.get("passed", True):
                        self.logger.log(f"      ⚠️ Final video failed quality gate! Issues: {eval_res.get('issues', [])}", "WARN")
                    else:
                        self.logger.log(f"      ✅ Final video passed quality gate! Score: {eval_res.get('overall') or eval_res.get('overall_score') or 0}/10", "INFO")

                    score = eval_res.get("overall") or eval_res.get("overall_score") or 0
                    self.logger.update_item("wave_final_video_eval", "final_stitched_video", "completed", output=os.path.basename(stitched_video_path), eval_score=score, eval_result=eval_res)
                except Exception as e:
                    err_msg = str(e)
                    self.logger.log(f"      ❌ Final video evaluation error: {err_msg}", "ERROR")
                    self.logger.update_item("wave_final_video_eval", "final_stitched_video", "failed", error=err_msg)

                self.logger.update_wave("wave_final_video_eval", "completed")

        except RuntimeError as e:
            self.logger.log(f"\n❌ Pipeline aborted due to critical error: {e}", "ERROR")
            raise
        finally:
            self.logger.close()


    def _has_pending_depth(self, depth):
        """Check if any shot is registered at this continuation depth."""
        return any(shot["_depth"] == depth for shot in self.all_shots)

    def generate_stitch_metadata(self):
        """Generate a JSON manifest file listing all generated videos in order,
        and stitch them using ffmpeg programmatically if crossfade is possible."""
        stitch_list = []
        video_paths = []
        for shot in self.all_shots:
            prefix = shot["filename_prefix"]
            video_path = self.state["videos"].get(prefix)
            if video_path and os.path.exists(video_path):
                stitch_list.append({
                    "shot_id": prefix,
                    "local_path": os.path.abspath(video_path),
                    "filename": os.path.basename(video_path)
                })
                video_paths.append(video_path)
        
        output_path = os.path.join(self.output_dir, "stitch_list.json")
        with open(output_path, "w") as f:
            json.dump(stitch_list, f, indent=2)
            
        self.logger.log(f"\n🎬 Stitch metadata saved successfully to: {output_path}", "INFO")
        self.logger.log(f"   Order of files to stitch: {', '.join(x['shot_id'] for x in stitch_list)}", "INFO")

        # Programmatic crossfade stitching using continuation_pipeline script function
        if len(video_paths) > 0:
            self.logger.log("🔗 Stitching videos together using ffmpeg...", "INFO")
            try:
                from continuation_pipeline import generate_stitch_metadata as pipeline_stitch
                overlap_seconds = self.global_cfg.get("overlap_seconds", 1.0)
                fps = self.global_cfg.get("fps", 25)
                
                output_metadata_path = os.path.join(self.output_dir, "stitch_metadata.json")
                meta = pipeline_stitch(
                    video_files=video_paths,
                    overlap_seconds=overlap_seconds,
                    fps=fps,
                    output_json_path=output_metadata_path
                )
                
                stitched_video_path = os.path.join(self.output_dir, "final_stitched_video.mp4")
                cmd_str = meta.get("ffmpeg_xfade_command") or meta.get("ffmpeg_trim_concat_command")
                if cmd_str:
                    cmd_str = cmd_str.replace("stitched_xfade_output.mp4", f'"{stitched_video_path}"')
                    cmd_str = cmd_str.replace("stitched_output.mp4", f'"{stitched_video_path}"')
                    
                    self.logger.log(f"Running ffmpeg stitch command: {cmd_str}", "INFO")
                    try:
                        cmd_tokens = shlex.split(cmd_str)
                    except ValueError:
                        cmd_tokens = cmd_str.split()
                    res = subprocess.run(cmd_tokens, capture_output=True, text=True)
                    if res.returncode == 0 and os.path.exists(stitched_video_path):
                        self.logger.log(f"🎉 Successfully stitched video saved to: {stitched_video_path}", "INFO")
                        self.state["stitched_video"] = stitched_video_path
                    else:
                        self.logger.log(f"⚠️ ffmpeg stitch command returned {res.returncode}. error: {res.stderr}", "WARN")
            except Exception as e:
                self.logger.log(f"⚠️ Failed to programmatically stitch videos: {e}", "WARN")


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
    parser.add_argument("--random-seed", action="store_true",
                        help="Use a random seed base on each run to avoid cached generations")

    args = parser.parse_args()
    base_url = args.url

    # Resolve output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = os.path.dirname(os.path.abspath(args.prompts))

    # Parse auth credentials
    comfyui_auth = None
    auth_source = args.auth or os.environ.get("COMFYUI_AUTH", None)
    if auth_source:
        if ":" in auth_source:
            parts = auth_source.split(":", 1)
            comfyui_auth = (parts[0], parts[1])
        else:
            comfyui_auth = auth_source

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

    if args.random_seed:
        import random
        new_seed = random.randint(1, 10000000)
        if "global" not in prompts_data:
            prompts_data["global"] = {}
        prompts_data["global"]["seed_base"] = new_seed
        print(f"🎲 Random seed base activated: {new_seed}")

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
