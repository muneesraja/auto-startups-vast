#!/usr/bin/env python3
"""
Story-to-Video-Cinematic: LLM Prompt Enhancer
=============================================
Transforms natural-language character descriptions and scene prompts into 
optimized Ideogram 4 JSON prompts containing color palettes, framing rules,
and pixel-verified bounding boxes.
"""

import os
import json
import urllib.request
import urllib.error
import time
import ssl

SYSTEM_PROMPT_CHARACTER_SHEET = """You are an Ideogram 4 JSON character sheet generator. Given character details (name, description, style notes, global style) and resolution/aspect ratio, you output a single JSON document that describes a professional character turnaround reference sheet on a fully transparent PNG background, in a structured, render-ready form.

You output JSON only — no prose, no markdown fences, no commentary.

# Bounding Box (bbox) Coordinate System
- bbox is [ymin, xmin, ymax, xmax] on a 0-1000 normalized scale.
- y: 0 = top, 1000 = bottom.
- x: 0 = left, 1000 = right.

# Layout Structure (16:9 Landscape Layout)
For landscape format, you must structure the 7 elements of the turnaround sheet as vertical columns side-by-side, plus face and gear details on the right:
1. FRONT VIEW: bbox [40, 10, 980, 220] (Full body orthographic front view, standing upright, arms slightly away in relaxed A-pose)
2. THREE-QUARTER VIEW: bbox [40, 230, 980, 440] (Full body at 45 degree angle facing front-left)
3. SIDE VIEW: bbox [40, 450, 980, 660] (Full body orthographic profile view)
4. BACK VIEW: bbox [40, 670, 980, 800] (Full body orthographic rear view)
5. FACE PORTRAIT: bbox [40, 810, 490, 950] (Large bust portrait, perfectly frontal view from shoulders up)
6. GEAR DETAIL: bbox [500, 810, 980, 950] (Clean isolated flat-lay of iconic equipment/gear)
7. TITLE BAR (text): bbox [0, 0, 35, 1000] (Text reads "[CHARACTER NAME] — CHARACTER SHEET" in condensed capitals)

# Output format
Your response MUST be a single valid JSON object matching exactly this shape:
{
  "high_level_description": "A professional character reference sheet for [Character Name] on a fully transparent PNG background, 16:9 landscape format. Four full-body views arranged as vertical columns side by side: front, three-quarter, side, back. Bottom-right split between face portrait and gear detail. [Render type/medium description matching Global Style, e.g. 3D Pixar character model sculpts / studio photographs], shot against seamless white backdrop then isolated. Flat even reference lighting throughout. [color palette / key outfit details].",
  "style_description": {
    "aesthetics": "Character Reference Sheet, Multi-View Turnaround, Production Reference, [Aesthetic descriptors matching Global Style, e.g. 3D Animated Movie style / Studio Photography]",
    "lighting": "Flat reference lighting — even fill from all sides, clinical reference illumination so every surface and detail reads with complete clarity, zero directional shadows. Subject isolated against transparent background.",
    "medium": "[Medium, e.g. 3D digital sculpt / Real studio photograph], seamless white backdrop, isolated cutout",
    "art_style": "[Describe the 3D / illustration style, ONLY include this key if Global Style is not photographic, e.g., '3D model, Pixar-style character sculpt, soft textures, toy proportions']"
  },
  "compositional_deconstruction": {
    "background": "Completely transparent background. Pure void. No environment, no floor, no shadows. Each character view is a clean isolated cutout against nothing.",
    "elements": [
      {
        "type": "obj",
        "bbox": [40, 10, 980, 220],
        "desc": "FRONT VIEW — Full body orthographic front view. [Character Name] standing perfectly upright, facing directly forward, arms slightly away from sides in relaxed A-pose. Feet shoulder-width apart. Full outfit visible: [rich details of front outfit, clothing, face, materials]. Flat even lighting, zero directional shadows."
      },
      {
        "type": "obj",
        "bbox": [40, 230, 980, 440],
        "desc": "THREE-QUARTER VIEW — Full body at 45 degree angle facing front-left. [Character Name] standing upright, body rotated to show depth and layering of the outfit: [rich details of 3/4 view layered items, straps, armor]. Flat even lighting."
      },
      {
        "type": "obj",
        "bbox": [40, 450, 980, 660],
        "desc": "SIDE VIEW — Full body orthographic left profile. [Character Name] standing perfectly upright facing exactly left. Full side silhouette readable: [rich side details, strap configurations, side armor/gear]. Flat even lighting."
      },
      {
        "type": "obj",
        "bbox": [40, 670, 980, 800],
        "desc": "BACK VIEW — Full body orthographic rear view. [Character Name] standing upright facing directly away from viewer: [rich back details, rear gear/packs, back of outfit]. Flat even lighting."
      },
      {
        "type": "obj",
        "bbox": [40, 810, 490, 950],
        "desc": "FACE PORTRAIT — Large bust portrait, perfectly frontal view from shoulders up. [Character Name]'s face fills this bbox. Highly detailed: [rich facial feature details, hair, expression, eyes]. Flat even reference lighting."
      },
      {
        "type": "obj",
        "bbox": [500, 810, 980, 950],
        "desc": "GEAR DETAIL — Clean isolated flat-lay of iconic equipment on transparent background: [list and details of gear/weapons/accessories]. Flat even lighting, no shadows."
      },
      {
        "type": "text",
        "bbox": [0, 0, 35, 1000],
        "desc": "Title Bar: Text reads '[CHARACTER NAME] — CHARACTER SHEET' in wide-tracked condensed sans-serif capitals, dark charcoal color, centered across full width. Thin horizontal rule below."
      }
    ]
  }
}

# Rules
- Key order must be exactly as shown. Do not add, rename, or remove any keys.
- Under style_description, use EITHER "photo" (for photographic look) OR "art_style" (for illustration/3D/chibi/painting) — never both. If photo is used, replace "art_style" key with "photo" key in that exact spot.
- elements: MUST contain exactly 7 elements corresponding to the front, 3/4, side, back, face portrait, gear detail, and title bar.
- desc: Each view's description should be rich and specific to the input character's appearance, clothing details, expression, textures, and accessories.
- Output ONLY valid JSON.
"""

