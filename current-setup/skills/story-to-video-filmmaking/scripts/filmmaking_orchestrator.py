#!/usr/bin/env python3
"""
Story-to-Video-Filmmaking: Recursive Filmmaking Orchestrator
============================================================
Replaces the old linear Phase 2 → Phase 3 → Phase 4 flow with a recursive
per-chain loop that interleaves image generation, video generation, and tail
frame extraction in the order the story demands.

Architecture:
  The pipeline groups shots into:
  - Independent shots and chain_start shots: image gen (FF+LF) happens first
  - Continuation chains: processed shot-by-shot sequentially:
      Gen LF (anchored to tail) → FFLF video → Extract tail → next shot

  Cross-scene chains and independent shots can be processed in parallel
  (on multi-GPU setups), but this implementation processes them sequentially
  for single-GPU Vast.ai deployments.

Recursive Loop (per continuation chain):
  Shot N (chain_start):
    1. Generate FF  [Flux, char refs]
    2. Generate LF  [Flux, FF as anchor + lf_refs]
    3. FFLF video gen (Stage 1 seed hunt → Stage 2 → Stage 3)
    4. Extract tail frame (ffmpeg, at overlap_seconds from end)
  Shot N+1 (continuation):
    1. FF = tail frame from Shot N
    2. Generate LF  [Flux, tail frame as anchor + lf_refs]
    3. FFLF video gen
    4. Extract tail frame
  ...repeat until chain ends

Usage:
    # Full pipeline — all shots
    python3 filmmaking_orchestrator.py --prompts filmmaking_prompt.json

    # Fast mode (skip seed hunt, direct Stage 2+3)
    python3 filmmaking_orchestrator.py --prompts filmmaking_prompt.json --fast

    # Interactive seed selection
    python3 filmmaking_orchestrator.py --prompts filmmaking_prompt.json --interactive

    # Process a single shot (useful for re-running failed shots)
    python3 filmmaking_orchestrator.py --prompts filmmaking_prompt.json --shot film_001_shot002

    # Dry-run (prints plan without generating anything)
    python3 filmmaking_orchestrator.py --prompts filmmaking_prompt.json --dry-run

    # Skip already-rendered shots
    python3 filmmaking_orchestrator.py --prompts filmmaking_prompt.json --skip-existing
"""
import argparse
import json
import os
import sys
import copy
import time

from comfyui_api import (
    curl_json,
    wait_for_prompt,
    download_output,
    get_available_images,
    upload_image,
    DEFAULT_BASE_URL,
)
from workflow_builder import build_dynamic_workflow, load_workflow_template
from filmmaking_utils import load_filmmaking_prompts, upload_image_if_needed
from continuation_pipeline import extract_continuation_frame
from generate_frames import generate_frames_for_shot
from fflf_executor import execute_fflf_shot

DEFAULT_FILMMAKING_OUTPUT_DIR = "/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video-filmmaking"


# ── Chain Topology Resolver ────────────────────────────────────

def resolve_chains(shots):
    """Group shots into chains and identify independent shots.

    Returns:
        chains: list of chains, each chain is a list of shots in order
        A chain is a list starting with chain_start/independent followed by
        its continuation shots.
    """
    # Build a lookup by filename_prefix
    shot_by_prefix = {s["filename_prefix"]: s for s in shots}

    # Determine which shots are continuation/bridge (i.e., have a predecessor)
    has_predecessor = set()
    for shot in shots:
        if shot.get("continues_from"):
            has_predecessor.add(shot["filename_prefix"])

    # Root shots: chain_start or independent (no predecessor within this run)
    root_shots = [s for s in shots if s["filename_prefix"] not in has_predecessor]

    # Build chains by following continues_from links
    chains = []
    for root in root_shots:
        chain = [root]
        # Find shots that continue from the last shot in this chain
        while True:
            last_prefix = chain[-1]["filename_prefix"]
            next_shots = [s for s in shots if s.get("continues_from") == last_prefix]
            if not next_shots:
                break
            if len(next_shots) > 1:
                print(f"   ⚠️  Multiple shots continue from '{last_prefix}' — using the first one: {next_shots[0]['filename_prefix']}")
            chain.append(next_shots[0])
        chains.append(chain)

    return chains


