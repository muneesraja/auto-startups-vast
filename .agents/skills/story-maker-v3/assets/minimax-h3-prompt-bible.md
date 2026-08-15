# Minimax H3 prompt bible (story-maker-v3)

Distilled from `Research/minimax-h3/` (single-shot, multi-shot, and
storyboard-reference examples). Minimax H3 is an omni-modal R2V model: it
takes reference images (we attach ONE storyboard sheet), follows a timeline
prompt with high adherence, and generates video with **native stereo audio**
(voice, SFX, music). Hard limit: **15 seconds per generation**.

## Prompt skeleton (storyboard-reference, the v3 default)

```
Reference

Use the provided storyboard as the exact visual guide for composition,
framing, character appearance, environment, and sequence progression.

Maintain the exact appearance of <each character>, <the location>, lighting,
textures, proportions, props, and environment throughout the entire sequence.

<Character behavior locks — e.g. "The baby dinosaur remains adorable,
playful, and completely harmless. It never behaves aggressively.">

Generate a cinematic <duration>-second sequence with smooth motion and
natural editorial cuts only where specified.

<Visual style block — short lines, one quality per line:>
Pixar-quality cinematic 3D animation.
Feature-film quality.
Highly expressive facial animation.
Natural body mechanics.
Physically accurate lighting.
Smooth temporal consistency.

Timeline

SHOT 1 — 0.0–7.2s (Continuous Shot)

<If flowing from the previous generation/scene: "Continue directly from the
previous scene.">

<Action lines — one visible event per line, present tense, in order.
Expressions, physical beats, props. Short lines.>

<Camera lines — explicit and last within the shot:>
Begin with a handheld tracking shot following behind the baby.
As the baby reaches the dead end, smoothly arc around to a front
three-quarter angle.

Hard cinematic cut.

SHOT 2 — 7.2–15.0s (Continuous Shot)

<Action lines...>

<Dialogue inline where it happens:>
The dinosaur gently smiles and softly says,
"Mama."

<Camera lines...>

Final frame:
<One or two lines describing the exact closing image.>

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
No text.
No subtitles.
No watermark.
No logos.
```

Timecodes in the prompt are **generation-local** (start at 0.0). `SHOT N —
a–b s` lines and the shot count must match the storyboard generation exactly
(the `video_prompt` validator enforces this).

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
moves within one shot are well-followed when described in time order.

## Cuts vs continuous shots

- Mark a continuous take as `(Continuous Shot)` in the SHOT header and state
  "Camera remains completely continuous throughout the shot" when it matters.
- End a shot with the literal line `Hard cinematic cut.` to force an
  editorial cut before the next SHOT.
- For a strict one-take generation add: "Strict one-take cinematic shot. No
  cuts. No scene changes. No teleportation."

## Audio (native — always direct it)

- Put spoken lines in quotes on their own line, introduced by who says them
  and how ("softly says,"). The model voices and lip-syncs them.
- Describe the soundscape explicitly: footsteps, ambience, impacts, music
  mood and where it swells or softens. Without direction the model invents
  audio.

## What makes prompts fail

- Timecodes past 15s, or SHOT ranges that disagree with the storyboard.
- Internal ids (`char_01`) — describe characters by appearance instead.
- Vague action ("they fight") instead of visible beats.
- Camera direction scattered mid-action — keep camera lines grouped and
  explicit per shot.
- Missing Negative Prompt — always include the identity/deformation/text
  block, plus scene-specific bans (e.g. "No dinosaur growth. No horror.").
