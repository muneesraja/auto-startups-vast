# Prompt Writer — Ref2VA Per-Clip Prompts

**Input:** `ledger.clips[]` + `bible.json` + `prompt_prefix` (shared
block from the plan).
**Output:** `prompts_out/clip_k.txt` — one Ref2VA 6-section prompt per
clip.

## Job

Write the per-clip Ref2VA prompts that H3-Base-Ref2VA consumes directly.
Each clip gets three per-clip sections (`summary`,
`detailed_description`, `overall_soundscape`); the `prompt_prefix`
supplies the other three (`subject_definitions`, `retention_analysis`,
`non_diegetic_music`) and is prepended at submission time.

## Rules

- **Load the spec.** Read
  [`../../minimax-h3-prompter/references/ref2va-format.md`](../../minimax-h3-prompter/references/ref2va-format.md)
  for the full 6-section specification. Do not restate it here — follow
  it exactly. Also read
  [`references/prompt-craft.md`](../references/prompt-craft.md) for the
  chaining conventions on top of the spec.
- **`prompt_prefix` contains shared blocks.** The prefix carries
  `subject_definitions` + `retention_analysis` + `non_diegetic_music`
  for the whole chain. Do NOT duplicate these in any clip's prompt. Each
  clip file contains ONLY `summary`, `detailed_description`, and
  `overall_soundscape`.
- **Per-clip sections.** Each clip has:
  - `summary:` — one short paragraph with the task-type prefix (e.g.
    `[reference generation]`).
  - `detailed_description:` — 350–500 words; the main body with
    `[Shot N]` cuts inside.
  - `overall_soundscape:` — 1–4 sentences; ambience and physical sounds
    across the full clip. Do not repeat dialogue or shot-synced events.
- **`[Shot N] At MM:SS.mmm` cuts.** Inside `detailed_description`:
  `[Shot 1]` has NO timestamp. Later shots: `[Shot N] At MM:SS.mmm, the
  camera cuts to …` with strictly increasing cut times within the clip's
  `duration_s`. Pull shot timings from `ledger.clips[k].shots[]`.
- **Hinge rule in prompt text.** For clip k>1, `[Shot 1]` is a
  CONTINUATION, not a fresh open. It has NO cut verb. Open with:
  "Continuing seamlessly from the previous clip, <Subject N> …". Do NOT
  write "the camera cuts to" at the clip opening — that inserts a hard
  cut at the seam and breaks the chain. See
  [`references/prompt-craft.md`](../references/prompt-craft.md) §The
  hinge rule.
- **Only declared labels.** Only `<Subject N>` / `<Picture N>` /
  `<Video N>` / `<Audio N>` labels declared in `prompt_prefix`'s
  `subject_definitions` may appear. No clip invents new labels. Label
  indices must not exceed the count of wired reference assets.
- **Anti-bleed text for ≥2 cast clips.** When a clip has ≥2 cast members
  on screen, each character's first appearance in `detailed_description`
  carries the anti-bleed clause from `bible.json`'s `anti_bleed` field.
  Reaffirm at any shot where both share the frame.
- **Dialogue from audio mapping.** Spoken lines come from
  `ledger.clips[k].audio.lines[]` — use the exact `text` verbatim inside
  `<d>[lang] ...</d>`. Assign speaker IDs (S1, S2…) in order of first
  vocal event and reuse throughout.
- **Camera motion vocabulary.** Use the Ref2VA spec's motion types (Zoom
  In/Out, Push In/Pull Out, Pan, Truck, Tilt, Tracking, Static, etc.)
  with amplitude and speed qualifiers. Write as natural English, not
  stacked labels.

## Output format

One text prompt per clip at `prompts_out/clip_k.txt`, containing ONLY
the three per-clip sections in spec order:

```
summary:
<prefix> <one paragraph>

detailed_description:
<style sentence>
[Shot 1] ...
[Shot 2] At MM:SS.mmm, ...
...

overall_soundscape:
<1-4 sentences>
```

Also write `prompt_file` path and compute `prompt_hash` back into the
ledger for each clip.

## What invalidates the ledger

Editing a clip's `prompt` after it is rendered invalidates that clip and
all later clips (the prefix checkpoint grows from that point — see
[`references/checkpoint-contract.md`](../references/checkpoint-contract.md)).
Editing `prompt_prefix` (shared blocks) invalidates EVERY clip, since all
clips receive the prefix at submission. A label index that exceeds the
wired reference count causes the model to hallucinate a missing reference
— the render will drift or fail silently.
