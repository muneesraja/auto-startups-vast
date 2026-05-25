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
import base64
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error

# ── Defaults ──────────────────────────────────────────────────
DEFAULT_BASE_URL = "https://comfy-instance_mandi-qwen.muneesraja.com"
DEFAULT_OUTPUT_DIR = "/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video"
MAX_ITERATIONS_DEFAULT = 3
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
PASS_THRESHOLD = 7.0

# Evaluation weights
CATEGORY_WEIGHTS = {
    "character_accuracy": 0.30,
    "facial_expression": 0.25,
    "scene_composition": 0.20,
    "action_depicted": 0.15,
    "style_consistency": 0.10,
}

# Workflow templates directory (relative to this script's parent)
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "workflow-templates"
)


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

    return data


# ── Workflow Template Loader ─────────────────────────────────

def load_workflow_template(template_name, templates_dir=None):
    """Load a workflow template JSON from the templates directory.

    Args:
        template_name: Name of template (without .json extension)
        templates_dir: Override templates directory path

    Returns:
        dict: The raw workflow template with placeholder tokens
    """
    if templates_dir is None:
        templates_dir = TEMPLATES_DIR

    template_path = os.path.join(templates_dir, f"{template_name}.json")
    if not os.path.exists(template_path):
        available = [f.replace(".json", "") for f in os.listdir(templates_dir)
                     if f.endswith(".json")]
        raise FileNotFoundError(
            f"Workflow template not found: {template_path}\n"
            f"Available templates: {', '.join(available) or 'none'}"
        )

    with open(template_path) as f:
        template = json.load(f)

    # Return raw template preserving metadata starting with _
    return template


def _apply_overrides(workflow, overrides, overrides_map):
    """Apply agent-specified parameter overrides to workflow nodes.

    Args:
        workflow: The workflow dict (modified in place)
        overrides: Dict of override_name → value from prompt.json shot
        overrides_map: Dict of override_name → {"node": id, "key": input_key}
                       from template metadata
    """
    if not overrides or not overrides_map:
        return workflow

    applied = []
    for name, value in overrides.items():
        mapping = overrides_map.get(name)
        if mapping is None:
            print(f"   ⚠️ Unknown override '{name}' — skipping")
            continue

        node_id = mapping["node"]
        input_key = mapping["key"]

        if node_id not in workflow:
            print(f"   ⚠️ Override '{name}' targets node {node_id} which doesn't exist — skipping")
            continue

        workflow[node_id]["inputs"][input_key] = value
        applied.append(f"{name}={value}")

    if applied:
        print(f"   🎛️  Overrides applied: {', '.join(applied)}")

    return workflow


def _prune_unused_refs(workflow, num_refs, ref_slots, conditioning_node, conditioning_input_pattern):
    """Prune unused LoadImage nodes and their connections on the conditioning node.

    Args:
        workflow: The workflow dict (modified in place)
        num_refs: Number of actual references provided
        ref_slots: Dict mapping slot number (str/int) -> {"load_image_node": node_id, "required": bool}
        conditioning_node: Node ID of conditioning node (e.g. "104")
        conditioning_input_pattern: Pattern like "images.image_{N}"
    """
    sorted_slots = sorted(ref_slots.items(), key=lambda x: int(x[0]))

    for slot_str, info in sorted_slots:
        slot_num = int(slot_str)
        if slot_num > num_refs:
            if info.get("required", False):
                continue

            node_id = info["load_image_node"]
            if node_id in workflow:
                del workflow[node_id]

            if conditioning_node in workflow:
                input_key = conditioning_input_pattern.format(N=slot_num)
                if input_key in workflow[conditioning_node]["inputs"]:
                    del workflow[conditioning_node]["inputs"][input_key]


def _spawn_extra_refs(workflow, num_refs, template_refs, spawn_node_id_start, conditioning_node, conditioning_input_pattern):
    """Spawn new LoadImage nodes for reference slots beyond the template count.

    Args:
        workflow: The workflow dict (modified in place)
        num_refs: Number of actual references provided
        template_refs: Number of slots in the base template (e.g. 4)
        spawn_node_id_start: Starting integer for new node IDs (e.g. 1001)
        conditioning_node: Node ID of conditioning node (e.g. "104")
        conditioning_input_pattern: Pattern like "images.image_{N}"
    """
    if num_refs <= template_refs:
        return workflow

    for slot_num in range(template_refs + 1, num_refs + 1):
        spawn_id = str(spawn_node_id_start + (slot_num - template_refs - 1))

        # 1. Create LoadImage node
        workflow[spawn_id] = {
            "inputs": {
                "image": f"__REFERENCE_{slot_num}__"
            },
            "class_type": "LoadImage",
            "_meta": {"title": f"Load Image (ref {slot_num})"}
        }

        # 2. Connect to conditioning node
        if conditioning_node in workflow:
            input_key = conditioning_input_pattern.format(N=slot_num)
            workflow[conditioning_node]["inputs"][input_key] = [spawn_id, 0]

    return workflow