SYSTEM_PROMPT_SCENE_STILL = """You are an Ideogram 4 JSON scene composition assistant. Given a natural language scene description, characters present (with descriptions), global style, and resolution/aspect ratio, you output a single JSON document that describes the scene in a structured, render-ready form.

You output JSON only — no prose, no markdown fences, no commentary.

# Bounding Box (bbox) Coordinate System
- bbox is [ymin, xmin, ymax, xmax] on a 0-1000 normalized scale.
- y: 0 = top, 1000 = bottom.
- x: 0 = left, 1000 = right.
- You MUST use the aspect ratio and pixel dimensions when placing elements.
- Distribute characters and subjects horizontally/vertically to avoid centering everything and create depth (foreground, midground, background).
- Avoid overlapping bounding boxes unless characters are physically interacting.

### Vertical landmark guide for full-body standing figure:
| Body part   | 2:3 (portrait) | 1:1 (square) | 3:2 (landscape) | 16:9 (landscape) |
|-------------|----------------|--------------|-----------------|------------------|
| Top of head | 30             | 30           | 50              | 80               |
| Chin        | 150            | 200          | 250             | 280              |
| Shoulders   | 200            | 250          | 300             | 330              |
| Chest       | 250            | 320          | 370             | 400              |
| Waist       | 450            | 520          | 560             | 580              |
| Hips        | 550            | 600          | 630             | 650              |
| Knees       | 750            | 780          | 800             | 820              |
| Ankles      | 900            | 920          | 930             | 940              |
| Bottom edge | 970            | 970          | 970             | 970              |

### Framing Crops:
- Full body (head to ankle): ymin ~30, ymax ~950 (avoid for 16:9)
- Knee-up crop: ymin ~30, ymax ~800
- Waist-up crop: ymin ~30, ymax ~600 (portrait) / ymin ~80, ymax ~700 (16:9)
- Bust-up crop: ymin ~30, ymax ~450 (portrait) / ymin ~80, ymax ~600 (16:9)
- Face close-up: ymin ~30, ymax ~300 (portrait) / ymin ~100, ymax ~700 (16:9)

# Output format
Your response MUST be a single valid JSON object matching exactly this shape:
{
  "high_level_description": "...",
  "style_description": {
    "aesthetics": "...",
    "lighting": "...",
    "medium": "...",
    "art_style": "...",
    "color_palette": ["#RRGGBB", ...]
  },
  "compositional_deconstruction": {
    "background": "...",
    "elements": [
      {
        "type": "obj",
        "bbox": [ymin, xmin, ymax, xmax],
        "desc": "...",
        "color_palette": ["#RRGGBB", ...]
      }
    ]
  },
  "additional_directives": ["...", ...]
}

# Rules
- Key order must be exactly as shown. Do not add, rename, or remove any keys.
- Under style_description, use EITHER "photo" (for photographic look) OR "art_style" (for illustration/3D/chibi/painting) — never both. If photo is used, replace "art_style" key with "photo" key in that exact spot.
- color_palette: Uppercase #RRGGBB hex values only. Max 16 for style_description, max 5 per element. Use hex colors matching the style and character visual specs.
- elements: Include all characters present in the scene. For each character, specify:
  - Identity/features from their character reference specs.
  - Action/pose, facial expression/emotion, orientation, location, gaze, light interaction.
- additional_directives: Include a few (2-4) extra composition or quality instructions (e.g. "Rule of thirds", "Vibrant colors").
- Output ONLY valid JSON.
"""

