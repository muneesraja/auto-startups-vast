#!/usr/bin/env python3
"""
Story-to-Video: Scene Evaluation (v2)
========================================
Evaluates generated scene images against their manifest descriptions using Gemini 2.5 Flash.

v2 changes:
- 5 evaluation categories (character_accuracy, facial_expression, scene_composition,
  action_depicted, style_consistency) with updated weights
- Scene details + target expressions passed to Gemini for better evaluation
- expression_detail per character in output (expected vs observed)
- Supports v1 and v2 manifests (auto-detects)

Usage:
    python3 evaluate_scene.py --manifest story_manifest.json --scene 1 --image scene_001_iter1.png
    python3 evaluate_scene.py --manifest story_manifest.json --scene 1 --image scene_001_iter1.png --shot 2
    python3 evaluate_scene.py --manifest story_manifest.json --all --scenes-dir ./scenes
"""

import argparse
import json
import os
import sys

from comfyui_api import DEFAULT_OUTPUT_DIR
from gemini_eval import (
    call_gemini_vision,
    resolve_provider,
    compute_weighted_score,
    build_eval_prompt as build_eval_prompt_base,
    parse_eval_response as parse_eval_response_base,
    GEMINI_MODEL,
    OPENROUTER_MODEL,
    PASS_THRESHOLD,
    CATEGORY_WEIGHTS_V2,
    CATEGORY_WEIGHTS_V1,
    REASONING_MAX_CHARS,
)



# ── Manifest Loader ──────────────────────────────────────────

def detect_manifest_version(manifest):
    """Detect v1 vs v2 manifest format."""
    if manifest.get("total_shots_budget") is not None:
        return "v2"
    scenes = manifest.get("scenes", [])
    if scenes and isinstance(scenes[0].get("shots"), list):
        return "v2"
    if scenes and "emotion" in scenes[0]:
        return "v1"
    return "v1"


def load_manifest(manifest_path):
    """Load story manifest JSON."""
    with open(manifest_path) as f:
        return json.load(f)


def get_scene_info(manifest, scene_number, shot_number=None):
    """Extract scene prompt info from manifest.

    For v2 manifests, if shot_number is provided, includes shot-level
    facial_expression targets in the evaluation prompt.
    Returns dict with version, scene info, and optionally shot info.
    """
    version = detect_manifest_version(manifest)
    style = manifest.get("style", "")
    char_map = {c["id"]: c["identity_spec"] for c in manifest.get("characters", [])}
    char_names = {c["id"]: c["name"] for c in manifest.get("characters", [])}
    char_personality = {c["id"]: c.get("personality_traits", "") for c in manifest.get("characters", [])}

    for scene in manifest.get("scenes", []):
        if scene["scene_number"] == scene_number:
            # Use shot-level characters_present if available, fall back to scene-level
            characters = scene.get("characters_present", [])
            if shot_number is not None:
                for shot in scene.get("shots", []):
                    if shot.get("shot_number") == shot_number:
                        shot_chars = shot.get("characters_present", [])
                        if shot_chars:
                            characters = shot_chars
                        break
            char_descriptions = []
            char_expressions = {}

            # Build character identity lines
            for cid in characters:
                name = char_names.get(cid, cid)
                spec = char_map.get(cid, "")
                personality = char_personality.get(cid, "")

                if len(characters) >= 3:
                    short = spec.split(",")[0] + ", " + ", ".join(spec.split(",")[1:3])
                    desc = f"- {name}: {short}"
                else:
                    desc = f"- {name}: {spec}"

                if personality:
                    desc += f" | Traits: {personality}"
                char_descriptions.append(desc)

            # v2: extract facial expressions from shots
            facial_expression_lines = []
            if version == "v2" and scene.get("shots"):
                # If a specific shot is requested, use that shot's expressions
                if shot_number is not None:
                    for shot in scene["shots"]:
                        if shot.get("shot_number") == shot_number:
                            for cid, expr in shot.get("facial_expression", {}).items():
                                name = char_names.get(cid, cid)
                                facial_expression_lines.append(f"- {name}: {expr}")
                                char_expressions[cid] = expr
                            break
                else:
                    # No specific shot — collect all expressions from all shots
                    all_expressions = {}
                    for shot in scene["shots"]:
                        for cid, expr in shot.get("facial_expression", {}).items():
                            if cid not in all_expressions:
                                all_expressions[cid] = []
                            all_expressions[cid].append(f"{expr} (shot {shot['shot_number']})")
                    for cid, exprs in all_expressions.items():
                        name = char_names.get(cid, cid)
                        facial_expression_lines.append(f"- {name}: {'; '.join(exprs)}")
                    char_expressions = {cid: "; ".join(exprs) for cid, exprs in all_expressions.items()}

            # v1 uses "emotion", v2 uses "mood"
            mood = scene.get("mood", scene.get("emotion", "neutral mood"))

            expected_parts = [
                "CHARACTERS EXPECTED:",
                *char_descriptions,
            ]

            # Add facial expression targets (v2)
            if facial_expression_lines:
                expected_parts.append("")
                expected_parts.append("EXPECTED FACIAL EXPRESSIONS:")
                expected_parts.extend(facial_expression_lines)

            expected_parts.extend([
                "",
                "SCENE CONTEXT:",
                f"Setting: {scene.get('setting', 'outdoor scene')}.",
                f"Action: {scene.get('action', 'characters in scene')}.",
                f"Mood: {mood}.",
                f"Camera: {scene.get('camera', 'medium shot')}.",
                f"Style: {style}.",
            ])

            # Add shot-specific info
            shot_info = None
            if version == "v2" and scene.get("shots") and shot_number is not None:
                for shot in scene["shots"]:
                    if shot.get("shot_number") == shot_number:
                        shot_info = shot
                        expected_parts.extend([
                            "",
                            "SHOT DETAILS:",
                            f"Shot {shot_number}: {shot.get('description', '')}",
                            f"Camera: {shot.get('camera_override', scene.get('camera', 'medium shot'))}",
                        ])
                        break

            return {
                "version": version,
                "title": scene.get("title", f"Scene {scene_number}"),
                "characters": characters,
                "expected_description": "\n".join(expected_parts),
                "action": scene.get("action", ""),
                "mood": mood,
                "setting": scene.get("setting", ""),
                "camera": scene.get("camera", ""),
                "style": style,
                "char_expressions": char_expressions,
                "shot_info": shot_info,
            }

    return None


