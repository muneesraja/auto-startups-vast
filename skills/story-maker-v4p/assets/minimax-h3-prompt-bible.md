# Minimax H3 prompt bible (story-maker-v4p)

Production contract for Agent 5. Distilled from the official MiniMax H3
guides vendored in `assets/official/`. Read this first. Open the official
files only when writing a hard prompt:

- [`official/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md`](official/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md) — six-section Ref2VA
- [`official/VIDEO_PROMPT_WRITING_GUIDE_base_en.md`](official/VIDEO_PROMPT_WRITING_GUIDE_base_en.md) — shared shot / camera / dialogue / sound body language

**This pipeline is H3-Base-Ref2VA.** Attach one storyboard sheet as
`<Picture 1>` and, when `render_all.py` will pass a tail clip, declare
`<Video 1>`. Do **not** switch to T2VA's three-field
`integrated_multimodal_description` format. Do **not** emit the I2VA
first-frame instruction (`For the target video, at 0.00 seconds...`) unless
the attached image is truly a pinned start frame. Our storyboard sheet is a
shot-planning picture, not a first frame.

Hard limit: **15 seconds per generation**. Ref2VA input caps (official README):
images ≤ 9, videos ≤ 3, mixed files ≤ 12.

**Resolution:** local ComfyUI runs H3-Base (~768 short edge;
`MINIMAX_MEGAPIXELS`). H3-Regenerate-2K is not open-sourced — do not add 2K
API/workflow code.

## The 6-section Ref2VA contract

Output ONLY these six sections, in this exact order, with lowercase field names
followed by a colon. No preamble, no markdown fences, no commentary.