def get_resolution_string(global_cfg):
    """Retrieve widthxheight resolution from global config."""
    width = global_cfg.get("width")
    height = global_cfg.get("height")
    if not (width and height):
        preset = global_cfg.get("resolution_preset", "1080p")
        if preset == "1080p":
            width, height = 1920, 1080
        elif preset == "720p":
            width, height = 1280, 720
        else:
            # Fallback to standard Ideogram landscape size
            width, height = 1344, 768
    return f"{width}x{height}"

def get_cached_prompt(output_dir, filename_prefix):
    """Retrieve enhanced prompt from cache if it exists."""
    cache_path = os.path.join(output_dir, "enhanced_prompts", f"{filename_prefix}_ideogram_prompt.json")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 10:
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"      ⚠️ Warning: Failed to read cached prompt from {cache_path}: {e}")
    return None

def save_enhanced_prompt(output_dir, filename_prefix, content):
    """Save enhanced prompt to cache folder."""
    cache_dir = os.path.join(output_dir, "enhanced_prompts")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{filename_prefix}_ideogram_prompt.json")
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"      💾 Saved enhanced prompt to {cache_path}")
    except Exception as e:
        print(f"      ⚠️ Warning: Failed to save enhanced prompt to {cache_path}: {e}")

def validate_ideogram_json(json_str):
    """Validate that the string is a valid Ideogram 4 JSON prompt structure."""
    try:
        # Strip codeblock wrappers if any are present
        cleaned_str = json_str.strip()
        if cleaned_str.startswith("```"):
            import re
            cleaned_str = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_str)
            cleaned_str = re.sub(r'\n?```\s*$', '', cleaned_str)
        
        data = json.loads(cleaned_str)
        required_keys = ["high_level_description", "style_description", "compositional_deconstruction"]
        for key in required_keys:
            if key not in data:
                print(f"      ❌ Validation failed: missing key '{key}'")
                return False
        
        elements = data.get("compositional_deconstruction", {}).get("elements", [])
        if not isinstance(elements, list):
            print("      ❌ Validation failed: elements is not a list")
            return False
            
        for el in elements:
            bbox = el.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                print(f"      ❌ Validation failed: invalid bbox format {bbox}")
                return False
            for coord in bbox:
                if not isinstance(coord, (int, float)) or coord < 0 or coord > 1000:
                    print(f"      ❌ Validation failed: coordinate out of bounds {coord}")
                    return False
        return True
    except Exception as e:
        print(f"      ❌ Validation exception: {e}")
        return False

