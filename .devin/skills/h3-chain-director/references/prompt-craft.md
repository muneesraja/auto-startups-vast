# H3-Chain Director — Ref2VA Prompt Craft

How to write the per-clip Ref2VA 6-section prompts for the chained H3
workflow, and the `prompt_prefix` split that de-duplicates shared blocks.

**The 6-section spec itself lives in
[`ref2va-format.md`](../../minimax-h3-prompter/references/ref2va-format.md)
(`subject_definitions`, `summary`, `retention_analysis`,
`detailed_description`, `overall_soundscape`, `non_diegetic_music`). Load
that file. This document does NOT restate the section rules — it only
adds the chaining/prefix conventions on top.**

---

## The `prompt_prefix` split

A chained plan is N clips (each ≤15s) that form one seamless generation
chain. Three of the six sections are identical across every clip and
belong to the **whole chain**, not any single clip:

| Section | Lives in | Scope |
|---|---|---|
| `subject_definitions` | `prompt_prefix` | all clips |
| `retention_analysis` | `prompt_prefix` | all clips |
| `non_diegetic_music` | `prompt_prefix` | all clips |
| `summary` | clip `prompt` | per-clip |
| `detailed_description` | clip `prompt` | per-clip |
| `overall_soundscape` | clip `prompt` | per-clip |

The plan carries `prompt_prefix` once at the top level. Each clip's
`prompt` field contains ONLY the three per-clip sections. At submission
time the runner prepends `prompt_prefix` to the clip's `prompt` so the
model receives all six sections in spec order.

### Why the prefix matters

The shipped workflow duplicates the same `subject_definitions`,
`retention_analysis`, and `non_diegetic_music` blocks verbatim across
~14 shots. Two costs:

1. **Drift** — a hand-edit to one copy is not propagated, so clip 7's
   `<Subject 2>` line silently diverges from clip 1's.
2. **Token waste** — the duplicated blocks are re-sent on every clip,
   burning context on text the model already saw.

The prefix eliminates both: one source of truth, sent once, prepended
mechanically.

---

## Micro-shots inside one clip

Fast-paced cutting lives INSIDE a single seamless generation via the
`[Shot N] At MM:SS.mmm` cut convention from `ref2va-format.md` §4. A
single 10–15s clip routinely carries 4–7 micro-shots:

- `[Shot 1]` has NO timestamp (clip start).
- `[Shot 2] At 00:02.400, the camera cuts to …` — strictly increasing
  cut times within the clip's `duration_s`.
- Each cut must add NEW information (subject, space, state, viewpoint,
  time). A mere distance/angle change is camera motion, not a cut.
- Cut verbs: "the camera cuts to", "the shot cuts/transitions/changes/
  switches to". Cross-dissolve/fade/wipe ONLY if the brief asked.

This is how a music-video or short-form reel gets rapid viral rhythm
without leaving the Ref2VA single-generation envelope.

---

## The hinge rule (clip-to-clip continuity)

Clips are chained, not independent. The seam between clip k and clip k+1
is a **hinge**, authored on both sides:

- **Clip k, last shot** is a held or simple-motion beat — no new
  subject, no camera whip. It is the visual anchor clip k+1 continues
  from. Example: "…<Subject 1> holds the pose, breathing slowly, as the
  camera settles into a Static Shot."
- **Clip k+1, `[Shot 1]`** is a CONTINUATION, not a fresh open. It has
  NO cut verb before it (per spec, `[Shot 1]` never has a timestamp),
  and its first line states the carry-over: "Continuing seamlessly from
  the previous clip, <Subject 1> …". Do NOT write "the camera cuts to"
  at the clip k+1 opening — that would insert a hard cut at the seam
  and break the chain.

The hinge is what makes N clips read as one uninterrupted video.

---

## Reference label consistency

- Only labels declared in `prompt_prefix`/`subject_definitions` may
  appear in any clip's `summary`, `detailed_description`, or
  `overall_soundscape`. No clip invents a new `<Subject N>`,
  `<Picture N>`, `<Video N>`, or `<Audio N>`.
- No label index may exceed the count of wired reference assets. If the
  upload order defines `<Picture 1>`…`<Picture 3>`, a clip must never
  cite `<Picture 4>`.
- A label keeps ONE fixed meaning across all clips (defined once in the
  prefix, reused everywhere).

---

## Anti-bleed text

When a clip has ≥2 cast members on screen, each character's description
carries explicit anti-bleed text for the OTHERS — a clause that pins
their distinct features so the model does not merge them. Place it in
`detailed_description` at each character's first appearance in the clip:

