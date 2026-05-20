#!/usr/bin/env python3
"""
Story-to-Video: Scene Generator (v2)
======================================
Generates scene images via ComfyUI Qwen Image Edit 2511 API.

v2 changes:
- Supports v2 manifests with per-shot generation
- Shot-level prompts include facial_expression per character
- 5-category evaluation (character_accuracy, facial_expression, scene_composition,
  action_depicted, style_consistency) with updated weights
- Expression_detail tracking in evaluation output
- Scene context + target expressions passed to Gemini evaluator

Usage:
    python3 generate_scene.py --manifest story_manifest.json --scene 1 [--seed 42]
    python3 generate_scene.py --manifest story_manifest.json --all
    python3 generate_scene.py --manifest story_manifest.json --all --url https://my-comfyui.example.com
    python3 generate_scene.py --manifest story_manifest.json --scene 1 --shot 2 --evaluate

Requires: curl (Cloudflare blocks Python urllib)
Tested: RTX 3090, 6 scenes, ~3 min total
"""
import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error

from expression_engine import expand_expression, expand_expressions_for_shot

# ── Defaults ──────────────────────────────────────────────────
DEFAULT_BASE_URL = "https://comfy-instance_mandi-qwen.muneesraja.com"
DEFAULT_OUTPUT_DIR = "/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video"
MAX_ITERATIONS_DEFAULT = 3
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
PASS_THRESHOLD = 7.0

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

# Character → reference image filename mapping (override per story via manifest)
DEFAULT_REF_IMAGES = {
    "hare": "hare_reference_sheet.png",
    "tortoise": "tortoise_reference_sheet.png",
    "squirrel": "squirrel_reference_sheet.png",
    "fox": "fox_reference_sheet.png",
    "forest_animals": "forest_animals_reference_sheet.png",
}

# Fallbacks when a character ref is missing from the instance
DEFAULT_FALLBACKS = {
    "fox": "tortoise_reference_sheet.png",
}


# ── Manifest Version Detection ──────────────────────────────

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


# ── API Helpers ──────────────────────────────────────────────

def curl_json(method, endpoint, base_url, data=None, timeout=30):
    """Make ComfyUI API call via curl (avoids Cloudflare 403 on urllib)."""
    cmd = ["curl", "-s", "-X", method, f"{base_url}{endpoint}"]
    if data is not None:
        cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(data)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def wait_for_prompt(prompt_id, base_url, poll_interval=5, max_wait=180):
    """Poll /history/{prompt_id} until completion or error."""
    start = time.time()
    while time.time() - start < max_wait:
        data = curl_json("GET", f"/history/{prompt_id}", base_url)
        if prompt_id in data:
            info = data[prompt_id]
            status = info.get("status", {}).get("status_str", "unknown")
            if status == "success":
                return info.get("outputs", {})
            elif status == "error":
                msgs = info.get("status", {}).get("messages", [])
                for msg in msgs:
                    if msg[0] == "execution_error":
                        raise RuntimeError(
                            f"Node {msg[1]['node_id']} ({msg[1]['node_type']}): "
                            f"{msg[1]['exception_message']}"
                        )
                raise RuntimeError(f"Execution error: {json.dumps(msgs)[:500]}")
        time.sleep(poll_interval)
    raise TimeoutError(f"Prompt {prompt_id} timed out after {max_wait}s")


def download_output(filename, output_path, base_url, subfolder=""):
    """Download an output image from ComfyUI."""
    url = f"{base_url}/view?filename={filename}&subfolder={subfolder}&type=output"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    subprocess.run(["curl", "-s", "-o", output_path, url], timeout=60)
    return os.path.exists(output_path)


def get_available_images(base_url):
    """Query ComfyUI for available input images."""
    data = curl_json("GET", "/object_info/LoadImage", base_url)
    try:
        images = data["LoadImage"]["input"]["required"]["image"][0]
        return set(images)
    except (KeyError, TypeError):
        return set()


