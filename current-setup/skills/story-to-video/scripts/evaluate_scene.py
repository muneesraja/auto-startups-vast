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
import base64
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

# ── Constants ──────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_OUTPUT_DIR = "/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video"

# v2 weights: character_accuracy reduced, facial_expression added
CATEGORY_WEIGHTS_V2 = {
    "character_accuracy": 0.30,
    "facial_expression": 0.25,
    "scene_composition": 0.20,
    "action_depicted": 0.15,
    "style_consistency": 0.10,
}

# v1 weights (backward compat)
CATEGORY_WEIGHTS_V1 = {
    "character_accuracy": 0.40,
    "scene_composition": 0.25,
    "action_depicted": 0.20,
    "style_consistency": 0.15,
}

PASS_THRESHOLD = 7.0
MAX_RETRIES = 2
RETRY_DELAY = 3  # seconds


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
            characters = scene.get("characters_present", [])
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


# ── Gemini Vision API ─────────────────────────────────────────

def encode_image(image_path):
    """Read and base64-encode an image file."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_gemini_vision(prompt_text, image_path, api_key, model=GEMINI_MODEL):
    """Call Gemini API with image + text, return parsed JSON response."""
    img_b64 = encode_image(image_path)

    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/png")

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt_text},
                {"inline_data": {"mime_type": mime_type, "data": img_b64}},
            ]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
        }
    }

    url = f"{GEMINI_API_URL}/{model}:generateContent?key={api_key}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})

    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())

            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "text" in part:
                        return part["text"]

            return json.dumps({"error": "No text in Gemini response", "raw": data})

        except urllib.error.HTTPError as e:
            error_body = e.read().decode()[:500]
            if e.code == 429 and attempt < MAX_RETRIES:
                wait = RETRY_DELAY * (attempt + 1)
                print(f"   ⏳ Rate limited, retrying in {wait}s...")
                time.sleep(wait)
                # Re-encode for retry
                payload_retry = {
                    "contents": [{
                        "parts": [
                            {"text": prompt_text},
                            {"inline_data": {"mime_type": mime_type, "data": img_b64}},
                        ]
                    }],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.2,
                    }
                }
                req = urllib.request.Request(url, data=json.dumps(payload_retry).encode(),
                                             headers={"Content-Type": "application/json"})
                continue
            return json.dumps({"error": f"Gemini HTTP {e.code}", "details": error_body})

        except urllib.error.URLError as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            return json.dumps({"error": f"Gemini connection error: {str(e)}"})

        except Exception as e:
            return json.dumps({"error": f"Gemini unexpected error: {str(e)}"})

    return json.dumps({"error": "Max retries exceeded"})


def build_eval_prompt(scene_info):
    """Build the evaluation prompt for Gemini vision.

    v2: includes facial expression targets and shot-level details.
    v1: classic 4-category evaluation.
    """
    version = scene_info.get("version", "v1")

    if version == "v2":
        return f"""You are evaluating an AI-generated scene image against its description.

{scene_info['expected_description']}

STEP 1 - DESCRIBE WHAT YOU SEE:
Before scoring, describe exactly what you see in the image. List every visible character and their position.
For EACH character with a specified facial expression, describe their face in detail:
- What is their mouth doing? (smiling, frowning, neutral, open, etc.)
- What are their eyes doing? (wide, narrowed, looking somewhere specific, closed?)
- What is their brow/forehead doing? (flat, furrowed, raised, relaxed?)
- Overall emotional impression of their face?

Then describe the setting, action, and overall style/mood.

STEP 2 - SCORE BY CATEGORY:
Rate each category 0-10:
1. Character Accuracy (30% weight): Do characters match their identity specs? Correct colors, features, clothing?
2. Facial Expression (25% weight): Does each character's facial expression match the expected expression described above? Score 10 for exact match, 7 for close approximation, 4 for partially matching, 1 for completely wrong expression. If a character's face is not visible (turned away or too small), score N/A and exclude from average.
3. Scene Composition (20% weight): Are all specified characters present? Is the setting correct?
4. Action Depicted (15% weight): Does the scene show the described action?
5. Style Consistency (10% weight): Does the style match the described style?

Critical issues that automatically fail: missing main character, wrong setting/location, completely wrong action.

STEP 3 - IDENTIFY ISSUES:
List specific problems. For facial expression issues, be precise about which character and what was wrong.
Example: "Hare's expression is neutral instead of the specified 'confident grin, eyes determined'"

STEP 4 - DECIDE:
- passed: true if weighted average score >= {PASS_THRESHOLD} AND no critical issues (missing character, wrong setting)
- passed: false otherwise
- If false, provide a refined_prompt that adds specificity for the identified issues while preserving what worked. Only modify the parts related to the issues. Do not add global statements like "high quality" or "detailed".
- For facial expression issues: strengthen expression descriptors using the three-region rule (mouth + eyes + brow) or move expression earlier in the prompt.

STEP 5 - EXPRESSION DETAIL:
For each character that had a specified facial expression, provide:
- expected: the facial expression that was specified
- observed: what you actually see in the image

