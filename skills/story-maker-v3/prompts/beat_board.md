# Agent 1b — Beat Board

**Input:** `<run_dir>/developed_story.md` (Agent 1) + target duration.
**Output:** `<run_dir>/beat_board.md` — the story's dramatic beats before scenes are formed.
Then run `python3 scripts/validate.py beat_board.md --schema beat_board --target-seconds <N>`
and fix until it passes.

## Job

Extract the story's **dramatic beats** — the meaningful changes that drive the
narrative. A beat is NOT "girl walks → girl walks." A beat is "something happens
that changes the character's situation or emotion."

The beat board is the bridge between the developed story and the scene breakdown.
Agent 2 (scene writer) reads it to decide how to group beats into scenes.

## Rules

- **8–15 beats** for short-form (30s–5min). Fewer for very short ads (min 3).
  More for longer episodes, but never fewer than 3.
- **Each beat is a change.** If a beat doesn't change the character's situation,
  emotion, or the audience's understanding, it's not a beat — cut it.
- **Visible action.** Write what the camera can see, not inner thoughts.
  "Kemi freezes, eyes wide" not "Kemi feels afraid."
- **Emotional register.** Name the emotion the audience should feel. This drives
  shot size, camera, pacing, and sound choices downstream. See
  [`assets/directors-guide.md`](../assets/directors-guide.md) Section 1 for the
  emotion→visual mapping.
- **Estimated timing.** Rough seconds per beat — these are guides for Agent 2's
  scene sizing, NOT binding. The actual timing is set by `scenes.md`
  `target_seconds`. Don't overthink precision; a 15s estimate is fine for a
  beat that might be 10–20s.
- **Anti-sameness.** Consecutive beats must differ in emotional register,
  location, or action type. Three "tension" beats in a row means the story is
  stalling — escalate or change.
- **Story structure.** The beats should trace the spine:
  setup → escalation → climax → resolution. The first beat establishes, the
  middle beats escalate, one beat is the climax (maximum tension/turning point),
  and the last beat resolves.

## Output format (load-bearing — the validator parses this exactly)

```
# Beat Board — <story title>

target_seconds: 180
beat_count: 9

## Beat 1 — Joy
description: Kemi and baby Timi forage peacefully along a sunlit jungle stream.
emotion: joy
estimated_seconds: 15

## Beat 2 — Omen
description: Birdsong fades to dead silence; menacing yellow eyes open in the undergrowth.
emotion: unease
estimated_seconds: 8

## Beat 3 — Threat
description: A fierce hyena emerges snarling from the shadows.
emotion: fear
estimated_seconds: 7

## Beat 4 — Chase
description: Kemi clutches her plantains and sprints through thick foliage with the predator in pursuit.
emotion: tension
estimated_seconds: 12

## Beat 5 — Stand
description: Kemi reaches a clearing, lowers the plantains, and pivots into a martial arts stance.
emotion: determination
estimated_seconds: 6

## Beat 6 — Duel
description: Kemi and the hyena clash in a wire-fu style duel; she dodges claws and delivers acrobatic kicks.
emotion: excitement
estimated_seconds: 15

## Beat 7 — Impact
description: A falling Fufu tin drops from the sky and bonks the hyena flat on the head.
emotion: shock
estimated_seconds: 5

## Beat 8 — Scramble
description: The hyena revives and snatches the tin; an all-out chaotic scramble erupts across the clearing.
emotion: chaos
estimated_seconds: 12

## Beat 9 — Triumph
description: Kemi executes a flying dive to reclaim the tin, sprints to the ridge, and hoists it proudly toward camera.
emotion: triumph
estimated_seconds: 10
```

### Field notes

- **Header names are exact.** The parser matches `## Beat N — <emotion>`.
- **`description`** is a single line: concrete, visible, present-tense.
- **`emotion`** is one word or a short phrase naming the audience feeling.
  Suggested vocabulary: joy, unease, fear, tension, determination, excitement,
  shock, chaos, triumph, sadness, wonder, relief, anger, tenderness, suspense.
  Other emotions are accepted (warn-only) — creativity is encouraged.
- **`estimated_seconds`** is an integer. The sum across all beats should be
  roughly within 50% of `target_seconds` (the validator warns if outside this).
- **Beat numbers are sequential** starting at 1. No gaps, no duplicates.

## Validate

```
python3 scripts/validate.py <run_dir>/beat_board.md --schema beat_board --target-seconds <N>
```

Read `<run_dir>/beat_board.md.validation.json`; on `ok:false`, fix every listed
error and re-run. **Do not proceed to Agent 2 until the beat board passes.**
