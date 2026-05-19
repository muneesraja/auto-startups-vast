# Evaluate & Refine Loop — Design Document

Complete design for the generate → evaluate → refine loop, including all 15 edge cases.

## Core Flow

1. **Generate** — Queue prompt to ComfyUI, download scene PNG
2. **Evaluate** — Vision AI reads png + compares against original prompt from manifest
3. **Refine** — Vision AI produces an improved prompt targeting specific issues
4. **Loop** — Re-generate with refined prompt, up to max-iterations (default: 3)
5. **Save** — Best iteration wins (highest score), even if it didn't pass threshold

## Pass Threshold

A scene passes when: **score >= 7 AND no critical issues** (missing character, wrong setting).
Use AND, not OR. A score-3 scene with "no critical issues" must NOT pass.

## Vision Evaluation Format (v2)

Vision AI returns 5 raw category scores; the script computes the weighted average.

**Weights**: character_accuracy=0.30, facial_expression=0.25, scene_composition=0.20, action_depicted=0.15, style_consistency=0.10

```json
{
  "scene_number": 1,
  "shot_number": 2,
  "iteration": 1,
  "category_scores": {
    "character_accuracy": 7,
    "facial_expression": 5,
    "scene_composition": 8,
    "action_depicted": 7,
    "style_consistency": 9
  },
  "score": 7.0,
  "passed": false,
  "issues": ["Hare's expression is neutral instead of the specified mocking smirk"],
  "strengths": ["Good composition", "Correct aspect ratio", "Character likenesses are accurate"],
  "refined_prompt": "<improved prompt or null if passed>",
  "vision_description": "A forest clearing with a hare standing proudly...",
  "expression_detail": {
    "hare": {"expected": "mocking smirk, one eyebrow raised, corner of mouth curled", "observed": "neutral face, slight smile"},
    "tortoise": {"expected": "calm plodding expression, no reaction", "observed": "matching expected - calm peaceful face"}
  }
}
```

### Why Weights Changed (v1 → v2)

v1 weights: character_accuracy=0.40, scene_composition=0.25, action_depicted=0.20, style_consistency=0.15

v2 weights: character_accuracy=0.30, facial_expression=0.25, scene_composition=0.20, action_depicted=0.15, style_consistency=0.10

**Rationale**: Facial expression is the primary differentiator between shots within the same scene. A 5-shot scene where every face is neutral defeats the purpose of shot-level planning. Expression accuracy is now weighted second only to character identity because:
- Character identity is foundational (wrong character = total failure)
- Expression is the core value-add of shot-level manifests
- Scene composition, action, and style are still important but secondary to "does the character look like they feel what we intended?"

## Evaluation Prompt Template (v2)

Always include chain-of-thought: describe first, then score. Now includes **facial expression targets** and **shot-level details**.

```
You are evaluating an AI-generated scene image against its description.

CHARACTERS EXPECTED:
{character_list_with_identity_specs}

SHOT DESCRIPTION:
Action: {shot.description}
Expected Facial Expressions:
{facial_expression_list_per_character}

SCENE CONTEXT:
Setting: {setting}
Mood: {scene.mood}
Camera: {shot.camera_override or scene.camera}
Style: {style}

STEP 1 - Describe what you see:
List every character visible in the image and their approximate position.
For EACH character, describe their facial expression in detail:
- What is their mouth doing? (smiling, frowning, neutral, open, etc.)
- What are their eyes doing? (wide, narrowed, looking somewhere specific, closed?)
- What is their brow/forehead doing? (flat, furrowed, raised, relaxed?)
- Overall emotional impression of their face?

Then describe the setting, action, and overall style.

STEP 2 - Score each category 0-10:
- CHARACTER_ACCURACY: Do characters match their identity specs? Correct colors, features, clothing?
- FACIAL_EXPRESSION: Does each character's facial expression match the expected expression described above? Score 10 for exact match, 7 for close approximation, 4 for partially matching, 1 for completely wrong expression.
- SCENE_COMPOSITION: Are all specified characters present? Is the setting correct?
- ACTION_DEPICTED: Does the image show the described action?
- STYLE_CONSIATION: Does the style match the specified art style?

STEP 3 - Respond in JSON only:
{
  "category_scores": { "character_accuracy": N, "facial_expression": N, "scene_composition": N, "action_depicted": N, "style_consistency": N },
  "passed": <true if score >= 7 AND no critical issues>,
  "issues": ["list of specific problems"],
  "strengths": ["what the model got right"],
  "refined_prompt": "<improved prompt addressing issues, or null if passed>",
  "expression_detail": {
    "character_id": {
      "expected": "<the specified facial expression>",
      "observed": "<what you actually see in the image>"
    }
  }
}
```

