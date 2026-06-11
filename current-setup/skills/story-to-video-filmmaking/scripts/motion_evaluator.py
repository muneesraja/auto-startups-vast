#!/usr/bin/env python3
"""
Story-to-Video-Filmmaking: Motion Quality Evaluator (Phase 3)
============================================================
Extracts keyframes from 3 low-res preview videos and calls the Gemini/OpenRouter vision
API to select the best motion path.
"""
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error

from gemini_eval import resolve_provider, encode_image, parse_eval_response, OPENROUTER_API_URL, GEMINI_API_URL, GEMINI_MODEL, OPENROUTER_MODEL

MOTION_EVAL_PROMPT = """
You are a cinematic quality evaluator for an AI animation pipeline.
We have generated 3 Stage 1 preview videos (low-resolution drafts) for a single shot.
For each preview video, we have extracted 5 evenly spaced frames from start to end:
- Image 1 to 5: Preview 0 (Start, 25%, 50%, 75%, End)
- Image 6 to 10: Preview 1 (Start, 25%, 50%, 75%, End)
- Image 11 to 15: Preview 2 (Start, 25%, 50%, 75%, End)

The original First Frame (FF) and Last Frame (LF) compositions were:
- First Frame: {first_frame_desc}
- Last Frame: {last_frame_desc}
- Requested Motion: {motion_prompt}

Compare the 3 previews and evaluate them based on:
1. **Motion Fluidity (40%):** Does the sequence of 5 frames flow smoothly? Are there sudden jump cuts, flickering artifacts, or frozen frames?
2. **Natural Movement (25%):** Do characters and camera moves follow natural physics?
3. **Trajectory Coherence (20%):** Does the motion lead logically from the first frame design toward the last frame design?
4. **Prompt Adherence (15%):** Does the motion match the requested motion prompt?

Score each preview 0 to 10.
Decide which preview (0, 1, or 2) represents the best overall motion quality.

Respond in this exact JSON format only:
{{
  "selected_index": N,
  "scores": [
    {{
      "index": 0,
      "motion_fluidity": N,
      "natural_movement": N,
      "ff_lf_trajectory": N,
      "prompt_adherence": N,
      "overall": N,
      "reasoning": "..."
    }},
    {{
      "index": 1,
      "motion_fluidity": N,
      "natural_movement": N,
      "ff_lf_trajectory": N,
      "prompt_adherence": N,
      "overall": N,
      "reasoning": "..."
    }},
    {{
      "index": 2,
      "motion_fluidity": N,
      "natural_movement": N,
      "ff_lf_trajectory": N,
      "prompt_adherence": N,
      "overall": N,
      "reasoning": "..."
    }}
  ],
  "reasoning": "Reason for selecting preview N over the others..."
}}
"""

# ── Frame Extraction (ffmpeg) ──────────────────────────────────

def get_video_frame_count(video_path):
    """Retrieve the total number of frames in a video using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=nb_read_frames", "-of", "default=nokey=1:noprint_wrappers=1",
        video_path
    ]
    # Fallback to packet count if frame count fails
    cmd_fallback = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=nb_frames", "-of", "default=nokey=1:noprint_wrappers=1",
        video_path
    ]
    
    for c in [cmd, cmd_fallback]:
        try:
            result = subprocess.run(c, capture_output=True, text=True, timeout=15)
            val = result.stdout.strip()
            if val and val != "N/A" and val.isdigit():
                return int(val)
        except Exception:
            pass
            
    # Default fallback
    return 125  # Assumed 5s at 25fps if ffprobe fails


def extract_frame_at_index(video_path, frame_idx, output_path):
    """Extract a single frame by index using ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", fr"select=eq(n\,{frame_idx})",
        "-vframes", "1", output_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return os.path.exists(output_path)
    except Exception as e:
        print(f"      ❌ ffmpeg extraction error at frame {frame_idx}: {e}")
        return False


def extract_preview_keyframes(video_path, prefix, output_dir):
    """Extract 5 representative frames from a video."""
    num_frames = get_video_frame_count(video_path)
    print(f"   🎞️  Video: {os.path.basename(video_path)} ({num_frames} total frames)")
    
    indices = [
        0,
        int(0.25 * (num_frames - 1)),
        int(0.50 * (num_frames - 1)),
        int(0.75 * (num_frames - 1)),
        num_frames - 1
    ]
    
    extracted = []
    for i, idx in enumerate(indices):
        out_name = f"{prefix}_frame_{i}.png"
        out_path = os.path.join(output_dir, out_name)
        if extract_frame_at_index(video_path, idx, out_path):
            extracted.append(out_path)
            
    return extracted


# ── Vision API Multi-Image Request ─────────────────────────────

