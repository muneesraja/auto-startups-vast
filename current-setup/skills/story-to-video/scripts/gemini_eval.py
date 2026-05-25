#!/usr/bin/env python3
"""
Gemini Vision Evaluation Shared Utilities
"""

import base64
import json
import os
import re
import time
import urllib.request
import urllib.error

# Constants
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
PASS_THRESHOLD = 7.0

# Evaluation weights
CATEGORY_WEIGHTS_V2 = {
    "character_accuracy": 0.30,
    "facial_expression": 0.25,
    "scene_composition": 0.20,
    "action_depicted": 0.15,
    "style_consistency": 0.10,
}

CATEGORY_WEIGHTS_V1 = {
    "character_accuracy": 0.40,
    "scene_composition": 0.25,
    "action_depicted": 0.20,
    "style_consistency": 0.15,
}

# Alias for generate_scene.py compat
CATEGORY_WEIGHTS = CATEGORY_WEIGHTS_V2


def encode_image(image_path):
    """Read and base64-encode an image file."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_gemini_vision(prompt_text, image_path, api_key, model=GEMINI_MODEL, max_retries=2, retry_delay=3):
    """Call Gemini API with image + text, return raw response string."""
    img_b64 = encode_image(image_path)

    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/png")

    payload = {
        "contents": [{"parts": [
            {"text": prompt_text},
            {"inline_data": {"mime_type": mime_type, "data": img_b64}},
        ]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
        }
    }

    url = f"{GEMINI_API_URL}/{model}:generateContent?key={api_key}"
    req_data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=req_data,
                                 headers={"Content-Type": "application/json"})

    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode())
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "text" in part:
                        return part["text"]
            return json.dumps({"error": "No text in Gemini response", "raw": data})
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()[:500]
            if e.code == 429 and attempt < max_retries:
                wait = retry_delay * (attempt + 1)
                print(f"   ⏳ Rate limited, retrying in {wait}s...")
                time.sleep(wait)
                req = urllib.request.Request(url, data=req_data,
                                             headers={"Content-Type": "application/json"})
                continue
            return json.dumps({"error": f"Gemini HTTP {e.code}", "details": error_body})
        except urllib.error.URLError as e:
            if attempt < max_retries:
                time.sleep(retry_delay)
                continue
            return json.dumps({"error": f"Gemini connection error: {str(e)}"})
        except Exception as e:
            return json.dumps({"error": f"Gemini error: {str(e)}"})

    return json.dumps({"error": "Max retries exceeded"})


def compute_weighted_score(category_scores, version="v2", legacy_math=False):
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

    if legacy_math:
        # evaluate_scene.py math logic (with potential double division scaling)
        if weight_sum < sum(weights.values()):
            return round(total / weight_sum * (1.0 / (weight_sum / sum(weights.values()))), 2)
        return round(total, 2)
    else:
        # standard weighted average
        if weight_sum < sum(weights.values()):
            return round(total / weight_sum, 2)
        return round(total, 2)


def build_eval_prompt(expected_description, version="v2"):
    """Build evaluation prompt from expected description."""
    if version == "v2":
        return f"""You are evaluating an AI-generated scene image against its description.

{expected_description}

STEP 1 - DESCRIBE WHAT YOU SEE:
Before scoring, describe exactly what you see in the image. List every visible character and their position.
For EACH character with a specified facial expression, describe their face in detail:
- What is their mouth doing? (smiling, frowning, neutral, open, etc.)
- What are their eyes doing? (wide, narrowed, looking somewhere specific, closed?)
- What is their brow/forehead doing? (flat, furrowed, raised, relaxed?)
- Overall emotional impression of their face?

Then describe the setting, action, and overall style/mood.

STEP-2 - SCORE BY CATEGORY:
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
        return f"""You are evaluating an AI-generated scene image against its expected description.

EXPECTED SCENE DESCRIPTION:
{expected_description}

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


def parse_eval_response(response_text):
    """Parse Gemini evaluation response, handling various JSON formats."""
    text = response_text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)

    # Remove control characters that break JSON parsing
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', text)

    try:
        result = json.loads(text, strict=False)
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]+\}', text)
        if match:
            candidate = match.group()
            try:
                result = json.loads(candidate, strict=False)
            except json.JSONDecodeError:
                depth = 0
                start = text.find('{')
                if start != -1:
                    for i in range(start, len(text)):
                        if text[i] == '{':
                            depth += 1
                        elif text[i] == '}':
                            depth -= 1
                            if depth == 0:
                                try:
                                    result = json.loads(text[start:i+1], strict=False)
                                    break
                                except json.JSONDecodeError:
                                    continue
                    else:
                        return None
                else:
                    return None
        else:
            return None

    # Normalize category scores
    if "category_scores" in result:
        scores = result["category_scores"]
        if isinstance(scores, str):
            try:
                scores = json.loads(scores)
            except:
                scores = {}
        result["category_scores"] = scores

    # Compute weighted score if not present
    if "score" not in result or result["score"] == 0:
        result["score"] = compute_weighted_score(result.get("category_scores", {}))

    if "expression_detail" not in result:
        result["expression_detail"] = {}

    return result
