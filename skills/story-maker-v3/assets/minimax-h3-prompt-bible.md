# Minimax H3 prompt bible (story-maker-v3)

Distilled from `Research/minimax-h3/` and the official H3-Base-Ref2VA
specification at `.devin/skills/minimax-h3-prompter/references/ref2va-format.md`.
Minimax H3 is an omni-modal R2V model: it takes reference images (we attach ONE
storyboard sheet), follows a structured 6-section prompt with high adherence,
and generates video with **native stereo audio** (voice, SFX, music).
Hard limit: **15 seconds per generation**.

## The 6-section Ref2VA contract

Output ONLY these six sections, in this exact order, with lowercase field names
followed by a colon. No preamble, no markdown fences, no commentary.

```
subject_definitions:
<Subject N> is the <what> in <Picture M>, with <concrete features to preserve>.
<Picture N> is <a concrete frame/composition anchor — the storyboard sheet>.

summary:
[reference generation] <one-sentence story of this generation>.

retention_analysis:
<Subject 1> (appears in [Shot 1], [Shot N]): fully_preserved - <what is retained>.
<Picture 1> (storyboard reference): fully_preserved - composition and panel sequence.

detailed_description:
<1-2 sentence style statement BEFORE [Shot 1].>
[Shot 1] <action, camera, audio. NO timestamp on Shot 1.>
[Shot 2] At MM:SS.mmm, the shot cuts to <new information>. <action, camera, audio.>
<Identity/count locks as inline prose: "Never generate duplicate characters.">

overall_soundscape:
<1-4 sentences: diegetic ambience + physical action sounds + non-verbal human sounds.>

non_diegetic_music:
<1-3 sentences: score the characters CANNOT hear — instrumentation, tempo, rhythm, dynamics. N/A if no score.>
```

### Which strings are literal control tokens (do not vary these)

| token | purpose |
|---|---|
| `subject_definitions:` `summary:` `retention_analysis:` `detailed_description:` `overall_soundscape:` `non_diegetic_music:` | section headers — exact, lowercase, colon |
| `[Shot N]` | shot header — exact bracket syntax |
| `At MM:SS.mmm` | timestamp prefix for shots 2+ — exact format |
| `<Subject N>` `<Picture N>` `<Video N>` `<Audio N>` | reference labels — exact angle-bracket syntax |
| `<d>[Language] ...</d>` | dialogue tag — exact syntax |
| `(S1)` `(S2)` | speaker IDs — exact parenthetical syntax |
| `<scenetrans>` `<cutoff>` | dialogue continuity markers — exact |

### Which strings are canonical transition phrases (pick one, do not invent synonyms)

| transition | canonical phrase | when |
|---|---|---|
| `hard_cut` | `Hard cinematic cut.` | new subject, space, state, viewpoint, or time |
| `cut_on_action` | `Cut on the action.` | mid-motion cut; movement carries across |
| `reaction_cut` | `Cut to the reaction.` | action → face/reaction beat |
| `match_cut` | `Match cut on <element>.` | graphic/positional match (name the element) |
| `whip_pan` | `Whip pan transition.` | camera-motivated; pairs with bridges |
| `audio_led` | `Audio leads the cut.` | next shot's sound starts before the visual (L/J cut) |
| `continuous` | *(no phrase)* + "Camera remains completely continuous throughout the shot." | same take continues |
| `camera_move` | *(not a cut — describe a camera move)* | only framing/angle changes |

**The new-information rule (from the Ref2VA spec):** A cut must add NEW
information (subject, space, state, viewpoint, time). If only distance or
angle changes, use camera motion instead. The validator warns on same-character
`hard_cut` and on 3+ consecutive identical transitions.

## Camera motion vocabulary

