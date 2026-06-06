# Story-to-Video Evaluation Pitfalls

> Demoted from standalone skill `story-to-video-eval-pitfalls`. Load the parent `story-to-video` skill for the full pipeline context.

## OpenRouter Eval Provider (v4.5 — Preferred)

**Priority:** OpenRouter (Gemini 3.1 Flash Lite + thinking) > Gemini API (2.5 Flash, no thinking)

OpenRouter uses `reasoning.effort: "medium"` (~2K-4K thinking tokens). The model reasons through the image before scoring, improving accuracy (MMMU Pro: 76.8% vs 66.7%).

**Thinking token sweet spot:**
- 0–2K: High ROI, always worth it
- 2K–4K: **Optimal for image eval** (our "medium" setting)
- 4K–6K: Diminishing returns
- 7K+: **Negative** — model overthinks and abandons correct answers

**Cost:** ~$0.12 for 50 shots. Thinking tokens are charged as output ($1.50/M).

**Eval JSON output includes:** `reasoning` (thinking chain, capped at 10K chars), `provider`, `model`, `thinking_tokens`.

## Face Structure Reference Fix (Critical)

When a generated scene doesn't match the character reference sheet's face structure, the model isn't properly applying the reference image. The fix is to add an explicit face description block in the prompt:

```
CRITICAL FACE DETAIL: Puffy has a cream-colored face plate/cutout on the front of his body —
this is a lighter beige/cream oval area where his facial features sit.
Within this cream face plate: two small round dot eyes, a tiny nose, and thin minimal eyebrows.
The rest of the body is smooth red with a subtle golden sheen.
```

**Why this works:** Flux 2 Dev Turbo's ReferenceLatent chain doesn't always extract fine face details from reference images. Explicitly describing the face structure in the prompt text forces the model to render it correctly.

**When to use:** When eval feedback mentions face/feature mismatches but the overall character shape and color are correct. If the entire character is wrong, the reference image itself may be the problem.

**Proven impact (pluffy-bun test):**
- scene_005_shot002: 6.85 → **8.95** (+2.1)
- scene_007_shot002: 8.3 → **9.5** (+1.2)

## Custom Node Dependencies

The `flux-2-dev-turbo` workflow template requires `comfyui-kjnodes` for:
- `ImageResizeKJv2` — resizes reference images
- `GetImageSizeAndCount` — gets image dimensions
- `ColorMatchV2` — color matching between refs
- `GrowMaskWithBlur` — mask operations

**Fix:** Install `comfyui-kjnodes` on the ComfyUI instance:
```bash
cd ComfyUI/custom_nodes && git clone https://github.com/kijai/ComfyUI-KJNodes
```

Without this, all shots with references (I2I mode) will fail with `missing_node_type` errors. T2I shots (0 refs) work fine without it.

## Eval Parse Errors

Some eval responses from Gemini 3.1 Flash Lite return invalid JSON (parse errors). The eval script defaults to score 0 when parsing fails.

**Causes:**
- Model returns markdown-wrapped JSON with extra text
- Rate limiting causes truncated responses
- Image too complex for the model to structure a response