def upload_image(filepath, base_url, name=None):
    """Upload an image to ComfyUI's input directory."""
    name = name or os.path.basename(filepath)
    cmd = [
        "curl", "-s", "-X", "POST",
        f"{base_url}/upload/image",
        "-F", f"image=@{filepath}",
        "-F", f"name={name}",
        "-F", "overwrite=true",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return json.loads(result.stdout) if result.stdout.strip() else {}


# ── Image Selection ─────────────────────────────────────────

def build_ref_mapping(characters, available):
    """Auto-build character → reference sheet mapping using naming convention."""
    mapping = {}
    for c in characters:
        convention_name = f"{c}_reference_sheet.png"
        if convention_name in available:
            mapping[c] = convention_name
        elif c in DEFAULT_REF_IMAGES and DEFAULT_REF_IMAGES[c] in available:
            mapping[c] = DEFAULT_REF_IMAGES[c]
    return mapping


def pick_images(characters, available, ref_images, fallbacks):
    """Select up to 3 reference images. Falls back for missing characters."""
    auto_mapping = build_ref_mapping(characters, available)
    merged = {**auto_mapping, **ref_images}

    images = []
    for c in characters:
        ref = merged.get(c)
        if ref and ref in available:
            images.append(ref)
        else:
            fallback = fallbacks.get(c, "example.png")
            print(f"   ⚠️ {c} ref not on instance, using {fallback}")
            images.append(fallback)
    # Deduplicate preserving order
    unique = list(dict.fromkeys(images))
    while len(unique) < 3:
        unique.append(unique[0] if unique else "example.png")
    return unique[:3]


# ── Workflow Builder ─────────────────────────────────────────

def build_workflow(image1, image2, image3, prompt_text, seed=42, filename_prefix="scene"):
    """Build the complete Qwen Image Edit 2511 API workflow."""
    return {
        "197": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "qwen_image_edit_2511_fp8_e4m3fn.safetensors", "weight_dtype": "default"}},
        "209": {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": ["197", 0], "lora_name": "Qwen-Image-Lightning-4steps-V2.0.safetensors", "strength_model": 1}},
        "149": {"class_type": "TorchCompileModelQwenImage", "inputs": {
            "model": ["209", 0], "backend": "inductor", "fullgraph": False,
            "mode": "default", "dynamic": False, "creduce": True, "compile_shape": 64}},
        "145": {"class_type": "ModelSamplingAuraFlow", "inputs": {
            "model": ["149", 0], "shift": 3.1}},
        "75": {"class_type": "CFGNorm", "inputs": {
            "model": ["145", 0], "strength": 1.0}},
        "38": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
            "type": "qwen_image", "device": "default"}},
        "39": {"class_type": "VAELoader", "inputs": {
            "vae_name": "split_files/vae/qwen_image_vae.safetensors"}},
        "213": {"class_type": "LoadImage", "inputs": {"image": image1}},
        "175": {"class_type": "LoadImage", "inputs": {"image": image2}},
        "182": {"class_type": "LoadImage", "inputs": {"image": image3}},
        "200": {"class_type": "ImageResizeKJv2", "inputs": {
            "image": ["213", 0], "mask": ["213", 1], "width": 1280, "height": 720,
            "upscale_method": "lanczos", "keep_proportion": "total_pixels",
            "pad_color": "0, 0, 0", "crop_position": "center", "divisible_by": 32, "device": "cpu"}},
        "201": {"class_type": "ImageResizeKJv2", "inputs": {
            "image": ["175", 0], "width": 1280, "height": 720,
            "upscale_method": "lanczos", "keep_proportion": "total_pixels",
            "pad_color": "0, 0, 0", "crop_position": "center", "divisible_by": 32, "device": "cpu"}},
        "202": {"class_type": "ImageResizeKJv2", "inputs": {
            "image": ["182", 0], "width": 1280, "height": 720,
            "upscale_method": "lanczos", "keep_proportion": "total_pixels",
            "pad_color": "0, 0, 0", "crop_position": "center", "divisible_by": 32, "device": "cpu"}},
        "176": {"class_type": "EmptySD3LatentImage", "inputs": {
            "width": 1280, "height": 720, "batch_size": 1}},
        "154": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {
            "clip": ["38", 0], "prompt": prompt_text,
            "image1": ["200", 0], "image2": ["201", 0], "image3": ["202", 0]}},
        "153": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {
            "clip": ["38", 0], "prompt": prompt_text,
            "image1": ["200", 0], "image2": ["201", 0], "image3": ["202", 0]}},
        "163": {"class_type": "ConditioningZeroOut", "inputs": {
            "conditioning": ["154", 0]}},
        "88": {"class_type": "VAEEncode", "inputs": {
            "pixels": ["200", 0], "vae": ["39", 0]}},
        "172": {"class_type": "VAEEncode", "inputs": {
            "pixels": ["201", 0], "vae": ["39", 0]}},
        "180": {"class_type": "VAEEncode", "inputs": {
            "pixels": ["202", 0], "vae": ["39", 0]}},
        "162": {"class_type": "ReferenceLatent", "inputs": {
            "conditioning": ["153", 0], "latent": ["88", 0]}},
        "171": {"class_type": "ReferenceLatent", "inputs": {
            "conditioning": ["162", 0], "latent": ["172", 0]}},
        "179": {"class_type": "ReferenceLatent", "inputs": {
            "conditioning": ["171", 0], "latent": ["180", 0]}},
        "184": {"class_type": "Any Switch (rgthree)", "inputs": {
            "any_01": ["179", 0], "any_02": ["171", 0], "any_03": ["162", 0]}},
        "205": {"class_type": "Any Switch (rgthree)", "inputs": {
            "any_01": ["176", 0], "any_02": ["88", 0]}},
        "196": {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {
            "conditioning": ["184", 0], "reference_latents_method": "index_timestep_zero"}},
        "195": {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {
            "conditioning": ["163", 0], "reference_latents_method": "index_timestep_zero"}},
        "3": {"class_type": "KSampler", "inputs": {
            "model": ["75", 0], "positive": ["196", 0], "negative": ["195", 0],
            "latent_image": ["205", 0], "seed": seed, "control_after_generate": "fixed",
            "steps": 4, "cfg": 1, "sampler_name": "euler", "scheduler": "simple", "denoise": 1}},
        "8": {"class_type": "VAEDecode", "inputs": {
            "samples": ["3", 0], "vae": ["39", 0]}},
        "214": {"class_type": "SaveImage", "inputs": {
            "images": ["8", 0], "filename_prefix": filename_prefix}},
    }


# ── Manifest Loader (v2 aware) ──────────────────────────────

