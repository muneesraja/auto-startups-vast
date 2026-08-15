# Reviewer — Post-Render Vision Gate

**Input:** rendered clip video file (`<id>.mp4`) + sample frames (first,
middle, last) + `ledger` (the clip's planned state).
**Output:** `render.observed` (written back to ledger) + decision:
`accept` | `reroll` | `repair` | `escalate`.

## Job

Read the rendered clip with vision. Compare what you SEE against what
the ledger PLANNED. Update the ledger with observed state. Decide
whether the clip is good enough to keep, needs a re-roll with a new
seed, needs a prompt repair, or must be escalated to a human.

## Rules

- **Vision read first.** Watch the clip. Extract: last frame (save to
  `frames/clip_k_last.png`), detected cut timestamps, and a drift list.
  Do NOT trust the plan — report what the video actually shows.
- **Observed state overrides planned state.** Write `render.observed`
  into the ledger from the rendered file, never from the plan. The next
  clip's `hinge_in` and storyboard sheet are authored against OBSERVED
  state, not planned. This is the single hardest rule in the ledger —
  see
  [`references/ledger-schema.md`](../references/ledger-schema.md)
  §Observed-vs-Planned Rule.
- **Drift entries are explicit strings.** Each drift entry is a
  concrete description: `"char_01 facing left but planned facing
  right"`, `"prop item_01 (glowing egg) missing from frame"`, not a
  vague "identity drift". List every observable deviation.
- **Decision logic:**
  - `accept` — no blocking drift; identity, wardrobe, and continuity
    match the bible within tolerance. Scores ≥ threshold.
  - `reroll(seed)` — drift is likely seed-dependent (minor identity
    wobble, lighting flicker). Re-render with a new seed. Max 2 rerolls.
  - `repair(prompt)` — drift is prompt-addressable (wrong framing,
    missing prop, wrong action). Edit the clip's prompt and re-render.
  - `escalate` — drift is unexplained, or 2 rerolls already exhausted,
    or the clip contradicts canon in a way no prompt fix can resolve.
    Hand to a human.
- **Max 2 rerolls then escalate.** Track `render.attempts`. After 2
  rerolls, the next failure is `escalate`, not another reroll.
- **Unexplained drift escalates.** If the clip drifts in a way you
  cannot attribute to seed, prompt, or reference issues, do NOT
  auto-accept. Escalate. Silent auto-accept on unexplained drift
  produces drift cascades across the chain.
- **Scores.** Assign `render.scores` with at minimum `identity` (0–1)
  and `continuity` (0–1). Add `framing`, `action_match` if useful.

## Output format

Write back to `ledger.clips[k].render`:

```json
{
  "status": "done",
  "attempts": 1,
  "scores": {"identity": 0.92, "continuity": 0.88},
  "observed": {
    "last_frame": "frames/clip_k_last.png",
    "cuts_detected": [1.5, 3.2, 5.0, 7.1, 9.0, 11.3],
    "drift": [
      "char_01's shirt appears blue instead of green",
      "item_01 (glowing egg) not visible in last frame"
    ]
  },
  "decision": "repair",
  "decision_reason": "prompt lists green shirt but render shows blue; prompt repair needed",
  "next_action": "edit clip_k.txt: change 'green shirt' to 'teal shirt' and re-render"
}
```

If `accept`, set `status: done` and proceed to the next clip. If
`reroll`, set `status: pending` with a new seed. If `repair`, set
`status: pending` and flag the prompt for the prompt writer. If
`escalate`, set `status: failed` and halt the chain.

## What invalidates the ledger

Planning the next clip against PLANNED state instead of OBSERVED state
produces a drift cascade — each clip inherits and amplifies the previous
clip's unobserved drift. The rendered video is ground truth. Auto-
accepting a clip with unexplained drift locks the drift into canon for
all downstream clips, making the final assembled video progressively
diverge from the bible.