Respond in this exact JSON format only:
{{
  "description": "what I see in the image",
  "category_scores": {{
    "character_accuracy": 0,
    "facial_expression": 0,
    "scene_composition": 0,
    "action_depicted": 0,
    "style_consistency": 0
  }},
  "score": 0,
  "passed": false,
  "issues": ["list of specific problems"],
  "strengths": ["what the model got right"],
  "refined_prompt": "improved prompt or null if passed",
  "expression_detail": {{
    "character_id": {{
      "expected": "the specified facial expression",
      "observed": "what you actually see"
    }}
  }}
}}"""

    else:
        # v1 evaluation (4 categories)
        return f"""You are evaluating an AI-generated scene image against its expected description.

EXPECTED SCENE DESCRIPTION:
{scene_info['expected_description']}

STEP 1 - DESCRIBE WHAT YOU SEE:
Before scoring, describe exactly what you see in the image. List every visible character, their appearance, the setting, the action, and the overall style/mood.

STEP 2 - SCORE BY CATEGORY:
Rate each category 0-10:
1. Character Accuracy (40% weight): Do characters match their identity specs? Correct colors, features, clothing?
2. Scene Composition (25% weight): Are all specified characters present? Is the setting correct?
3. Action Depicted (20% weight): Does the scene show the described action?
4. Style Consistency (15% weight): Does the style match the described style?

Critical issues that automatically fail: missing main character, wrong setting/location, completely wrong action.

STEP 3 - IDENTIFY ISSUES:
List specific problems. Example: "Fox character is missing entirely", "Hare has green headband instead of blue"

STEP 4 - DECIDE:
- passed: true if weighted average score >= {PASS_THRESHOLD} AND no critical issues (missing character, wrong setting)
- passed: false otherwise
- If false, provide a refined_prompt that adds specificity for the identified issues while preserving what worked. Only modify the parts related to the issues. Do not add global statements like "high quality" or "detailed".

Respond in this exact JSON format only:
{{
  "description": "what I see in the image",
  "category_scores": {{
    "character_accuracy": 0,
    "scene_composition": 0,
    "action_depicted": 0,
    "style_consistency": 0
  }},
  "score": 0,
  "passed": false,
  "issues": ["list of specific problems"],
  "strengths": ["what the model got right"],
  "refined_prompt": "improved prompt or null if passed"
}}"""


def compute_weighted_score(category_scores, version="v2"):
    """Compute weighted average from raw category scores."""
    weights = CATEGORY_WEIGHTS_V2 if version == "v2" else CATEGORY_WEIGHTS_V1
    total = 0.0
    weight_sum = 0.0
    for cat, weight in weights.items():
        score = category_scores.get(cat)
        if score is not None:
            total += score * weight
            weight_sum += weight
    if weight_sum == 0:
        return 0.0
    return round(total / weight_sum * (1.0 / (weight_sum / sum(weights.values()))), 2) if weight_sum < sum(weights.values()) else round(total, 2)


def parse_eval_response(raw_text, scene_number, iteration, version="v2"):
    """Parse Gemini's response and add computed weighted score."""
    # Try to extract JSON from response
    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        json_match = re.search(r'```json\s*(.*?)\s*```', raw_text, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                return _parse_error_result(raw_text, scene_number, iteration, version)
        else:
            return _parse_error_result(raw_text, scene_number, iteration, version)

    # Check for API-level errors
    if "error" in result:
        return _parse_error_result(raw_text, scene_number, iteration, version)

    # Recompute weighted score from raw category scores (don't trust model's math)
    if "category_scores" in result:
        result["score"] = compute_weighted_score(result["category_scores"], version)

    # Check for critical issues
    critical_keywords = ["missing", "absent", "not present", "wrong setting", "incorrect setting"]
    has_critical = any(
        kw in " ".join(result.get("issues", [])).lower()
        for kw in critical_keywords
    )

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
                   iteration=1, output_dir=None, api_key=None):
    """Evaluate a single scene image against its manifest description.

    For v2 manifests, shot_number can be provided to evaluate against
    specific shot-level facial expressions.
    """
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("❌ GEMINI_API_KEY not set. Export it or pass --api-key.")
        sys.exit(1)

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
    print(f"🔍 Evaluating Scene {scene_number}{shot_label}: {scene_info['title']}")
    print(f"   Image: {image_path}")
    print(f"   Manifest version: {version}")
    print(f"   Characters: {len(scene_info['characters'])}, {scene_info['setting'][:50]}...")
    if scene_info.get("char_expressions"):
        print(f"   Facial expressions: {len(scene_info['char_expressions'])} characters")

    # Build evaluation prompt and call Gemini
    eval_prompt = build_eval_prompt(scene_info)
    raw_response = call_gemini_vision(eval_prompt, image_path, api_key)

    # Parse and validate response
    result = parse_eval_response(raw_response, scene_number, iteration, version)

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
    parser.add_argument("--api-key", default=None, help="Gemini API key (or set GEMINI_API_KEY)")
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
                             iteration=args.iteration, output_dir=output_dir, api_key=api_key)
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
                       iteration=args.iteration, output_dir=output_dir, api_key=api_key)