def print_execution_plan(chains, mode):
    """Print a human-readable execution plan."""
    total_shots = sum(len(c) for c in chains)
    total_chains = len(chains)
    print(f"\n📋 Execution Plan ({total_chains} chain(s), {total_shots} shot(s) total, mode={mode.upper()})")
    print("=" * 70)
    for chain_idx, chain in enumerate(chains):
        root = chain[0]
        root_type = root["shot_type"]
        print(f"\n  Chain {chain_idx + 1}: [{root['filename_prefix']}] (root type={root_type})")
        for shot_idx, shot in enumerate(chain):
            prefix = shot["filename_prefix"]
            shot_type = shot["shot_type"]
            lf_refs = shot.get("lf_references", [])
            note = shot.get("lf_reference_note", "")

            ff_src = "generate" if shot_type in ("chain_start", "independent") else "tail←prev_video"
            anchor_src = "FF image" if shot_type in ("chain_start", "independent") else "tail frame"

            print(f"    [{shot_idx + 1}] {prefix} (type={shot_type})")
            print(f"         FF: {ff_src}")
            print(f"         LF: generate — anchor={anchor_src}, lf_refs={lf_refs}")
            if note:
                print(f"         📝 {note}")
            print(f"         🎬 FFLF video → Extract tail frame")
    print("=" * 70)


# ── Per-Chain Recursive Processor ─────────────────────────────

def process_chain(chain, global_cfg, image_template, video_template,
                  base_url, output_dir, scenes_dir, videos_dir, motion_eval_dir,
                  references_base_dir, available_images, mode, auth,
                  skip_existing, evaluate, api_key, provider,
                  quality_gate=False, quality_gate_min_score=7.0,
                  quality_gate_max_retries=1):
    """Process a full continuation chain recursively.

    Returns:
        dict: {prefix -> {"path": video_path, "tail_frame": tail_path, "skipped": bool}}
    """
    results = {}
    tail_frame_path = None  # Tracks the tail frame from the previous shot's video

    for shot_idx, shot in enumerate(chain):
        prefix = shot["filename_prefix"]
        shot_type = shot["shot_type"]

        print(f"\n{'─'*60}")
        print(f"  🎬 Processing shot [{shot_idx+1}/{len(chain)}]: {prefix} (type={shot_type})")
        print(f"{'─'*60}")

        # ── Skip check ──────────────────────────────────────────
        if skip_existing:
            existing = sorted(
                f for f in os.listdir(videos_dir)
                if f.startswith(prefix) and f.endswith(('.mp4', '.webm', '.gif'))
                and os.path.getsize(os.path.join(videos_dir, f)) > 1024 * 100  # >100KB
            )
            if existing:
                existing_path = os.path.join(videos_dir, existing[-1])
                print(f"  ⏭️  Skipping {prefix} ({existing[-1]} exists, {os.path.getsize(existing_path)/1024/1024:.1f}MB)")
                # Still need to extract tail for next continuation shot
                tail_frame_path = _extract_tail(existing_path, shot, global_cfg, scenes_dir, prefix)
                results[prefix] = {"path": existing_path, "tail_frame": tail_frame_path, "skipped": True}
                continue

        # ── Step 1: Image Generation ─────────────────────────────
        # For continuation/bridge shots, pass the actual tail frame as the structural anchor
        structural_anchor = None
        if shot_type in ("continuation", "bridge"):
            if tail_frame_path and os.path.exists(tail_frame_path):
                structural_anchor = tail_frame_path
                # Also set this as the first_frame_image so the FFLF executor can upload it
                shot = copy.deepcopy(shot)
                shot["first_frame_image"] = os.path.basename(tail_frame_path)
                print(f"  🔗 Using tail frame as FF: {os.path.basename(tail_frame_path)}")
            else:
                print(f"  ⚠️  No tail frame available for {prefix}. LF will generate without structural anchor.")

        print(f"\n  📸 Phase 2 — Generating still images...")
        if quality_gate:
            print(f"   🔍 Per-image quality gate ENABLED (min_score={quality_gate_min_score}, max_retries={quality_gate_max_retries})")

        frame_result = generate_frames_for_shot(
            shot_data=shot,
            global_cfg=global_cfg,
            workflow_template=image_template,
            base_url=base_url,
            scenes_dir=scenes_dir,
            references_base_dir=references_base_dir,
            available_images=available_images,
            api_key=api_key,
            provider=provider,
            evaluate=evaluate,
            auth=auth,
            structural_anchor_path=structural_anchor,
            quality_gate=quality_gate,
            quality_gate_min_score=quality_gate_min_score,
            quality_gate_max_retries=quality_gate_max_retries,
        )

        if evaluate and (frame_result["first_frame_path"] or frame_result["last_frame_path"]):
            feedback_dir = os.path.join(output_dir, "feedback")
            os.makedirs(feedback_dir, exist_ok=True)
            feedback_path = os.path.join(feedback_dir, f"{prefix}_still_eval.json")
            with open(feedback_path, "w") as f:
                json.dump(frame_result["evaluations"], f, indent=2)
            print(f"  📄 Still eval saved: {feedback_path}")

        # Check LF was generated (required to proceed)
        if not frame_result["last_frame_path"]:
            print(f"  ❌ LF generation failed for {prefix}. Aborting this chain at this shot.")
            results[prefix] = None
            break  # Stop chain — can't continue without LF

        # ── Step 2: FFLF Video Generation ───────────────────────
        print(f"\n  🎥 Phase 3 — FFLF video generation...")
        video_path = execute_fflf_shot(
            shot_data=shot,
            global_cfg=global_cfg,
            workflow_template=video_template,
            base_url=base_url,
            videos_dir=videos_dir,
            scenes_dir=scenes_dir,
            motion_eval_dir=motion_eval_dir,
            available_images=available_images,
            mode=mode,
            auth=auth
        )

        if not video_path:
            print(f"  ❌ Video generation failed for {prefix}. Aborting chain at this shot.")
            results[prefix] = None
            break

        # ── Step 3: Extract Tail Frame (for next shot in chain) ──
        tail_frame_path = None
        if shot_idx < len(chain) - 1:
            # There's a next shot — extract tail frame now
            print(f"\n  🎞️  Phase 4 — Extracting tail frame for next shot...")
            tail_frame_path = _extract_tail(video_path, shot, global_cfg, scenes_dir, prefix)
            if tail_frame_path:
                print(f"  ✅ Tail frame ready: {os.path.basename(tail_frame_path)}")
            else:
                print(f"  ⚠️  Tail frame extraction failed. Next continuation shot will generate LF without anchor.")

        results[prefix] = {
            "path": video_path,
            "tail_frame": tail_frame_path,
            "skipped": False
        }

    return results


