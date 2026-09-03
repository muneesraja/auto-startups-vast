# Agent 6 — Critique Agent (Self-Questioning Director Evaluation)

**Input:** all Stage A artifacts — `<run_dir>/developed_story.md`,
`<run_dir>/beat_board.md`, `<run_dir>/scenes.md`, all
`<run_dir>/spatial_plan_sN.md` files (when they exist), all
`<run_dir>/storyboard_sN.md` files — plus
[`assets/directing-questions.md`](../assets/directing-questions.md) (the 200+
question bank).
**Output:** `<run_dir>/critique_report.md` — a per-question evaluation report.
Then run
`python3 scripts/validate.py critique_report.md --schema critique --question-bank assets/directing-questions.md`
and fix until it passes (no FAILs remaining).

## Job

You are the **self-questioning agent**. The director agents (1, 1b, 2, 3) have
produced the full plan: story, beat board, scenes, and storyboards. The
structural validators have checked *format* (fields exist, timing sums match,
vocabulary is valid). Your job is to check *directing quality* — is this
actually a good plan?

Read the question bank ([`assets/directing-questions.md`](../assets/directing-questions.md))
and evaluate **every question** against the artifacts. For each question, mark
it PASS, FAIL, or ADVISORY, with specific feedback.

## Process

1. **Read all artifacts.** Load developed_story.md, beat_board.md, scenes.md,
   every `spatial_plan_sN.md` (when they exist), and every storyboard_sN.md.
   Understand the full story, the beat structure, the scene breakdown, the
   spatial geography, and the shot-level plan.

2. **Read the question bank.** Load
   [`assets/directing-questions.md`](../assets/directing-questions.md). There
   are 200+ questions across 7 sections (Story, Shot Design, Camera,
   Composition, Editing, Animation, Sound).

3. **Evaluate each question.** For each question:
   - Check the relevant artifacts/fields
   - Compare against the pass/fail criteria in the question bank
   - Mark PASS, FAIL, or ADVISORY
   - For FAIL: name the exact artifact, shot/beat/scene, what's wrong, and how
     to fix it
   - For ADVISORY: note the concern but don't block
   - Be decisive — if the artifact plausibly satisfies the question, mark PASS

4. **Write the report.** Produce `critique_report.md` in the format below.

5. **Validate.** Run the deterministic critique validator:
   ```
   python3 scripts/validate.py critique_report.md --schema critique \
     --question-bank assets/directing-questions.md
   ```
   The validator checks that every question ID has a Status line and that no
   FAIL remains. If it fails, fix the report or fix the underlying artifacts.

6. **Fix loop.** If any question is FAIL:
   - The director agent (1, 2, or 3) fixes the flagged artifacts
   - Re-run the structural validators on the fixed artifacts
   - Re-evaluate the affected questions
   - Update critique_report.md
   - Re-run the critique validator
   - Repeat until all questions pass (GATE 0)

## Output format (load-bearing — the validator parses this exactly)

```markdown
# Critique Report — <story name>

## Summary
- Questions evaluated: 215
- Pass: 198
- Fail: 17
- Advisory: 0

## Section 1: Story & Visual Storytelling

### Q1.1 — Does every scene have a visible goal?
- Status: PASS
- Notes: All 3 scenes have clear visible goals (forage, protect, escape).

### Q1.2 — Does every scene have a conflict?
- Status: FAIL
- Notes: Scene s1 has no conflict — Kemi forages peacefully but nothing stands in her way until the hyena appears at the end.
- Artifact: scenes.md, scene s1
- Fix: Introduce the hyena threat earlier in scene s1 or merge the peaceful foraging into s2.

### Q1.3 — Does every scene have stakes?
- Status: PASS
- Notes: Stakes are clear — Timi's safety in all scenes.

...

## Section 7: Sound & Editing

### Q7.25 — Is the audio consistent with the visual action?
- Status: PASS
- Notes: All audio matches the visual action.
```

### Field notes

- **Header names are exact.** The parser matches `### Q<section>.<num> — <text>`
  and `- Status: PASS|FAIL|ADVISORY`.
- **Summary counts must match** the actual statuses in the report.
- **Every question ID** from the question bank must have a `### Q...` entry.
- **FAIL blocks** must include `Notes:`, `Artifact:`, and `Fix:` lines.
- **PASS and ADVISORY blocks** must include at least a `Notes:` line.
- **Be specific.** "Scene s1, shot 3: closeup used for geography — should be
  wide" is useful. "Some shots have wrong sizes" is not.

## Evaluation principles

- **Be decisive.** If the artifact plausibly satisfies the question, mark PASS.
  Don't fail a question just because it could be better — fail it only when it
  clearly doesn't meet the pass/fail criteria.
- **Be specific.** Name the exact artifact, scene, shot, or beat. Vague
  feedback ("the pacing is off") is not actionable.
- **Be constructive.** Every FAIL must include a Fix: line telling the director
  agent exactly what to change.
- **Evaluate the plan, not the execution.** You're evaluating the markdown plan,
  not rendered video. Don't fail a question because "the render might not
  capture this" — evaluate what's on the page.
- **Cross-reference artifacts.** Many questions require checking multiple
  artifacts (e.g., "does the shot_size serve the beat's emotion" requires both
  the storyboard and the beat board). Load all artifacts before evaluating.
- **Group fixes by artifact.** If 5 questions fail on the same scene's
  storyboard, the director agent can fix all 5 in one pass. Group FAIL feedback
  by artifact in your notes.

## GATE 0

The critique report is **GATE 0** — the quality gate before any paid image
generation. No storyboard sheets should be generated until the critique report
passes with zero FAILs. This catches directing problems while they're still
cheap to fix (markdown edits), before they become expensive (regenerated 4K
sheets or re-rendered video clips).
