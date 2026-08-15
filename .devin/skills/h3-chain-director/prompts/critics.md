# Critics — Tier 1 Single-Pass Critique

**Input:** `ledger` (full) + `bible.json` + `sheet_prompts/` + `prompts_out/`.
**Output:** `<run_dir>/critique.md`.

## Job

Single-pass critique of the entire Tier 1 output: the ledger, bible,
sheet prompts, and clip prompts. Read once, score once, emit a rubric.
This is NOT multi-round — you diagnose, you do not fix.

## Rules

- **Single pass (CritiCS-style).** Read all artifacts once. Produce the
  rubric. Do not loop, do not rewrite, do not suggest rewrites — only
  diagnose.
- **Three check domains:**

### Continuity
- **Hinge linkage.** For every clip k>1: does `hinge_in` reference the
  same beat as clip k-1's `hinge_out`? Does the clip prompt's `[Shot 1]`
  open with a continuation (no cut verb)? A mismatch is `fail`.
- **Quad conflicts.** Check `clips[k].quads[]` for temporal
  contradictions: an item `destroyed` in clip 3 cannot be `held_by` a
  character in clip 5 without a restoration event.
- **Item state.** Verify SCORE tracking: `items[].state` transitions
  are monotone (`active → lost → destroyed`), never reversed without an
  on-screen event.

### Retention / Pacing
- **Shot density.** 6–9 shots per clip; flag <6 (too slow) or >9 (too
  fast for H3 coherence). Fallback profile (4–5 shots) is acceptable
  only if flagged.
- **WPS.** Spoken words per second ≤ 3.5 per line (from audio mapping).
  Flag violations.
- **Hook cadence.** Cold-open hook in clip 1 `[Shot 1]` (≤1.5s);
  re-hook every ~10s (every clip or every other clip); loopable final
  beat in the last clip's last shot.

### H3-Format
- **Label consistency.** Every `<Subject N>` in any clip prompt must be
  declared in `prompt_prefix`/`subject_definitions`. No clip invents
  labels. No index exceeds the wired reference count.
- **Frame grid.** Every clip's `length` satisfies `length % 17 == 5`.
  Flag off-grid clips.
- **Prompt structure.** Each clip prompt has exactly three sections
  (`summary`, `detailed_description`, `overall_soundscape`) in spec
  order. No duplicated shared sections. `[Shot 1]` has no timestamp;
  later shots have `At MM:SS.mmm` with increasing times.
- **Anti-bleed.** Clips with ≥2 cast have anti-bleed text at first
  appearance. Flag missing anti-bleed.

- **EIPE 6-question checklist per clip.** For each clip, answer:
  1. Does the summary have a task-type prefix?
  2. Does `[Shot 1]` have no timestamp?
  3. Are cut times strictly increasing within `duration_s`?
  4. Does every shot have one sound cue?
  5. Are only declared labels used?
  6. Is the hinge rule respected (clip k>1 opens with continuation)?
- **Severity → advisory/blocking.** `fail` on continuity (hinge
  mismatch, quad conflict) or H3-format (label violation, off-grid) =
  blocking. `warn` = advisory. `pass` = clear.

## Output format

```markdown
# Tier 1 Critique

## Rubric

| Domain | Check | Result | Detail |
|---|---|---|---|
| Continuity | Hinge linkage | pass/fail | <issues or "clean"> |
| Continuity | Quad conflicts | pass/warn/fail | <contradictions or "clean"> |
| Continuity | Item state | pass/warn/fail | <issues or "clean"> |
| Retention | Shot density | pass/warn | <per-clip flags> |
| Retention | WPS | pass/warn | <violations or "clean"> |
| Retention | Hook cadence | pass/warn/fail | <missing points> |
| H3-Format | Label consistency | pass/fail | <violations or "clean"> |
| H3-Format | Frame grid | pass/fail | <off-grid clips or "clean"> |
| H3-Format | Prompt structure | pass/warn/fail | <issues or "clean"> |
| H3-Format | Anti-bleed | pass/warn | <missing or "present"> |

## EIPE Per-Clip Checklist
| Clip | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 |
|---|---|---|---|---|---|---|
| 1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2 | ... |

## Verdict
blocking | advisory | pass

## Findings
1. <finding with severity, clip index, and location>
2. ...
```

## What invalidates the ledger

A `blocking` verdict means the clips must not be rendered. Rendering
with a hinge mismatch produces a visible jump at the clip seam; rendering
with a label violation causes the model to hallucinate a missing
reference. Fix the flagged clips, re-run this critique, then proceed to
rendering only on `pass` or `advisory`.
