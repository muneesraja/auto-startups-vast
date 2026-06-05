# Phase 0 & Phase 1: Story Expansion, Character Sheets, and Upload

This phase covers turning a high-level story prompt into a structured manifest, generating neutral character reference sheets, obtaining user approval, and uploading/verifying them on the ComfyUI instance.

## Prerequisites for Phase 0

- **Gemini API key** — Must be in `.env` file (next to skill dir). Free tier `gemini-2.5-flash-image` quota is severely limited (daily limit can be 0). Use a paid tier key. See `.env.example` for format.
- **Python packages**: `pip install google-genai Pillow` — required by `generate_story_assets.py`. **No venv needed** — these work system-wide. System-wide install is simpler and reliable for single-purpose VPS scripts.
- **API key loading priority**: `.env` file → `GEMINI_API_KEY` env var → `--token` JSON path (subprocess doesn't load `.bashrc`)

| Package | Install | Used by |
|---|---|---|
| `google-genai` | `pip install google-genai` | `generate_story_assets.py` (Gemini image gen) |
| `Pillow` | `pip install Pillow` | `generate_story_assets.py` (image processing) |

**⚠️ GEMINI_API_KEY in subprocess:**
`.bashrc` exports are NOT sourced by non-interactive shells. If running scripts from a terminal subprocess, explicitly extract and export the key:
```bash
export GEMINI_API_KEY=$(grep GEMINI_API_KEY ~/.bashrc | head -1 | sed 's/.*="\([^"]*\)".*/\1/')
```
Otherwise the script silently gets an empty key → `API_KEY_INVALID` errors on all 3 retry attempts.

**⚠️ gemini-2.5-flash-preview-image daily quota:**
This model has a **separate** (and much stricter) free tier quota than `gemini-2.5-flash` (text/vision). The image generation free tier can hit daily limit = 0 even when text/vision works fine. If you see `429 RESOURCE_EXHAUSTED` with `limit: 0` for `gemini-2.5-flash-preview-image`, the daily quota is exhausted — wait for reset (midnight Pacific) or switch to a paid plan. More details in `references/ops/gemini-image-gen-quotas.md`.

---

## Phase 0: Story Expansion & Character Sheet Generation

This phase takes a high-level user story and turns it into the assets needed for all subsequent phases.

### Step A — Research & Story → Manifest (v2)

**Before planning prompts, review the Qwen Image Edit community research:**
- [references/models/qwen-image-edit-prompting-guide.md](../models/qwen-image-edit-prompting-guide.md) — includes Reddit community research (8 threads, 600+ comments: offset fixes, LoRA tradeoffs, multi-ref strategies, inpaint masking, max-quality workflow, 2509-vs-2511, face dataset tips, Chinese prompting)
- [references/ops/reddit-scraping-patterns.md](../ops/reddit-scraping-patterns.md) — how to re-scrape Reddit if fresh research is needed (JSON API patterns, what works vs what doesn't)
- If the guide is stale (>30 days old), re-run Reddit research using the patterns in `references/ops/reddit-scraping-patterns.md` and update the prompting guide

Then take the user's high-level story prompt and expand it into a full `story_manifest.json` (v2 schema) with:
- Characters (id, name, identity_spec, personality_traits)
- Scenes with **shots array** — each shot has description, facial_expression (per character), and optional camera_override
- `total_shots_budget` (default 50 for ~5 min story) and `total_duration_seconds` (default 300)
- Style directive (e.g., "children's book watercolor illustration")
- **Read [references/story-manifest-format.md](../story-manifest-format.md) for the full v2 schema**
- **Read [references/facial-expression-vocabulary.md](../facial-expression-vocabulary.md) for expression descriptors**
- **Read [references/models/qwen-image-edit-prompting-guide.md](../models/qwen-image-edit-prompting-guide.md) for Qwen prompting best practices BEFORE writing prompts**

### Step B — Manifest → Character Reference Sheets

Automatically generate 7-view character reference sheets using **Gemini 2.5 Flash Image** (`gemini-2.5-flash-image`):

```bash
# Generate character sheets only
python3 generate_story_assets.py --manifest story_manifest.json --phase characters

# Force regeneration of existing sheets
python3 generate_story_assets.py --manifest story_manifest.json --phase characters --force
```

Each sheet shows: 4 body views (front, 3/4 left, right profile, back) + 3 face close-ups (front, 3/4 left, right profile) on a white background.

**⚠️ CRITICAL — Neutral Expressions Only:** Character reference sheets MUST show characters with **neutral/resting expressions**. If a reference sheet shows a character smiling, frowning, or showing any emotion, it will bias every downstream scene toward that expression — Qwen Image Edit uses reference sheets as anchors and will reproduce the sheet's expression regardless of the prompt. The evaluation check for `expression_neutrality >= 6` enforces this.

### Step C — Upload to ComfyUI

Upload generated sheets to the ComfyUI instance:

```bash
# Upload all character sheets
for f in characters/*_reference_sheet.png; do
  curl -X POST "$COMFY_URL/upload/image" -F "image=@$f" -F "overwrite=true"
done
```

---

## Phase 0B: Character Sheet Approval Gate

Before proceeding to scene generation, **every character reference sheet must be approved by the user**. This prevents wasting GPU time on scenes built from bad reference sheets.

### Flow

```
Step B generates character sheets
        ↓
Step C uploads to ComfyUI
        ↓
Phase 0B: Display sheets to user for review
        ↓
User approves ✓ or rejects ✗ per character
        ↓
If rejected: regenerate specific characters, loop back to 0B
        ↓
All approved → proceed to Phase 1
```

### What Gets Reviewed

For each character, send to the user:
1. **The reference sheet image** (inline, so the user sees it immediately)
2. **Identity spec** from the manifest
3. **Evaluation scores** from Gemini (character_likeness, expression_neutrality, style_match, feature_visibility)

### Approval/Rejection

- **Approve per-character**: User says "Hare looks good" → mark Hare as approved
- **Reject per-character**: User says "Fox's eyes are wrong" or "Tortoise is smiling, needs neutral" → regenerate that specific character
- **Regenerate with feedback**: Pass the user's feedback as refinement instructions to the character sheet prompt
- **No proceeding without approval**: Do NOT start scene generation until ALL characters are approved

### Neutrality Check

The Gemini evaluation for character sheets checks `expression_neutrality` (0-10). If a sheet scores < 6, flag it for regeneration rather than asking the user — a non-neutral sheet will cause expression drift in all downstream scenes.

```
Auto-reject criteria (don't even show to user):
- expression_neutrality < 6 → regenerate with "neutral resting face, no emotion"
- character_likeness < 5 → regenerate with stronger identity spec
- style_match < 5 → regenerate with style more prominently in prompt
```

### Implementation

In script form:
```bash
# Evaluate all character sheets
python3 evaluate_scene.py --manifest story_manifest.json --phase characters

# Review results — auto-reject if expression_neutrality < 6
# Only show to user if all auto-reject criteria pass
```

In agent workflow:
1. After Step C (upload), run character sheet evaluation for each image
2. Auto-reject any sheet with expression_neutrality < 6 — regenerate immediately
3. For sheets that pass auto-check, display them to the user with:
   - Image (inline or attached)
   - Character name + identity spec
   - Evaluation scores
4. Ask user to approve or reject per character
5. If rejected, incorporate user feedback and regenerate only that character
6. Loop until all characters approved

---

## Phase 1: Upload & Verify Character Reference Sheets

If Phase 0 has already generated character sheets, this phase is simply upload + verify.

1. **Upload generated sheets** — Use the curl command from Phase 0 Step C, or upload manually:
   `curl -X POST "$COMFY_URL/upload/image" -F "image=@teddy_bear_reference_sheet.png" -F "overwrite=true"`
2. **Verify availability** — Check `/object_info/LoadImage` for the `image` input's enum list of available filenames
3. **If a ref is missing** — Either run Phase 0 Step B to generate it, or create a character sheet manually and upload

### Reference Sheet Prompt Template

**⚠️ Neutrality is critical.** The default prompt below has been battle-tested to produce neutrality scores of 9-10/10. Earlier weaker prompts (single "neutral" mention, no ALL-CAPS) consistently scored 2-3/10. Do NOT soften the neutrality language.

```text
Create a professional character reference sheet for the following character.

Character: {identity_spec}

Layout:
- Top row: four full-body standing views (front, left 3/4 view, right side profile, back view)
- Bottom row: three face close-up portraits (front, left 3/4 angle, right side profile)

CRITICAL REQUIREMENTS - READ CAREFULLY:
- CONSISTENT identity across ALL seven views — same face, same body, same outfit
- STRICTLY NEUTRAL facial expression in ALL views — this is the most important requirement. The character must have a BLANK, CALM, RESTING face. ABSOLUTELY NO SMILING. NO FROWN. NO RAISED EYEBROWS. NO EMOTION WHATSOEVER. Just a completely neutral, relaxed, resting face with mouth closed and eyes looking forward. Think of a passport photo expression. If any view shows even a hint of a smile, it will be rejected.
- Clean white/neutral background
- Even studio lighting with no dramatic shadows
- Style: {style}
- Each view clearly separated with space between them
- Character should be the same scale/proportion in each view
```

#### Iterative Neutrality Loop (Battle-Tested)

If the initial generation scores < 6 on expression_neutrality (common with weaker prompts or certain character types), use this regeneration loop:

1. **Generate** the reference sheet
2. **Evaluate** with Gemini Vision: score expression_neutrality, character_likeness, style_match on 0-10 scale
3. **If neutrality < 6**: regenerate with the same prompt PLUS this appended feedback line:
   `SPECIFICALLY FIX THIS ISSUE FROM PREVIOUS ATTEMPT: {specific_issue_from_evaluation}`
4. **Repeat** up to 3 times. In practice, the improved prompt above scores 9-10 on first attempt.

**Results from testing:**
- Old prompt (single "neutral" mention, no emphasis): Gajoo scored **2/10**, Chinnu scored **3/10** on neutrality
- Improved prompt (ALL-CAPS, multiple reinforces, passport analogy): Gajoo scored **10/10**, Chinnu scored **9/10** on first generation

### Auto-Verify & Fallback

Always verify reference images exist on the instance before queuing. If a character's ref is missing:

```bash
# Check available images
curl -s "$COMFY_URL/object_info/LoadImage" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for img in data['LoadImage']['input']['required']['image'][0]: print(f'  - {img}')
"
```

Define fallbacks in the script config (e.g., fox missing → tortoise as similar woodland character).
