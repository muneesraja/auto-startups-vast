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
- **Per shot (Flux 2 Dev Turbo 8-step)**: ~60-80 seconds on RTX 3090
- **Prompt queue**: instant
- **Polling**: 5-second intervals

### Bulk Queue + Poll Pattern (Recommended for 20+ shots)

For large batches (20+ shots), the sequential `generate_scene.py` approach works but the agent's `execute_code` timeout (300s) limits batches to ~3 shots. A more efficient approach is to **bulk queue all shots, then poll for completion**:

```python
# 1. Queue all remaining shots at once
for shot in remaining_shots:
    workflow = build_dynamic_workflow(template, shot, global_cfg)
    result = curl_json("POST", "/prompt", BASE_URL, data={"prompt": workflow})
    queued.append({"prefix": shot["filename_prefix"], "prompt_id": result["prompt_id"]})

# 2. Save queue state for polling
with open("queue_state.json", "w") as f:
    json.dump({"queued": queued}, f)

# 3. Poll script (run in background with notify_on_complete)
while pending:
    time.sleep(10)
    for pid, prefix in pending.items():
        data = curl_json("GET", f"/history/{pid}", BASE_URL)
        if pid in data and data[pid]["status"]["status_str"] == "success":
            # Download output
            download_output(filename, out_path, BASE_URL)
            del pending[pid]
```

**Benefits:**
- ComfyUI processes the queue sequentially — no GPU contention
- Agent doesn't need to actively monitor — polling script runs in background
- `notify_on_complete` fires when all shots are done
- Each shot takes ~60-80 sec on Flux 2 Dev Turbo, so 50 shots ≈ 50-65 min

**Python output buffering:** Always use `python3 -u` (unbuffered) for background scripts. Without `-u`, stdout is buffered and the polling script appears to produce no output.

**Deduplication:** Check for existing files before queuing to avoid regenerating on retries:
```python
existing = [f for f in os.listdir(OUTPUT_DIR) if f.startswith(prefix+"_") and f.endswith('.png')]
if existing: continue  # skip
```

---

## Vision Evaluation Model

- **Provider:** Google AI Studio — `gemini-2.5-flash`
- **API:** Direct REST API call via `urllib.request` to Google Generative Language API. `GEMINI_API_KEY` must be set in `.env` file.
- **Response format:** `responseMimeType: "application/json"` forces structured JSON output. The script uses `temperature: 0.2` for consistent scoring.

### Antigravity CLI (`agy`) — Alternative Evaluator

When Gemini API credits are unavailable or for faster bulk evaluation, use `agy` CLI (Antigravity v1.0.5+) with Gemini 3.5 Flash (Low).

**Key facts:**
- `agy` reads image files directly — no base64 encoding needed
- Must run from the **story's work directory** (e.g., `story-to-video/pluffy-bun/`) — `agy` reads context from `cwd`
- Default timeout is 5 min; set `--print-timeout 2m` for faster failures
- No Gemini 2.5 Flash — use `Gemini 3.5 Flash (Low)` (cheapest) or `Gemini 3.5 Flash (Medium)`
- Auto-approve with `--dangerously-skip-permissions`

**Evaluation command pattern:**
```bash
cd $STORY_DIR && agy -p "Evaluate this illustration for a children's story.
EXPECTED: [scene description from manifest]
Characters: [characters in this shot]
Character reference sheets provided: [paths to ref images]. Compare characters in the scene to these references.
Style: 3D Pixar pastel animation.

Score 0-10: character_accuracy (does the character match the reference sheet?), expression, style, composition, overall. Also 'issues' array.
Reply ONLY JSON." \
  --dangerously-skip-permissions \
  --model "Gemini 3.5 Flash (Low)"
```

**Character reference comparison:** Always include the character reference sheet paths in the eval prompt when characters are present. This lets the evaluator visually compare the generated character against the reference sheet, catching body shape deviations, color mismatches, and feature differences that text-only evaluation misses.

**Tips:**
- Run from the **story's work directory** (e.g., `story-to-video/pluffy-bun/`) — `agy` reads context from `cwd`, so the story manifest and scenes should be accessible
- Do NOT use `/tmp` — it gets contaminated by other story files (hare_ref.png, tortoise_ref.png, etc.)
- Keep prompts short — long prompts cause timeouts (>65s)
- One image per call — batch by running multiple terminal calls
- Scores are comparable to Gemini API eval but less structured (may need parsing)

**Bulk evaluation pattern:**
```python
import subprocess, json
STORY_DIR = "/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video/pluffy-bun"
CHAR_DIR = f"{STORY_DIR}/characters"
REFS = {"puffy": f"{CHAR_DIR}/puffy_reference_sheet_final.png", "jalapeno": f"{CHAR_DIR}/jalapeno_reference_sheet_v4.png"}

for shot in shots:
    chars = shot["characters_present"]
    ref_images = [REFS[c] for c in chars if c in REFS]
    ref_line = f"Character reference sheets: {', '.join(ref_images)}. Compare characters to these." if ref_images else ""
    
    r = subprocess.run(
        ["agy", "-p", 
         f"Evaluate this illustration. EXPECTED: {desc} Characters: {chars}. {ref_line}\n"
         f"Score 0-10: character_accuracy (match ref?), expression, style, composition, overall. Issues array.\nReply ONLY JSON.",
         "--dangerously-skip-permissions", "--model", "Gemini 3.5 Flash (Low)"],
        capture_output=True, text=True, timeout=120, cwd=STORY_DIR
    )
    # Parse JSON from stdout
```

---