def urlopen_with_retry(req, timeout=120, max_retries=3, initial_delay=2.0):
    """Wraps urllib.request.urlopen with exponential backoff retries for 429/5xx and network errors."""
    for attempt in range(max_retries):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                if attempt == max_retries - 1:
                    raise
                delay = initial_delay * (2 ** attempt)
                print(f"   ⚠️ API returned HTTP {e.code}. Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(delay)
            else:
                raise
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == max_retries - 1:
                raise
            delay = initial_delay * (2 ** attempt)
            print(f"   ⚠️ Network error: {e}. Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})...")
            time.sleep(delay)

def call_vision_multi(prompt_text, image_paths, api_key, provider_name, model_name):
    """Call the vision API with multiple images (15 frames)."""
    if provider_name == "openrouter":
        content = [{"type": "text", "text": prompt_text}]
        for path in image_paths:
            b64 = encode_image(path)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"}
            })
            
        payload = {
            "model": model_name,
            "max_tokens": 4000,
            "messages": [{"role": "user", "content": content}]
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        req = urllib.request.Request(OPENROUTER_API_URL, data=json.dumps(payload).encode(), headers=headers)
        
        try:
            with urlopen_with_retry(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
            choice = data.get("choices", [{}])[0]
            reasoning = choice.get("message", {}).get("reasoning", "")
            response = choice.get("message", {}).get("content", "")
            return {"response": response, "reasoning": reasoning}
        except Exception as e:
            raise RuntimeError(f"OpenRouter Multi call failed: {e}")
            
    else:  # Gemini
        parts = [{"text": prompt_text}]
        for path in image_paths:
            b64 = encode_image(path)
            parts.append({"inline_data": {"mime_type": "image/png", "data": b64}})
            
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2
            }
        }
        
        url = f"{GEMINI_API_URL}/{model_name}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        
        try:
            with urlopen_with_retry(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "text" in part:
                        return {"response": part["text"], "reasoning": ""}
            raise RuntimeError("No text in Gemini multi response")
        except Exception as e:
            raise RuntimeError(f"Gemini Multi call failed: {e}")


# ── Motion Evaluation Coordinator ─────────────────────────────

def evaluate_motion_previews(preview_paths, first_frame_path, last_frame_path, motion_prompt,
                             first_frame_desc=None, last_frame_desc=None, provider=None, api_key=None):
    """Grades 3 preview videos and returns evaluation results with selected index."""
    provider_name, resolved_key, call_fn = resolve_provider(provider)
    if api_key:
        resolved_key = api_key
        
    model_name = OPENROUTER_MODEL if provider_name == "openrouter" else GEMINI_MODEL
    
    # Extract frames for each preview
    temp_dir = os.path.join(os.path.dirname(preview_paths[0]), "temp_frames")
    os.makedirs(temp_dir, exist_ok=True)
    
    all_extracted = []
    print("   🎞️  Extracting frames from preview clips...")
    for idx, path in enumerate(preview_paths):
        prefix = f"p{idx}"
        extracted = extract_preview_keyframes(path, prefix, temp_dir)
        all_extracted.extend(extracted)
        
    if len(all_extracted) != 15:
        raise RuntimeError(f"Failed to extract 15 preview frames (got {len(all_extracted)})")
        
    # Formulate descriptions
    ff_desc = first_frame_desc or (os.path.basename(first_frame_path) if first_frame_path else "extracted continuation frame")
    lf_desc = last_frame_desc or (os.path.basename(last_frame_path) if last_frame_path else "expected ending frame")
    
    prompt = MOTION_EVAL_PROMPT.format(
        first_frame_desc=ff_desc,
        last_frame_desc=lf_desc,
        motion_prompt=motion_prompt
    )
    
    print(f"   🧠 Rating previews using {provider_name}...")
    res = call_vision_multi(prompt, all_extracted, resolved_key, provider_name, model_name)
    response_text = res["response"].strip()
    reasoning_text = res["reasoning"]
    
    # Parse evaluation JSON
    if response_text.startswith("```"):
        response_text = re.sub(r'^```(?:json)?\s*\n?', '', response_text)
        response_text = re.sub(r'\n?```\s*$', '', response_text)
        
    try:
        eval_json = json.loads(response_text)
        if reasoning_text:
            eval_json["reasoning_thinking"] = reasoning_text
    except Exception as e:
        print(f"      ❌ Failed to parse motion eval JSON: {e}")
        # Return fallback
        eval_json = {
            "selected_index": 0,
            "scores": [
                {"index": 0, "overall": 7.0, "reasoning": "fallback"},
                {"index": 1, "overall": 6.5, "reasoning": "fallback"},
                {"index": 2, "overall": 6.0, "reasoning": "fallback"}
            ],
            "reasoning": "Fallback to index 0 due to response parsing failure."
        }
        
    # Clean up extracted frame files
    for path in all_extracted:
        try:
            os.remove(path)
        except OSError:
            pass
    try:
        os.rmdir(temp_dir)
    except OSError:
        pass
        
    return eval_json
