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

MOTION_EVAL_PROMPT_V1 = """
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

# V2 prompt (2026-06-11, elephant story run) — explicitly anchors on FF + LF stills,
# forces ranked comparison, demands per-frame visual evidence, and weights LF-arrival
# as the dominant signal. Calibration against hand-scored judgments on shot 1.2 of the
# elephant story showed v2 agreed with human ranking (B > A > C) at 0.35 weighted
# distance, vs v1 which was off by 2 positions. See references/fflf-production-learnings.md
# for full calibration notes.
#
# Why these specific design choices:
# - FF + LF included as actual image attachments: the model no longer has to
#   remember/reconstruct the target from text descriptions, eliminating a major
#   source of evaluation drift between runs.
# - 3 frames per video (10% / 50% / 90%) instead of 5: the 90% frame is the
#   only one that actually correlates with LF-arrival. 10% catches early
#   trajectory divergence. 50% catches frozen-middle and mid-motion issues.
# - Forced a/b/c comparison instead of independent scoring: kills the
#   "all three look great, give them all 9" failure mode where the model
#   produces nearly identical scores for all candidates.
# - LF-arrival weighted at 35% with explicit "chain-cleanliness > prettiness"
#   tie-breaker: the only thing that matters for the next shot in the chain
#   is whether this shot's tail frame matches the LF.
# - "Cite ONE specific visual observation" mandatory per video: kills hand-waving
#   "this looks smoother" claims without pointing to actual pixels.
# - temperature=0.2 (set in call site): same prompt + same images + same answer
#   on re-runs. v1 had no temp control and produced different winners across runs.
MOTION_EVAL_PROMPT = """You will evaluate 3 candidate videos (A, B, C) for one shot of an FFLF (First-Frame-Last-Frame) animation pipeline.

GOAL: pick the video that will chain CLEANLY into the next shot. The video that "looks best in isolation" is NOT necessarily the winner — chain-cleanliness matters more than prettiness.

WHAT YOU WILL SEE (in this exact order):
- Image 1: **First Frame (FF)** — where the shot MUST start
- Image 2: **Last Frame (LF)** — where the shot MUST end
- Image 3: Video A — frame 1 (10% in)
- Image 4: Video A — frame 2 (50% in)
- Image 5: Video A — frame 3 (90% in)
- Image 6: Video B — frame 1
- Image 7: Video B — frame 2
- Image 8: Video B — frame 3
- Image 9: Video C — frame 1
- Image 10: Video C — frame 2
- Image 11: Video C — frame 3

MOTION PROMPT (what the shot should DO):
"{motion_prompt}"

SCORING RUBRIC — score each video 0-10 on these 4 axes:

1. **LF-arrival accuracy (35%)**: Frame 3 (90% in) of the video should already closely resemble the LF image (Image 2). Same character pose, same camera framing, same background. If frame 3 looks nothing like LF, the next shot will NOT chain. (Cite the visual delta in 1 sentence.)

2. **Motion prompt faithfulness (30%)**: Does the actual motion match the prompt? For this shot: does the foot actually slide forward on wet moss with a slight wobble? Are moss displacement / water droplets visible? (If the prompt says "foot slides" and the video shows the camera panning away from the foot, that is FAIL even if it looks pretty.)

3. **Smoothness (20%)**: Are the 3 frames a smooth progression? Any sudden jumps, flicker, frozen frames, or background warping? (15% of overall — chain-cleanliness is more important than raw smoothness.)

4. **Subject consistency (15%)**: Does the chibi baby elephant foot stay consistent across all 3 frames of this video? (Skin color, chibi proportions, the mossy stone texture.)

TIE-BREAKERS (in order):
- LF-arrival accuracy is the STRONGEST signal. If one video's frame 3 clearly matches the LF and another's doesn't, the LF-match wins even at the cost of smoothness.
- A video with smooth motion that fails to reach the LF is WORSE than a slightly jerky video that arrives at the LF.
- Among videos with similar LF-arrival, prefer the one whose middle frame (50%) shows the most plausible interpolation between FF and LF.