def _build_workflow_legacy(template, shot_data, global_cfg):
    """Build a ComfyUI API workflow by replacing template placeholders (legacy fallback)."""
    workflow = copy.deepcopy(template)

    # Build replacement map
    prompt_text = shot_data["prompt"]
    negative_prompt = shot_data.get("negative_prompt", global_cfg.get("negative_prompt", ""))
    seed = shot_data.get("seed", global_cfg.get("seed_base", 42))
    width = global_cfg["width"]
    height = global_cfg["height"]
    filename_prefix = shot_data["filename_prefix"]
    references = list(shot_data.get("references", []))

    # Pad references to ensure we have enough for the template's slots
    while len(references) < 10:
        references.append(references[0] if references else "example.png")

    # Walk the workflow dict and replace placeholder strings
    workflow_str = json.dumps(workflow)

    # String replacements
    workflow_str = workflow_str.replace("__PROMPT__", _json_escape(prompt_text))
    workflow_str = workflow_str.replace("__NEGATIVE_PROMPT__", _json_escape(negative_prompt))
    workflow_str = workflow_str.replace("__FILENAME_PREFIX__", _json_escape(filename_prefix))

    # Reference image replacements (up to 10 slots)
    for i in range(10):
        placeholder = f"__REFERENCE_{i+1}__"
        if placeholder in workflow_str:
            workflow_str = workflow_str.replace(placeholder, _json_escape(references[i]))

    # Numeric replacements
    workflow_str = workflow_str.replace('"__SEED__"', str(seed))
    workflow_str = workflow_str.replace('"__WIDTH__"', str(width))
    workflow_str = workflow_str.replace('"__HEIGHT__"', str(height))
    workflow_str = workflow_str.replace('__SEED__', str(seed))
    workflow_str = workflow_str.replace('__WIDTH__', str(width))
    workflow_str = workflow_str.replace('__HEIGHT__', str(height))

    result = json.loads(workflow_str)

    # Verify no remaining placeholders
    remaining = re.findall(r'__[A-Z_]+__', workflow_str)
    if remaining:
        print(f"   ⚠️ Unreplaced placeholders in workflow: {set(remaining)}")

    # Strip metadata keys starting with _
    return {k: v for k, v in result.items() if not k.startswith("_")}


