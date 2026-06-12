# QC Prompt Template — Worked Examples

## Template 1: FF Gate (Character Sheet)

**Use case:** Verify that the generated FF still matches the character reference sheet.

**Image budget:** 2 (FF + 1 ref)

**Inputs:**
- FF PNG (the generated image)
- 1 character reference sheet (front view, neutral expression)
- `qc_reference_strategy.ff_gate`

**Prompt:**
```text
You are a quality control reviewer for AI-generated film stills.

Compare the generated image (Image 1) against the provided character reference sheet (Image 2) and determine if the character matches.

For this image, evaluate:
1. CHARACTER_LIKENESS (0-10): Does the character's appearance match the reference sheet?
2. STYLE_MATCH (0-10): Does the visual style match?
3. EXPRESSION_NEUTRALITY: N/A for scene stills

Reference sheet: Chomp is a 6-month-old gray wolf cub with soft fur, big amber eyes, white chest patch, slightly oversized paws. 3D Pixar style.

Generated image context:
- Shot: shot05_ff
- First Frame prompt: "A 6-month-old gray wolf cub named Chomp..."
- Characters expected: chomp
- Gate: ff_gate

Respond in JSON:
{
  "character_likeness": <0-10>,
  "style_match": <0-10>,
  "expression_neutrality": "N/A",
  "overall_score": <0-10>,
  "pass": <true/false>,
  "rejection_reason": "...",
  "specific_issues": [...]
}
```

## Template 2: LF Gate (Continuity + Character)

**Use case:** Verify that LF matches FF (continuity) AND that the character still matches the reference.

**Image budget:** 3 (LF + FF + 1 ref)

**Inputs:**
- LF PNG
- FF PNG (for continuity check)
- 1 character reference sheet

**Prompt:**
```text
You are a quality control reviewer for AI-generated film stills.

Compare the last frame (Image 1) against the first frame (Image 2) and the character reference sheet (Image 3) and determine:
1. Is the last frame a valid edit of the first frame? (continuity check)
2. Does the character still match the reference sheet?

Evaluate:
1. CHARACTER_LIKENESS (0-10): Does the character match the reference?
2. STYLE_MATCH (0-10): Is the 3D Pixar style maintained?
3. CONTINUITY_DELTA (0-1): Visual difference from FF (0 = identical/frozen, 1 = very different)
   - If 0, the edit had no effect and the shot is FROZEN

Reference sheet: Chomp is a 6-month-old gray wolf cub, amber eyes, white chest patch, 3D Pixar style.

Generated image context:
- Shot: shot05_lf
- First Frame prompt: "A 6-month-old gray wolf cub..."
- Last Frame prompt: "Edit image 1. KEEP UNCHANGED: Chomp identity... CHANGE: head turns 30° right, ears flatten..."
- Characters expected: chomp
- Gate: lf_gate

Respond in JSON:
{
  "character_likeness": <0-10>,
  "style_match": <0-10>,
  "continuity_delta": <0-1>,
  "pass": <true/false>,
  "rejection_reason": "...",
  "specific_issues": [...]
}
```

## Template 3: Motion Eval (v2.1, deferred)

**Use case:** Verify motion fluidity and subject consistency across video frames.

**Image budget:** 5 (3 video frames at 10%/50%/90% + FF + LF)

**Inputs:**
- 3 video frames (extracted at 10%, 50%, 90% of video duration)
- FF PNG
- LF PNG

**Prompt:** (similar structure, focused on motion)

## Anti-Patterns (DO NOT USE)

### ❌ Anti-Pattern 1: Vague prompt

```text
Does this image look good? Score it 1-10.
```

**Why wrong:** No specific criteria, no reference comparison, no JSON structure. Useless verdict.

### ❌ Anti-Pattern 2: Prose-only response

```text
The image looks mostly good. The character's eyes are slightly off-color...
```

**Why wrong:** Not parseable as JSON, can't be used by the retry loop. The verdict has to be machine-parseable.

### ❌ Anti-Pattern 3: Multiple images not labeled

```text
Compare these 3 images.
```

**Why wrong:** Model doesn't know which is FF, which is LF, which is reference. Always label them.