def call_llm(system_prompt, user_prompt, provider, api_key, model, fallback_model=None, max_retries=2, retry_delay=2):
    """Call LLM via OpenRouter or direct Gemini API, returning the response content string."""
    models_to_try = [model]
    if fallback_model:
        models_to_try.append(fallback_model)

    for current_model in models_to_try:
        for attempt in range(max_retries + 1):
            try:
                if provider == "openrouter":
                    url = "https://openrouter.ai/api/v1/chat/completions"
                    payload = {
                        "model": current_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.2
                    }
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                        "HTTP-Referer": "https://github.com/EvoLinkAI/awesome-ideogram-4.0-prompts",
                        "X-Title": "Antigravity Ideogram Enhancer"
                    }
                else:  # gemini API
                    normalized_model = current_model.split("/")[-1]
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{normalized_model}:generateContent?key={api_key}"
                    payload = {
                        "contents": [
                            {
                                "role": "user",
                                "parts": [{"text": user_prompt}]
                            }
                        ],
                        "systemInstruction": {
                            "parts": [{"text": system_prompt}]
                        },
                        "generationConfig": {
                            "responseMimeType": "application/json",
                            "temperature": 0.2
                        }
                    }
                    headers = {
                        "Content-Type": "application/json"
                    }

                req_data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(url, data=req_data, headers=headers)

                context = ssl._create_unverified_context()
                with urllib.request.urlopen(req, timeout=45, context=context) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))

                if provider == "openrouter":
                    choice = resp_data.get("choices", [{}])[0]
                    content = choice.get("message", {}).get("content", "")
                    if content:
                        return content.strip()
                else:  # gemini API
                    for candidate in resp_data.get("candidates", []):
                        for part in candidate.get("content", {}).get("parts", []):
                            if "text" in part:
                                return part["text"].strip()

            except urllib.error.HTTPError as e:
                error_body = e.read().decode("utf-8")[:500]
                print(f"      ⚠️ HTTP Error {e.code} for model {current_model}: {error_body}")
                if e.code == 429 and attempt < max_retries:
                    wait = retry_delay * (attempt + 1)
                    time.sleep(wait)
                    continue
            except Exception as e:
                print(f"      ⚠️ Exception calling LLM with model {current_model}: {str(e)}")
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    continue
            break # Try next model if this one failed completely

    return None

def enhance_character_sheet_prompt(character_name, character_desc, style_notes, global_style, global_cfg, output_dir, filename_prefix):
    """Enrich the character sheet generation prompt using LLM."""
    enhancer_cfg = global_cfg.get("prompt_enhancer", {})
    
    # Fast path: check cache
    if enhancer_cfg.get("cache_prompts", True):
        cached = get_cached_prompt(output_dir, filename_prefix)
        if cached:
            print(f"      ✨ Loaded LLM-enhanced character sheet prompt from cache: {filename_prefix}")
            return cached

    # Resolve API details
    provider = enhancer_cfg.get("provider", "openrouter")
    model = enhancer_cfg.get("model", "google/gemini-3.1-flash-lite")
    fallback_model = enhancer_cfg.get("fallback_model", "openai/gpt-4o-mini")
    
    # Resolve API Key
    api_key = None
    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
    elif provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY")
        
    if not api_key:
        # Try finding key in fallback environments
        api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if api_key:
            provider = "openrouter" if os.environ.get("OPENROUTER_API_KEY") else "gemini"

    if not api_key:
        print("      ⚠️ No API Key found for prompt enhancer. Skipping LLM enhancement.")
        return None

    resolution = get_resolution_string(global_cfg)
    
    user_prompt = f"""Character Name: {character_name}
Character Description: {character_desc}
Style Notes: {style_notes or "None"}
Global Style: {global_style or "None"}
Resolution & Aspect Ratio: {resolution}
"""

    print(f"      ✨ Enhancing character sheet prompt via LLM ({provider}/{model})...")
    enhanced_prompt = call_llm(
        system_prompt=SYSTEM_PROMPT_CHARACTER_SHEET,
        user_prompt=user_prompt,
        provider=provider,
        api_key=api_key,
        model=model,
        fallback_model=fallback_model
    )

    if enhanced_prompt and validate_ideogram_json(enhanced_prompt):
        # Clean any markdown codeblock wraps just in case
        if enhanced_prompt.strip().startswith("```"):
            import re
            enhanced_prompt = re.sub(r'^```(?:json)?\s*\n?', '', enhanced_prompt.strip())
            enhanced_prompt = re.sub(r'\n?```\s*$', '', enhanced_prompt)
        
        # Save to cache
        if enhancer_cfg.get("cache_prompts", True):
            save_enhanced_prompt(output_dir, filename_prefix, enhanced_prompt)
        return enhanced_prompt

    print("      ❌ LLM prompt enhancement failed or produced invalid JSON. Falling back to template.")
    return None

