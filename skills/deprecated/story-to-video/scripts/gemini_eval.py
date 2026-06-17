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
OPENROUTER_MODEL = "google/gemini-3.1-flash-lite"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
REASONING_EFFORT = "medium"  # ~2K-4K thinking tokens — optimal for image eval
REASONING_MAX_CHARS = 10000  # Cap reasoning output in JSON
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


MAX_REFERENCE_IMAGES = 3  # Max reference images per eval (generated + refs = 4 total)


def encode_image(image_path):
    """Read and base64-encode an image file."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _build_image_parts(image_path, reference_images=None):
    """Build a list of image parts for API calls.

    Args:
        image_path: Path to the generated image (always included)
        reference_images: Optional list of reference image paths (max 3)

    Returns:
        List of dicts with mime_type and base64 data
    """
    parts = []

    # Always include the generated image first
    img_b64 = encode_image(image_path)
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/png")
    parts.append({"mime_type": mime_type, "data": img_b64})

    # Add reference images (up to MAX_REFERENCE_IMAGES)
    if reference_images:
        for ref_path in reference_images[:MAX_REFERENCE_IMAGES]:
            if os.path.exists(ref_path):
                ref_b64 = encode_image(ref_path)
                ref_ext = os.path.splitext(ref_path)[1].lower()
                ref_mime = mime_map.get(ref_ext, "image/png")
                parts.append({"mime_type": ref_mime, "data": ref_b64})
            else:
                print(f"   ⚠️ Reference image not found: {ref_path}")

    return parts


def call_gemini_vision(prompt_text, image_path, api_key, model=GEMINI_MODEL,
                       reference_images=None, max_retries=2, retry_delay=3):
    """Call Gemini API with image + text, return raw response string.

    Args:
        prompt_text: The evaluation prompt
        image_path: Path to the generated image
        api_key: API key
        model: Gemini model name
        reference_images: Optional list of reference image paths (max 3)
        max_retries: Max retry attempts
        retry_delay: Delay between retries
    """
    image_parts = _build_image_parts(image_path, reference_images)

    # Build Gemini content parts (text + images)
    parts = [{"text": prompt_text}]
    for img in image_parts:
        parts.append({"inline_data": {"mime_type": img["mime_type"], "data": img["data"]}})

    payload = {
        "contents": [{"parts": parts}],
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


def call_openrouter_vision(prompt_text, image_path, api_key, model=OPENROUTER_MODEL,
                           reference_images=None, reasoning_effort=REASONING_EFFORT,
                           max_retries=2, retry_delay=3):
    """Call OpenRouter API with image + text using OpenAI-compatible format.

    Args:
        prompt_text: The evaluation prompt
        image_path: Path to the generated image
        api_key: API key
        model: OpenRouter model name
        reference_images: Optional list of reference image paths (max 3)
        reasoning_effort: Thinking token budget ("low", "medium", "high")
        max_retries: Max retry attempts
        retry_delay: Delay between retries

    Returns dict with:
        - response: str (the evaluation JSON text)
        - reasoning: str (thinking chain, capped at REASONING_MAX_CHARS)
        - thinking_tokens: int (token count from usage)
    """
    image_parts = _build_image_parts(image_path, reference_images)

    # Build OpenAI-compatible content array (text + images)
    content = [{"type": "text", "text": prompt_text}]
    for img in image_parts:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{img['mime_type']};base64,{img['data']}"}
        })

    payload = {
        "model": model,
        "max_tokens": 10000,
        "reasoning": {"effort": reasoning_effort},
        "messages": [{"role": "user", "content": content}]
    }

    req_data = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(OPENROUTER_API_URL, data=req_data, headers=headers)

    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())

            # Extract response text and reasoning
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            response_text = message.get("content", "")
            reasoning_text = message.get("reasoning", "")

            # Also check reasoning_details array (alternative format)
            if not reasoning_text:
                for rd in message.get("reasoning_details", []):
                    if isinstance(rd, dict) and "text" in rd:
                        reasoning_text += rd["text"] + "\n"

            # Cap reasoning output
            if len(reasoning_text) > REASONING_MAX_CHARS:
                reasoning_text = reasoning_text[:REASONING_MAX_CHARS] + "\n[truncated]"

            thinking_tokens = data.get("usage", {}).get("reasoning_tokens", 0)

            if not response_text:
                return {"response": json.dumps({"error": "No text in OpenRouter response", "raw": data}),
                        "reasoning": reasoning_text, "thinking_tokens": thinking_tokens}

            return {"response": response_text, "reasoning": reasoning_text.strip(),
                    "thinking_tokens": thinking_tokens}

        except urllib.error.HTTPError as e:
            error_body = e.read().decode()[:500]
            if e.code == 429 and attempt < max_retries:
                wait = retry_delay * (attempt + 1)
                print(f"   ⏳ Rate limited, retrying in {wait}s...")
                time.sleep(wait)
                req = urllib.request.Request(OPENROUTER_API_URL, data=req_data, headers=headers)
                continue
            return {"response": json.dumps({"error": f"OpenRouter HTTP {e.code}", "details": error_body}),
                    "reasoning": "", "thinking_tokens": 0}
        except urllib.error.URLError as e:
            if attempt < max_retries:
                time.sleep(retry_delay)
                continue
            return {"response": json.dumps({"error": f"OpenRouter connection error: {str(e)}"}),
                    "reasoning": "", "thinking_tokens": 0}
        except Exception as e:
            return {"response": json.dumps({"error": f"OpenRouter error: {str(e)}"}),
                    "reasoning": "", "thinking_tokens": 0}

    return {"response": json.dumps({"error": "Max retries exceeded"}),
            "reasoning": "", "thinking_tokens": 0}


def resolve_provider(provider=None):
    """Resolve which vision provider to use.
    
    Priority: OpenRouter > Gemini CLI/agy > Gemini API.
    Returns (provider_name, api_key_or_none, call_function).
    """
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")

    if provider == "openrouter" or (provider is None and openrouter_key):
        if not openrouter_key:
            raise ValueError("OPENROUTER_API_KEY not set in environment")
        return ("openrouter", openrouter_key, call_openrouter_vision)

    if provider == "gemini" or (provider is None and gemini_key):
        if not gemini_key:
            raise ValueError("GEMINI_API_KEY not set in environment")
        return ("gemini", gemini_key, call_gemini_vision)

    raise ValueError(
        "No vision API key found. Set OPENROUTER_API_KEY (preferred) or GEMINI_API_KEY in environment."
    )


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


def build_eval_prompt(expected_description, version="v2", reference_names=None):
    """Build evaluation prompt from expected description.

    Args:
        expected_description: The expected scene description text
        version: Prompt version ("v1" or "v2")
        reference_names: Optional list of reference image filenames being provided
    """
    # Build reference instruction block
    ref_instruction = ""
    if reference_names:
        ref_list = ", ".join(reference_names)
        ref_instruction = f"""