def load_manifest(manifest_path):
    """Load story manifest JSON and build scene data.

    For v2: returns per-shot data with facial expressions in prompts.
    For v1: backward compatible single-scene prompts.
    Returns (title, scenes_dict, version).
    """
    with open(manifest_path) as f:
        manifest = json.load(f)

    version = detect_manifest_version(manifest)
    style = manifest.get("style", "")
    char_map = {c["id"]: c["identity_spec"] for c in manifest.get("characters", [])}
    char_names = {c["id"]: c["name"] for c in manifest.get("characters", [])}
    char_personality = {c["id"]: c.get("personality_traits", "") for c in manifest.get("characters", [])}

    scenes = {}
    for scene in manifest.get("scenes", []):
        num = scene["scene_number"]
        characters = scene.get("characters_present", [])
        setting = scene.get("setting", "")
        action = scene.get("action", "")
        mood = scene.get("mood", scene.get("emotion", "neutral mood"))
        camera = scene.get("camera", "medium shot")

        # Build character identity lines
        char_descriptions = []
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

        if version == "v2" and scene.get("shots"):
            # ── v2: Build per-shot data ──
            shot_list = []
            for shot in scene["shots"]:
                shot_num = shot.get("shot_number", len(shot_list) + 1)
                shot_action = shot.get("description", action)
                shot_camera = shot.get("camera_override", camera)
                shot_expressions = shot.get("facial_expression", {})

                # Build per-shot prompt
                expr_lines = []
                char_expr_map = {}
                for cid, expr in shot_expressions.items():
                    name = char_names.get(cid, cid)
                    expanded_expr = expand_expression(expr)
                    expr_lines.append(f"- {name}: {expanded_expr}")
                    char_expr_map[cid] = expanded_expr

                prompt_parts = ["Characters in this scene must match the provided reference images exactly:"]
                prompt_parts.extend(char_descriptions)

                if expr_lines:
                    prompt_parts.append("")
                    prompt_parts.append("Facial expressions:")
                    prompt_parts.extend(expr_lines)

                prompt_parts.extend([
                    "",
                    f"Mood: {mood}.",
                    f"Action: {shot_action}.",
                    f"Scene setting: {setting}.",
                    f"Camera: {shot_camera}.",
                    f"Style: {style}.",
                ])

                shot_list.append({
                    "shot_number": shot_num,
                    "action": shot_action,
                    "camera": shot_camera,
                    "prompt": "\n".join(prompt_parts),
                    "facial_expression": char_expr_map,
                    "duration_seconds": shot.get("duration_seconds", 6),
                })

            scenes[num] = {
                "title": scene.get("title", f"Scene {num}"),
                "characters": characters,
                "shots": shot_list,
                "mood": mood,
                "setting": setting,
                "camera": camera,
                "action": action,
                "style": style,
            }
        else:
            # ── v1: Single prompt per scene ──
            prompt_parts = ["Characters in this scene must match the provided reference images exactly:"]
            prompt_parts.extend(char_descriptions)
            prompt_parts.extend([
                "",
                f"Scene setting: {setting}.",
                f"Action: {action}.",
                f"Mood: {mood}.",
                f"Camera: {camera}.",
                f"Style: {style}.",
            ])

            scenes[num] = {
                "title": scene.get("title", f"Scene {num}"),
                "characters": characters,
                "prompt": "\n".join(prompt_parts),
            }

    return manifest.get("title", "story"), scenes, version


# ── Scene Generation ─────────────────────────────────────────

def generate_scene(scene_num, scene_data, base_url, output_dir,
                   available_images, ref_images, fallbacks, seed=42,
                   filename_prefix=None):
    """Generate a single scene image."""
    images = pick_images(scene_data["characters"], available_images, ref_images, fallbacks)
    prefix = filename_prefix or f"scene_{scene_num:03d}"
    prompt = scene_data["prompt"]

    print(f"🎬 Scene {scene_num}: {scene_data['title']}")
    print(f"   Characters: {', '.join(scene_data['characters'])}")
    print(f"   Input images: {images}")
    print(f"   Seed: {seed}")
    print(f"   Prompt: {prompt[:120]}...")

    workflow = build_workflow(
        image1=images[0], image2=images[1], image3=images[2],
        prompt_text=prompt, seed=seed, filename_prefix=prefix
    )

    result = curl_json("POST", "/prompt", base_url, data={"prompt": workflow, "client_id": "story-to-video"})
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
        outputs = wait_for_prompt(prompt_id, base_url)
    except (RuntimeError, TimeoutError) as e:
        print(f"   ❌ {e}")
        return None

    for nid, out in outputs.items():
        for item in out.get("images", []):
            filename = item["filename"]
            out_path = os.path.join(output_dir, filename)
            if download_output(filename, out_path, base_url, item.get("subfolder", "")):
                size = os.path.getsize(out_path)
                print(f"   ✅ Saved: {out_path} ({size/1024:.0f} KB)")
                return out_path

    print(f"   ⚠️ No images in output")
    return None


# ═══════════════════════════════════════════════════════════════
#  GEMINI VISION EVALUATION (v2)
# ═══════════════════════════════════════════════════════════════