### How `facial_expression_list_per_character` is Built

From the manifest v2 shot data:

```
Expected Facial Expressions:
- Hare: mocking smirk, one eyebrow raised, corner of mouth curled
- Tortoise: calm plodding expression, no reaction to the taunt
```

Characters not present in the shot's `facial_expression` map are evaluated only on character accuracy, not expression. If a character IS listed, their expression is evaluated against the specific descriptors.

## Character Sheet Evaluation (Phase 0B)

Character reference sheets are evaluated differently from scene shots. The evaluation focuses on:
1. **Character likeness** — Does the generated sheet match the identity spec?
2. **Neutral expression** — Is the character shown with a neutral/resting face? (Critical for downstream expression generation)
3. **Style consistency** — Does the style match the manifest's style field?
4. **Visibility** — Are all key features (face, body, distinguishing marks) clearly visible?

### Character Sheet Evaluation Prompt

```
You are evaluating an AI-generated character reference sheet for a story illustration.

CHARACTER: {name}
IDENTITY SPEC: {identity_spec}
ART STYLE: {style}

STEP 1 - Describe what you see:
Describe the character's appearance, proportions, coloring, and distinguishing features.
What expression is the character showing? Is it neutral/resting, or showing emotion?

STEP 2 - Score each category 0-10:
- CHARACTER_LIKENESS: Does the character match the identity spec? Correct species, colors, proportions, clothing/accessories?
- EXPRESSION_NEUTRALITY: Is the character shown with a neutral, resting face? (10 = perfectly neutral, 5 = slight smile/frown, 1 = strong emotion visible)
- STYLE_MATCH: Does the art style match "{style}"?
- FEATURE_VISIBILITY: Are all key features clearly visible and not obscured?

STEP 3 - Respond in JSON only:
{
  "category_scores": { "character_likeness": N, "expression_neutrality": N, "style_match": N, "feature_visibility": N },
  "passed": <true if weighted score >= 7 AND expression_neutrality >= 6>,
  "issues": ["list of specific problems"],
  "strengths": ["what the model got right"],
  "refined_prompt": "<improved character sheet prompt, or null if passed>"
}
```

**Pass threshold**: weighted score >= 7 AND expression_neutrality >= 6

If a character sheet shows a strong emotion (e.g., smiling, angry), it will bias every downstream scene toward that expression because Qwen Image Edit uses the reference sheet as an anchor. **Neutral expressions on reference sheets are critical.**

## Prompt Refinement Rules

When a scene fails evaluation:
- **Only modify parts related to the issues** - preserve all other wording exactly
- **Never add global restatements** like "high quality" or "detailed"
- **Convert negations to positives** - "NOT a dark scene" becomes "bright, sun-dappled clearing with warm golden light"
- **JSON-escape refined prompts** before injecting into ComfyUI payload - newlines, quotes, backslashes can break the workflow JSON
- **Keep prompt under 2000 chars** - truncate character descriptions if needed, never truncate action/emotion/camera
- **For facial expression failures**: strengthen the expression descriptors (add mouth + eyes + brow specifics) or move expression description earlier in the prompt
- **For character accuracy failures**: verify reference sheets are uploaded and referenced correctly before refining prompt

### Expression-Specific Refinement

When `facial_expression` is flagged as an issue:

1. **Check if expression was too vague** → make it more specific with the three-region rule (mouth + eyes + brow)
2. **Check if expression was overridden by action** → move expression before action in the prompt
3. **Check if expression contradicts the action** → resolve the contradiction explicitly ("despite X, character's face shows Y")
4. **Check if the character's reference sheet has a strong expression** → flag for character sheet regeneration with neutral expression

## Edge Cases

### EC-1: ComfyUI Generation Failure
- Validation errors: don't consume iteration, fix config, retry once
- Execution errors (OOM, crash): retry same prompt once, then skip scene
- Timeout (>180s): skip scene, mark status "timeout"
- **Generation failures don't consume eval iterations**

### EC-2: Vision Model Returns Non-JSON
- Try json.loads() on response
- Try extracting JSON from markdown code fences
- If still unparseable (on a 200 OK response): treat as pass, log eval_parse_error
- If HTTP error / timeout: don't consume iteration, keep image, log eval_api_error

### EC-3: Vision Says Passed With Obvious Issues
- Trust the vision model. Issues are still logged for human review.
- The feedback JSON provides an audit trail for manual review later.

