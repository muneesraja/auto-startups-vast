#!/usr/bin/env python3
"""
Story-to-Video: Scene Generator (v3)
======================================
Generates scene images via ComfyUI using prompt.json (agent-composed prompts)
and config-driven workflow templates.

v3 changes:
- prompt.json is the primary input (agent composes prompts, script executes)
- Config-driven workflow templates (swap models by adding a JSON file)
- Removed hardcoded prompt composition (load_manifest template logic)
- Removed hardcoded build_workflow (Qwen-specific node graph)
- Evaluation uses eval_context from prompt.json

Usage:
    python3 generate_scene.py --prompts prompt.json
    python3 generate_scene.py --prompts prompt.json --evaluate
    python3 generate_scene.py --prompts prompt.json --shot scene_001_shot001
    python3 generate_scene.py --prompts prompt.json --url https://my-comfyui.example.com

Requires: curl (Cloudflare blocks Python urllib)
Tested: RTX 3090
"""
import argparse
import json
import os
import shutil
import sys

from comfyui_api import (
    curl_json,
    wait_for_prompt,
    download_output,
    get_available_images,
    DEFAULT_BASE_URL,
    DEFAULT_OUTPUT_DIR,
)
from workflow_builder import build_dynamic_workflow, load_workflow_template
from gemini_eval import (
    call_gemini_vision,
    resolve_provider,
    compute_weighted_score,
    build_eval_prompt as build_eval_prompt_base,
    parse_eval_response,
    GEMINI_MODEL,
    OPENROUTER_MODEL,
    PASS_THRESHOLD,
    CATEGORY_WEIGHTS,
)

MAX_ITERATIONS_DEFAULT = 3



# ── prompt.json Loader ───────────────────────────────────────

def load_prompts(prompts_path):
    """Load prompt.json and return parsed data.

    Returns:
        dict with keys: version, model, workflow_template, global, shots
    """
    with open(prompts_path) as f:
        data = json.load(f)

    # Validate required fields
    required = ["version", "model", "workflow_template", "global", "shots"]
    for field in required:
        if field not in data:
            raise ValueError(f"prompt.json missing required field: '{field}'")

    global_cfg = data["global"]
    for field in ["style", "width", "height"]:
        if field not in global_cfg:
            raise ValueError(f"prompt.json global section missing required field: '{field}'")

    for i, shot in enumerate(data["shots"]):
        for field in ["scene", "shot", "prompt", "references", "filename_prefix"]:
            if field not in shot:
                raise ValueError(f"prompt.json shot[{i}] missing required field: '{field}'")

    print(f"📋 Loaded prompt.json (v{data['version']})")
    print(f"   Model: {data['model']}")
    print(f"   Template: {data['workflow_template']}")
    print(f"   Shots: {len(data['shots'])}")
    print(f"   Resolution: {global_cfg['width']}×{global_cfg['height']}")

    # Validate prompt token lengths (warn if exceeding model budget)
    _validate_prompt_lengths(data)

    # Warn if negative_prompt is set for Flux models (which ignore it)
    model = data.get("model", "")
    if "flux" in model.lower():
        if global_cfg.get("negative_prompt"):
            print("   ⚠️  WARNING: negative_prompt is populated in global settings, but Flux uses ConditioningZeroOut natively. It will be ignored.")
        for shot in data.get("shots", []):
            if shot.get("negative_prompt"):
                print(f"   ⚠️  WARNING: Shot {shot.get('filename_prefix', 'unknown')} has negative_prompt set, which will be ignored by Flux.")

    return data


# ── Prompt Token Validation ──────────────────────────────────

# Rough token estimation: ~4 characters per token for English text.
# This is a conservative estimate; actual tokenizers may vary.
_CHARS_PER_TOKEN = 4

# Model-specific token budgets (ideal and max)
_TOKEN_BUDGETS = {
    "qwen-image-edit-2511": {"ideal": 150, "max": 200},
    "hidream-o1-dev": {"ideal": 150, "max": 200},
    "flux-2-klein-9b": {"ideal": 180, "max": 250},
    "flux-2-dev-turbo": {"ideal": 250, "max": 350},
}
_DEFAULT_TOKEN_BUDGET = {"ideal": 150, "max": 200}


