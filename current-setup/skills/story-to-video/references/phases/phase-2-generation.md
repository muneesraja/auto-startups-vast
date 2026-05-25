# Phase 2 & Phase 2.5: Scene Generation and Evaluation Loop

This phase covers batch generating scene images from `prompt.json` and running them through the vision-based Gemini evaluation loop.

## Phase 2: Generate Scene Images

### Using the Script

```bash
# Generate all shots from prompt.json
python3 generate_scene.py --prompts prompt.json

# Generate a specific shot
python3 generate_scene.py --prompts prompt.json --shot scene_001_shot001

# Dry-run (parse + build workflows without queuing)
python3 generate_scene.py --prompts prompt.json --dry-run

# With evaluation
python3 generate_scene.py --prompts prompt.json --evaluate

# Override ComfyUI URL and output directory
python3 generate_scene.py --prompts prompt.json \
  --url https://mandi-qwen.muneesraja.com \
  --output-dir /root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video/little-tiger

# Skip already-generated shots
python3 generate_scene.py --prompts prompt.json --skip-existing

# Evaluate existing images without regenerating
python3 generate_scene.py --prompts prompt.json --evaluate-only
```

### How the Script Works

1. Reads `prompt.json` → validates schema
2. Loads the workflow template matching `workflow_template` field from `assets/workflow-templates/`
3. For each shot:
   - Replaces template placeholders with shot data (prompt, refs, seed, dimensions)
   - Queues the workflow to ComfyUI API
   - Polls `/history/{prompt_id}` until completion
   - Downloads output image
4. If `--evaluate`: sends image + `eval_context` to Gemini Vision for scoring
5. If evaluation fails: uses `refined_prompt` from Gemini, increments seed, retries (max 3 iterations)

### Generation Timing

- **Per shot (Qwen 4-step)**: ~20-30 seconds on RTX 3090
- **Per shot (HiDream 28-step)**: ~60-90 seconds on RTX 3090 (estimated)
- **Prompt queue**: instant
- **Polling**: 5-second intervals

---

## Vision Evaluation Model

- **Provider:** Google AI Studio — `gemini-2.5-flash`
- **API:** Direct REST API call via `urllib.request` to Google Generative Language API. `GEMINI_API_KEY` must be set in `.env` file.
- **Response format:** `responseMimeType: "application/json"` forces structured JSON output. The script uses `temperature: 0.2` for consistent scoring.

---

## Phase 2.5: Evaluate & Refine Loop

After generating a scene, optionally run a vision-based evaluation to check quality. If the image doesn't pass, refine the prompt and regenerate — up to 3 iterations.

### Architecture

```
GENERATE ──▶ EVALUATE ──▶ PASS?
  ▲                        │
  │                    Yes → Save final, next scene
  │                    No  → REFINE prompt, loop (max 3)
  └────────────────────────┘
```

### v2 Script Notes

- **`generate_scene.py --all` on v2 manifests** iterates all shots across all scenes, not just scenes. Each shot gets its own ComfyUI call with its own prompt.
- **`generate_scene.py --scene X --shot Y`** targets a specific shot. Omit `--shot` to generate the first shot of a v2 scene (or the whole scene for v1).
- **Expression drift detection**: The v2 eval passes `expected` expressions to Gemini so it can compare against `observed` and give a specific `facial_expression` score. If expression drift is detected, the refined prompt strengthens descriptors using the three-region rule (mouth + eyes + brow) or moves expression text earlier in the prompt.
- **v1 backward compat**: If `detect_manifest_version()` returns v1 (no `shots` array, no `total_shots_budget`), the script falls back to 4-category eval and single-prompt-per-scene generation. v1 manifests work without changes.

### Pass Threshold

A scene passes when: **score ≥ 7 AND no critical issues** (missing character, wrong setting). Use AND, not OR — a scene with score 3 but "no critical issues" must NOT pass.

### Vision Evaluation Returns Raw Sub-Scores

