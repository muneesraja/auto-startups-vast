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

- **8–15 beats** (advisory target) for short-form (30s–5min). Fewer for very
  short ads. The validator **enforces only the 3-beat minimum**; the 8–15
  range and "more for longer episodes" are guidance, not errors — a
  deliberate 16-beat board warns but passes.
- **Each beat is a change.** If a beat doesn't change the character's situation,
  emotion, or the audience's understanding, it's not a beat — cut it.
- **Visible action.** Write what the camera can see, not inner thoughts.
  "Ollie freezes, eyes wide" not "Ollie feels afraid."
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

Canonical worked example:
[`assets/example-ollie.md`](../assets/example-ollie.md) — all prompts use
this same story (Ollie, the pond, the basket) so examples stay consistent
across agents.

```
# Beat Board — Ollie's Dive

target_seconds: 224
beat_count: 9

## Beat 1 — Pride
description: Ollie admires his handmade basket on the mossy boulder, beaming.
emotion: joy
estimated_seconds: 15

## Beat 2 — Spill
description: A dragonfly startles Ollie; the basket tumbles into the pond.
emotion: shock
estimated_seconds: 15

## Beat 3 — Discovery
description: Peering through the hollow cylinder, Ollie glimpses the glowing underwater world — an idea ignites.
emotion: wonder
estimated_seconds: 15

## Beat 4 — Trial and Error
description: Three helmet prototypes fail — no seal, no air, a flooding snorkel.
emotion: tension
estimated_seconds: 45

## Beat 5 — Breakthrough
description: The bark-disc float keeps the snorkel upright; the rig finally works.
emotion: triumph
estimated_seconds: 20

## Beat 6 — Wonder
description: Ollie explores a bioluminescent paradise, dances with leaf-fish, and wakes a lakebed of blooming flower-snails.
emotion: awe
estimated_seconds: 75

## Beat 7 — Peril
description: A giant iridescent fish approaches; its friendly smile unhinges into a cavernous jaw.
emotion: fear
estimated_seconds: 25

## Beat 8 — Rescue
description: Caloo plunges in, snatches Ollie by the scruff, and outruns the lunging predator.
emotion: tension
estimated_seconds: 10

## Beat 9 — Button
description: Soaked under his father's glare, Ollie offers the wet helmet and a cheesy grin: "Hey, Dad... Thirsty?"
emotion: relief
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