### EC-4: All 3 Iterations Fail
- Compare all iteration scores
- Copy highest-scoring iteration as final scene_XXX.png
- Log: best_effort true, max_iterations_reached 3, needs_manual_review true
- Continue to next scene (don't block pipeline)

### EC-5: Iteration 1 Passes Immediately
- Copy scene_001_shot002_iter1.png to scene_001_shot002.png
- Feedback JSON: passed true, iteration 1, refined_prompt null
- Fast path, most common case

### EC-6: Character Reference Sheet Missing
- If local file exists in characters/: auto-upload before generation
- If no local file: use fallback mapping (already in script)
- Log: fallback_used with the mapping

### EC-7: Scene Manifest Missing Fields
- action required: skip scene if missing
- mood defaults to "neutral mood" (v1 used "emotion" — v2 renamed to "mood")
- camera defaults to "medium shot, eye level"
- setting defaults to "outdoor scene"
- facial_expression defaults to "neutral, calm expression" per character (if missing from shot)

### EC-8: Refined Prompt Regression
- Track all iteration scores
- Pick the highest score, not the latest iteration
- Log: regression_detected true, best_iteration N

### EC-9: Concurrent Generation (v2)
- Not in scope for v1, sequential only
- File structure supports it (scene numbers are independent)

### EC-10: ComfyUI Instance Goes Down
- Catch connection errors/timeouts in curl_json()
- Log status instance_down, exit gracefully
- Already-generated scenes and feedback preserved on disk
- Re-running picks up where it left off (idempotent: checks for existing scene_XXX.png)

### EC-11: Seed Determinism
- Iteration N uses seed + N to ensure different starting points
- Seed recorded in feedback JSON for reproducibility

### EC-12: Very Long Prompts
- Track prompt length in chars
- If refined prompt > 2000 chars, truncate character descriptions
- Never truncate action/expression/camera
- Log: prompt_truncated true, original_length N, truncated_length N

### EC-13: Corrupted PNG (from Opencode review)
- Check file size > 1000 bytes before evaluation
- If corrupted, don't evaluate, don't consume iteration, log error

### EC-14: Vision API Down (from Opencode review)
- 3-second timeout, 2 retries on vision API calls
- If all retries fail: keep image, log eval_api_error, don't loop

### EC-15: Refined Prompt Breaks JSON (from Opencode review)
- Sanitize: escape quotes, remove newlines, strip backslashes
- If queue returns validation error after refined prompt: fall back to original prompt, log refinement_failed

### EC-16: Facial Expression Evaluation Ambiguity (v2)
- If a character's face is turned away or very small in frame, expression evaluation is unreliable
- Gemini should score expression as N/A (excluded from average) if face is < 5% of image area or turned > 60° away
- Log: expression_eval_skipped true, reason "face_too_small" or "face_turned_away"

### EC-17: Character Sheet Has Non-Neutral Expression (v2)
- If character sheet evaluation shows expression_neutrality < 6, flag for regeneration
- Do NOT proceed to scene generation with a strongly expressive reference sheet
- Log: character_sheet_expression_warning true, character_id, observed_expression
- Approval gate (Phase 0B) catches this before scene generation starts

## Vision Model: Gemini 2.5 Flash (Direct API)

**Why this model:**
- Free tier, reliable, good at detailed image analysis with JSON mode
- `qwen3-coder-next:cloud` does NOT support vision (returns 400 "this model does not support image input")
- MiniMax MCP vision tool has auth issues (subscription being dropped)
- `gemini-3.1-pro` exhausts free tier quota quickly (429 after a few calls)
- Gemini CLI (`gemini` npm package) has broken `ripGrep.js` dependency on our VPS — use direct REST API instead

**API call pattern (Python urllib, not Gemini CLI):**

```python
import json, urllib.request, base64, os

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"

def call_gemini_vision(prompt_text, image_path, api_key):
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}

    payload = {
        "contents": [{"parts": [
            {"text": prompt_text},
            {"inline_data": {"mime_type": mime_map.get(ext, "image/png"), "data": img_b64}}
        ]}],
        "generationConfig": {
            "responseMimeType": "application/json",  # forces structured JSON output
            "temperature": 0.2  # consistent scoring
        }
    }

    url = f"{GEMINI_API_URL}/{GEMINI_MODEL}:generateContent?key={api_key}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
        for candidate in data["candidates"]:
            for part in candidate["content"]["parts"]:
                if "text" in part:
                    return part["text"]
```

**Key pitfalls:**
- `GEMINI_API_KEY` is in `~/.bashrc` but NOT auto-exported in subprocess environments. Must `source ~/.bashrc` first or pass `--api-key` flag to `evaluate_scene.py`.
- Rate limiting: Free tier has req/min and token/day limits. Script retries on 429 with backoff (2 retries, 3s delay).
- **Never use the Gemini CLI (`gemini` npm package)** on our VPS — it has a broken `ripGrep.js` dependency. Use the direct REST API pattern above.