def build_dynamic_workflow(template, shot_data, global_cfg):
    """Build a ComfyUI API workflow dynamically supporting pruning, spawning, and overrides.

    Falls back to legacy builder if template does not have _reference_slots metadata.
    """
    ref_slots = template.get("_reference_slots")
    if ref_slots is None:
        return _build_workflow_legacy(template, shot_data, global_cfg)

    # Deep copy raw template
    workflow = copy.deepcopy(template)

    # Get references and configurations
    references = list(shot_data.get("references", []))
    num_refs = len(references)

    # Limit number of references to max_references
    max_refs = template.get("_max_references", 12)
    if num_refs > max_refs:
        print(f"   ⚠️ Too many references ({num_refs}) for model max ({max_refs}). Truncating to {max_refs}.")
        references = references[:max_refs]
        num_refs = max_refs

    template_refs = template.get("_template_references", 4)
    spawn_node_id_start = template.get("_spawn_node_id_start", 1001)
    conditioning_node = template.get("_conditioning_node", "104")
    conditioning_input_pattern = template.get("_conditioning_input_pattern", "images.image_{N}")

    # Apply reference modifications
    if num_refs < template_refs:
        _prune_unused_refs(
            workflow,
            num_refs,
            ref_slots,
            conditioning_node,
            conditioning_input_pattern
        )
    elif num_refs > template_refs:
        _spawn_extra_refs(
            workflow,
            num_refs,
            template_refs,
            spawn_node_id_start,
            conditioning_node,
            conditioning_input_pattern
        )

    # Apply parameter overrides
    overrides = shot_data.get("overrides", {})
    overrides_map = template.get("_overrides_map", {})
    workflow = _apply_overrides(workflow, overrides, overrides_map)

    # Apply text substitutions
    prompt_text = shot_data["prompt"]
    negative_prompt = shot_data.get("negative_prompt", global_cfg.get("negative_prompt", ""))
    seed = shot_data.get("seed", global_cfg.get("seed_base", 42))
    width = global_cfg["width"]
    height = global_cfg["height"]
    filename_prefix = shot_data["filename_prefix"]

    # Pad references to ensure all remaining slots are replaced
    effective_refs_count = max(1, num_refs)
    padded_refs = list(references)
    while len(padded_refs) < effective_refs_count:
        padded_refs.append(padded_refs[0] if padded_refs else "example.png")

    # Walk the workflow dict and replace placeholder strings
    workflow_str = json.dumps(workflow)

    # String replacements
    workflow_str = workflow_str.replace("__PROMPT__", _json_escape(prompt_text))
    workflow_str = workflow_str.replace("__NEGATIVE_PROMPT__", _json_escape(negative_prompt))
    workflow_str = workflow_str.replace("__FILENAME_PREFIX__", _json_escape(filename_prefix))

    # Reference image replacements
    for i in range(len(padded_refs)):
        placeholder = f"__REFERENCE_{i+1}__"
        if placeholder in workflow_str:
            workflow_str = workflow_str.replace(placeholder, _json_escape(padded_refs[i]))

    # Numeric replacements
    workflow_str = workflow_str.replace('"__SEED__"', str(seed))
    workflow_str = workflow_str.replace('"__WIDTH__"', str(width))
    workflow_str = workflow_str.replace('"__HEIGHT__"', str(height))
    workflow_str = workflow_str.replace('__SEED__', str(seed))
    workflow_str = workflow_str.replace('__WIDTH__', str(width))
    workflow_str = workflow_str.replace('__HEIGHT__', str(height))

    result = json.loads(workflow_str)

    # Verify no remaining placeholders
    remaining = re.findall(r'__[A-Z_]+__', workflow_str)
    if remaining:
        print(f"   ⚠️ Unreplaced placeholders in workflow: {remaining}")

    # Strip metadata keys starting with _
    return {k: v for k, v in result.items() if not k.startswith("_")}


def _json_escape(text):
    """Escape text for safe embedding in JSON string values.

    Handles newlines, quotes, backslashes, and other special characters
    that could break the JSON structure when replacing placeholder tokens.
    """
    # json.dumps adds surrounding quotes — strip them
    return json.dumps(text)[1:-1]


# ── Scene Generation ─────────────────────────────────────────

def generate_shot(shot_data, global_cfg, workflow_template, base_url, output_dir,
                  available_images, seed_override=None):
    """Generate a single shot image using prompt.json data.

    Args:
        shot_data: Single shot object from prompt.json
        global_cfg: Global config from prompt.json
        workflow_template: Loaded workflow template dict
        base_url: ComfyUI instance URL
        output_dir: Directory to save output images
        available_images: Set of available image filenames on ComfyUI
        seed_override: Override the seed (for retry iterations)

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
                       data={"prompt": workflow, "client_id": "story-to-video"})

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

    # Download output images
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
#  GEMINI VISION EVALUATION
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


def compute_weighted_score(category_scores):
    """Compute weighted average from raw category scores."""
    total = 0.0
    weight_sum = 0.0
    for cat, weight in CATEGORY_WEIGHTS.items():
        score = category_scores.get(cat)
        if score is not None:
            total += score * weight
            weight_sum += weight
    if weight_sum == 0:
        return 0.0
    if weight_sum < sum(CATEGORY_WEIGHTS.values()):
        return round(total / weight_sum, 2)
    return round(total, 2)


def build_eval_prompt(eval_context, prompt_text):
    """Build evaluation prompt from prompt.json's eval_context.

    Args:
        eval_context: The eval_context object from a prompt.json shot
        prompt_text: The prompt that was used to generate the image
    """
    # Build expected description from eval_context
    desc_parts = ["EXPECTED SCENE DESCRIPTION:", ""]
    desc_parts.append(f"Generation prompt: {prompt_text}")
    desc_parts.append("")

    if eval_context.get("characters_present"):
        desc_parts.append(f"Characters expected: {', '.join(eval_context['characters_present'])}")

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

STEP 2 - SCORE BY CATEGORY:
Rate each category 0-10:
1. Character Accuracy (30% weight): Do characters match their identity specs? Correct colors, features, clothing?
2. Facial Expression (25% weight): Does each character's facial expression match the expected expression? Score 10 for exact match, 7 for close approximation, 4 for partially matching, 1 for completely wrong.
3. Scene Composition (20% weight): Are all specified characters present? Is the setting correct?
4. Action Depicted (15% weight): Does the scene show the described action?
5. Style Consistency (10% weight): Does the style match the described style?

Critical issues that automatically fail: missing main character, wrong setting/location, completely wrong action.

STEP 3 - IDENTIFY ISSUES:
List specific problems. For facial expression issues, be precise.

STEP 4 - DECIDE:
- passed: true if weighted average score >= {PASS_THRESHOLD} AND no critical issues
- passed: false otherwise
- If false, provide a refined_prompt that fixes the issues. Only modify parts related to the issues.

STEP 5 - EXPRESSION DETAIL:
For each character with a specified expression, provide expected vs observed.

Respond in this exact JSON format only:
{{"description": "what I see", "category_scores": {{"character_accuracy": 0, "facial_expression": 0, "scene_composition": 0, "action_depicted": 0, "style_consistency": 0}}, "score": 0, "passed": false, "issues": ["list"], "strengths": ["list"], "refined_prompt": "improved prompt or null if passed", "expression_detail": {{"character_id": {{"expected": "specified expression", "observed": "what you actually see"}}}}}}"""


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
        result["score"] = compute_weighted_score(result.get("category_scores", {}))

    if "expression_detail" not in result:
        result["expression_detail"] = {}

    return result