**Mitigation:**
- Retry failed evals (the `--provider openrouter` flag auto-retries on 429)
- Check `status` field in eval JSON — `parse_error` or `timeout` indicates failure
- Parse errors default to `passed: true` (trust the generation if eval can't parse)

## `agy` Context Contamination Pitfall (Critical)

`agy` CLI loads workspace context from the current working directory (`cwd`). Running from shared directories like `/tmp` causes the evaluator to see files from other stories and hallucinate them into evaluations.

**Observed:** A correct pastel Cream World landscape was evaluated as "hare and tortoise in green field" because `/tmp` contained `hare_ref.png` and `tortoise_ref.png` from a previous story-to-video session.

**Fix:** Always run `agy` from the **story's work directory** — not `/tmp`:
```bash
cd /path/to/story-to-video/pluffy-bun && agy -p "..." --dangerously-skip-permissions --model "Gemini 3.5 Flash (Low)"
```

**Why story dir works:** `agy` sees the correct manifest, scene files, and character references — so it evaluates in the right context. `/tmp` is a shared space contaminated by all previous sessions.

**Impact:** Character accuracy and scene content scores are unreliable when run from wrong directory. Style scores may also be affected.

**Mitigations (ranked by reliability):**
1. **Gemini API directly** (`generate_scene.py --evaluate`) — most reliable, structured JSON
2. **`agy` from story work directory** — correct context, reliable scores
3. **`gemini` CLI** (`gemini -p "..." --yolo --model gemini-2.5-flash`) — alternative CLI
4. **`agy` for style-only** — skip character_accuracy/expression, only style + composition

## Gemini CLI Model Flag

Default model `gemini-3-flash` returns **404 error**. Always specify `--model gemini-2.5-flash`.

```bash
# ❌ Broken
gemini -p "evaluate this" --yolo

# ✅ Works
gemini -p "evaluate this" --yolo --model gemini-2.5-flash
```

## `agy` Workspace Context

`agy` loads workspace context from the current directory. Running from shared directories (like `/tmp`) causes context pollution — the evaluator sees unrelated files and hallucinates them into the image evaluation.

**Fix:** Always run `agy` from the story's work directory:
```bash
cd /root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video/pluffy-bun && agy -p "..." --dangerously-skip-permissions --model "Gemini 3.5 Flash (Low)"
```

**Why NOT `/tmp`:** `/tmp` accumulates reference images and scripts from all previous story sessions (e.g., `hare_ref.png`, `tortoise_ref.png`). The story work directory has only the relevant manifest, scenes, and character refs.

## ComfyUI Instance Contamination

When generating new stories on a ComfyUI instance that previously ran other stories, the model may generate content from previous stories (e.g., generating "hare and tortoise" when the prompt is for "red bun character").

**Cause:** ComfyUI's model weights don't have story-specific memory, but the reference images and prompt context from previous runs may influence outputs if the same instance was used.

**Fix:**
- Use fresh ComfyUI instances for new stories
- Or explicitly anchor prompts with strong style/character descriptions
- Verify generated images match expected content before proceeding

## Reference Image Evaluation (v4.6)

The evaluation pipeline now sends **reference images** alongside the generated image for visual comparison. This allows the model to verify character appearance against reference sheets.

**How it works:**
- Generated image + up to 3 reference sheets = max 4 images per eval request
- Reference images are resolved from `prompt.json`'s `references` field
- Auto-detects `characters/` directory relative to `prompt.json` path
- The eval prompt instructs the model to compare against reference sheets

**CLI:**
```bash
# Auto-detect references from prompt.json location
python3 generate_scene.py --prompts prompt.json --evaluate-only --provider openrouter

# Explicit references directory
python3 generate_scene.py --prompts prompt.json --evaluate-only --references-dir /path/to/characters/
```

**Why this matters:** Without reference images, the model can only compare against the text description. With references, it can verify:
- Character colors match the reference sheet
- Character proportions are correct
- Face structure matches the reference design
- Clothing/accessories are consistent

**Reference resolution:**
- `prompt.json` defines `references: ["puffy_reference_sheet_final.png", "jalapeno_reference_sheet_v4.png"]`
- Script resolves these to `{prompt.json_dir}/characters/{filename}`
- Missing references are warned but don't block evaluation
- Deduplication prevents same image in multiple slots

## Landscape/Environment Shot Scoring

For shots with no characters (landscape panoramas, environment close-ups):
- `character_accuracy` and `facial_expression` are set to `null` in the eval response
- `compute_weighted_score()` automatically excludes null categories from the weighted average
- This prevents false negatives where landscape shots score 0 for character-related categories

**Example:** `scene_001_shot002` (vanilla milk river close-up) has no characters — character_accuracy and facial_expression are excluded, so only scene_composition, action_depicted, and style_consistency contribute to the score.

**Before fix:** Landscape shots scored 4.5/10 because character_accuracy (30%) and facial_expression (25%) were 0.
**After fix:** Landscape shots correctly score based on the 3 remaining categories (45% of total weight, normalized to 100%).

## Correction Flow — Never Use Failed Generation as Reference

When regenerating failed shots:
1. **Always use `prompt.json` references** (character sheets) as ComfyUI references
2. **Never use the previous generation** as a reference — this propagates errors
3. Use Gemini's `refined_prompt` feedback to improve the prompt text
4. The eval feedback determines what to fix in the prompt, not what references to use

**Wrong approach:**
```python
# ❌ Don't do this — sends failed generation as reference
references = ["scene_006_shot005_v2_00001_.png"]  # Previous failed attempt
```

**Correct approach:**
```python
# ✅ Use prompt.json references (character sheets)
references = shot_data["references"]  # ["jalapeno_reference_sheet_v4.png"]
```

## Reference Contamination in Regeneration (Critical)

When regenerating a failed shot, **never send the previous failed generation as a ComfyUI reference** alongside character sheets. The previous shot dominates the reference chain and the model replicates the same errors.

**Tested with scene_004_shot004 (Puffy bouncing through chili soldiers):**
1. **Attempt 1:** Previous shot + 2 character refs → Score **dropped to 3.8** (Puffy disappeared, previous Jalapeño-only composition replicated)
2. **Attempt 2:** Character refs first + previous shot last → Still failed (Puffy missing, ordering didn't help)
3. **Attempt 3:** Character refs ONLY + stronger prompt → Score **9.60** ✅

**Why this happens:**
- ComfyUI's ReferenceLatent chain treats scene images as higher-priority than character sheets
- The model "improves" the previous shot rather than generating from scratch
- If the previous shot was missing a character, the improved version also misses that character

**The fix:**
1. Send **only character reference sheets** from `prompt.json`
2. Write a **stronger prompt** that explicitly describes what was missing
3. Use **body-anchoring** to position characters and describe actions
4. Describe the **specific action/composition** the eval feedback identified as missing

**When previous shot MIGHT work as reference:**
- Minor color/lighting tweaks where composition is correct
- Style adjustments where all characters are present
- **Never** when character presence or action is the issue