def _extract_tail(video_path, shot, global_cfg, scenes_dir, prefix):
    """Extract the tail frame from a video for use as the next shot's FF."""
    if not video_path or not os.path.exists(video_path):
        return None
    overlap_seconds = shot.get("overrides", {}).get("overlap_seconds") or global_cfg.get("overlap_seconds", 1.0)
    fps = shot.get("overrides", {}).get("fps") or global_cfg.get("fps", 25)
    target_image_name = f"{prefix}_tail_frame.png"
    target_image_path = os.path.join(scenes_dir, target_image_name)
    try:
        extracted = extract_continuation_frame(
            video_path=video_path,
            overlap_seconds=overlap_seconds,
            fps=fps,
            output_path=target_image_path
        )
        return extracted if extracted and os.path.exists(extracted) else None
    except Exception as e:
        print(f"  ⚠️  Tail frame extraction error: {e}")
        return None


# ── Main CLI ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Story-to-Video-Filmmaking: Recursive Filmmaking Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 filmmaking_orchestrator.py --prompts filmmaking_prompt.json
  python3 filmmaking_orchestrator.py --prompts filmmaking_prompt.json --fast
  python3 filmmaking_orchestrator.py --prompts filmmaking_prompt.json --interactive
  python3 filmmaking_orchestrator.py --prompts filmmaking_prompt.json --shot film_001_shot002
  python3 filmmaking_orchestrator.py --prompts filmmaking_prompt.json --skip-existing --fast
        """
    )
    parser.add_argument("--prompts", default="filmmaking_prompt.json",
                        help="Path to filmmaking_prompt.json (default: filmmaking_prompt.json)")
    parser.add_argument("--url", default=os.environ.get("COMFYUI_URL", DEFAULT_BASE_URL),
                        help=f"ComfyUI base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--output-dir", default=DEFAULT_FILMMAKING_OUTPUT_DIR,
                        help=f"Output base directory (default: {DEFAULT_FILMMAKING_OUTPUT_DIR})")
    parser.add_argument("--shot", type=str, default=None,
                        help="Process only a specific shot (matches filename_prefix)")
    parser.add_argument("--fast", action="store_true",
                        help="Skip Stage 1 seed hunting, use Stage 2+3 directly")
    parser.add_argument("--interactive", action="store_true",
                        help="Prompt user in terminal to select Stage 1 preview index")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip shots whose videos already exist in videos/")
    parser.add_argument("--evaluate", action="store_true",
                        help="Run per-frame quality and FF↔LF coherence evaluations")
    parser.add_argument("--dry-run", action="store_true",
                        help="Resolve chains and print execution plan without generating anything")
    parser.add_argument("--auth", type=str, default=None,
                        help="ComfyUI Basic Auth in username:password format")
    parser.add_argument("--api-key", default=os.environ.get("GEMINI_API_KEY", ""),
                        help="Gemini/OpenRouter API key for motion and quality evaluation")
    parser.add_argument("--provider", choices=["openrouter", "gemini"], default=None,
                        help="Vision provider for evaluation")
    parser.add_argument("--references-dir", type=str, default=None,
                        help="Character reference sheets folder (defaults to sibling 'characters/')")
    parser.add_argument("--quality-gate", action="store_true",
                        help="Run per-image quality gate after each still is generated (catches character drift)")
    parser.add_argument("--preflight-audit", action="store_true",
                        help="Run pre-flight FF↔LF text-based audit before Phase 2 (advisory, does not block)")
    parser.add_argument("--quality-gate-min-score", type=float, default=None,
                        help="Override global.quality_gate.min_score for this run (default: use value from filmmaking_prompt.json)")
    parser.add_argument("--quality-gate-max-retries", type=int, default=None,
                        help="Override global.quality_gate.max_retries for this run (default: use value from filmmaking_prompt.json)")

    args = parser.parse_args()
    base_url = args.url

    # Resolve output directory: project-local by default (cwd / story folder),
    # never the global skill root. This prevents cross-project contamination
    # when running multiple stories back-to-back. See the `wolf` 2026-06-11
    # run for the failure mode this fixes.
    if args.output_dir == DEFAULT_FILMMAKING_OUTPUT_DIR:
        # Default not overridden — use the directory holding filmmaking_prompt.json
        # (one level up from prompts file, or the prompts file's own dir).
        prompts_dir = os.path.dirname(os.path.abspath(args.prompts))
        output_dir = prompts_dir
    else:
        output_dir = args.output_dir

    # Establish subdirectories
    scenes_dir = os.path.join(output_dir, "scenes")
    videos_dir = os.path.join(output_dir, "videos")
    motion_eval_dir = os.path.join(output_dir, "motion_eval")
    for d in [scenes_dir, videos_dir, motion_eval_dir]:
        os.makedirs(d, exist_ok=True)

    # Parse auth
    comfyui_auth = None
    if args.auth:
        parts = args.auth.split(":", 1)
        if len(parts) == 2:
            comfyui_auth = (parts[0], parts[1])
        else:
            print("❌ Invalid auth format. Use username:password")
            sys.exit(1)

    # Load prompts
    try:
        prompts_data = load_filmmaking_prompts(args.prompts)
    except Exception as e:
        print(f"❌ Error loading prompts: {e}")
        sys.exit(1)

    global_cfg = prompts_data["global"]
    shots = prompts_data["shots"]

    # Filter to a single shot if specified
    if args.shot:
        # Find the shot and all shots it depends on (its chain)
        target = next((s for s in shots if s["filename_prefix"] == args.shot), None)
        if not target:
            print(f"❌ Shot '{args.shot}' not found in filmmaking_prompt.json")
            sys.exit(1)
        shots = [target]

    # Resolve references directory
    if args.references_dir:
        references_base_dir = args.references_dir
    else:
        prompts_dir = os.path.dirname(os.path.abspath(args.prompts))
        references_base_dir = os.path.join(prompts_dir, "characters")

    print(f"📂 Reference Sheets Dir: {references_base_dir}")

    # Load workflow templates
    image_template_name = (
        prompts_data.get("image_workflow_template")
        or global_cfg.get("image_workflow_template", "flux-2-dev-turbo")
    )
    video_template_name = prompts_data.get("workflow_template", "ltx-23-fflf-seed-hunter")

    try:
        image_template = load_workflow_template(image_template_name)
        print(f"🔧 Image template: {image_template_name}")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    try:
        video_template = load_workflow_template(video_template_name)
        print(f"🔧 Video template: {video_template_name}")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Resolve execution mode
    mode = "auto"
    if args.fast:
        mode = "fast"
    elif args.interactive:
        mode = "interactive"

    # Resolve chain topology
    chains = resolve_chains(shots)

    # Dry-run
    if args.dry_run:
        print_execution_plan(chains, mode)
        print("\n✅ Dry-run complete — no images or videos generated.")
        return

    # Pre-flight FF↔LF audit (advisory, does not block by default)
    if args.preflight_audit:
        print(f"\n{'─'*70}")
        print(f"  🔍 Pre-flight FF↔LF Audit")
        print(f"{'─'*70}")
        import subprocess
        audit_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt_audit.py")
        audit_proc = subprocess.run(
            [sys.executable, audit_script, args.prompts],
            capture_output=True, text=True, timeout=60
        )
        print(audit_proc.stdout)
        if audit_proc.returncode != 0:
            print(f"  ⚠️  Pre-flight audit found risks (exit {audit_proc.returncode})")
            print(f"     Review feedback/ff_lf_audit_preflight.md and re-author risky LFs before continuing.")
            # We do not block by default. Use --strict-preflight (future) to make it blocking.
        else:
            print(f"  ✅ Pre-flight audit passed — LFs look healthy.")
        print()

    print_execution_plan(chains, mode)

    # Discover available images on ComfyUI
    try:
        available = get_available_images(base_url, auth=comfyui_auth)
        print(f"📷 Found {len(available)} files in ComfyUI input directory")
    except Exception as e:
        print(f"⚠️  Could not fetch ComfyUI available images: {e}")
        available = set()

    # Process chains sequentially
    all_results = {}
    start_time = time.time()
    for chain_idx, chain in enumerate(chains):
        print(f"\n\n{'═'*70}")
        print(f"  🎬 Processing Chain {chain_idx+1}/{len(chains)} — {len(chain)} shot(s)")
        print(f"{'═'*70}")

        chain_results = process_chain(
            chain=chain,
            global_cfg=global_cfg,
            image_template=image_template,
            video_template=video_template,
            base_url=base_url,
            output_dir=output_dir,
            scenes_dir=scenes_dir,
            videos_dir=videos_dir,
            motion_eval_dir=motion_eval_dir,
            references_base_dir=references_base_dir,
            available_images=available,
            mode=mode,
            auth=comfyui_auth,
            skip_existing=args.skip_existing,
            evaluate=args.evaluate,
            api_key=args.api_key,
            provider=args.provider,
            quality_gate=(
                args.quality_gate
                or global_cfg.get("quality_gate", {}).get("enabled", False)
            ),
            quality_gate_min_score=(
                args.quality_gate_min_score
                if args.quality_gate_min_score is not None
                else global_cfg.get("quality_gate", {}).get("min_score", 7.0)
            ),
            quality_gate_max_retries=(
                args.quality_gate_max_retries
                if args.quality_gate_max_retries is not None
                else global_cfg.get("quality_gate", {}).get("max_retries", 1)
            ),
        )
        all_results.update(chain_results)

    # Final summary
    elapsed = time.time() - start_time
    print(f"\n\n{'═'*70}")
    print(f"  🎬 Filmmaking Orchestrator — Final Summary ({elapsed/60:.1f}min)")
    print(f"{'═'*70}")
    total = len(all_results)
    succeeded = sum(1 for r in all_results.values() if r and not r.get("skipped"))
    skipped = sum(1 for r in all_results.values() if r and r.get("skipped"))
    failed = sum(1 for r in all_results.values() if not r)

    for prefix, result in all_results.items():
        if result is None:
            print(f"  ❌ {prefix}: Failed")
        elif result.get("skipped"):
            print(f"  ⏭️  {prefix}: Skipped — {result['path']}")
        else:
            size_mb = os.path.getsize(result["path"]) / 1024 / 1024 if result["path"] and os.path.exists(result["path"]) else 0
            print(f"  ✅ {prefix}: {result['path']} ({size_mb:.1f}MB)")

    print(f"\n  Total: {total} shots — ✅ {succeeded} done, ⏭️ {skipped} skipped, ❌ {failed} failed")

    if succeeded + skipped > 0:
        print(f"\n  💡 To stitch all videos into one film, run:")
        video_files = [
            r["path"] for prefix, r in sorted(all_results.items())
            if r and r.get("path") and os.path.exists(r["path"])
        ]
        if video_files:
            files_list = " ".join(f'"{f}"' for f in video_files)
            print(f"  python3 continuation_pipeline.py --stitch {files_list}")


if __name__ == "__main__":
    main()