def call_gemini_vision(prompt_text, image_path, api_key, model=GEMINI_MODEL):
    """Call Gemini API with image + text, return raw response string."""
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/png")

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

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

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode())
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "text" in part:
                        return part["text"]
            return json.dumps({"error": "No text in Gemini response"})
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()[:500]
            if e.code == 429 and attempt < 2:
                wait = 5 * (attempt + 1)
                print(f"   ⏳ Rate limited, retrying in {wait}s...")
                time.sleep(wait)
                req = urllib.request.Request(url, data=req_data,
                                             headers={"Content-Type": "application/json"})
                continue
            return json.dumps({"error": f"Gemini HTTP {e.code}", "details": error_body})
        except Exception as e:
            return json.dumps({"error": f"Gemini error: {str(e)}"})

return json.dumps({"error": "Max retries exceeded"})


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
    # Normalize if some categories were N/A (excluded from average)
    if weight_sum < sum(weights.values()):
        return round(total / weight_sum, 2)
    return round(total, 2)


def build_eval_prompt_v2(scene_info):
    """Build v2 evaluation prompt with facial expression targets."""
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
- passed: true if weighted average score >= {PASS_THRESHOLD} AND no critical issues
- passed: false otherwise
- If false, provide a refined_prompt that adds specificity for the identified issues. Only modify parts related to the issues. Do not add global statements like "high quality" or "detailed".
- For facial expression issues: strengthen expression descriptors using the three-region rule (mouth + eyes + brow) or move expression earlier in the prompt.

STEP 5 - EXPRESSION DETAIL:
For each character that had a specified facial expression, provide expected vs observed.

Respond in this exact JSON format only:
{{"description": "what I see", "category_scores": {{"character_accuracy": 0, "facial_expression": 0, "scene_composition": 0, "action_depicted": 0, "style_consistency": 0}}, "score": 0, "passed": false, "issues": ["list"], "strengths": ["list"], "refined_prompt": "improved prompt or null if passed", "expression_detail": {{"character_id": {{"expected": "specified expression", "observed": "what you actually see"}}}}}}"""


def build_eval_prompt_v1(expected_description):
    """Build v1 evaluation prompt (4 categories, no expressions)."""
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
- passed: true if weighted average score >= {PASS_THRESHOLD} AND no critical issues
- passed: false otherwise
- If false, provide a refined_prompt that adds specificity for the identified issues. Do not add "high quality" or "detailed".

Respond in JSON only:
{{"description": "what I see", "category_scores": {{"character_accuracy": 0, "scene_composition": 0, "action_depicted": 0, "style_consistency": 0}}, "score": 0, "passed": false, "issues": ["list"], "strengths": ["list"], "refined_prompt": "improved prompt or null if passed"}}"""


def build_scene_eval_context(manifest, scene_data, scene_num, shot_num=None, version="v2"):
    """Build evaluation context from manifest data including facial expressions.

    Returns a dict with:
      - expected_description: full text description for Gemini
      - char_expressions: {character_id: expected_expression} for v2
      - scene_details: human-readable scene summary
    """
    char_names = {c["id"]: c["name"] for c in manifest.get("characters", [])}
    char_map = {c["id"]: c["identity_spec"] for c in manifest.get("characters", [])}
    char_personality = {c["id"]: c.get("personality_traits", "") for c in manifest.get("characters", [])}
    style = manifest.get("style", "")

    # Extract expression targets per character
    char_expressions = {}
    expression_lines = []

    characters = scene_data.get("characters", [])

    # Build character identity lines
    identity_lines = []
    for cid in characters:
        name = char_names.get(cid, cid)
        spec = char_map.get(cid, "")
        personality = char_personality.get(cid, "")
        if len(characters) >= 3:
            short = spec.split(",")[0] + ", " + ", ".join(spec.split(",")[1:3])
            line = f"- {name}: {short}"
        else:
            line = f"- {name}: {spec}"
        if personality:
            line += f" | Traits: {personality}"
        identity_lines.append(line)

    # For v2, get facial_expression from shot data
    if version == "v2":
        expr_map = {}
        if scene_data.get("shots") and shot_num is not None:
            for shot in scene_data["shots"]:
                if shot.get("shot_number") == shot_num:
                    expr_map = shot.get("facial_expression", {})
                    break
        elif scene_data.get("facial_expression"):
            # Fallback: scene-level expression (v2 without shots)
            expr_map = scene_data["facial_expression"]

        for cid, expr in expr_map.items():
            name = char_names.get(cid, cid)
            expanded = expand_expression(expr)
            char_expressions[cid] = expanded
            expression_lines.append(f"- {name} expected expression: {expanded}")

    # Build expected description
    setting = scene_data.get("setting", "")
    action = scene_data.get("action", "")
    mood = scene_data.get("mood", scene_data.get("emotion", ""))
    camera = scene_data.get("camera", "medium shot")

    desc_parts = []
    desc_parts.append("EXPECTED SCENE DESCRIPTION:")
    desc_parts.append("")
    desc_parts.append("Characters (must match reference images):")
    desc_parts.extend(identity_lines)

    if expression_lines:
        desc_parts.append("")
        desc_parts.append("Expected facial expressions:")
        desc_parts.extend(expression_lines)

    desc_parts.append("")
    desc_parts.append(f"Setting: {setting}")
    desc_parts.append(f"Action: {action}")
    desc_parts.append(f"Mood: {mood}")
    desc_parts.append(f"Camera: {camera}")
    desc_parts.append(f"Style: {style}")

    # Scene details summary for Gemini
    scene_detail_lines = [
        f"Scene {scene_num}" + (f", Shot {shot_num}" if shot_num else ""),
        f"Title: {scene_data.get('title', '')}",
        f"Mood: {mood}",
        f"Action: {action}",
    ]
    if expression_lines:
        scene_detail_lines.append("Target expressions: " + "; ".join(expression_lines))

    return {
        "expected_description": "\n".join(desc_parts),
        "char_expressions": char_expressions,
        "scene_details": "\n".join(scene_detail_lines),
    }


