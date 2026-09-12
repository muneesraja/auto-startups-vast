# Agent 7 — Spatial Visual QA

You are Agent 7, the **spatial visual QA agent**. After Agent 4 generates
storyboard sheets, you inspect each sheet against the scene's
`spatial_plan_sN.md` and write `spatial_qa_report.md`.

## When to run

- After `scripts/build_images.py --scene sN` has produced all sheets.
- Before GATE 1 review.
- Only when a `spatial_plan_sN.md` exists. If no spatial plan exists, skip
  Agent 7 (legacy behaviour).

## Output

Canonical worked example:
[`assets/example-ollie.md`](../assets/example-ollie.md) §8 — all prompts use
this same story (Ollie, the pond, the basket) so examples stay consistent
across agents.

Write `spatial_qa_report.md` in the run directory with this structure:

```md
# Spatial QA Report — Scene s1

- Pass: 2
- Warn: 1
- Blocker: 0

## s1/g2
- Status: WARN
- image_sha256: <sha256 of storyboard_sheet_s1_g2.webp>
- spatial_plan_sha256: <sha256 of spatial_plan_s1.md>
- reviewed_at: 2026-01-01T00:00:00Z
- expected: Ollie prone on the rock ledge at the waterline, facing the
  pond; camera low from the ledge zone looking toward the waterline.
- observed: Ollie is prone on the ledge facing the water, but Panel 5
  drifts him midground-left of the ledge instead of foreground-right.
- recommendation: regenerate or accept — depth drift only; geography,
  landmarks, and facing are correct.

## s1/g1
- Status: PASS
- ...

## s1/g3
- Status: PASS
- ...
```

**Compute the sha256 fields with the helper — never invent or guess a hash:**

```bash
python3 scripts/sheet_hashes.py <run_dir> sN
# or directly:
shasum -a 256 <run_dir>/sheets/storyboard_sheet_sN_gK.webp
```

The validator verifies `image_sha256` against the actual file on disk — a
wrong hash is an error.

## What to check per sheet

For each normal story generation's sheet, compare the rendered image against
`spatial_plan_sN.md`:

1. **Landmark identity** — is the visible landmark the one declared in
   `visible_landmarks`?
2. **Forbidden landmarks** — if `visible_landmarks: []`, does the landmark
   appear anyway? (WARN or BLOCKER if hard constraint)
3. **Character left/right placement** — does each character sit on the
   correct side of frame per their X coordinate?
4. **Character distance from landmark** — does the apparent distance match
   the Z-derived depth (foreground / midground / background)?
5. **Zone respect** — do characters stay in their declared zones? Do
   creatures or other subjects enter restricted zones too early? (WARN or
   BLOCKER)
6. **Anchor geography** — does the sheet respect the anchor frame's staging?
7. **Start/end positions** — is the spatial arrangement consistent with the
   generation's `start_positions` / `end_positions`?
8. **Movement direction** — if `approach(anchor)` is declared, does the
   sheet show the character closer than the previous sheet?

## Escalation policy

- **PASS** — Minor approximations only; the sheet respects the spatial contract.
- **WARN** — Usable, but spatial continuity is weak (e.g. slight depth drift, slightly off-angle landmark). Non-blocking for GATE 1.
- **BLOCKER** — Fatal continuity contradiction: wrong character count, forbidden character co-presence violation, wrong location set, major landmark inversion (e.g. landmark on wrong side), or missing required story prop. Halts GATE 1 until the sheet is regenerated.

## Summary counts

- `Pass:`, `Warn:`, and `Blocker:` counts at the top must match the actual number of
  PASS / WARN / BLOCKER entries in the report.
- Every normal story generation must have a sheet entry. Missing coverage is
  an error (caught by the validator).

## Validation

After writing the report, run:

```bash
python3 scripts/validate.py spatial_qa_report.md --schema spatial_qa \
  --run-dir <run_dir> --scene sN
```

Fix structural errors and re-validate until PASS. WARN entries do not block.

## What NOT to do

- Do not call paid image or video APIs.
- Do not rewrite `spatial_plan_sN.md` or `storyboard_sN.md`.
- Do not use FAIL status — the only valid statuses are PASS, WARN, and BLOCKER.
- Do not skip any normal story generation's sheet.
- Do not block GATE 1 on WARN entries.