| Dimension | Expression | Description |
|---|---|---|
| Motion type | Zoom In / Zoom Out | Focal length changes; camera body stays. |
| Motion type | Push In / Pull Out | Camera moves forward or backward. |
| Motion type | Pan Left / Pan Right | Camera stays; lens pivots horizontally. |
| Motion type | Truck Left / Truck Right | Camera translates horizontally. |
| Motion type | Tilt Up / Tilt Down | Camera stays; lens pivots vertically. |
| Motion type | Pedestal Up / Pedestal Down | Entire camera moves up or down. |
| Motion type | Arc Shot | Camera moves in an arc around the subject. |
| Motion type | Tracking Shot | Camera follows a moving subject. |
| Motion type | Static Shot | Camera position and lens remain still. |
| Motion type | Shake Slightly / Shake Strongly | Slight or strong camera shake. |
| Motion type | POV | The subject's point of view. |
| Motion type | Roll Clockwise / Roll Counterclockwise | Camera rolls around the lens axis. |
| Amplitude | with small amplitude | Small-range change. |
| Amplitude | with large amplitude | Large-range change. |
| Speed | at slow speed | Slow movement. |
| Speed | at fast speed | Fast movement. |

Compose them naturally: "slow cinematic Push In at slow speed", "Tracking
Shot with large amplitude", "gentle whip pan following the stick". Chained
moves within one shot are well-followed when described in time order. The
dragon exemplar (`Research/minimax-h3/dragon/story-board-2.md`) shows three
motivated camera moves inside a single 7.2s shot — this is the model for
`sustained` pacing.

## Dialogue format

Stable speaker IDs `(S1)`, `(S2)` assigned in order of first vocal event and
reused at every later event. Delivery and identity anchors go OUTSIDE the `<d>`
tag; exact spoken words go INSIDE with a language tag:

```
<Subject 2> (S1) turns and says, <d>[English] Stay close, Timi!</d>
```

- Preserve the user's words verbatim — never translate or rewrite.
- Dialogue crossing a cut: use `<scenetrans>` at the connecting points in both
  shots plus "continues seamlessly across the cut".
- Speech truncated by the video end: `<cutoff>`.
- Off-screen speech: mark "off-screen" and state the on-screen lips stay closed.

## Audio (two separate sections)

### overall_soundscape (diegetic)
Ambience, physical action sounds, non-verbal human sounds across the FULL
generation. Do not repeat dialogue, singing, or shot-synced sound events here.
Use `N/A` only if the user explicitly requests complete silence.

**Sound design layers** (see `assets/directors-guide.md` Section 7):
- **Foley**: footsteps, fabric, props — the texture of physical existence
- **Ambient**: room tone, wind, distant traffic — the space around the action
- **Impact**: punches, door slams, cracks — the punctuation of action
- **Silence**: the pause before a reveal, the breath after impact — silence
  is a sound choice, not the absence of one

### non_diegetic_music (score)
Score the CHARACTERS CANNOT hear: instrumentation, tempo, rhythm, dynamic
changes only — no abstract mood words, no emotional-function explanations.
Music audible to characters (radio, singing, phone) is diegetic → belongs in
`detailed_description`. `N/A` when no score.

**Music synchronization**: the pattern is
**anticipation → movement → impact → sound → reaction → silence/music hit**.
The music hit lands ON the impact or the reaction, not randomly. Time it to
the shot's emotional peak.

## Animation beats in `detailed_description`

Write each `[Shot N]` action as a sequence of micro-beats in time order, not
a single verb. Animation is not "the character turns around" — it is
**hear sound → freeze → eyes move → head turns → body follows → reaction.**

See `assets/directors-guide.md` Section 6 for the full animation principles
reference (anticipation, follow-through, squash & stretch, timing, spacing,
exaggeration, weight, secondary motion).

## Identity/count locks (replaces Negative Prompt)

Neither official Ref2VA spec has a `negative_prompt` field. Identity and count
locks go as **inline prose** inside `detailed_description`, e.g.:

> "Never generate mirrored hands, duplicated arms, extra palms, or a second
> spatula."

This is spec-faithful and preserves the control that prevents identity drift
and duplicate characters.

## What makes prompts fail

- Missing or misordered sections (the validator enforces all six, in order).
- `[Shot 1]` with a timestamp, or later shots without `At MM:SS.mmm`.
- Non-increasing timestamps, or timestamps that disagree with the storyboard.
- Shot count mismatching the storyboard generation.
- Internal ids (`char_01`) — describe characters by appearance instead.
- Vague action ("they fight") instead of visible beats.
- Camera direction scattered mid-action — keep camera lines grouped and
  explicit per shot.
- `char_NN` tokens anywhere in the prompt.
