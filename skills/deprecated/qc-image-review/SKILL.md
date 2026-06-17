---
name: qc-image-review
version: 2.0.0
description: Binary pass/fail QC gate for AI-generated stills and video frames. Uses Gemini 3.1 Flash Lite via OpenRouter. Per-gate image budget enforcement. Strict JSON output. Owned by stv-reviewer profile.
tags: [qc, validation, gemini, vision, openrouter, v2.0]
metadata:
  hermes:
    related_skills: [story-direction, comfyui-ops]
---

# QC Image Review (v2.0)

## Quick-start (one sentence)

Run binary pass/fail QC on a generated image by sending it + reference sheets to Gemini 3.1 Flash Lite via OpenRouter, with strict per-gate image budget enforcement and structured JSON output.

---

## What changed in v2.0

| Area | v1.4.0 (monolith) | v2.0 (chunked) |
|---|---|---|
| Output | Weighted score (0-10) + prose | **Binary pass/fail + JSON** |
| Model | Gemini 2.5 Flash (hallucinated cherry) | **Gemini 3.1 Flash Lite** (validated for likeness) |
| Per-gate spec | Loose | **Strict 2/3/5 image budget** (FF/LF/motion) |
| Cost | Variable (~$0.10/shot) | **~$0.003/shot** (40x cheaper) |
| Retry | Manual | **1 retry max, then escalate** |

---

## 1. Role

You are the **strict binary gatekeeper**. You do NOT give scores with commentary. You give **PASS or FAIL** with a single sentence rejection reason. That's it.

You run 3 distinct gates, each with a different image budget:
- **FF gate** (2 images: FF + 1 ref)
- **LF gate** (3 images: LF + FF + 1 ref)
- **Motion eval gate** (5 images: 3 video frames + FF + LF) — **v2.1, deferred in v1.0**

The Director picks which character sheet variant to pass per gate per shot via `qc_reference_strategy`. You respect that.

---

## 2. Why Gemini 3.1 Flash Lite (Not 2.5 Flash)

In the wolf story, Gemini 2.5 Flash hallucinated character identity: it described a wolf cub as "a cherry in a kitchen" (it had also been trained on the cherry story). This is a **catastrophic failure mode** for QC.

Gemini 3.1 Flash Lite is validated for:
- **Likeness scoring** (the specific task we need)
- **Style match** (3D Pixar vs other)
- **Continuity delta** (LF vs FF)

Cost: ~$0.0005 per image, ~$0.014 per 14-shot film. **Negligible versus generation cost.**

---

## 3. The QC Prompt Template

```python
REVIEW_PROMPT = """You are a quality control reviewer for AI-generated film stills.

Compare the generated image (Image 1) against the provided character reference sheet(s) and determine if the character matches.

For each image, evaluate:
1. CHARACTER_LIKENESS (0-10): Does the character's appearance match the reference sheet? Check proportions, colors, features.
2. STYLE_MATCH (0-10): Does the visual style match? (3D Pixar, chibi, realistic, etc.)
3. EXPRESSION_NEUTRALITY (0-10, reference sheets only): Is the expression neutral/calm? (Not applicable for scene stills — use N/A)

Reference sheets:
{reference_descriptions}

Generated image context:
- Shot: {shot_prefix}
- First Frame prompt: {ff_prompt}
- Last Frame prompt: {lf_prompt}
- Characters expected: {characters_present}

Respond in JSON:
{{
  "character_likeness": <0-10>,
  "style_match": <0-10>,
  "expression_neutrality": <0-10 or "N/A">,
  "overall_score": <0-10>,
  "pass": <true/false>,
  "rejection_reason": "<string, only if pass=false>",
  "specific_issues": ["<issue1>", "<issue2>"]
}}"""
```

---

## 4. Per-Gate Image Budget

| Gate | Max images | Includes | Cost (approx) |
|---|---|---|---|
| FF | 2 | FF + 1 ref | ~$0.0005 |
| LF | 3 | LF + FF + 1 ref | ~$0.001 |
| Motion (v2.1) | 5 | 3 video frames + FF + LF | ~$0.0015 |

**Total per shot (worst case): 5 images = ~$0.003**
**Total per 14-shot film: 14 × $0.003 = ~$0.042**

**Hard enforcement:** if `qc_reference_strategy` requests more than the budget, use the first N and log a warning.

---

## 5. How to Call (openrouter_qc.py)

```python
def review_image(
    image_paths: list[str],
    shot_metadata: dict,
    gate: str,  # "ff_gate" | "lf_gate" | "motion_eval"
    comfyui_url: str = None,
) -> dict:
    """
    Run binary pass/fail QC on an image.
    
    Args:
        image_paths: list of local file paths to include (max per budget)
        shot_metadata: shot info from story_manifest.json
        gate: which gate to run
        comfyui_url: optional, for downloading remote images
    
    Returns:
        JSON dict with pass/fail verdict and scores
    """
```

