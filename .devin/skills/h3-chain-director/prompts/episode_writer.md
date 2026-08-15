# Episode Writer — Episode Prose

**Input:** season arc (next 1–2 detailed episodes) + `series_state.json` +
previous episode's rendered end state (`episode_end_states[N-1]`).
**Output:** `stories/<series>/episode-N.md` + `stories/<series>/episode-N.meta.json`.

## Job

Write the episode as loose, playful, present-tense prose — not screenplay
format, not rigid beat sheets. This is the house style. The prose feeds
the expander (Tier 1) which turns it into a filmable treatment.

## House style exemplars

Read `stories/bamboo-the-dino/episode-1.md` before writing. These
verbatim excerpts demonstrate the voice:

> "A curious little baby discovers a mysterious egg hidden in a dusty
> basement. While playing with it, the egg suddenly begins to crack. Out
> hatches an adorable baby dinosaur with huge yellow eyes."

> "Terrified, the baby mistakes the dinosaur for a monster and runs away
> through the basement. Believing the baby is its parent, the innocent
> dinosaur joyfully follows, trying to stay close rather than harm the
> baby."

> "Instead of attacking, the dinosaur simply smiles, looks up with its
> big yellow eyes, and softly says, **"Mama!"** Realizing the tiny
> creature is completely harmless and only wants love, the baby's fear
> begins to melt away, marking the beginning of an unexpected friendship
> between the two."

House rules: present tense, casual capitalization tolerated, similes over
literalism, physical comedy described as action not labeled, run-on
energy is acceptable. Do NOT polish this into formal screenwriting.

## Rules

- **HoLLMwood Writer + Actor.** Write prose with the Writer persona; let
  the Actor persona handle dialogue lines — keep them short, punchy, and
  in-character.
- **CONCOCT concreteness.** Every beat has a concrete physical anchor:
  a prop, a gesture, a spatial change. No abstract emotional narration
  without a visible correlative.
- **Continue from rendered state.** If this is episode 2+, read
  `episode_end_states[N-1]` from `series_state.json` — that is the
  RENDERED end state from the previous episode's final clip, not the
  scripted claim. Continue from THAT.
- **Stable cast ids.** Use the exact `char_NN` ids from
  `series_state.canon.cast`. Never invent new ids.
- **Hook cadence.** Structure beats to hit: cold-open hook in the first
  beat, re-hook every ~10s of screen time, payoff before the
  cliffhanger, loopable final beat. See
  [`references/series-continuity.md`](../references/series-continuity.md)
  §Hook cadence.
- **Sidecar.** Produce `episode-N.meta.json` with `end_state`,
  `threads_opened[]`, `threads_closed[]`, `hook`, `beats[]`,
  `format`, `target_runtime_s`. Follow the schema in
  [`references/series-continuity.md`](../references/series-continuity.md)
  §`episode-N.meta.json`.
- **Skip if exists.** If `episode-N.md` already exists, SKIP this role.
  W4 (story critics) audits the existing file instead.

## Output format

### `episode-N.md`

Free-form present-tense prose, 3–8 paragraphs. No headers, no beat
labels — just the story. Bold dialogue with `**"..."**`.

### `episode-N.meta.json`

```json
{
  "episode": N,
  "end_state": "<one-line description of the final state>",
  "threads_opened": ["<thread_id>", ...],
  "threads_closed": ["<thread_id>", ...],
  "hook": "<the cold-open hook>",
  "beats": ["<beat 1>", "<beat 2>", ...],
  "format": "short-form reel",
  "target_runtime_s": 60
}
```

## What invalidates the ledger

Writing episode N+1 against the scripted `end_state` instead of the
rendered `episode_end_states[N]` produces a continuity break — the
video shows one thing, the next episode's prose assumes another. The
rendered video is ground truth; always continue from it.
