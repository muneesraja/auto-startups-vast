# Minimax H3 prompt bible (story-maker-v4c)

MiniMax H3 / Hailuo 3.0 only. Omni-modal R2V: **one** storyboard sheet as
`@image1` at 0.00s, a timeline prompt, native stereo audio. Max **15 seconds**
per generation.

This is an **image-to-video** prompt: the sheet already holds subject,
composition, and style. Write motion, camera, what changes, what must stay
unchanged, sound layers, and a **viewer takeaway**. Do not re-describe the
still.

Must Read: [`prompts/creature_behavior.md`](../prompts/creature_behavior.md),
[`prompts/coverage.md`](../prompts/coverage.md). Ads also Read
[`prompts/commercial_ad.md`](../prompts/commercial_ad.md).

## Pre-write pass

Do not emit the prompt until all of these exist:

1. Context — sheet lock + opening composition.
2. Timeline — actions in order, including ending state.
3. Camera — **one** sentence per shot (type, direction, amplitude, speed).
4. Sound — dialogue vs physical vs ambience vs music, unmixed.
5. Constraints — identity, wardrobe, product, lighting, creature role/state.
6. S.C.E.N.E. + purpose — Subject, Context, Event, Nuance, Exclusions, and
   what the viewer should understand.

On GATE 2 failure, change **one** category (see repair table).

## Mode

I2VA / R2V. Python attaches the storyboard sheet only. Open with frame
alignment, blank line, then the three audiovisual fields. Do not invent extra
reference pictures.

One-take generations: omit `Hard cinematic cut.` and add “Strict one-take.
No cuts. No scene changes. No teleportation.”

## Three fields (do not mix)

| Field | Put here | Keep out |
| --- | --- | --- |
| `integrated_multimodal_description` | Style, composition, actions, shots, speakers, dialogue, visible text, diegetic sound | Background-music paragraph |
| `overall_soundscape` | Ambience, footsteps, impacts, fabric, wind, rain, breathing | Full dialogue / lyrics |
| `non_diegetic_music` | Score the audience hears: instruments, tempo, dynamics; or `N/A` | Radio/phone music inside the scene (that is diegetic) |

## Per-shot order

Visual hook (style + subject + place) → one primary action → environment
reaction → one camera sentence → ending state on the last shot. One visible
event per line.

`[Shot 1]` has no inner timestamp. Later shots: `[Shot N] At 00:MM.SSS` with
**increasing** generation-local times that match `SHOT N — a–b s` headers.

A cut must add information. One camera move: e.g. “The camera pushes in with
small amplitude at slow speed.” Coverage match: tracking for travel, push-in
for emotion, orbit for product/reveal, static/slow push for danger.

## Dialogue

Stable speaker IDs `(S1)` `(S2)` by **appearance**, never `char_NN`. Exact
speech only inside `<d>[English] ... </d>` (name the language first if not
English). Delivery sits outside the block. After a short line, add silent
action so the model does not invent speech.

Visible text: exact short English in `"double quotes"` only if the user
supplied it. Default: no generated supers.

## Validator-legal skeleton

The validator requires the words `storyboard`, `Timeline`, `SHOT N — a–b s`,
`Negative Prompt`, and rejects `char_NN`. Extra Hailuo fields are allowed.

