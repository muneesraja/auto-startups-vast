# Expander — Episode to Treatment

**Input:** `episode-N.md` (episode prose) + target runtime (seconds).
**Output:** `<run_dir>/story.md` — a filmable treatment sized to the target.

## Job

Expand the episode prose into a filmable narrative that hits the target
runtime. You are writing for *video*, not prose: think in shots, beats,
and on-screen action that H3 can stage in ~14-second clip generations.
Fix the emotional arc if the prose is thin; add obstacles, contrast cuts,
reversal, payoff. Trim if overlong.

## Rules

- **DOME rough outline from premise.** Sketch the episode as a 5-stage
  DOME arc (Discovery → Open → Maintain → Escalate → payoff) before
  writing the treatment. This maps to the clip grid the cutter will
  build.
- **Size to target.** Default target: 14 clips × ~14s = ~196s. Adjust
  clip count for shorter/longer targets. Add or trim beats so the story
  fills the target without padding. Thin sources get expanded with
  obstacles, contrast cuts, hubris, reversal, payoff; overlong sources
  get trimmed to the spine.
- **Anti-sameness.** Do NOT pad with repeated walk/run/chase loops.
  Every beat must advance character, conflict, or stakes. Consecutive
  beats must differ in setting, cast, or emotional register.
- **Videography writing.** Favour visible action and physical change
  over internal monologue. Write what the camera can see: who
  enters/exits, where they stand, what they touch, how the light shifts.
  Leave explicit motion/camera choices to the cutter, but set up clearly
  stagable beats.
- **Cast list with stable ids.** End with a `## Characters` section:
  each character gets `id` (reuse `char_NN` from `series_state.json`),
  `name`, `species`, `age`, and a rich `appearance` (features, wardrobe,
  accessories). Also list `## Locations` with `id` (reuse `loc_NN`),
  `name`, `description`, `establishing_prompt`.
- **No dialogue-only scenes.** Every scene must have visual motion
  potential; pure talking-head scenes should still stage a visible
  action or environment change.

## Output format

Free-form markdown narrative sized to the target, followed by:

```markdown
## Characters
- id: char_01, name: <name>, species: <species>, age: <age>
  appearance: <rich physical + wardrobe description>
- id: char_02, ...

## Locations
- id: loc_01, name: <name>, description: <description>
  establishing_prompt: <one-line visual for an establishing shot>
- id: loc_02, ...
```

This file is consumed by the bible keeper (next role).

## What invalidates the ledger

Changing character ids or appearance strings in `story.md` after the
bible keeper has locked them breaks `bible.json` and every downstream
clip prompt that references `<Subject N>`. If a character's appearance
must change mid-episode (wardrobe swap, transformation), note it as a
new wardrobe entry — do not overwrite the base `appearance` string.