def build_eval_prompt(scene_info):
    """Build the evaluation prompt for Gemini vision.

    v2: includes facial expression targets and shot-level details.
    v1: classic 4-category evaluation.
    """
    version = scene_info.get("version", "v1")
    return build_eval_prompt_base(scene_info['expected_description'], version=version)


def parse_eval_response(raw_text, scene_number, iteration, version="v2"):
    """Parse Gemini's response and add computed weighted score."""
    result = parse_eval_response_base(raw_text)
    if not result:
        return _parse_error_result(raw_text, scene_number, iteration, version)

    # Check for API-level errors
    if "error" in result:
        return _parse_error_result(raw_text, scene_number, iteration, version)

    # Recompute weighted score from raw category scores (don't trust model's math)
    if "category_scores" in result:
        result["score"] = compute_weighted_score(result["category_scores"], version, legacy_math=True)

    # Check for critical issues — only flag character/setting problems, not expression nuances
    critical_keywords = ["missing character", "character is missing", "character is absent", 
                         "wrong setting", "incorrect setting", "not present in the scene",
                         "character not visible", "character missing"]
    issues_text = " ".join(result.get("issues", [])).lower()
    # Also check for standalone "missing" or "absent" but exclude expression-related contexts
    expression_words = ["expression", "aspect", "detail", "shame", "fear", "panic", "mouth", "eyes", "brow"]
    has_critical = any(kw in issues_text for kw in critical_keywords)
    if not has_critical:
        # Check standalone "missing"/"absent" but only if NOT about expressions
        for kw in ["missing", "absent"]:
            if kw in issues_text:
                # Find the sentence containing the keyword
                for issue in result.get("issues", []):
                    if kw in issue.lower():
                        # Only critical if no expression words in the same sentence
                        if not any(ew in issue.lower() for ew in expression_words):
                            has_critical = True
                            break

    # Override passed based on score AND critical issues
    score = result.get("score", 0)
    if score >= PASS_THRESHOLD and not has_critical:
        result["passed"] = True
        result["refined_prompt"] = None
    else:
        result["passed"] = False

    result["scene_number"] = scene_number
    result["iteration"] = iteration
    result["version"] = version

    # Sanitize refined prompt for JSON injection into ComfyUI workflow
    if result.get("refined_prompt"):
        rp = result["refined_prompt"]
        rp = rp.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", "")
        if len(rp) > 2000:
            rp = rp[:1950] + "..."
            result["prompt_truncated"] = True
        result["refined_prompt"] = rp

    # Fill missing expression_detail for v1 backward compat
    if "expression_detail" not in result:
        result["expression_detail"] = {}

    return result