def _validate_prompt_lengths(data):
    """Check prompt token lengths and warn if over budget."""
    model = data.get("model", "")
    budget = _TOKEN_BUDGETS.get(model, _DEFAULT_TOKEN_BUDGET)
    ideal = budget["ideal"]
    max_tokens = budget["max"]

    over_ideal = []
    over_max = []
    for shot in data["shots"]:
        prompt = shot.get("prompt", "")
        # Rough token count estimation
        est_tokens = len(prompt) / _CHARS_PER_TOKEN
        shot_id = f"scene_{shot['scene']:03d}_shot{shot['shot']:03d}"

        if est_tokens > max_tokens:
            over_max.append((shot_id, int(est_tokens)))
        elif est_tokens > ideal:
            over_ideal.append((shot_id, int(est_tokens)))

    if over_ideal or over_max:
        print(f"\n⚠️  Prompt token validation (model: {model}, budget: {ideal}–{max_tokens} tokens):")
        for shot_id, tokens in over_ideal:
            print(f"   ⚠️  {shot_id}: ~{tokens} tokens (over ideal {ideal} but within max {max_tokens})")
        for shot_id, tokens in over_max:
            print(f"   🚫 {shot_id}: ~{tokens} tokens (EXCEEDS max {max_tokens} — risk of quality degradation)")
        print(f"   Tip: Use abbreviated identity specs after first shot, short-form style, and omit repeated settings.")


# ── Scene Generation ─────────────────────────────────────────

def generate_shot(shot_data, global_cfg, workflow_template, base_url, output_dir,
                  available_images, seed_override=None, auth=None):
    """Generate a single shot image using prompt.json data.

    Args:
        shot_data: Single shot object from prompt.json
        global_cfg: Global config from prompt.json
        workflow_template: Loaded workflow template dict
        base_url: ComfyUI instance URL
        output_dir: Directory to save output images
        available_images: Set of available image filenames on ComfyUI
        seed_override: Override the seed (for retry iterations)
        auth: Optional tuple of (username, password) for Basic Auth

    Returns:
        str: Path to generated image, or None on failure
    """
    scene_num = shot_data["scene"]
    shot_num = shot_data["shot"]
    prefix = shot_data["filename_prefix"]
    references = shot_data.get("references", [])

    print(f"🎬 Scene {scene_num}, Shot {shot_num}")
    print(f"   References: {references}")
    print(f"   Seed: {shot_data.get('seed', global_cfg.get('seed_base', 42))}")
    print(f"   Prompt: {shot_data['prompt'][:120]}...")

    # Verify reference images exist on the instance
    missing = [ref for ref in references if ref not in available_images]
    if missing:
        print(f"   ⚠️ Missing references on instance: {missing}")
        # Don't fail — the workflow may still work with available refs

    # Apply seed override if provided
    if seed_override is not None:
        shot_data_copy = {**shot_data, "seed": seed_override}
    else:
        shot_data_copy = shot_data

    # Build the workflow from template
    workflow = build_dynamic_workflow(workflow_template, shot_data_copy, global_cfg)

    # Queue the workflow
    result = curl_json("POST", "/prompt", base_url,
                       data={"prompt": workflow, "client_id": "story-to-video"},
                       auth=auth)

    if "error" in result:
        err = result["error"]
        node_errors = result.get("node_errors", {})
        print(f"   ❌ Queue error: {err.get('type')}: {err.get('message')}")
        for nid, errs in node_errors.items():
            for e in errs.get("errors", []):
                print(f"      Node {nid}: {e.get('details', e.get('message', ''))}")
        return None

    prompt_id = result.get("prompt_id")
    print(f"   ⏳ Queued: {prompt_id}")

    try:
        outputs = wait_for_prompt(prompt_id, base_url, auth=auth)
    except (RuntimeError, TimeoutError) as e:
        print(f"   ❌ {e}")
        return None

    # Download output images
    for nid, out in outputs.items():
        for item in out.get("images", []):
            filename = item["filename"]
            out_path = os.path.join(output_dir, filename)
            if download_output(filename, out_path, base_url, item.get("subfolder", ""), auth=auth):
                size = os.path.getsize(out_path)
                print(f"   ✅ Saved: {out_path} ({size/1024:.0f} KB)")
                return out_path

    print(f"   ⚠️ No images in output")
    return None


# ═══════════════════════════════════════════════════════════════
#  GEMINI VISION EVALUATION
# ═══════════════════════════════════════════════════════════════

