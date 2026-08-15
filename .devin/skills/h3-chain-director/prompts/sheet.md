# Sheet Author — Storyboard Sheet Prompts

**Input:** `ledger.clips[]` + `bible.json`.
**Output:** `sheet_prompts/clip_k.txt` — one storyboard sheet prompt per
clip.

## Job

Write 3×2 panel-grid storyboard sheet prompts for the gpt-image family.
Each sheet is a previsualization grid that blocks composition, framing,
angle, and action per shot for the downstream video prompt. This is NOT
key art — polish and fine texture are resolved by the video model.

## Rules

- **Grid geometry.** State explicitly in every prompt: **"3 columns × 2
  rows, 6 panels, left-to-right then top-to-bottom"** with thin neutral
  gutters. One sheet per clip.
- **Per-panel shot description.** Each panel gets: framing, angle,
  action, environment, lighting. Pull these from `ledger.clips[k].shots`
  — panels map to shots in order. If a clip has 7+ shots, the last 1–2
  shots are video-only tail beats with no dedicated panel (see
  [`references/micro-shot-grammar.md`](../references/micro-shot-grammar.md)
  §Worked Example).
- **Inline negatives.** gpt-image has no `negative_prompt` parameter.
  Append this verbatim to every sheet prompt:
  `no text, no captions, no labels, no numbers, no borders, no watermark`
- **≤6 reference images.** Use the anchor + previous strategy: identity
  plate (`asset_id@version` from `bible.json`) + previous clip's sheet.
  Max 4–6 refs; degrading past ~7. See
  [`references/storyboard-sheets.md`](../references/storyboard-sheets.md)
  §Reference Anchoring.
- **Anchor + previous chaining.** Clip 1: anchor (identity plate) only.
  Clip 2+: anchor + previous sheet. This gives identity lock +
  shot-to-shot continuity — the sweet spot.
- **Sheet is previsualization, NOT key art.** Write the prompt for
  composition blocking, not polish. Do not describe fine texture,
  photorealistic lighting, or render quality — the video model handles
  that. Describe what is in each panel: who, where, what action, what
  framing.
- **Character appearance from bible.** Pull `appearance_lock` and
  `wardrobe` from `bible.json` for each character in the clip. Use the
  lock verbatim — never paraphrase appearance in a sheet prompt.
- **Hinge panels.** If clip k+1's first shot is a hinge continuation,
  clip k+1's panel 1 should visually match clip k's last panel (same
  composition, held pose).

## Output format

One text prompt per clip at `sheet_prompts/clip_k.txt`:

```
A cinematic storyboard previsualization sheet, 3 columns × 2 rows, 6 panels,
left-to-right then top-to-bottom, thin neutral gutters between panels.
<style block from bible/treatment>

Panel 1: <framing>, <angle> — <action>, <environment>, <lighting>
Panel 2: <framing>, <angle> — <action>, <environment>, <lighting>
Panel 3: <framing>, <angle> — <action>, <environment>, <lighting>
Panel 4: <framing>, <angle> — <action>, <environment>, <lighting>
Panel 5: <framing>, <angle> — <action>, <environment>, <lighting>
Panel 6: <framing>, <angle> — <action>, <environment>, <lighting>

Character: <appearance_lock>. <wardrobe>.
References: identity plate = <anchor_asset>, previous sheet = <previous_asset>.
no text, no captions, no labels, no numbers, no borders, no watermark.
```

Also write `sheet_prompt` back into `ledger.clips[k].sheet_prompt`.

## What invalidates the ledger

Changing the panel-to-shot mapping after a sheet is generated
invalidates the sheet (the drawn panels no longer match the ledger's
shot plan). The sheet must be regenerated and the video prompt updated
to match. Swapping the anchor identity plate after sheets are drawn
breaks identity continuity — all sheets referencing the old plate must
be regenerated against the new `asset_id@version`.