def _parse_error_result(raw_text, scene_number, iteration, version="v2"):
    """Return a default result for parse errors."""
    default_scores = {
        "character_accuracy": 0, "facial_expression": 0,
        "scene_composition": 0, "action_depicted": 0, "style_consistency": 0,
    } if version == "v2" else {
        "character_accuracy": 0, "scene_composition": 0,
        "action_depicted": 0, "style_consistency": 0,
    }
    return {
        "scene_number": scene_number,
        "iteration": iteration,
        "version": version,
        "eval_parse_error": True,
        "description": "",
        "category_scores": default_scores,
        "score": 0,
        "passed": True,  # Trust the generation if eval can't parse
        "issues": [],
        "strengths": ["Evaluation parse error — accepting image as-is"],
        "refined_prompt": None,
        "expression_detail": {},
        "raw_response": raw_text[:500],
    }


# ── Main Evaluation ──────────────────────────────────────────

def evaluate_scene(image_path, manifest_path, scene_number, shot_number=None,
                   iteration=1, output_dir=None, api_key=None, provider=None):
    """Evaluate a single scene image against its manifest description.

    For v2 manifests, shot_number can be provided to evaluate against
    specific shot-level facial expressions.
    provider: 'openrouter', 'gemini', or None (auto-detect from env)
    """
    # Resolve provider (OpenRouter > Gemini API)
    try:
        provider_name, resolved_key, call_fn = resolve_provider(provider)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    if api_key:
        resolved_key = api_key  # CLI override takes priority

    # Load manifest and get scene info
    manifest = load_manifest(manifest_path)
    version = detect_manifest_version(manifest)
    scene_info = get_scene_info(manifest, scene_number, shot_number=shot_number)
    if not scene_info:
        print(f"❌ Scene {scene_number} not found in manifest")
        sys.exit(1)

    # Validate image exists and is non-empty
    if not os.path.exists(image_path):
        print(f"❌ Image not found: {image_path}")
        sys.exit(1)
    if os.path.getsize(image_path) < 1000:
        print(f"⚠️ Image may be corrupted (only {os.path.getsize(image_path)} bytes): {image_path}")

    shot_label = f", Shot {shot_number}" if shot_number else ""
    model_name = OPENROUTER_MODEL if provider_name == "openrouter" else GEMINI_MODEL
    print(f"🔍 Evaluating Scene {scene_number}{shot_label}: {scene_info['title']}")
    print(f"   Image: {image_path}")
    print(f"   Provider: {provider_name} | Model: {model_name}")
    print(f"   Manifest version: {version}")
    print(f"   Characters: {len(scene_info['characters'])}, {scene_info['setting'][:50]}...")
    if scene_info.get("char_expressions"):
        print(f"   Facial expressions: {len(scene_info['char_expressions'])} characters")

    # Build evaluation prompt and call vision API
    eval_prompt = build_eval_prompt(scene_info)
    raw_response = call_fn(eval_prompt, image_path, resolved_key)

    # Handle OpenRouter dict response vs Gemini string response
    reasoning_text = ""
    thinking_tokens = 0
    if isinstance(raw_response, dict):
        reasoning_text = raw_response.get("reasoning", "")
        thinking_tokens = raw_response.get("thinking_tokens", 0)
        raw_response = raw_response["response"]
        if reasoning_text:
            print(f"   🧠 Thinking: {len(reasoning_text)} chars, {thinking_tokens} tokens")

    # Parse and validate response
    result = parse_eval_response(raw_response, scene_number, iteration, version)

    # Add provider metadata and reasoning to result
    result["provider"] = provider_name
    result["model"] = model_name
    if reasoning_text:
        result["reasoning"] = reasoning_text
    if thinking_tokens:
        result["thinking_tokens"] = thinking_tokens

    # Print summary
    print(f"\n   📊 Evaluation Result (Iteration {iteration}, {version}):")
    if result.get("eval_parse_error"):
        print(f"   ⚠️  Parse error — accepting image as-is")
    else:
        scores = result.get("category_scores", {})
        weights = CATEGORY_WEIGHTS_V2 if version == "v2" else CATEGORY_WEIGHTS_V1
        for cat, score in scores.items():
            weight = weights.get(cat, 0)
            label = cat.replace("_", " ").title()
            print(f"   {label}: {score}/10 (weight: {weight:.0%})")
        print(f"   Weighted Score: {result.get('score', 0)}/10")
        print(f"   Passed: {'✅ YES' if result.get('passed') else '❌ NO'}")
        if result.get("issues"):
            print(f"   Issues:")
            for issue in result["issues"]:
                print(f"     - {issue}")
        if result.get("strengths"):
            print(f"   Strengths:")
            for s in result["strengths"]:
                print(f"     + {s}")
        if result.get("refined_prompt"):
            print(f"   Refined prompt: {result['refined_prompt'][:100]}...")
        # Print expression details
        if result.get("expression_detail"):
            print(f"   Expression Detail:")
            for cid, detail in result["expression_detail"].items():
                print(f"     {cid}: expected='{detail.get('expected', '?')}' → observed='{detail.get('observed', '?')}'")

    # Save feedback JSON
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        shot_suffix = f"_shot{shot_number:02d}" if shot_number else ""
        feedback_path = os.path.join(output_dir, f"scene_{scene_number:03d}{shot_suffix}_iter{iteration}.json")
        with open(feedback_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\n   💾 Feedback saved: {feedback_path}")

    return result


# ── CLI ───────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate generated scene images (v2: facial expressions, 5 categories)")
    parser.add_argument("--manifest", required=True, help="Path to story_manifest.json")
    parser.add_argument("--scene", type=int, help="Scene number to evaluate")
    parser.add_argument("--shot", type=int, help="Shot number to evaluate (v2 manifests only)")
    parser.add_argument("--image", help="Path to the generated scene image")
    parser.add_argument("--all", action="store_true", help="Evaluate all scenes (finds images automatically)")
    parser.add_argument("--iteration", type=int, default=1, help="Iteration number (default: 1)")
    parser.add_argument("--output-dir", default=None, help="Directory for feedback JSON files")
    parser.add_argument("--api-key", default=None, help="Vision API key (overrides env)")
    parser.add_argument("--provider", choices=["openrouter", "gemini"], default=None,
                        help="Vision provider (default: auto-detect from env, OpenRouter preferred)")
    parser.add_argument("--scenes-dir", default=None, help="Directory containing scene images (for --all)")

    args = parser.parse_args()

    if not args.scene and not args.all:
        parser.print_help()
        sys.exit(1)

    api_key = args.api_key or os.environ.get("GEMINI_API_KEY", "")

    if args.all:
        # Evaluate all scenes
        manifest = load_manifest(args.manifest)
        version = detect_manifest_version(manifest)
        scenes_dir = args.scenes_dir or os.path.dirname(args.manifest)
        output_dir = args.output_dir or os.path.join(DEFAULT_OUTPUT_DIR, manifest.get("title", "story"), "feedback")
        os.makedirs(output_dir, exist_ok=True)

        for scene in manifest.get("scenes", []):
            num = scene["scene_number"]
            # Find the latest iteration image
            best_image = None
            final = os.path.join(scenes_dir, f"scene_{num:03d}.png")
            if os.path.exists(final):
                best_image = final
            else:
                for i in range(3, 0, -1):
                    iter_path = os.path.join(scenes_dir, f"scene_{num:03d}_iter{i}_00001_.png")
                    if os.path.exists(iter_path):
                        best_image = iter_path
                        break

            if best_image:
                # For v2 manifests, evaluate against first shot by default
                shot_num = None
                if version == "v2" and scene.get("shots"):
                    shot_num = 1  # Default to first shot
                evaluate_scene(best_image, args.manifest, num, shot_number=shot_num,
                             iteration=args.iteration, output_dir=output_dir,
                             api_key=args.api_key, provider=args.provider)
                print()
            else:
                print(f"⚠️ No image found for scene {num}, skipping")
                print()

    elif args.scene:
        if not args.image:
            print("❌ --image is required when using --scene")
            sys.exit(1)
        output_dir = args.output_dir or os.path.join(os.path.dirname(args.image), "..", "feedback")
        evaluate_scene(args.image, args.manifest, args.scene, shot_number=args.shot,
                       iteration=args.iteration, output_dir=output_dir,
                       api_key=args.api_key, provider=args.provider)