def evaluate_with_gemini(image_path, shot_data, api_key):
    """Evaluate a generated scene image using Gemini Vision.

    Args:
        image_path: Path to the generated image
        shot_data: Shot object from prompt.json (contains prompt + eval_context)
        api_key: Gemini API key

    Returns:
        Parsed evaluation result dict or None on failure
    """
    eval_context = shot_data.get("eval_context", {})
    prompt_text = shot_data["prompt"]
    eval_prompt = build_eval_prompt(eval_context, prompt_text)

    print(f"   🔍 Evaluating with Gemini...")

    response = call_gemini_vision(eval_prompt, image_path, api_key)

    if not response:
        print(f"   ❌ Empty response from Gemini")
        return None

    result = parse_eval_response(response)
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
                            output_dir, available_images, api_key,
                            max_iterations=3):
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
            output_dir, available_images, seed_override=current_seed
        )

        if not image_path:
            print(f"   ❌ Generation failed, retrying with different seed...")
            current_seed += 1
            continue

        # Evaluate the image
        result = evaluate_with_gemini(image_path, shot_copy, api_key)

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
                        help="Gemini API key (or set GEMINI_API_KEY env var)")
    parser.add_argument("--cleanup-iters", action="store_true",
                        help="Remove intermediate iteration images (keep only final)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip shots that already have a _final.png file")

    args = parser.parse_args()
    base_url = args.url
    output_dir = args.output_dir
    scenes_dir = os.path.join(output_dir, "scenes")

    # Load API key
    if not args.api_key:
        args.api_key = os.environ.get("GEMINI_API_KEY", "")

    os.makedirs(scenes_dir, exist_ok=True)

    # ── Load prompt.json ──
    prompts_data = load_prompts(args.prompts)
    global_cfg = prompts_data["global"]
    shots = prompts_data["shots"]

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
    available = get_available_images(base_url)
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
            result = evaluate_with_gemini(image_path, shot, args.api_key)
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

        # Skip if final already exists
        if args.skip_existing:
            expected_path = os.path.join(scenes_dir, f"{prefix}_final.png")
            if os.path.exists(expected_path):
                print(f"\n🎬 {prefix}: ⏭️  Skipping (final exists)")
                results[prefix] = {"path": expected_path, "iterations": 0,
                                   "passed": None, "skipped": True}
                continue

        if args.evaluate:
            if not args.api_key:
                print("❌ GEMINI_API_KEY required for --evaluate mode")
                sys.exit(1)

            result = generate_with_eval_loop(
                shot, global_cfg, workflow_template, base_url,
                scenes_dir, available, args.api_key, args.max_iterations
            )
        else:
            path = generate_shot(
                shot, global_cfg, workflow_template, base_url,
                scenes_dir, available
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