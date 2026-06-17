#!/usr/bin/env python3
"""
Quality Gates: Implements five structured evaluation gates using OpenRouter or Gemini API.
"""

import os
import sys
import base64
import urllib.request
import json
import re

script_dir = os.path.dirname(os.path.abspath(__file__))

from gemini_eval import (
    evaluate_image_against_reference,
    call_openrouter_vision,
    call_gemini_vision,
    OPENROUTER_API_URL,
    GEMINI_API_URL,
)

# ── Gate 1: Character Sheet QA ──────────────────────────────────────

def evaluate_character_sheet(image_path, character_info, global_style, provider, api_key):
    """Gate 1: Score a character sheet. Uses the existing QUALITY_GATE_PROMPT from gemini_eval.
    
    Args:
        image_path: Path to the generated character sheet
        character_info: Dict with keys: display_name, description, style_notes
        global_style: Global style string
        provider: "openrouter" | "gemini"
        api_key: Vision API key
    Returns:
        Dict with keys: character_likeness, style_match, expression_neutrality, overall, rejected, rejection_reason
    """
    char_name = character_info.get("display_name", "")
    char_spec = character_info.get("description", "")
    if character_info.get("style_notes"):
        char_spec += f" | Style notes: {character_info['style_notes']}"
        
    return evaluate_image_against_reference(
        image_path=image_path,
        reference_images=[],
        character_name=char_name,
        character_spec=char_spec,
        style_description=global_style,
        provider=provider,
        api_key=api_key
    )

# ── Gate 2: FF Scene Composition ────────────────────────────────────

GATE_2_PROMPT = """You are evaluating a scene composition image...
Image 1: The generated scene (evaluate this)
Image 2+: Character reference sheets

The scene was generated from this prompt: "{ff_prompt}"
Characters expected: {characters_desc}
Target style: {global_style}

Score 0-10 on these parameters:
1. composition_accuracy: Are characters placed correctly per the prompt?
2. environment_match: Does the setting match the description?
3. character_presence: Are all expected characters visible?
4. style_consistency: Does it match the target style?

Respond ONLY in JSON:
{{
  "composition_accuracy": N,
  "environment_match": N,
  "character_presence": N,
  "style_consistency": N,
  "overall": N,
  "passed": bool,
  "issues": [...]
}}"""

def evaluate_scene_composition(image_path, character_sheet_paths, ff_prompt, 
                                characters_desc, global_style, provider, api_key, model=None):
    """Gate 2: Score a raw FF scene still against its prompt and character sheets."""
    if not api_key:
        return {"error": "No API key provided", "passed": False, "overall": 0}

    if not model:
        model = "google/gemini-3.1-flash-lite" if provider == "openrouter" else "gemini-2.5-flash"

    prompt = GATE_2_PROMPT.format(
        ff_prompt=ff_prompt,
        characters_desc=characters_desc,
        global_style=global_style
    )

    return _call_gate_api(prompt, image_path, character_sheet_paths, provider, api_key, model)

# ── Gate 3: Klein Consistency Check ─────────────────────────────────

GATE_3_PROMPT = """You are comparing a character-edited image against references...
Image 1: The edited scene (evaluate this)
Image 2: The raw scene BEFORE editing (compare backgrounds)
Image 3+: Character reference sheets

Score 0-10 on these parameters:
1. character_likeness: Does each character match their reference sheet?
2. background_preservation: Is the background identical to the raw scene?
3. edit_quality: Are there artifacts, blending issues, or identity drift?

Respond ONLY in JSON:
{{
  "character_likeness": N,
  "background_preservation": N,
  "edit_quality": N,
  "overall": N,
  "passed": bool,
  "issues": [...]
}}"""

def evaluate_klein_consistency(edited_path, raw_path, character_sheet_paths, 
                                provider, api_key, model=None):
    """Gate 3: Compare Klein-edited image against raw input + character sheets."""
    if not api_key:
        return {"error": "No API key provided", "passed": False, "overall": 0}

    if not model:
        model = "google/gemini-3.1-flash-lite" if provider == "openrouter" else "gemini-2.5-flash"

    prompt = GATE_3_PROMPT
    ref_images = [raw_path] + (character_sheet_paths or [])

    return _call_gate_api(prompt, edited_path, ref_images, provider, api_key, model)

# ── Gate 4: LF Delta Verification ──────────────────────────────────

GATE_4_PROMPT = """You are comparing a First Frame (FF) and Last Frame (LF)...
Image 1: First Frame (FF)
Image 2: Last Frame (LF)

The intended change was: "{lf_edit_instruction}"

Score 0-10 on these parameters:
1. delta_accuracy: Does the LF show exactly the described change?
2. identity_preserved: Are characters visually identical between FF and LF?
3. background_preserved: Is the background/lighting unchanged?
4. delta_magnitude: Is the change subtle enough for smooth video interpolation?
   (10 = perfect subtle change, 5 = moderate, 1 = complete scene overhaul)

Respond ONLY in JSON:
{{
  "delta_accuracy": N,
  "identity_preserved": N,
  "background_preserved": N,
  "delta_magnitude": N,
  "overall": N,
  "passed": bool,
  "issues": [...]
}}"""