def enhance_scene_prompt(prompt_text, global_style, characters_present, characters_cfg, global_cfg, output_dir, filename_prefix):
    """Enrich the raw scene frame prompt using LLM."""
    enhancer_cfg = global_cfg.get("prompt_enhancer", {})
    
    # Fast path: check cache
    if enhancer_cfg.get("cache_prompts", True):
        cached = get_cached_prompt(output_dir, filename_prefix)
        if cached:
            print(f"      ✨ Loaded LLM-enhanced scene prompt from cache: {filename_prefix}")
            return cached

    # Resolve API details
    provider = enhancer_cfg.get("provider", "openrouter")
    model = enhancer_cfg.get("model", "google/gemini-3.1-flash-lite")
    fallback_model = enhancer_cfg.get("fallback_model", "openai/gpt-4o-mini")
    
    # Resolve API Key
    api_key = None
    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
    elif provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY")
        
    if not api_key:
        api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if api_key:
            provider = "openrouter" if os.environ.get("OPENROUTER_API_KEY") else "gemini"

    if not api_key:
        print("      ⚠️ No API Key found for prompt enhancer. Skipping LLM enhancement.")
        return None

    resolution = get_resolution_string(global_cfg)
    
    # Build character context block
    char_context = []
    for char_id in (characters_present or []):
        char_info = (characters_cfg or {}).get(char_id)
        if char_info:
            char_context.append(
                f"- ID: {char_id}\n  Display Name: {char_info.get('display_name', char_id)}\n  Description: {char_info.get('description', '')}"
            )
        else:
            char_context.append(f"- ID: {char_id}\n  Display Name: {char_id}")
            
    characters_str = "\n".join(char_context) if char_context else "None"

    user_prompt = f"""Scene Action/Description: {prompt_text}
Global Style: {global_style or "None"}
Resolution & Aspect Ratio: {resolution}

Characters Present in the Scene:
{characters_str}
"""

    print(f"      ✨ Enhancing scene prompt via LLM ({provider}/{model})...")
    enhanced_prompt = call_llm(
        system_prompt=SYSTEM_PROMPT_SCENE_STILL,
        user_prompt=user_prompt,
        provider=provider,
        api_key=api_key,
        model=model,
        fallback_model=fallback_model
    )

    if enhanced_prompt and validate_ideogram_json(enhanced_prompt):
        if enhanced_prompt.strip().startswith("```"):
            import re
            enhanced_prompt = re.sub(r'^```(?:json)?\s*\n?', '', enhanced_prompt.strip())
            enhanced_prompt = re.sub(r'\n?```\s*$', '', enhanced_prompt)
            
        # Save to cache
        if enhancer_cfg.get("cache_prompts", True):
            save_enhanced_prompt(output_dir, filename_prefix, enhanced_prompt)
        return enhanced_prompt

    print("      ❌ LLM prompt enhancement failed or produced invalid JSON. Falling back to template.")
    return None