def parse_eval_response(response_text, version="v2"):
    """Parse Gemini evaluation response, handling various JSON formats."""
    # Strip markdown code fences if present
    text = response_text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)

    # Remove control characters that break JSON parsing
    # (Gemini sometimes includes literal newlines/tabs inside string values)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', text)

    try:
        result = json.loads(text, strict=False)
    except json.JSONDecodeError:
        # Try extracting the first valid JSON object from within text
        match = re.search(r'\{[\s\S]+\}', text)
        if match:
            candidate = match.group()
            try:
                result = json.loads(candidate, strict=False)
            except json.JSONDecodeError:
                # Try progressively shorter matches (greedy → first { to last })
                # Find balanced braces
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
                        print(f"   ⚠️ Could not parse eval response as JSON")
                        return None
                else:
                    print(f"   ⚠️ No JSON found in eval response")
                    return None
        else:
            print(f"   ⚠️ No JSON found in eval response")
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
        result["score"] = compute_weighted_score(result.get("category_scores", {}), version)

    # Handle expression_detail for v2
    if version == "v2" and "expression_detail" not in result:
        result["expression_detail"] = {}

    result["version"] = version
    return result


def evaluate_with_gemini(image_path, scene_info, api_key, version="v2"):
    """Evaluate a generated scene image using Gemini 2.5 Flash.

    Args:
        image_path: Path to the generated image
        scene_info: Dict from build_scene_eval_context() with expected_description, etc.
        api_key: Gemini API key
        version: "v1" or "v2" (determines eval prompt and categories)

    Returns:
        Parsed evaluation result dict or None on failure
    """
    if version == "v2":
        prompt = build_eval_prompt_v2(scene_info)
    else:
        prompt = build_eval_prompt_v1(scene_info["expected_description"])

    print(f"   🔍 Evaluating with Gemini ({version})...")

    response = call_gemini_vision(prompt, image_path, api_key)

    if not response:
        print(f"   ❌ Empty response from Gemini")
        return None

    result = parse_eval_response(response, version)
    if result is None:
        print(f"   ❌ Could not parse Gemini response")
        print(f"   Raw: {response[:200]}...")
        return None

    # Print results
    scores = result.get("category_scores", {})
    weighted = result.get("score", 0)
    passed = result.get("passed", False)
    issues = result.get("issues", [])
    strengths = result.get("strengths", [])
    expr_detail = result.get("expression_detail", {})

    categories = list(CATEGORY_WEIGHTS_V2.keys()) if version == "v2" else list(CATEGORY_WEIGHTS_V1.keys())
    print(f"   📊 Scores: " + " | ".join(f"{cat}: {scores.get(cat, 'N/A')}" for cat in categories))
    print(f"   📊 Weighted: {weighted:.1f}/10 | {'✅ PASS' if passed else '❌ FAIL'}")

    if issues:
        print(f"   ⚠️ Issues: {'; '.join(issues[:5])}")
    if strengths:
        print(f"   💪 Strengths: {'; '.join(strengths[:3])}")
    if expr_detail and version == "v2":
        for cid, detail in expr_detail.items():
            print(f"   😐 {cid}: expected='{detail.get('expected', '?')}' observed='{detail.get('observed', '?')}'")

    if not passed and result.get("refined_prompt"):
        print(f"   🔄 Refined prompt available for retry")

    return result