```
subject_definitions:
<Subject N> is the <what> in <Picture 1>, with <concrete features to preserve>.
<Picture 1> is a storyboard reference for [Shot 1] and [Shot N], defining viewpoint, subject placement, and shot order.
<Video 1> is the continuation source: the last 3 seconds of the previous generation.

summary:
[reference generation] The target video shows <one-sentence story>.
# when a tail is attached:
[reference generation + video continuation] The target video continues from <Video 1> and shows ...

retention_analysis:
<Subject 1> (appears in [Shot 1], [Shot N]): fully_preserved - <what is retained>.
<Picture 1> (storyboard reference): fully_preserved - composition and panel sequence.
<Video 1> (opening continuation): partially_preserved - motion and ending state carry into [Shot 1]; not a frame pin.

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

The picture is the **file**. The subject is the **reusable content** inside it.
If an image only defines a character, cite it inside the `<Subject>` line; do
not also create a standalone `<Picture>` unless the image is a frame anchor or
storyboard.

**One clear role per attached asset.** Name what each reference controls
(identity, wardrobe, location, storyboard order, continuation, voice).

### Task-type prefixes (summary)

| Task type | When |
|---|---|
| `reference generation` | Image/video/audio guides identity, scene, style, action, camera, or storyboard without being a concrete frame or the source being edited |
| `video continuation` | New content continues from an existing source video (our 3s tail) |
| `keyframe completion` | An image is the actual first/last/key frame (not our default) |
| `video editing` | An existing source video is directly modified |
| `audio reuse` / `audio reference` | Audio is copied vs timbre/style referenced |

Combine with ` + `. Do not invent types. First generation of the run:
`[reference generation]`. Every later generation that receives a tail:
`[reference generation + video continuation]`.

### Tail video (`<Video 1>`)

`render_all.py` attaches the previous generation's last 3 seconds as
`ref_video`. Official Ref2VA requires that asset to be labeled.

- **g1 of the first scene:** no `<Video>` line.
- **g2+ of a scene, and g1 of a later scene:** define `<Video 1>` in
  `subject_definitions`, include it in `retention_analysis`, and cite it in
  Shot 1 as the opening continuation (not a storyboard frame pin).

Use `partially_preserved` or `weak_reference` for the tail — continuity of
motion/state, not 1:1 copy of the clip.

### 360° Background Source Video Recipe (Contradiction-Free Walls)

The tricky part with AI-generated animations is that the background changes every time the cut switches.
Character consistency has been largely controlled with reference images, but backgrounds often get redrawn
from scratch each time, which is a frequent hassle.

As a workaround, first shooting the desired background in a consistent form with H3, then extracting just the
needed walls later, completely eliminates background drift:

1. **Wide-angle opening frame:** Start with a slightly wide-angle still image as the opening plate of the room/environment (`assets/locations/<lid>.webp`).
2. **360° pan video:** Render a single video panning 360° around the room from a fixed pivot point with MiniMax H3:
   ```
   [reference generation] The target video shows a full 360-degree panoramic sweep of the empty environment.
   detailed_description:
   Cinematic stylized animation.
   [Shot 1] From a fixed central camera pivot point, the camera pans 360 degrees horizontally to the right with small amplitude at slow constant speed, smoothly sweeping across all four walls, corners, windows, and architectural features of the room, returning seamlessly to the opening frame. Completely empty space with no characters, no people, and held static lighting throughout.
   ```
   This video becomes the **sole definitive reference for the room**.
3. **Wall frame extraction:** For each cut in the scene, extract a single frame of the wall the camera is facing via `tools/background_extractor.py` and attach it as a reference plate (`<Picture 2>`).
4. **Principle:** *It doesn't have to be an orbit video specifically; as long as you create a "source for backgrounds that can be extracted later without contradictions," that seems to do the trick.*


## Shots, cuts, camera (from base_en)

`detailed_description` follows the official T2VA body language even though the
field name is `detailed_description` (Ref2VA), not `integrated_multimodal_description`.

- Write English. Preserve original language only inside `<d>` and for visible
  on-screen text.
- Style: 1–2 sentences **before** `[Shot 1]` (Ref2VA difference). Common style
  words: `Cinematic`, `live-action`, `2D-animated`, `3D CG`, `claymation`,
  `watercolor`, `vintage film`. Derive style from the storyboard sheet.
- Target **350–500 English words** in `detailed_description`. Dialogue-dense
  clips may run long to fit spoken lines. One shot is not an excuse to be short.
- `[Shot 1]` has **no timestamp**. Later shots: `[Shot N] At MM:SS.mmm` with
  strictly increasing generation-local times.
- **One main camera idea per shot.** Action in playback order.
- Ordinary cuts: `the camera cuts to` / `the shot cuts to` (also
  `the shot transitions to` / `the shot changes to` / `the shot switches to`).
- A cut must add **new information** (subject, space, state, viewpoint, time).
  If only distance or a slight angle changes, describe camera motion instead.

### Canonical transition phrases (pick one; do not invent synonyms)

| transition | canonical phrase | when |
|---|---|---|
| `hard_cut` | `Hard cinematic cut.` | new subject, space, state, viewpoint, or time |
| `cut_on_action` | `Cut on the action.` | mid-motion cut; movement carries across |
| `reaction_cut` | `Cut to the reaction.` | action → face/reaction beat |
| `match_cut` | `Match cut on <element>.` | graphic/positional match (name the element) |
| `whip_pan` | `Whip pan transition.` | camera-motivated |
| `audio_led` | `Audio leads the cut.` | next shot's sound starts before the visual |
| `continuous` | *(no phrase)* + "Camera remains completely continuous throughout the shot." | same take continues |
| `camera_move` | *(not a cut — describe a camera move)* | only framing/angle changes |

### Camera motion: type + amplitude + speed

Write as natural English inside the shot, not stacked labels at the end.

| Dimension | Expression |
|---|---|
| Motion type | Zoom In / Zoom Out, Push In / Pull Out, Pan Left / Pan Right, Truck Left / Truck Right, Tilt Up / Tilt Down, Pedestal Up / Pedestal Down, Arc Shot, Tracking Shot, Static Shot, Shake Slightly / Shake Strongly, POV, Roll Clockwise / Roll Counterclockwise |
| Amplitude | with small amplitude / with large amplitude (omit for medium) |
| Speed | at slow speed / at fast speed (omit for normal) |

```
The camera pushes in with small amplitude at slow speed toward the folded letter in her hands.
The camera pans right with large amplitude at fast speed, revealing the open doorway.
The camera holds a static shot as the runner exits the frame.
```

Chained moves within one shot are well-followed when described in time order.

## Dialogue and visible text (from base_en)

Stable speaker IDs `(S1)`, `(S2)` assigned in order of first vocal event.
Delivery and identity anchors go OUTSIDE `<d>`; exact spoken words go INSIDE
with a language tag. Preserve the user's words verbatim.

```
<Subject 2> (S1) turns and says, <d>[English] Stay close, Timi!</d>
The young woman with a quiet, breathy voice (S1) says: <d>[English] I get off at the next station.</d>
```

- Off-screen: exact phrase `says in an off-screen voiceover`, then the
  on-screen character's lips remain completely closed.
- Dialogue crossing a cut: `<scenetrans>` at both connecting points plus
  "continues seamlessly across the cut".
- Speech truncated by video end: `<cutoff>`.
- Group speech: `(S1,S2)`.
- Visible banners, signs, labels: English double quotation marks, verbatim
  (`A red neon sign reading "OPEN" glows above the doorway.`).

H3 has no negative-prompt field. Identity and count locks go as **inline
prose** inside `detailed_description`:

> "Never generate mirrored hands, duplicated arms, extra palms, or a second
> spatula."

## Audio (two separate sections)

### overall_soundscape (diegetic)

1–4 English sentences, one paragraph: ambience, physical action sounds,
non-verbal human sounds across the FULL generation. Do not repeat dialogue,
singing, or shot-synced sound events. `N/A` only if the user requests complete
silence.

**Sound design layers** (see `assets/directors-guide.md` Section 7): Foley,
Ambient, Impact, Silence.

### non_diegetic_music (score)

1–3 sentences: instrumentation, tempo, rhythm, dynamic changes — no abstract
mood words, no emotional-function explanations. Music audible to characters
(radio, singing, phone) is diegetic → `detailed_description`. `N/A` when no
score.

**Music synchronization**: anticipation → movement → impact → sound →
reaction → silence/music hit. Time the hit to the shot's emotional peak.

## Animation beats in `detailed_description`

Write each `[Shot N]` action as a sequence of micro-beats in time order, not
a single verb. Animation is not "the character turns around" — it is
**hear sound → freeze → eyes move → head turns → body follows → reaction.**

See `assets/directors-guide.md` Section 6.

## What makes prompts fail

- Missing or misordered sections (the validator enforces all six, in order).
- `[Shot 1]` with a timestamp, or later shots without `At MM:SS.mmm`.
- Non-increasing timestamps, or timestamps that disagree with the storyboard.
- Shot count mismatching the storyboard generation.
- Internal ids (`char_01`) — describe characters by appearance instead.
- Missing `<Video 1>` on a generation that will receive a tail (validator warns).
- Vague action ("they fight") instead of visible beats.
- Camera direction scattered mid-action — keep one main camera idea per shot.
- Emitting the I2VA first-frame instruction for a storyboard sheet.