REFERENCE IMAGES PROVIDED:
The following reference images are attached for visual comparison:
- Image 1: The generated scene image (evaluate this)
{chr(10).join(f"- Image {i+2}: {name} (character/style reference)" for i, name in enumerate(reference_names))}

You MUST compare the generated image against the reference images to verify:
- Character appearance matches reference sheets (colors, features, proportions, clothing)
- Character identity is consistent with the reference design
- Style matches the reference aesthetic

"""

    # Landscape instruction (when no characters present)
    landscape_instruction = """
LANDSCAPE/ENVIRONMENT SHOT NOTE:
If no characters are specified in this scene, set character_accuracy and facial_expression to null
(do not include them in category_scores). These categories only apply when characters are present.
The weighted score will automatically exclude null categories.
"""

    if version == "v2":
        return f"""You are evaluating an AI-generated scene image against its description.
{ref_instruction}{expected_description}

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
1. Character Accuracy (30% weight): Do characters match their identity specs AND the provided reference images? Correct colors, features, clothing, proportions? If no characters are in the scene, set to null.
2. Facial Expression (25% weight): Does each character's facial expression match the expected expression described above? Score 10 for exact match, 7 for close approximation, 4 for partially matching, 1 for completely wrong expression. If a character's face is not visible (turned away or too small), score N/A and exclude from average. If no characters are in the scene, set to null.
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
    "character_accuracy": 0 or null if no characters,
    "facial_expression": 0 or null if no characters,
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
{ref_instruction}
EXPECTED SCENE DESCRIPTION:
{expected_description}

STEP 1 - DESCRIBE WHAT YOU SEE:
Before scoring, describe exactly what you see in the image. List every visible character, their appearance, the setting, the action, and the overall style/mood.

STEP 2 - SCORE BY CATEGORY:
Rate each category 0-10:
1. Character Accuracy (40% weight): Do characters match their identity specs AND the provided reference images? Correct colors, features, clothing? If no characters are in the scene, set to null.
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
    "character_accuracy": 0 or null if no characters,
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