The vision model returns category scores; the script computes the weighted average:

**v2 scoring (5 categories):**
```json
{
  "category_scores": {
    "character_accuracy": 6,
    "facial_expression": 4,
    "scene_composition": 8,
    "action_depicted": 7,
    "style_consistency": 9
  },
  "score": 6.5,
  "passed": false,
  "issues": ["Hare's expression is neutral, not the specified confident grin"],
  "strengths": ["Good composition, correct setting"],
  "refined_prompt": "<improved prompt or null if passed>",
  "expression_detail": {
    "hare": {"expected": "confident grin, eyes determined", "observed": "neutral face, no expression"},
    "tortoise": {"expected": "gentle knowing smile", "observed": "gentle knowing smile"}
  }
}
```

**v1 scoring (4 categories, backward compat):**
```json
{
  "category_scores": {
    "character_accuracy": 6,
    "scene_composition": 8,
    "action_depicted": 7,
    "style_consistency": 9
  },
  "score": 7.15,
  "passed": false,
  "issues": ["Fox character is missing"],
  "strengths": ["Good composition, correct aspect ratio"],
  "refined_prompt": "<improved prompt or null if passed>"
}
```

Weights (v2): character_accuracy=0.30, facial_expression=0.25, scene_composition=0.20, action_depicted=0.15, style_consistency=0.10.

**Why facial_expression is 25%**: Expression accuracy differentiates shots within the same scene. A 5-shot scene where every face is neutral defeats the purpose of shot-level planning.

### Chain-of-Thought Evaluation

The evaluation prompt instructs the vision AI to **describe what it sees first**, then score. This gives an audit trail and reduces hallucination:
```
First, describe every character you see in the image and their approximate position.
Then describe the setting, action, and style.
Then score each category 0-10.
```

### Prompt Refinement Rules

- **Only modify parts related to the issues.** Preserve all other wording exactly.
- **Never add global restatements** like "high quality" or "detailed".
- **Extract negations** — "NOT a dark scene" is weak for diffusion models. Instead, describe what IS wanted: "bright, sun-dappled clearing with warm golden light".
- **JSON-escape refined prompts** before injecting into ComfyUI payload — newlines, quotes, and backslashes from the vision model can break the workflow JSON.

### Edge Cases

See [references/evaluation/evaluate-loop-design.md](../evaluation/evaluate-loop-design.md) for the full 12-edge-case plan. Key rules:
- **Generation failures don't consume eval iterations.** Only successful generations that fail evaluation count.
- **Vision API failures:** 3s timeout, 2 retries. If all fail, keep the image (don't loop on eval failures).
- **Vision parse errors:** If JSON is unparseable after extraction attempts, treat as pass and log `eval_parse_error`.
- **Regression detection:** Track all iteration scores; pick the highest, not the latest.
- **Idempotency:** Re-running skips completed scenes (checks for existing `scene_XXX.png`).
- **Seed increment:** Iteration N uses `seed + N` to avoid same-output loops.
- **Disk space:** Log available disk before starting; `--cleanup-iterations` flag to delete non-best iter files after scene passes.

### Pipeline Summary

After a full run, generate `pipeline_summary.json` at the story root:

```json
{
  "story_slug": "hare-and-tortoise",
  "completed_at": "...",
  "scenes": [
    {"scene": 1, "best_iteration": 1, "passed": true, "score": 8.5},
    {"scene": 2, "best_iteration": 3, "passed": false, "needs_manual_review": true}
  ]
}
```

### File Structure

```
story-to-video/{story-slug}/
├── characters/           # Reference sheets
├── scenes/
│   ├── scene_001_iter1.png    # iteration 1
│   ├── scene_001_iter2.png    # iteration 2 (if needed)
│   ├── scene_001.png          # final (best iteration)
│   └── ...
├── feedback/
│   ├── scene_001_iter1.json   # evaluation per iteration
│   └── ...
├── pipeline_summary.json
└── story_manifest.json
```