def build_eval_prompt(eval_context, prompt_text, reference_names=None):
    """Build evaluation prompt from prompt.json's eval_context.

    Args:
        eval_context: The eval_context object from a prompt.json shot
        prompt_text: The prompt that was used to generate the image
        reference_names: Optional list of reference image filenames being provided
    """
    # Build expected description from eval_context
    desc_parts = ["EXPECTED SCENE DESCRIPTION:", ""]
    desc_parts.append(f"Generation prompt: {prompt_text}")
    desc_parts.append("")

    if eval_context.get("characters_present"):
        desc_parts.append(f"Characters expected: {', '.join(eval_context['characters_present'])}")
    else:
        desc_parts.append("Characters expected: None (landscape/environment shot)")

    if eval_context.get("setting"):
        desc_parts.append(f"Setting: {eval_context['setting']}")

    if eval_context.get("action"):
        desc_parts.append(f"Action: {eval_context['action']}")

    if eval_context.get("mood"):
        desc_parts.append(f"Mood: {eval_context['mood']}")

    if eval_context.get("expected_expressions"):
        desc_parts.append("")
        desc_parts.append("Expected facial expressions:")
        for char_id, expr in eval_context["expected_expressions"].items():
            desc_parts.append(f"- {char_id}: {expr}")

    expected_description = "\n".join(desc_parts)

    return build_eval_prompt_base(expected_description, version="v2",
                                  reference_names=reference_names)



def evaluate_with_gemini(image_path, shot_data, api_key=None, provider=None,
                         references_base_dir=None):
    """Evaluate a generated scene image using vision API.

    Args:
        image_path: Path to the generated image
        shot_data: Shot object from prompt.json (contains prompt + eval_context + references)
        api_key: API key override (optional)
        provider: 'openrouter', 'gemini', or None (auto-detect)
        references_base_dir: Base directory for resolving reference image paths
                            (e.g., /path/to/pluffy-bun/characters/)

    Returns:
        Parsed evaluation result dict or None on failure
    """
    # Resolve provider
    try:
        provider_name, resolved_key, call_fn = resolve_provider(provider)
    except ValueError as e:
        print(f"   ❌ {e}")
        return None
    if api_key:
        resolved_key = api_key

    eval_context = shot_data.get("eval_context", {})
    prompt_text = shot_data["prompt"]

    # Resolve reference images from prompt.json
    reference_filenames = shot_data.get("references", [])
    reference_images = []
    reference_names = []
    if references_base_dir and reference_filenames:
        for ref_name in reference_filenames:
            ref_path = os.path.join(references_base_dir, ref_name)
            if os.path.exists(ref_path):
                reference_images.append(ref_path)
                reference_names.append(ref_name)
            else:
                print(f"   ⚠️ Reference image not found: {ref_path}")

    eval_prompt = build_eval_prompt(eval_context, prompt_text,
                                    reference_names=reference_names if reference_names else None)

    model_name = OPENROUTER_MODEL if provider_name == "openrouter" else GEMINI_MODEL
    ref_count = len(reference_images)
    print(f"   🔍 Evaluating with {provider_name} ({model_name})...")
    print(f"   🖼️ Generated image: {os.path.basename(image_path)}")
    if ref_count:
        print(f"   📎 Reference images ({ref_count}): {', '.join(reference_names)}")
    else:
        print(f"   📎 No reference images")

    response = call_fn(eval_prompt, image_path, resolved_key,
                       reference_images=reference_images if reference_images else None)

    # Handle OpenRouter dict response vs Gemini string response
    reasoning_text = ""
    thinking_tokens = 0
    if isinstance(response, dict):
        reasoning_text = response.get("reasoning", "")
        thinking_tokens = response.get("thinking_tokens", 0)
        response = response["response"]
        if reasoning_text:
            print(f"   🧠 Thinking: {len(reasoning_text)} chars, {thinking_tokens} tokens")

    if not response:
        print(f"   ❌ Empty response from {provider_name}")
        return None

    result = parse_eval_response(response)
    if result is None:
        print(f"   ❌ Could not parse response")
        print(f"   Raw: {response[:200]}...")
        return None

    # Add provider metadata and reasoning
    result["provider"] = provider_name
    result["model"] = model_name
    if reasoning_text:
        result["reasoning"] = reasoning_text
    if thinking_tokens:
        result["thinking_tokens"] = thinking_tokens

    # Print results
    scores = result.get("category_scores", {})
    weighted = result.get("score", 0)
    passed = result.get("passed", False)
    issues = result.get("issues", [])
    strengths = result.get("strengths", [])
    expr_detail = result.get("expression_detail", {})

    categories = list(CATEGORY_WEIGHTS.keys())
    print(f"   📊 Scores: " + " | ".join(f"{cat}: {scores.get(cat, 'N/A')}" for cat in categories))
    print(f"   📊 Weighted: {weighted:.1f}/10 | {'✅ PASS' if passed else '❌ FAIL'}")

    if issues:
        print(f"   ⚠️ Issues: {'; '.join(issues[:5])}")
    if strengths:
        print(f"   💪 Strengths: {'; '.join(strengths[:3])}")
    if expr_detail:
        for cid, detail in expr_detail.items():
            print(f"   😐 {cid}: expected='{detail.get('expected', '?')}' observed='{detail.get('observed', '?')}'")

    if not passed and result.get("refined_prompt"):
        print(f"   🔄 Refined prompt available for retry")

    return result