def generate_with_eval_loop(scene_num, scene_data, base_url, output_dir,
                            available_images, ref_images, fallbacks,
                            api_key, seed=42, max_iterations=3, version="v2",
                            manifest=None, shot_num=None):
    """Generate a scene image and evaluate with retry loop.

    For v2 manifests: can target a specific shot within the scene.
    For v1 manifests: generates the whole scene.

    Returns:
        dict with 'path', 'final_score', 'iterations', 'passed' or None on failure
    """
    # Build evaluation context
    if manifest and version == "v2":
        scene_info = build_scene_eval_context(manifest, scene_data, scene_num, shot_num, version)
    elif manifest:
        scene_info = build_scene_eval_context(manifest, scene_data, scene_num, None, version)
    else:
        scene_info = {"expected_description": scene_data.get("prompt", ""), "char_expressions": {}, "scene_details": ""}

    # For v2 with shots, use the specific shot's prompt
    if version == "v2" and scene_data.get("shots") and shot_num is not None:
        for shot in scene_data["shots"]:
            if shot.get("shot_number") == shot_num:
                scene_data = {**scene_data, "prompt": shot["prompt"]}
                break

    current_prompt = scene_data.get("prompt", "")
    current_seed = seed
    best_result = None
    best_path = None
    best_score = 0

    # Determine filename prefix
    if version == "v2" and shot_num is not None:
        filename_prefix = f"scene_{scene_num:03d}_shot{shot_num:03d}"
    else:
        filename_prefix = f"scene_{scene_num:03d}"

    for iteration in range(1, max_iterations + 1):
        print(f"\n{'='*60}")
        print(f"  Iteration {iteration}/{max_iterations} — Scene {scene_num}" +
              (f", Shot {shot_num}" if shot_num else ""))
        print(f"{'='*60}")

        # Update prompt if refined from previous evaluation
        if iteration > 1 and best_result and best_result.get("refined_prompt"):
            current_prompt = best_result["refined_prompt"]
            scene_data = {**scene_data, "prompt": current_prompt}
            print(f"   🔄 Using refined prompt from previous iteration")

        # Generate the image
        scene_data_copy = {**scene_data, "prompt": current_prompt}
        file_prefix = f"{filename_prefix}_iter{iteration}" if iteration > 1 else filename_prefix

        image_path = generate_scene(
            scene_num, scene_data_copy, base_url, output_dir,
            available_images, ref_images, fallbacks,
            seed=current_seed, filename_prefix=file_prefix
        )

        if not image_path:
            print(f"   ❌ Generation failed, retrying with different seed...")
            current_seed += 1
            continue

        # Evaluate the image
        result = evaluate_with_gemini(image_path, scene_info, api_key, version)

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
            # If passed on a later iteration, use the best version
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

        # Increment seed for next iteration
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
        description="Story-to-Video scene generator (v2: per-shot generation, facial expressions)")
    parser.add_argument("--manifest", help="Path to story_manifest.json")
    parser.add_argument("--scene", type=int, help="Generate a specific scene number")
    parser.add_argument("--shot", type=int, help="Generate a specific shot (v2 manifests only)")
    parser.add_argument("--all", action="store_true", help="Generate all scenes from manifest")
    parser.add_argument("--evaluate", action="store_true",
                        help="Evaluate generated images with Gemini Vision")
    parser.add_argument("--evaluate-only", action="store_true",
                        help="Evaluate an existing image without generating")
    parser.add_argument("--url", default=DEFAULT_BASE_URL,
                        help=f"ComfyUI base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--max-iterations", type=int, default=MAX_ITERATIONS_DEFAULT,
                        help=f"Max generation iterations (default: {MAX_ITERATIONS_DEFAULT})")
    parser.add_argument("--api-key", default=os.environ.get("GEMINI_API_KEY", ""),
                        help="Gemini API key (or set GEMINI_API_KEY env var)")
    parser.add_argument("--cleanup-iters", action="store_true",
                        help="Remove intermediate iteration images (keep only final)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip shots that already have a _final.png file")
    parser.add_argument("--auto-refine", action="store_true",
                        help="With --evaluate-only, auto-regenerate failed shots using eval refined_prompt")

    args = parser.parse_args()
    base_url = args.url
    output_dir = args.output_dir
    scenes_dir = os.path.join(output_dir, "scenes")

    # Load API key
    if not args.api_key or args.api_key == "":
        args.api_key = os.environ.get("GEMINI_API_KEY", "")

    os.makedirs(scenes_dir, exist_ok=True)

    # ── Evaluate-only mode ──
    if args.evaluate_only:
        if not args.api_key:
            print("❌ GEMINI_API_KEY required for evaluation")
            sys.exit(1)
        if not args.manifest:
            print("❌ --manifest required for evaluation context")
            sys.exit(1)

        manifest = json.load(open(args.manifest))
        version = detect_manifest_version(manifest)

        # Find image for specified scene/shot, or most recent
        if args.scene and args.shot:
            target = f"scene_{args.scene:03d}_shot{args.shot:03d}_final.png"
            image_path = os.path.join(scenes_dir, target)
            if not os.path.exists(image_path):
                # Try iter1 as fallback
                target = f"scene_{args.scene:03d}_shot{args.shot:03d}_00001_.png"
                image_path = os.path.join(scenes_dir, target)
        elif args.scene:
            # Find first matching scene image
            pattern = f"scene_{args.scene:03d}_"
            matches = [f for f in os.listdir(scenes_dir) if f.startswith(pattern) and f.endswith(("_final.png", "_00001_.png"))]
            image_path = os.path.join(scenes_dir, sorted(matches)[0]) if matches else None
        else:
            # Most recent image
            images = sorted(
                [os.path.join(scenes_dir, f) for f in os.listdir(scenes_dir)
                 if f.endswith(('.png', '.jpg', '.jpeg', '.webp'))],
                key=lambda p: os.path.getmtime(p), reverse=True
            )
            image_path = images[0] if images else None

        if not image_path or not os.path.exists(image_path):
            print(f"❌ No image found for scene {args.scene} shot {args.shot}")
            sys.exit(1)
        print(f"🔍 Evaluating: {image_path}")

        if args.scene:
            title, scenes, ver = load_manifest(args.manifest)
            scene_data = scenes.get(args.scene)
            if not scene_data:
                print(f"❌ Scene {args.scene} not found in manifest")
                sys.exit(1)
            scene_info = build_scene_eval_context(manifest, scene_data, args.scene, args.shot, version)
        else:
            scene_info = {"expected_description": "No scene context provided", "char_expressions": {}, "scene_details": ""}

        result = evaluate_with_gemini(image_path, scene_info, args.api_key, version)
        if result:
            print(f"\n📊 Final Score: {result.get('score', 0):.1f}/10 | {'✅ PASS' if result.get('passed') else '❌ FAIL'}")

            # Auto-refine: if failed and refined_prompt available, regenerate and re-eval
            if args.auto_refine and not result.get('passed') and result.get('refined_prompt'):
                if not args.scene:
                    print("   ⚠️ --auto-refine requires --scene and --shot for regeneration")
                    return

                print(f"\n🔄 Auto-refine: Using eval's refined prompt...")
                refined_prompt = result['refined_prompt']
                print(f"   Refined prompt preview: {refined_prompt[:150]}...")

                # Load manifest and discover images for generation
                title_refine, scenes_refine, ver_refine = load_manifest(args.manifest)
                scene_data_refine = scenes_refine.get(args.scene)
                if not scene_data_refine:
                    print(f"   ❌ Scene {args.scene} not found for auto-refine")
                    return

                available = get_available_images(base_url)
                ref_images_refine = {}
                manifest_refine = json.load(open(args.manifest))
                for c in manifest_refine.get("characters", []):
                    if "reference_image" in c:
                        ref_images_refine[c["id"]] = c["reference_image"]

                # Generate with refined prompt (offset seed to avoid same output)
                shot_data = {**scene_data_refine, "prompt": refined_prompt}
                filename_prefix = f"scene_{args.scene:03d}_shot{args.shot:03d}" if args.shot else f"scene_{args.scene:03d}"
                refine_seed = args.seed + 100  # Offset seed for variation

                new_path = generate_scene(
                    args.scene, shot_data, base_url, scenes_dir,
                    available, ref_images_refine, DEFAULT_FALLBACKS,
                    seed=refine_seed, filename_prefix=f"{filename_prefix}_refined"
                )

                if not new_path:
                    print(f"   ❌ Refined generation failed")
                    return

                # Re-evaluate the refined image
                print(f"   🔍 Re-evaluating refined image...")
                new_result = evaluate_with_gemini(new_path, scene_info, args.api_key, version)

                if new_result:
                    new_score = new_result.get('score', 0)
                    old_score = result.get('score', 0)
                    print(f"\n📊 Comparison: Original {old_score:.1f} → Refined {new_score:.1f}")

                    if new_score > old_score:
                        # Use refined version — copy to _final.png
                        final_path = os.path.join(scenes_dir, f"{filename_prefix}_final.png")
                        shutil.copy2(new_path, final_path)
                        print(f"   ✅ Refined version better! Copied to {final_path}")
                    else:
                        print(f"   ❌ Original was better, keeping it")

                    # Second auto-refine iteration if still failing
                    if not new_result.get('passed') and new_result.get('refined_prompt'):
                        print(f"\n🔄 Auto-refine iteration 2...")
                        refined_prompt_2 = new_result['refined_prompt']

                        shot_data_2 = {**scene_data_refine, "prompt": refined_prompt_2}
                        new_path_2 = generate_scene(
                            args.scene, shot_data_2, base_url, scenes_dir,
                            available, ref_images_refine, DEFAULT_FALLBACKS,
                            seed=refine_seed + 100, filename_prefix=f"{filename_prefix}_refined2"
                        )

                        if new_path_2:
                            print(f"   🔍 Re-evaluating refined image (iteration 2)...")
                            new_result_2 = evaluate_with_gemini(new_path_2, scene_info, args.api_key, version)
                            if new_result_2:
                                s2 = new_result_2.get('score', 0)
                                best_prev = max(old_score, new_score)
                                print(f"   📊 Iteration 2 score: {s2:.1f} (previous best: {best_prev:.1f})")
                                if s2 > best_prev:
                                    final_path = os.path.join(scenes_dir, f"{filename_prefix}_final.png")
                                    shutil.copy2(new_path_2, final_path)
                                    print(f"   ✅ Iteration 2 is best! Updated {final_path}")
                                else:
                                    print(f"   ❌ Previous version still better")
                else:
                    print(f"   ❌ Refined evaluation returned no result")
        return

    # ── Generation mode ──
    if not args.manifest:
        print("❌ --manifest required for generation")
        parser.print_help()
        sys.exit(1)

    title, scenes, version = load_manifest(args.manifest)
    manifest = json.load(open(args.manifest))

    # Discover available images on ComfyUI instance
    available = get_available_images(base_url)
    print(f"📷 Found {len(available)} available images on ComfyUI instance")

    # Load reference image mapping from manifest or defaults
    ref_images = {}
    for c in manifest.get("characters", []):
        if "reference_image" in c:
            ref_images[c["id"]] = c["reference_image"]
    fallbacks = DEFAULT_FALLBACKS

    if args.all:
        # Generate all scenes
        print(f"\📖 Generating scenes for: {title}")
        print(f"   Version: {version}")
        print(f"   Scenes: {len(scenes)}")

        results = {}
        for scene_num, scene_data in scenes.items():
            if version == "v2" and scene_data.get("shots"):
                # v2: generate each shot
                for shot in scene_data["shots"]:
                    shot_num = shot["shot_number"]

                    # Skip if final already exists
                    if args.skip_existing:
                        expected_path = os.path.join(scenes_dir, f"scene_{scene_num:03d}_shot{shot_num:03d}_final.png")
                        if os.path.exists(expected_path):
                            print(f"\n🎬 Scene {scene_num}, Shot {shot_num}: ⏭️  Skipping (final exists)")
                            results[(scene_num, shot_num)] = {"path": expected_path, "iterations": 0, "passed": None, "skipped": True}
                            continue

                    print(f"\n🎬 Scene {scene_num}, Shot {shot_num}: {scene_data.get('title', '')}")

                    if args.evaluate:
                        result = generate_with_eval_loop(
                            scene_num, scene_data, base_url, scenes_dir,
                            available, ref_images, fallbacks,
                            args.api_key, args.seed, args.max_iterations,
                            version, manifest, shot_num
                        )
                    else:
                        shot_data = {**scene_data, "prompt": shot["prompt"],
                                    "characters": scene_data.get("characters", [])}
                        path = generate_scene(
                            scene_num, shot_data, base_url, scenes_dir,
                            available, ref_images, fallbacks,
                            args.seed, filename_prefix=f"scene_{scene_num:03d}_shot{shot_num:03d}"
                        )
                        result = {"path": path, "iterations": 1, "passed": None} if path else None

                    results[(scene_num, shot_num)] = result
            else:
                # v1: single generation per scene
                if args.skip_existing:
                    expected_path = os.path.join(scenes_dir, f"scene_{scene_num:03d}_final.png")
                    if os.path.exists(expected_path):
                        print(f"\n🎬 Scene {scene_num}: ⏭️  Skipping (final exists)")
                        results[(scene_num, None)] = {"path": expected_path, "iterations": 0, "passed": None, "skipped": True}
                        continue

                print(f"\n🎬 Scene {scene_num}: {scene_data.get('title', '')}")

                if args.evaluate:
                    result = generate_with_eval_loop(
                        scene_num, scene_data, base_url, scenes_dir,
                        available, ref_images, fallbacks,
                        args.api_key, args.seed, args.max_iterations,
                        version, manifest
                    )
                else:
                    path = generate_scene(
                        scene_num, scene_data, base_url, scenes_dir,
                        available, ref_images, fallbacks, args.seed
                    )
                    result = {"path": path, "iterations": 1, "passed": None} if path else None

                results[(scene_num, None)] = result

        # Summary
        print(f"\n{'='*60}")
        print(f"  Generation Summary: {title}")
        print(f"{'='*60}")
        skipped = 0
        for key, result in results.items():
            scene_num, shot_num = key
            label = f"Scene {scene_num}" + (f", Shot {shot_num}" if shot_num else "")
            if result:
                if result.get("skipped"):
                    status = "⏭️"
                    skipped += 1
                else:
                    status = "✅" if result.get("passed") else ("⚠️" if result.get("path") else "❌")
                score = f" (score: {result.get('final_score', '?')})" if result.get("final_score") else ""
                print(f"  {label}: {status}{score} — {result.get('path', 'N/A')}")
            else:
                print(f"  {label}: ❌ Failed")
        total = len(results)
        if skipped:
            print(f"\n  ⏭️  {skipped}/{total} skipped (--skip-existing)")

    elif args.scene:
        # Generate a specific scene
        scene_data = scenes.get(args.scene)
        if not scene_data:
            print(f"❌ Scene {args.scene} not found in manifest")
            sys.exit(1)

        if version == "v2" and scene_data.get("shots") and args.shot:
            # v2: specific shot
            shot_data = None
            for shot in scene_data["shots"]:
                if shot.get("shot_number") == args.shot:
                    shot_data = shot
                    break
            if not shot_data:
                print(f"❌ Shot {args.shot} not found in Scene {args.scene}")
                sys.exit(1)

            gen_data = {**scene_data, "prompt": shot_data["prompt"]}

            if args.evaluate:
                result = generate_with_eval_loop(
                    args.scene, scene_data, base_url, scenes_dir,
                    available, ref_images, fallbacks,
                    args.api_key, args.seed, args.max_iterations,
                    version, manifest, args.shot
                )
            else:
                path = generate_scene(
                    args.scene, gen_data, base_url, scenes_dir,
                    available, ref_images, fallbacks,
                    args.seed, filename_prefix=f"scene_{args.scene:03d}_shot{args.shot:03d}"
                )
                result = {"path": path, "iterations": 1, "passed": None} if path else None
        else:
            # v1 or v2 without shots
            if args.evaluate:
                result = generate_with_eval_loop(
                    args.scene, scene_data, base_url, scenes_dir,
                    available, ref_images, fallbacks,
                    args.api_key, args.seed, args.max_iterations,
                    version, manifest
                )
            else:
                path = generate_scene(
                    args.scene, scene_data, base_url, scenes_dir,
                    available, ref_images, fallbacks, args.seed
                )
                result = {"path": path, "iterations": 1, "passed": None} if path else None

        if result:
            status = "✅ PASSED" if result.get("passed") else ("⚠️ GENERATED" if result.get("path") else "❌ FAILED")
            score = f" (score: {result.get('final_score', '?')})" if result.get("final_score") is not None else ""
            print(f"\n{status}{score}: {result.get('path', 'N/A')}")
    else:
        parser.print_help()

    # Cleanup intermediate files
    if args.cleanup_iters:
        print(f"\n🧹 Cleaning up intermediate iteration files...")
        for f in os.listdir(scenes_dir):
            if "_iter" in f and f.endswith(('.png', '.jpg')):
                os.remove(os.path.join(scenes_dir, f))
                print(f"   Removed: {f}")


if __name__ == "__main__":
    main()