> "<Subject 1> (the woman in the red leather jacket, dark bob, silver
> nose stud — distinct from <Subject 2>'s blonde ponytail and cream
> knit sweater) steps forward…"

Reaffirm the distinction at any shot where both share the frame.

---

## Worked example — 2-character music video

### `prompt_prefix` (written once, applies to all clips)

```
subject_definitions:
<Subject 1> is the woman in the red leather jacket, dark bob haircut, silver nose stud, whose appearance comes from <Picture 1>.
<Subject 2> is the man in the cream knit sweater and blonde ponytail, whose appearance comes from <Picture 2>.
<Picture 1> is the first-frame composition anchor for <Subject 1>.
<Picture 2> is the first-frame composition anchor for <Subject 2>.
<Audio 1> is the background-music style reference (synth-pop, 124 BPM).

retention_analysis:
<Subject 1> (appears in all clips): fully_preserved - red leather jacket, dark bob, silver nose stud.
<Subject 2> (appears in all clips): fully_preserved - cream knit sweater, blonde ponytail.
<Picture 1>: fully_preserved - opening frame composition for <Subject 1>.
<Picture 2>: fully_preserved - opening frame composition for <Subject 2>.
<Audio 1>: reference - target follows the synth-pop 124 BPM groove without copying the signal.

non_diegetic_music:
The track follows <Audio 1>'s synth-pop 124 BPM pulse throughout; the cuts land on the beat.
```

### Clip 1 `prompt` (6 micro-shots, fresh open)

```
summary:
[reference generation] A two-character music-video opener: <Subject 1> and <Subject 2> move through a neon-lit arcade, intercut on the beat.

detailed_description:
The target video uses a neon-soaked cinematic style with deep blacks and saturated magenta rim light.
[Shot 1] <Subject 1> (red leather jacket, dark bob, silver nose stud — distinct from <Subject 2>'s blonde ponytail and cream sweater) stands at a cabinet, back to camera; a slow Push In at slow speed. <Audio 1>'s pulse begins.
[Shot 2] At 00:02.000, the camera cuts to <Subject 2> (blonde ponytail, cream knit sweater — distinct from <Subject 1>'s dark bob and red jacket) at the change machine, feeding coins; Static Shot.
[Shot 3] At 00:04.200, the shot cuts to a Tracking Shot following <Subject 1> down the aisle, neon reflections sliding across her jacket.
[Shot 4] At 00:06.500, the camera cuts to <Subject 2> glancing over his shoulder toward <Subject 1>; a quick Pan Right.
[Shot 5] At 00:09.000, the shot cuts to both at the same cabinet, hands nearly touching the joystick; Push In with small amplitude.
[Shot 6] At 00:11.800, <Subject 1> turns to face <Subject 2>, holding the pose, breathing slowly, as the camera settles into a Static Shot — the hinge beat for the next clip.

overall_soundscape:
Arcade ambience — cabinet bleeps, coin clinks, distant crowd — under <Audio 1>'s synth-pop pulse; each cut lands on a beat.
```

### Clip 2 `prompt` (hinge-in continuation + 6 micro-shots)

```
summary:
[reference generation] [video continuation] The arcade scene continues: <Subject 1> and <Subject 2> play, then exit into a rain-slick street.

detailed_description:
Continuing seamlessly from the previous clip, <Subject 1> holds her turned pose facing <Subject 2> (blonde ponytail, cream sweater — distinct from <Subject 1>'s dark bob and red jacket) under the neon.
[Shot 1] <Subject 1> and <Subject 2> grip the joystick together; a slow Push In. Cabinet glow plays across both faces.
[Shot 2] At 00:02.300, the camera cuts to the screen reflected in <Subject 1>'s eyes; extreme close-up, Static Shot.
[Shot 3] At 00:04.800, the shot cuts to a wide of the aisle as <Subject 2> laughs, head back; Truck Left at slow speed.
[Shot 4] At 00:07.200, the camera cuts to the arcade exit door swinging open, street light flooding in; Pan Right.
[Shot 5] At 00:09.500, the shot cuts to <Subject 1> stepping out into rain-slick street, neon sign reading "OPEN" above; Tracking Shot.
[Shot 6] At 00:12.000, <Subject 2> follows, both paused under the awning, holding still as the camera settles — the hinge beat for the next clip.

overall_soundscape:
Arcade ambience fades as the door opens; rain hiss and distant traffic enter, <Audio 1>'s pulse carries underneath.
```

Note clip 2's `[Shot 1]` opens with "Continuing seamlessly from the
previous clip" and NO cut verb — the hinge. Clip 1's last shot and
clip 2's last shot are both held beats that hand off to the next clip.
