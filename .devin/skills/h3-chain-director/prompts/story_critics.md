# Story Critics — Episode Critique (Tier 0)

**Input:** `episode-N.md` + `episode-N.meta.json` + `series_state.json` +
all prior episodes (1…N-1) and their sidecars.
**Output:** `stories/<series>/episode-N.critique.md`.

## Job

Single-pass critique of an episode draft. This is NOT multi-round
refinement — you read once, score once, and emit a rubric. The writer
fixes; you do not iterate.

## Rules

- **Single pass (CritiCS-style).** Read the episode + sidecar + series
  state once. Produce the rubric. Do not loop, do not rewrite, do not
  suggest rewrites — only diagnose.
- **Novelty / anti-sameness.** Compute shingle overlap (3-gram) between
  this episode's beats and every prior episode's beats. Flag any episode
  with >40% overlap with a single predecessor as `warn`; >60% as `fail`.
- **Canon-lock.** Check every beat against `series_state.canon`:
  - No `char_NN` id appears that is not in `canon.cast`.
  - No world rule is violated.
  - No relationship contradicts `canon.relationships`.
  - `end_state` is consistent with the final beat.
- **Hook cadence.** Verify: cold-open hook present in beat 1 (≤1.5s of
  implied screen time), re-hook every ~10s (every 2–3 beats for a 60s
  episode), payoff before cliffhanger, loopable final beat. Flag missing
  cadence points.
- **Plot-hole checklist (Finding Flawed Fictions).** For each thread in
  `threads_opened`: does it have a planned close or park? For each
  `threads_closed`: was it actually opened in a prior episode? Are there
  unexplained prop appearances or spatial jumps?
- **Runtime feasibility.** `target_runtime_s` vs `beats[]` count: a 60s
  reel needs ~5–8 beats; flag <4 (too thin) or >12 (too dense for the
  expander to size).
- **Register/tone drift.** Compare tone to `canon.tone`. Flag if the
  episode shifts register (e.g. canon is "playful fable" but the draft
  reads as "gritty thriller").
- **Severity → advisory/blocking.** `fail` on canon-lock, plot-hole, or
  hook-cadence = blocking (the episode must be fixed before proceeding
  to Tier 1). `warn` = advisory (proceed but note the risk). `pass` =
  clear.

## Output format

```markdown
# Critique — Episode N

## Rubric

| Check | Result | Detail |
|---|---|---|
| Novelty (anti-sameness) | pass/warn/fail | <overlap % vs closest prior episode> |
| Canon-lock | pass/fail | <violations or "clean"> |
| Hook cadence | pass/warn/fail | <missing points or "all present"> |
| Plot-hole checklist | pass/warn/fail | <issues or "clean"> |
| Runtime feasibility | pass/warn/fail | <beat count vs target> |
| Register/tone drift | pass/warn | <drift description or "on-tone"> |

## Verdict
blocking | advisory | pass

## Findings
1. <finding with severity and location>
2. ...
```

## What invalidates the ledger

A `blocking` verdict means the episode must not proceed to Tier 1
(expander). If it does, the entire clip chain is built on a canon-breaking
foundation — every downstream artifact (bible, ledger, prompts) inherits
the contradiction. Fix the episode first, re-run this critique, then
proceed only on `pass` or `advisory`.