### Image compression for bandwidth
All images inlined as **JPEG q=85** in base64 (not PNG). PNG only if transparency is required (rare).

### Temperature
`0.1` — strict evaluation, minimal creativity.

### Max tokens
`1024` — cheap, fast, sufficient for the JSON output.

---

## 6. Pass/Fail Logic

### FF Gate
- `pass` if `character_likeness >= 7.0` AND no critical issues
- Critical issues: extra limbs, NSFW, corruption, missing character entirely

### LF Gate
- `pass` if `character_likeness >= 7.0` AND `continuity_delta > 0` AND no critical issues
- `continuity_delta` = visual difference from FF (0 = identical = frozen shot, FAIL)

### Motion Eval Gate (v2.1, deferred)
- `pass` if motion fluidity is high AND subject consistency is maintained across frames
- Skipped in v0.1 / v1.0 (too expensive, Director reviews motion manually)

---

## 7. Retry Logic

After 1 FAIL on the same shot:
1. Escalate to `stv-director` via `kanban_block(reason="QC failed: <reason>")`
2. Director decides: spawn retake sub-task OR accept current state

**Do not retry indefinitely** — that's a budget sink. 1 retry max per shot.

---

## 8. Output Contract

```json
{
  "gate": "ff_gate",
  "shot_id": "shot05",
  "pass": false,
  "scores": {
    "character_likeness": 6.2,
    "style_match": 8.5,
    "continuity_delta": null
  },
  "rejection_reason": "Chomp's eyes are blue instead of amber per the reference sheet",
  "specific_issues": [
    "eye color drift: blue vs amber",
    "fur texture slightly grayer than reference"
  ],
  "image_budget_used": 2,
  "cost_usd": 0.0005,
  "timestamp": "2026-06-12T06:00:00Z"
}
```

Strict JSON only. No prose around it.

---

## 9. Pre-Flight Text Audit (No Images)

Before any image generation, run a text-only audit on the prompts to catch obvious drift triggers. **All checks are text-based** — no image analysis happens at this stage.

### Risk 1: FROZEN
- **Symptom:** LF prompt is so similar to FF prompt that the I2I edit will have no visible effect (e.g., FF/LF differ by <10% of words, OR LF prompt is missing the required Edit-Instruction structure).
- **Detection:**
  - Word-level Jaccard similarity between FF prompt and LF prompt > 0.85, OR
  - LF prompt missing required Edit-Instruction keywords (`KEEP UNCHANGED:`, `CHANGE:`, `CAMERA:`, `MOOD:`)
- **Action:** Block the shot, ask Director to redesign LF. The i2i-writer probably fell back to T2I vocabulary (the 71% drift vector from the elephant story).

### Risk 2: SUBTLE
- **Symptom:** LF prompt is valid Edit-Instruction but the CHANGE section is minimal (≤3 non-stop-word tokens). The shot will pass structural checks but produce a barely-visible edit.
- **Detection:**
  - LF prompt has all 4 required Edit-Instruction sections, but
  - The CHANGE section has fewer than 3 non-stop-word tokens
- **Action:** Flag for Director, suggest more concrete pose deltas in CHANGE (degrees, distances, body parts).

### Risk 3: RADICAL
- **Symptom:** LF prompt describes a completely different scene from FF (e.g., new location, new characters entering, scene change).
- **Detection:**
  - FF prompt and LF prompt have <10% word overlap, OR
  - LF prompt introduces new characters not present in FF
- **Action:** Flag for Director, suggest breaking the shot into 2 separate shots or using a tail frame anchor.

### Implementation
- The `scripts/prompt_audit.py` script from the v1.4.0 monolith (`~/.hermes/skills/creative/story-to-video-filmmaking/scripts/prompt_audit.py`) does the text-only audit.
- v0.1 calls it as a pre-flight step before any image generation.
- v1.0 will rewrite this as a standalone `qc-image-review/scripts/text_audit.py` (deferred — not blocking v0.1).

---

## 10. Anti-temptation

You will be tempted to be helpful:
- "Here's a 6.8/10, maybe regenerate with this prompt tweak"
- "Looks good overall, just minor issues"
- "Score 8.5, would ship"

**Don't.** That's the Director's job, not yours. You are a gate, not a coach. PASS or FAIL, that's it. If you find yourself writing prose, you're doing the Director's job. Stop and emit JSON.

---

## 11. Migration from v1.4.0

The old `stv-reviewer` profile gave weighted scores with prose feedback. **That mode is retired.** v2.0 is binary only.

If you're given a `gemini_eval.py` task from v1.4.0, redirect: use `openrouter_qc.py` (this skill's script) with the new JSON output contract.