```
For the target video, at 0.00 seconds into the target video, @image1
(the provided storyboard sheet) is fully referenced.

Use the provided storyboard as the exact visual guide for composition,
framing, character appearance, environment, and sequence progression.
The sequence should communicate <viewer takeaway>.

Maintain the exact appearance of <people>, <creatures>, <product>, location,
lighting, textures, and proportions throughout.
Keep product shape, color, label, and position unchanged.
<creature behavior locks from creature_behavior.md>
<human lock in danger: tense faces, adults as shield, quiet voices>

Generate a <duration>-second sequence with editorial cuts only where specified.

<Tone style lines, one quality per line — grounded cinematic or stylized, not
always Pixar>

Timeline

integrated_multimodal_description:

SHOT 1 — 0.0–Xs (Continuous Shot)
[Shot 1]
Continue directly from the previous scene.
<hook + action + environment reaction>
The camera <type> with <amplitude> at <speed>.
The woman (S1) says: <d>[English] ...</d>

Hard cinematic cut.

SHOT N — a–b s
[Shot N] At 00:MM.SSS
...

Final frame:
<pose, object condition, composition, lighting, camera position>

overall_soundscape:
<ambient + physical + non-verbal>

non_diegetic_music:
<instrumentation + tempo + dynamics> or N/A

Negative Prompt
No identity changes.
No character redesign.
No extra characters.
No duplicate characters.
No anatomy errors.
No object deformation.
No clipping.
No flickering.
No morphing.
No inconsistent lighting.
No texture popping.
No low-resolution textures.
No text unless the quoted line was supplied.
No subtitles.
No watermark.
No pet-like wildlife.
No calm faces in danger.
No dutch canopy montage.
No idle prop orbits.
No stacked cameras.
No extra fingers.
No invented speech.
No unreadable labels.
No fake logos.
No extra or duplicate products.
No sudden camera jumps.
No fake testimonials, ratings, or analytics.
```

Timecodes are **generation-local** (start at 0.0). SHOT count and ranges must
match the storyboard generation.

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

**One move per shot.** Example: “The camera pushes in with small amplitude at
slow speed.” Do not chain track + arc + whip pan unless Tone is `play_comedy`.

## Cuts vs continuous

- `(Continuous Shot)` in the SHOT header; “Camera remains completely
  continuous throughout the shot” when it matters.
- End a shot with the literal line `Hard cinematic cut.` before the next SHOT.
- One-take: no cuts, no scene changes, no teleportation.

## Patterns (replace the old cute-dino default)

**Grounded protect / danger.** Predator or territorial animal in
`alert_assess` / `stalk` at `flight_zone` or closer. Adults between child and
animal. Static or slow push, then MCU reaction: tense faces, no smiles, quiet
voices. Next shot is human reaction, not a zoo portrait.

**Product hero hold.** Product is the sole visual owner. Slow Push In with
small amplitude. Light moves across real materials. Label locked. Final frame
is a still, readable pack. `non_diegetic_music` restrained or `N/A`.

**One-take scale.** One location, one camera sentence (slow Pull Out or
Tracking Shot). Environment reacts (wind, water, crowd). Creature states may
conflict in the same frame. End on a deliberate wide.

`stylized_character` (talking mascot, camera-smile) only when Tone is
`stylized`.

## Repair table

| Bad output | Fix |
| --- | --- |
| Still / weak motion | Add trigger, midpoint, ending (Event). |
| Camera fights the subject | One slow stable sentence; no extra rotation. |
| Unwanted speech | `(S1)` + exact `<d>` + silent action after. |
| Composition jump | Restate sheet anchors, then the next action. |
| Label / logo changed | Keep label, logo, color, pack unchanged. |
| Generic / no purpose | Add viewer takeaway. |
| Distorted hands | Brief natural hands; avoid finger CU. |
| Unreadable text | No generated text; overlay space unless user quoted a line. |
| Product duplicated | Show only one product. |
| Style drift mid-clip | Lock lighting, palette, camera style, product position. |
| Ad feels too slow | Main action in the first 3s of that generation. |
| Looks fake | Natural light, realistic motion, restrained camera. |
| Pet-like wildlife | Restore role/state/distance; human danger lock. |

## What makes prompts fail

- Timecodes past 15s, or SHOT ranges that disagree with the storyboard.
- Internal ids (`char_01`).
- First-frame-only description with no Event.
- “Cinematic” as the camera.
- Mixed sound layers (score inside action lines).
- Missing `Negative Prompt`.
- Missing takeaway or exclusions.