# ── Generate with Evaluation Loop ────────────────────────────

def generate_with_eval_loop(shot_data, global_cfg, workflow_template, base_url,
                            output_dir, available_images, api_key=None,
                            max_iterations=3, provider=None, references_base_dir=None,
                            auth=None):
    """Generate a shot and evaluate with retry loop.

    Returns:
        dict with 'path', 'final_score', 'iterations', 'passed' or None on failure
    """
    seed = shot_data.get("seed", global_cfg.get("seed_base", 42))
    current_prompt = shot_data["prompt"]
    current_seed = seed
    best_result = None
    best_path = None
    best_score = 0
    filename_prefix = shot_data["filename_prefix"]

    for iteration in range(1, max_iterations + 1):
        print(f"\n{'='*60}")
        print(f"  Iteration {iteration}/{max_iterations} — {filename_prefix}")
        print(f"{'='*60}")

        # Update prompt if refined from previous evaluation
        if iteration > 1 and best_result and best_result.get("refined_prompt"):
            current_prompt = best_result["refined_prompt"]
            print(f"   🔄 Using refined prompt from previous iteration")

        # Build shot data with current prompt and seed
        shot_copy = {**shot_data, "prompt": current_prompt, "seed": current_seed}
        file_prefix = f"{filename_prefix}_iter{iteration}" if iteration > 1 else filename_prefix

        # Override filename prefix for this iteration
        shot_copy["filename_prefix"] = file_prefix

        image_path = generate_shot(
            shot_copy, global_cfg, workflow_template, base_url,
            output_dir, available_images, seed_override=current_seed,
            auth=auth
        )

        if not image_path:
            print(f"   ❌ Generation failed, retrying with different seed...")
            current_seed += 1
            continue

        # Evaluate the image
        result = evaluate_with_gemini(image_path, shot_copy, api_key=api_key,
                                      provider=provider,
                                      references_base_dir=references_base_dir)

        if result is None:
            print(f"   ⚠️ Evaluation failed, keeping image without eval")
            return {"path": image_path, "final_score": None, "iterations": iteration, "passed": None}

        # Track best result
        score = result.get("score", 0)
        if score > best_score:
            best_score = score
            best_result = result
            best_path = image_path

        if result.get("passed", False):
            print(f"   ✅ PASSED on iteration {iteration} (score: {score:.1f})")
            final_path = os.path.join(output_dir, f"{filename_prefix}_final.png")
            if image_path != final_path:
                shutil.copy2(image_path, final_path)
            return {
                "path": final_path if os.path.exists(final_path) else image_path,
                "final_score": score,
                "iterations": iteration,
                "passed": True,
            }

        print(f"   ❌ Failed threshold on iteration {iteration} (score: {score:.1f}/{PASS_THRESHOLD})")
        current_seed += 1

    # Out of iterations - return best result
    print(f"\n   ⚠️ Max iterations reached. Best score: {best_score:.1f}")
    final_path = os.path.join(output_dir, f"{filename_prefix}_final.png")
    if best_path:
        shutil.copy2(best_path, final_path)
    return {
        "path": final_path if os.path.exists(final_path) else best_path,
        "final_score": best_score,
        "iterations": max_iterations,
        "passed": False,
    }