def evaluate_lf_delta(ff_path, lf_path, lf_edit_instruction, provider, api_key, model=None):
    """Gate 4: Compare FF vs LF to verify the edit delta is appropriate."""
    if not api_key:
        return {"error": "No API key provided", "passed": False, "overall": 0}

    if not model:
        model = "google/gemini-3.1-flash-lite" if provider == "openrouter" else "gemini-2.5-flash"

    prompt = GATE_4_PROMPT.format(lf_edit_instruction=lf_edit_instruction)
    ref_images = [lf_path]

    return _call_gate_api(prompt, ff_path, ref_images, provider, api_key, model)

# ── Gate 5: Final Video Story Coherence ─────────────────────────────

GATE_5_VIDEO_PROMPT = """Watch this video carefully, then answer:

1. What story is being told? Describe the narrative you perceive.
2. Are characters visually consistent throughout? Do they change appearance?
3. Are there any visual jumps or jarring transitions between shots?
4. Rate overall cinematic quality (1-10).

The INTENDED story was: "{story_summary}"
The characters should be: {characters_list}

Respond ONLY in JSON:
{{
  "perceived_story": "...",
  "story_matches_intent": true,
  "character_consistency": N,
  "transition_smoothness": N,
  "visual_quality": N,
  "jump_cut_timestamps": [],
  "overall_score": N,
  "passed": bool,
  "issues": [...]
}}"""

def evaluate_final_video(video_path, story_summary, characters_list, provider, api_key, model=None):
    """Gate 5: Evaluate stitched final video for story coherence.
    
    Sends video as base64 via OpenRouter's video_url content type or Gemini's inline_data.
    Uses google/gemini-3.5-flash (OpenRouter) or gemini-2.5-flash (Gemini) by default.
    """
    if not api_key:
        return {"error": "No API key provided", "passed": False, "overall_score": 0}

    if not model:
        model = "google/gemini-3.5-flash" if provider == "openrouter" else "gemini-2.5-flash"

    try:
        with open(video_path, "rb") as f:
            video_b64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return {"error": f"Failed to encode video: {str(e)}", "passed": False, "overall_score": 0}

    prompt = GATE_5_VIDEO_PROMPT.format(
        story_summary=story_summary,
        characters_list=", ".join(characters_list) if isinstance(characters_list, list) else characters_list
    )

    if provider == "openrouter":
        content = [
            {"type": "text", "text": prompt},
            {
                "type": "video_url",
                "video_url": {"url": f"data:video/mp4;base64,{video_b64}"}
            }
        ]
        payload = {
            "model": model,
            "max_tokens": 4000,
            "messages": [{"role": "user", "content": content}]
        }
        req_data = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        req = urllib.request.Request(OPENROUTER_API_URL, data=req_data, headers=headers)
        
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode())
            choice = data.get("choices", [{}])[0]
            response_text = choice.get("message", {}).get("content", "")
        except Exception as e:
            return {"error": f"OpenRouter call failed: {str(e)}", "passed": False, "overall_score": 0}
    else:
        # Direct Gemini API
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "video/mp4", "data": video_b64}}
                ]
            }],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2,
            }
        }
        url = f"{GEMINI_API_URL}/{model}:generateContent?key={api_key}"
        req_data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
        
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode())
            response_text = ""
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "text" in part:
                        response_text = part["text"]
                        break
        except Exception as e:
            return {"error": f"Gemini call failed: {str(e)}", "passed": False, "overall_score": 0}

    result = _parse_json_response(response_text)
    # Map overall_score to overall if needed
    if "overall_score" in result and "overall" not in result:
        result["overall"] = result["overall_score"]
    return result

# ── Helper Functions ────────────────────────────────────────────────

def _call_gate_api(prompt, image_path, reference_images, provider, api_key, model):
    """Encodes images and invokes the appropriate provider."""
    if provider == "openrouter":
        res = call_openrouter_vision(
            prompt_text=prompt,
            image_path=image_path,
            api_key=api_key,
            model=model,
            reference_images=reference_images,
            max_retries=1,
            retry_delay=2
        )
        raw = res.get("response", "{}")
    else:
        raw = call_gemini_vision(
            prompt_text=prompt,
            image_path=image_path,
            api_key=api_key,
            model=model,
            reference_images=reference_images,
            max_retries=1,
            retry_delay=2
        )
    return _parse_json_response(raw)

def _parse_json_response(raw):
    """Normalize and clean the API text to parse JSON safely."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', text)
    try:
        parsed = json.loads(text)
        # Handle parsed JSON mapping passed logic if missing
        if "passed" not in parsed:
            score = parsed.get("overall") or parsed.get("overall_score") or 0
            parsed["passed"] = score >= 6
        return parsed
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]+\}', text)
        if match:
            try:
                parsed = json.loads(match.group())
                if "passed" not in parsed:
                    score = parsed.get("overall") or parsed.get("overall_score") or 0
                    parsed["passed"] = score >= 6
                return parsed
            except json.JSONDecodeError:
                pass
    return {"error": f"Failed to parse JSON: {raw[:200]}", "passed": False, "overall": 0}