## Operational Pattern: Polling Over Watching

For any long-running batch process (generation, evaluation, uploads), **always use polling instead of actively watching each step**.

### Why
- Agent `execute_code` has a 300s timeout — batch of 3+ items will fail
- Actively watching wastes context tokens on intermediate output
- User shouldn't have to wait for each step to complete

### Pattern
1. **Queue all items** in a single fast script (submits work, doesn't wait)
2. **Save queue state** to a JSON file (prompt IDs, pending/complete status)
3. **Run poll script in background** with `terminal(background=True, notify_on_complete=True)`
4. **Poll script** checks status every 10-15 sec, downloads/saves results, updates queue state
5. **Agent continues** other work or reports status — doesn't block

### Template: Bulk Queue + Poll
```python
# Phase 1: Queue all (fast, ~3 sec)
queued = []
for item in items:
    result = submit_to_api(item)
    queued.append({"id": item["id"], "api_id": result["id"]})
with open("queue_state.json", "w") as f:
    json.dump({"queued": queued, "completed": [], "failed": []}, f)

# Phase 2: Poll script (runs in background)
# terminal(command="python3 -u poll_script.py", background=True, notify_on_complete=True)
```

### Poll Script Template
```python
#!/usr/bin/env python3
# Always use: python3 -u (unbuffered) for background scripts
import json, time, subprocess

while pending:
    time.sleep(10)
    for item in list(pending):
        status = check_api_status(item["api_id"])
        if status == "success":
            download_result(item)
            completed.append(item)
            del pending[item]
        elif status == "error":
            failed.append(item)
            del pending[item]
    print(f"Progress: {len(completed)} done, {len(failed)} failed, {len(pending)} remaining", flush=True)
```

### Key Rules
- **`python3 -u`** always — without unbuffered flag, background scripts produce no output
- **`notify_on_complete=True`** — agent gets notified when poll finishes, no manual checking
- **`cwd=STORY_DIR`** for agy commands — run from the story's work directory so agy has proper context (manifest, scenes). Do NOT use `/tmp` — it gets contaminated by other story files.
- **Skip existing** — check for output files before queuing to avoid re-processing on retries
- **Save queue state** — enables resume if poll script crashes

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

### Smart Reference Handling

#### Evaluation References

Only include character reference sheets when characters are present in the shot:

| Shot Type | Character Refs? | Why |
|-----------|----------------|-----|
| Characters present | ✅ Include | Evaluator compares character appearance against ref |
| Environment only | ❌ Skip | No character to compare — evaluate style/composition only |

#### Refinement References (Decision Matrix)

After evaluation identifies issues, the refinement approach depends on the issue type:

| Issue Type | Character Ref? | Scene Ref? | Best Approach |
|-----------|---------------|-----------|---------------|
| `character_body_shape` | ✅ | ❌ | Strong body-anchoring in prompt (describe what IS) |
| `character_expression` | ✅ | ❌ | Character ref + expression descriptors |
| `composition` | ❌ | ✅ | Scene ref + camera override |
| `style` | ❌ | ❌ | Regenerate from prompt |
| `environment` | ❌ | ❌ | Regenerate from prompt |

**⚠️ Key finding:** Including the problematic scene as a ReferenceLatent does NOT work well for body shape fixes. The ReferenceLatent conditions the generation but doesn't directly edit — it can reinforce the wrong shape. Instead, use **stronger prompt body-anchoring** (describe the correct body explicitly: "ONE single unified round sphere, no neck, no separate head").

#### Issue Classification

The evaluator classifies issues into types using keyword matching:
- `character_body_shape`: body, shape, form, proportion, sphere, round, limb
- `character_expression`: expression, face, smile, eyes, mouth, emotion
- `composition`: framing, composition, close-up, angle, position
- `environment`: background, setting, landscape, sky, ground
- `style`: style, coloring, lighting, texture, render, quality

#### Enhanced Eval Prompt

The enhanced eval prompt includes:
- Expected scene description
- Character reference sheets (if characters present)
- Issue type classification request
- Fix instructions request

```json
{
  "scores": {"character_accuracy": 6, "expression": 8, "style": 9, "composition": 10, "overall": 7.5},
  "issues": ["Body is two stacked spheres instead of one"],
  "issue_type": "character_body_shape",
  "fix_instructions": "Make body one single unified round sphere, legs must be red not orange",
  "ref_metadata": {
    "characters_in_shot": ["puffy"],
    "character_refs_used": ["puffy_reference_sheet_final.png"],
    "issue_type": "character_body_shape",
    "fix_instructions": "..."
  }
}
```

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

### Gemini Rate Limiting

When evaluating many shots in sequence, you **will** hit Gemini API rate limits (especially on free tier or high-volume runs). Symptoms: `N/A` scores for all categories, or parse failures on valid responses.

**Mitigation:**
- GEMINI_FREE_TIER rate limit: **~2 requests/min**. When evaluating more than 5 shots, you **must** use 30+ second delays between calls.
- The paid-tier Gemini Flash API allows ~15 requests/minute.
- **Recommended approach for bulk eval:** Use a bash loop with `sleep 30` between individual `--shot` evaluations. For free tier, use `sleep 60`.
- If you see consecutive `N/A` scores, pause for **120 seconds** before retrying — the rate limit window needs to fully reset.
- Script-level: `generate_scene.py` does not currently have built-in rate limiting between eval calls. When running bulk evals, call individual shots via `--shot` with delays between calls.
- **Best practice:** Evaluate scenes in small batches (3-4 shots) with 60s pauses between batches, rather than all 27 shots at once.

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