FOR EACH VIDEO, in your reasoning, cite ONE specific visual observation from that video's frames. Do not generalize.

RESPOND ONLY WITH THIS JSON (no other text, no markdown fences):
{{"a":{{"lf_arrival":N,"prompt_match":N,"smoothness":N,"consistency":N,"weighted":N,"note":"<one short observation citing a specific frame>"}},"b":{{"lf_arrival":N,"prompt_match":N,"smoothness":N,"consistency":N,"weighted":N,"note":"..."}},"c":{{"lf_arrival":N,"prompt_match":N,"smoothness":N,"consistency":N,"weighted":N,"note":"..."}},"winner":"a"|"b"|"c","reason":"<2-3 sentences max, evidence-based>"}}"""

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


def extract_preview_keyframes(video_path, prefix, output_dir, num_frames=3):
    """Extract representative frames from a video.

    Default: 3 frames at ~10% / 50% / 90% of the timeline. These positions are
    chosen because:
    - 10% catches early trajectory divergence from the FF
    - 50% catches frozen-middle and mid-motion artifacts
    - 90% correlates with LF-arrival accuracy (the strongest chain signal)

    The 10/50/90 split outperformed the legacy 0/25/50/75/100 split in
    calibration on the elephant story (2026-06-11) because 0% and 100% are
    always nearly identical to FF and LF respectively and add noise.
    """
    duration_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nokey=1:noprint_wrappers=1", video_path
    ]
    try:
        result = subprocess.run(duration_cmd, capture_output=True, text=True, timeout=10)
        dur = float(result.stdout.strip()) if result.stdout.strip() else 5.0
    except Exception:
        dur = 5.0
    print(f"   🎞️  Video: {os.path.basename(video_path)} ({dur:.2f}s)")

    if num_frames == 3:
        # V2 sampling: 10% / 50% / 90%
        pcts = [0.10, 0.50, 0.90]
    else:
        # Legacy V1 sampling: 0% / 25% / 50% / 75% / 100%
        pcts = [0.0, 0.25, 0.50, 0.75, 1.0]

    extracted = []
    for i, pct in enumerate(pcts):
        second = pct * dur
        out_name = f"{prefix}_frame_{i}.png"
        out_path = os.path.join(output_dir, out_name)
        # Use -ss before -i for fast keyframe-accurate seek
        cmd = [
            "ffmpeg", "-y", "-ss", f"{second:.2f}", "-i", video_path,
            "-frames:v", "1", "-q:v", "2", out_path
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
                extracted.append(out_path)
        except Exception as e:
            print(f"      ❌ ffmpeg extraction error at {pct*100:.0f}%: {e}")

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

def call_vision_multi(prompt_text, image_paths, api_key, provider_name, model_name,
                      anchor_image_paths=None, temperature=0.2, max_tokens=1500):
    """Call the vision API with multiple images.

    Args:
        prompt_text: the evaluation prompt
        image_paths: list of video-frame paths to attach (preview frames, in order)
        api_key, provider_name, model_name: routing
        anchor_image_paths: optional list of reference images to send FIRST
            (e.g. [first_frame_path, last_frame_path]) so the model can
            directly compare preview frames against the actual target FF + LF
        temperature: sampling temperature. 0.2 for deterministic eval
            (vs v1 default of 1.0 which produced different winners across runs)
        max_tokens: response budget
    """
    if anchor_image_paths is None:
        anchor_image_paths = []

    if provider_name == "openrouter":
        content = [{"type": "text", "text": prompt_text}]
        # Anchors first (FF, LF) — model sees the target before the candidates
        for path in anchor_image_paths:
            if path and os.path.exists(path):
                b64 = encode_image(path)
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"}
                })
        # Then preview frames
        for path in image_paths:
            b64 = encode_image(path)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"}
            })

        payload = {
            "model": model_name,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": content}]
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        req = urllib.request.Request(OPENROUTER_API_URL, data=json.dumps(payload).encode(), headers=headers)

        try:
            with urlopen_with_retry(req, timeout=180) as resp:
                data = json.loads(resp.read().decode())
            choice = data.get("choices", [{}])[0]
            reasoning = choice.get("message", {}).get("reasoning", "")
            response = choice.get("message", {}).get("content", "")
            return {"response": response, "reasoning": reasoning}
        except Exception as e:
            raise RuntimeError(f"OpenRouter Multi call failed: {e}")

    else:  # Gemini
        parts = [{"text": prompt_text}]
        for path in anchor_image_paths:
            if path and os.path.exists(path):
                b64 = encode_image(path)
                parts.append({"inline_data": {"mime_type": "image/png", "data": b64}})
        for path in image_paths:
            b64 = encode_image(path)
            parts.append({"inline_data": {"mime_type": "image/png", "data": b64}})

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }

        url = f"{GEMINI_API_URL}/{model_name}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})

        try:
            with urlopen_with_retry(req, timeout=180) as resp:
                data = json.loads(resp.read().decode())
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "text" in part:
                        return {"response": part["text"], "reasoning": ""}
            raise RuntimeError("No text in Gemini multi response")
        except Exception as e:
            raise RuntimeError(f"Gemini Multi call failed: {e}")


def _parse_v2_eval_response(response_text, reasoning_text=""):
    """Parse the V2 a/b/c format into the legacy selected_index/scores format.

    V2 response shape: {"a": {"lf_arrival": N, ...}, "b": ..., "c": ..., "winner": "a"|"b"|"c", "reason": "..."}
    Legacy shape:      {"selected_index": N, "scores": [{"index": 0, "overall": N, ...}, ...], "reasoning": "..."}
    """
    if response_text.startswith("```"):
        response_text = re.sub(r'^```(?:json)?\s*\n?', '', response_text)
        response_text = re.sub(r'\n?```\s*$', '', response_text)

    raw = json.loads(response_text)
    winner_letter = (raw.get("winner") or "a").lower()
    letter_to_idx = {"a": 0, "b": 1, "c": 2}
    selected_index = letter_to_idx.get(winner_letter, 0)

    scores = []
    for letter in ("a", "b", "c"):
        v = raw.get(letter, {})
        w = v.get("weighted")
        # Recompute weighted if missing or 0 (defensive — model should provide it)
        if not w:
            lf = v.get("lf_arrival", 0)
            pm = v.get("prompt_match", 0)
            sm = v.get("smoothness", 0)
            co = v.get("consistency", 0)
            w = round(0.35*lf + 0.30*pm + 0.20*sm + 0.15*co, 2)
        scores.append({
            "index": letter_to_idx[letter],
            "overall": w,
            "lf_arrival": v.get("lf_arrival"),
            "prompt_match": v.get("prompt_match"),
            "smoothness": v.get("smoothness"),
            "consistency": v.get("consistency"),
            "note": v.get("note", ""),
            "reasoning": v.get("note", "")
        })

    result = {
        "selected_index": selected_index,
        "scores": scores,
        "reasoning": raw.get("reason", "")
    }
    if reasoning_text:
        result["reasoning_thinking"] = reasoning_text

    # Compute confidence: lead of winner over runner-up
    sorted_scores = sorted(scores, key=lambda s: s["overall"], reverse=True)
    if len(sorted_scores) >= 2:
        result["lead_over_runnerup"] = round(sorted_scores[0]["overall"] - sorted_scores[1]["overall"], 2)
    else:
        result["lead_over_runnerup"] = 0.0

    return result


# ── Motion Evaluation Coordinator ─────────────────────────────

def evaluate_motion_previews(preview_paths, first_frame_path, last_frame_path, motion_prompt,
                             first_frame_desc=None, last_frame_desc=None, provider=None, api_key=None,
                             use_v2_prompt=True):
    """Grades 3 preview videos and returns evaluation results with selected index.

    Args:
        use_v2_prompt: if True (default), use the V2 prompt with FF + LF anchors
                       and the a/b/c ranked-comparison format. If False, use
                       the legacy V1 prompt (5 frames, 4-axis independent scoring).
    """
    provider_name, resolved_key, call_fn = resolve_provider(provider)
    if api_key:
        resolved_key = api_key

    model_name = OPENROUTER_MODEL if provider_name == "openrouter" else GEMINI_MODEL

    # Extract frames from each preview
    temp_dir = os.path.join(os.path.dirname(preview_paths[0]), "temp_frames")
    os.makedirs(temp_dir, exist_ok=True)

    all_extracted = []
    print("   🎞️  Extracting frames from preview clips...")
    n_frames = 3 if use_v2_prompt else 5
    for idx, path in enumerate(preview_paths):
        prefix = f"p{idx}"
        extracted = extract_preview_keyframes(path, prefix, temp_dir, num_frames=n_frames)
        all_extracted.extend(extracted)

    expected = 3 * n_frames
    if len(all_extracted) != expected:
        raise RuntimeError(f"Failed to extract {expected} preview frames (got {len(all_extracted)})")

    if use_v2_prompt:
        # V2: use a/b/c format, send FF + LF as anchor images FIRST so the
        # model has the actual target to compare against (not just text).
        prompt = MOTION_EVAL_PROMPT.format(motion_prompt=motion_prompt)
        anchor_paths = [first_frame_path, last_frame_path]
        print(f"   🧠 Rating previews using {provider_name} (V2 prompt, FF+LF anchors, 3 frames/video)...")
        res = call_vision_multi(
            prompt, all_extracted, resolved_key, provider_name, model_name,
            anchor_image_paths=anchor_paths, temperature=0.2, max_tokens=1500
        )
        response_text = res["response"].strip()
        reasoning_text = res["reasoning"]
        try:
            eval_json = _parse_v2_eval_response(response_text, reasoning_text)
        except Exception as e:
            print(f"      ❌ Failed to parse V2 eval JSON: {e}")
            eval_json = {
                "selected_index": 0,
                "scores": [
                    {"index": 0, "overall": 7.0, "reasoning": "fallback (V2 parse failed)"},
                    {"index": 1, "overall": 6.5, "reasoning": "fallback"},
                    {"index": 2, "overall": 6.0, "reasoning": "fallback"}
                ],
                "reasoning": f"Fallback to index 0 due to V2 parse failure: {e}",
                "lead_over_runnerup": 0.0
            }
    else:
        # Legacy V1 path
        ff_desc = first_frame_desc or (os.path.basename(first_frame_path) if first_frame_path else "extracted continuation frame")
        lf_desc = last_frame_desc or (os.path.basename(last_frame_path) if last_frame_path else "expected ending frame")
        prompt = MOTION_EVAL_PROMPT_V1.format(
            first_frame_desc=ff_desc,
            last_frame_desc=lf_desc,
            motion_prompt=motion_prompt
        )
        print(f"   🧠 Rating previews using {provider_name} (V1 prompt, 5 frames/video)...")
        res = call_vision_multi(prompt, all_extracted, resolved_key, provider_name, model_name)
        response_text = res["response"].strip()
        reasoning_text = res["reasoning"]
        # Parse legacy V1 JSON
        if response_text.startswith("```"):
            response_text = re.sub(r'^```(?:json)?\s*\n?', '', response_text)
            response_text = re.sub(r'\n?```\s*$', '', response_text)
        try:
            eval_json = json.loads(response_text)
            if reasoning_text:
                eval_json["reasoning_thinking"] = reasoning_text
        except Exception as e:
            print(f"      ❌ Failed to parse V1 motion eval JSON: {e}")
            eval_json = {
                "selected_index": 0,
                "scores": [
                    {"index": 0, "overall": 7.0, "reasoning": "fallback"},
                    {"index": 1, "overall": 6.5, "reasoning": "fallback"},
                    {"index": 2, "overall": 6.0, "reasoning": "fallback"}
                ],
                "reasoning": "Fallback to index 0 due to V1 response parsing failure."
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