# ── CLI ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Story-to-Video scene generator (v3: prompt.json + workflow templates)")
    parser.add_argument("--prompts", required=True,
                        help="Path to prompt.json (agent-composed prompts)")
    parser.add_argument("--shot", type=str,
                        help="Generate a specific shot by filename_prefix (e.g., scene_001_shot001)")
    parser.add_argument("--evaluate", action="store_true",
                        help="Evaluate generated images with Gemini Vision")
    parser.add_argument("--evaluate-only", action="store_true",
                        help="Evaluate existing images without generating")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse prompt.json and build workflows without queuing")
    parser.add_argument("--url", default=DEFAULT_BASE_URL,
                        help=f"ComfyUI base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--max-iterations", type=int, default=MAX_ITERATIONS_DEFAULT,
                        help=f"Max eval iterations (default: {MAX_ITERATIONS_DEFAULT})")
    parser.add_argument("--api-key", default=os.environ.get("GEMINI_API_KEY", ""),
                        help="Vision API key (overrides env)")
    parser.add_argument("--provider", choices=["openrouter", "gemini"], default=None,
                        help="Vision provider (default: auto-detect from env, OpenRouter preferred)")
    parser.add_argument("--cleanup-iters", action="store_true",
                        help="Remove intermediate iteration images (keep only final)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip shots that already have a _final.png file")
    parser.add_argument("--references-dir", type=str, default=None,
                        help="Directory containing reference images (default: auto-detect from prompt.json path)")
    parser.add_argument("--auth", type=str, default=None,
                        help="ComfyUI Basic Auth in username:password format")

    args = parser.parse_args()
    base_url = args.url
    output_dir = args.output_dir
    scenes_dir = os.path.join(output_dir, "scenes")

    # Load API key
    if not args.api_key:
        args.api_key = os.environ.get("GEMINI_API_KEY", "")

    # Parse auth
    comfyui_auth = None
    if args.auth:
        parts = args.auth.split(":", 1)
        if len(parts) == 2:
            comfyui_auth = (parts[0], parts[1])
        else:
            print("❌ Invalid auth format. Use username:password")
            sys.exit(1)

    os.makedirs(scenes_dir, exist_ok=True)

    # ── Load prompt.json ──
    prompts_data = load_prompts(args.prompts)
    global_cfg = prompts_data["global"]
    shots = prompts_data["shots"]

    # ── Resolve references directory ──
    # Auto-detect from prompt.json path (characters/ is sibling of prompt.json)
    if args.references_dir:
        references_base_dir = args.references_dir
    else:
        prompts_dir = os.path.dirname(os.path.abspath(args.prompts))
        references_base_dir = os.path.join(prompts_dir, "characters")
    if os.path.isdir(references_base_dir):
        ref_files = [f for f in os.listdir(references_base_dir) if f.endswith(('.png', '.jpg', '.jpeg'))]
        print(f"📎 Reference images directory: {references_base_dir} ({len(ref_files)} files)")
    else:
        print(f"⚠️ References directory not found: {references_base_dir}")
        references_base_dir = None

    # ── Load workflow template ──
    template_name = prompts_data["workflow_template"]
    try:
        workflow_template = load_workflow_template(template_name)
        print(f"🔧 Loaded workflow template: {template_name}")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # ── Dry-run mode ──
    if args.dry_run:
        print(f"\n🔍 Dry-run: building workflows for {len(shots)} shots...")
        for shot in shots:
            workflow = build_dynamic_workflow(workflow_template, shot, global_cfg)
            prefix = shot["filename_prefix"]
            refs = shot.get("references", [])
            print(f"   ✅ {prefix}: {len(workflow)} nodes, refs={refs}")
        print(f"\n✅ Dry-run complete. All {len(shots)} shots parsed successfully.")
        return

    # ── Discover available images ──
    available = get_available_images(base_url, auth=comfyui_auth)
    print(f"📷 Found {len(available)} available images on ComfyUI instance")

    # ── Filter shots ──
    if args.shot:
        shots = [s for s in shots if s["filename_prefix"] == args.shot]
        if not shots:
            print(f"❌ Shot '{args.shot}' not found in prompt.json")
            print(f"   Available: {[s['filename_prefix'] for s in prompts_data['shots']]}")
            sys.exit(1)

    # ── Evaluate-only mode ──
    if args.evaluate_only:
        if not args.api_key:
            print("❌ GEMINI_API_KEY required for evaluation")
            sys.exit(1)

        for shot in shots:
            prefix = shot["filename_prefix"]
            # Find existing image
            candidates = [
                os.path.join(scenes_dir, f"{prefix}_final.png"),
                os.path.join(scenes_dir, f"{prefix}_00001_.png"),
            ]
            image_path = next((p for p in candidates if os.path.exists(p)), None)

            if not image_path:
                # Try glob
                matches = [os.path.join(scenes_dir, f) for f in os.listdir(scenes_dir)
                           if f.startswith(prefix) and f.endswith(('.png', '.jpg'))]
                image_path = sorted(matches)[-1] if matches else None

            if not image_path:
                print(f"❌ No image found for {prefix}")
                continue

            print(f"\n🔍 Evaluating: {image_path}")
            result = evaluate_with_gemini(image_path, shot, api_key=args.api_key,
                                          provider=args.provider,
                                          references_base_dir=references_base_dir)
            if result:
                print(f"📊 Final: {result.get('score', 0):.1f}/10 | "
                      f"{'✅ PASS' if result.get('passed') else '❌ FAIL'}")
        return

    # ── Generation mode ──
    print(f"\n📖 Generating {len(shots)} shots")
    print(f"   Model: {prompts_data['model']}")

    results = {}
    for shot in shots:
        prefix = shot["filename_prefix"]

        # Skip if any image for this prefix already exists in the scenes dir.
        # Originally checked only for "{prefix}_final.png" (the eval-loop
        # convention), but the plain generate_shot path saves as
        # "{prefix}_00001_.png" / "{prefix}_00002_.png" — making the script
        # needlessly re-generate and overwrite a perfectly good image on
        # retries. (Caught 2026-06-05, t_7d0915a2 — second batch run wasted
        # ~10 minutes redoing shots 17+ that were already produced.)
        if args.skip_existing:
            existing = sorted(
                f for f in os.listdir(scenes_dir)
                if f.startswith(prefix + "_") and f.endswith(('.png', '.jpg'))
                and os.path.getsize(os.path.join(scenes_dir, f)) > 1024
            )
            if existing:
                existing_path = os.path.join(scenes_dir, existing[-1])
                print(f"\n🎬 {prefix}: ⏭️  Skipping ({existing[-1]} exists, "
                      f"{os.path.getsize(existing_path)/1024:.0f} KB)")
                results[prefix] = {"path": existing_path, "iterations": 0,
                                   "passed": None, "skipped": True}
                continue

        if args.evaluate:
            if not args.api_key and not os.environ.get("OPENROUTER_API_KEY"):
                print("❌ Vision API key required for --evaluate mode (set OPENROUTER_API_KEY or --api-key)")
                sys.exit(1)

            result = generate_with_eval_loop(
                shot, global_cfg, workflow_template, base_url,
                scenes_dir, available, api_key=args.api_key,
                max_iterations=args.max_iterations, provider=args.provider,
                references_base_dir=references_base_dir, auth=comfyui_auth
            )
        else:
            path = generate_shot(
                shot, global_cfg, workflow_template, base_url,
                scenes_dir, available, auth=comfyui_auth
            )
            result = {"path": path, "iterations": 1, "passed": None} if path else None

        results[prefix] = result

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"  Generation Summary ({prompts_data['model']})")
    print(f"{'='*60}")
    skipped = 0
    for prefix, result in results.items():
        if result:
            if result.get("skipped"):
                status = "⏭️"
                skipped += 1
            else:
                status = "✅" if result.get("passed") else ("⚠️" if result.get("path") else "❌")
            score = f" (score: {result.get('final_score', '?')})" if result.get("final_score") else ""
            print(f"  {prefix}: {status}{score} — {result.get('path', 'N/A')}")
        else:
            print(f"  {prefix}: ❌ Failed")
    total = len(results)
    if skipped:
        print(f"\n  ⏭️  {skipped}/{total} skipped (--skip-existing)")

    # ── Cleanup ──
    if args.cleanup_iters:
        print(f"\n🧹 Cleaning up intermediate iteration files...")
        for f in os.listdir(scenes_dir):
            if "_iter" in f and f.endswith(('.png', '.jpg')):
                os.remove(os.path.join(scenes_dir, f))
                print(f"   Removed: {f}")


if __name__ == "__main__":
    main()