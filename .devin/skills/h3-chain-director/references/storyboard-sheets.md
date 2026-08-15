# Storyboard Sheet Generation Reference

Prompt-adherent storyboard-sheet generation using the gpt-image family. These sheets are previsualization grids, NOT final polished key art. Load this when generating storyboard sheets for clips.

---

## Panel Ceiling & Grid

| Constraint | Value | Note |
|---|---|---|
| Panel ceiling | 6–8 per sheet | Identity drift accumulates past ~6 panels `[primary, 2026-08]`. |
| Recommended grid | 3 columns × 2 rows, 6 panels | One sheet per clip; matches the 6–9 micro-shot grammar (tail shots omit panels). |
| Gutter style | Thin neutral gutters | Light grey, minimal — panels read as a sequence, not separated cards. |

State geometry explicitly in every prompt: **"3 columns × 2 rows, 6 panels, left-to-right then top-to-bottom"** with a per-panel shot description.

---

## Negative List (inline)

gpt-image has no `negative_prompt` parameter. Exclusions go inline in the prompt body:

```
no text, no captions, no labels, no numbers, no borders, no watermark
```

Append this verbatim to every sheet prompt.

---

## Determinism & Gating

| Property | Value |
|---|---|
| Seed support | None `[primary, 2026-08]` |
| Reproducibility | Sheets are never reproducible |
| Mandatory gate | Human or vision gate on every sheet |
| Regeneration | Must be cheap and idempotent-by-file (overwrite `sheet.png`, keep `sheet_prompt` + `prompt_hash`) |

Because there is no seed, a vision/human gate is **mandatory** — never ship a sheet unchecked. Regeneration replaces the file in place; the ledger `prompt_hash` detects stale renders.

---

## Reference Anchoring

| Strategy | Refs | Result |
|---|---|---|
| Description only | 0 | Identity drifts within 2 sheets. |
| `anchor` only (identity plate) | 1 | Stable identity, weak scene continuity. |
| `anchor + previous` | 2 | **Sweet spot** — identity lock + shot-to-shot continuity. |
| `anchor + previous + scene` | 3–4 | Good for location changes. |
| > 6 refs | 7+ | Degrades — model loses focus `[secondary, 2026-08]`. |

Max 4–6 reference images; degrading past ~7 `[secondary, 2026-08]`.

---

## Cost & Latency

Date-stamped 2026-08.

| Model | Resolution | Cost / sheet | Latency | Source |
|---|---|---|---|---|
| gpt-image-2 | 4K / medium | ≈ $0.24 | ~90–160s | `[primary, 2026-08]` |
| nano-banana-2 | 4K | ≈ $0.15 | faster | `[secondary, 2026-08]` |
| Seedream 4 | 4K | ≈ $0.03 / 1K | fastest | `[secondary, 2026-08]` |

14 sheets (one per clip) on gpt-image-2 ≈ **$3.4** before retries. Budget 1.5× for regeneration.

---

## Prompt Templates

### 1. Identity Plate

```
A character identity reference plate for {cast_id}.
{appearance_lock}. {wardrobe}.
Full-body front view, neutral studio lighting, plain background.
no text, no captions, no labels, no numbers, no borders, no watermark.
```

### 2. 3×2 Storyboard Sheet (anchor + previous refs)

```
A cinematic storyboard previsualization sheet, 3 columns × 2 rows, 6 panels,
left-to-right then top-to-bottom, thin neutral gutters between panels.
{style_block}

Panel 1: {shot_1_framing}, {shot_1_angle} — {shot_1_action}
Panel 2: {shot_2_framing}, {shot_2_angle} — {shot_2_action}
Panel 3: {shot_3_framing}, {shot_3_angle} — {shot_3_action}
Panel 4: {shot_4_framing}, {shot_4_angle} — {shot_4_action}
Panel 5: {shot_5_framing}, {shot_5_angle} — {shot_5_action}
Panel 6: {shot_6_framing}, {shot_6_angle} — {shot_6_action}

Character: {appearance_lock}. {wardrobe}.
References: identity plate = {anchor_asset}, previous sheet = {previous_asset}.
no text, no captions, no labels, no numbers, no borders, no watermark.
```

### 3. Single-Panel Regeneration / Repair

```
A single storyboard panel, {framing}, {angle} — {action}.
Character: {appearance_lock}. {wardrobe}.
Match the visual style of {previous_sheet_asset}.
no text, no captions, no labels, no numbers, no borders, no watermark.
```

---

## Sheet Role

A storyboard sheet is a **previsualization grid**: it blocks composition, framing, angle, and action per shot for the downstream video prompt. It is not final key art — polish, lighting fidelity, and fine texture are resolved by the video model, not the sheet.
