# MiniMax H3 Prompt Bible (story-maker-v4)

Distilled from `Research/minimax-h3/`, MiniMax's official
`VIDEO_PROMPT_WRITING_GUIDE_base_en.md`, `VIDEO_PROMPT_WRITING_GUIDE_ref_en.md`,
and production benchmarks. For base keyframe modes (FL2VA, I2VA, L2VA, T2VA),
see [`assets/minimax-h3-modes-guide.md`](minimax-h3-modes-guide.md).
For the complete visual vocabulary (shots, 12 angles, 8 positions, 22 movements,
transitions, facial acting, micro-beats, composition rules), see
[`assets/cinematography-bible.md`](cinematography-bible.md).

MiniMax H3 is an omni-modal R2V model: it accepts up to 9 reference images, 3 reference
videos, 3 audio clips (12 files total), follows structured prompts,
and generates video with **native 32 kHz stereo audio** (voice, SFX, music).
Hard limit: **15 seconds per generation**. H3's Context-IR stage works best when
every shot is an explicit audiovisual instruction, not a plot summary.

---

## Formats Supported: Director's Brief (Default) vs Ref2VA (Legacy)

The skill supports two prompt formats:
1. **Director's Brief Format (Default & Recommended)**: High conditioning density, clear scannable per-shot timeline, style and characters upfront. Proven superior for complex multi-shot animation sequences.
2. **Ref2VA 6-Section Format (Legacy)**: The formal research protocol (`subject_definitions:`, `summary:`, `retention_analysis:`, `detailed_description:`, `overall_soundscape:`, `non_diegetic_music:`). Preserved for backwards compatibility.

Both formats are auto-detected by `validators.py`.

---

## 1. Director's Brief Format (Default)

### Template Structure

```
subject_definitions:Reference

Use the provided storyboard as the exact visual guide for composition,
framing, character appearance, environment, and sequence progression.

Maintain the exact appearance of [Character 1]: [Full descriptive paragraph of face, hair, clothing, palette, and key textures].

Maintain the exact appearance of [Character 2]: [Full descriptive paragraph].

[Environment context — spatial layout, lighting, atmospheric quality, time of day].

[Behavioral constraints & anti-artifact guardrails — e.g., "The characters are completely harmless and playful. Never generate duplicate characters, extra limbs, or distorted anatomy."]

Generate a cinematic [duration]-second [pacing] sequence matching the [grid]-panel storyboard.

[Style declaration line 1: craft, medium, texture]
[Style declaration line 2: lighting, palette, mood]
[Style declaration line 3: animation physics and aesthetic]
[Quality declarations: Feature-film quality. Highly expressive facial animation. Natural body mechanics. Temporal consistency.]

[For g2+ generations:
This is a seamless continuation from the previous generation.
SHOT 1 begins from the exact ending pose, camera angle, and lighting of the previous clip.]

Timeline

SHOT 1 — 0.0–X.Xs (Continuous Shot)

[Shot visual description: Shot size, camera angle, camera position, staging, and micro-beat acting sequence.]

[Camera instruction: 3D Camera Formula: [Motion Type] with [amplitude] at [speed].]

Audio: [Foley, room tone, footsteps, material rustle, impact, and inline dialogue.]

[Transition phrase: e.g., "Hard cinematic cut." or "Cut on the action."]

SHOT 2 — X.X–Y.Ys (Continuous Shot)
...
```

### Optimal Depth & Description Sweet Spot
- **Word Count**: Aim for **350–500 English words** across the combined `SHOT` blocks in the `Timeline`.
- **No Tag Stuffing**: Do not include keywords like `"4k"`, `"8k"`, `"masterpiece"`, `"photorealistic"`. H3 was trained on rich descriptive natural language.
- **No Studio Brand Names**: Describe the craft, medium, texture, and lighting instead of using commercial brand names.

---

## 2. Ref2VA 6-Section Contract (Legacy)

Output ONLY these six sections, in this exact order, with lowercase field names followed by a colon:

```
subject_definitions:
<Subject N> is the <what> in <Picture M>, with <concrete features to preserve>.
<Picture 1> is the storyboard reference for [Shot 1]..., defining viewpoint, placement, and shot order.
<Video 1> is the previous generation's rendered tail and continuation starting point (g2+ only).

summary:
[reference generation] <one-sentence story of this generation>.
# For g2+: [video continuation + reference generation] <continuation summary>.

retention_analysis:
<Subject 1> (appears in [Shot 1], [Shot N]): fully_preserved - <what is retained>.
<Picture 1> (storyboard reference): fully_preserved - composition and panel sequence.
<Video 1> (continuation starting point): fully_preserved - ending pose, staging, lighting, and motion state.

detailed_description:
<1-2 sentence style statement BEFORE [Shot 1].>
[Shot 1] <action, camera, audio. NO timestamp on Shot 1. For g2+, state seamless continuation from <Video 1>.>
[Shot 2] At MM:SS.mmm, the shot cuts to <new information>. <action, camera, audio.>
<Identity/count locks as inline prose: "Never generate duplicate characters.">

overall_soundscape:
<1-4 sentences: diegetic ambience + physical action sounds + non-verbal human sounds.>

non_diegetic_music:
<1-3 sentences: score the characters CANNOT hear — instrumentation, tempo, rhythm, dynamics. N/A if no score.>
```

---

## 3. The "One Job" Rule for Multi-Reference Conditioning

When attaching multiple references to H3, assign **one clear primary responsibility** to each reference asset:
- **Staging/Storyboard**: `<Picture 1>` defines camera angles, panel blocking, and composition progression across the grid.
- **Identity**: Specific character sheets define facial structure, hairstyle, and skin tone.
- **Wardrobe/Props**: Defined assets lock clothing or distinct props.
- **Motion Dynamics**: `<Video 1>` (or previous tail ref) carries over momentum, camera path, and ending pose.
- **Vocal Timbre**: `<Audio 1>` provides timbre, pitch cadence, and accent for a specific speaker `(Sx)`.

Never assign competing visual jobs to two different image assets.

---

## 4. Control Tokens & Canonical Transitions

### Literal Control Tokens (do not vary these)

| Token | Purpose |
|---|---|
| `subject_definitions:Reference` | Header for Director's Brief |
| `Timeline` | Timeline section header in Director's Brief |
| `SHOT N — start–ends (Continuous Shot)` | Shot header in Director's Brief |
| `[Shot N]` | Shot header in Ref2VA |
| `At MM:SS.mmm` | Timestamp prefix for shots 2+ in Ref2VA |
| `<d>[Language] ...</d>` | Dialogue tag — exact syntax |
| `(S1)` `(S2)` | Speaker IDs — exact parenthetical syntax |
| `<scenetrans>` `<cutoff>` | Dialogue continuity markers — exact |

### Canonical Transition Phrases (MiniMax H3 Validated)

See [`assets/cinematography-bible.md`](cinematography-bible.md) Section E for full details:

| Transition | Canonical Phrase | When to Use |
|---|---|---|
| `hard_cut` | `Hard cinematic cut.` | New subject, space, state, viewpoint, or time |
| `cut_on_action` | `Cut on the action.` | Mid-motion cut; movement carries across |
| `reaction_cut` | `Cut to the reaction.` | Action → face/reaction beat |
| `match_cut` | `Match cut on <element>.` | Graphic/positional match (name the element) |
| `whip_pan` | `Whip pan transition.` | Camera-motivated; rapid swish |
| `audio_led` | `Audio leads the cut.` | Next shot's sound starts before visual (J-cut) |
| `continuous` | *(no phrase or "Continuous take.")* | Same take continues |
| `camera_move` | *(describe camera move)* | Only framing/angle changes |

**The New-Information Rule**: A cut must add NEW information (subject, space, state, viewpoint, time). If only distance or angle changes, use camera motion instead.

---

## 5. Camera & Cinematography Grammar

Consult [`assets/cinematography-bible.md`](cinematography-bible.md) for full taxonomy:
- **Shot Sizes**: Section A (7 sizes from `extreme_wide` to `extreme_closeup`)
- **Camera Angles**: Section B (12 complete angles: `eye_level`, `low_angle`, `high_angle`, `birds_eye`, `worms_eye`, `dutch_angle`, `over_the_shoulder`, `pov`, `three_quarter_front`, `three_quarter_back`, `profile`, `top_down`)
- **Camera Positions**: Section C (8 positions on the 360° ring)
- **3D Camera Formula**: Always specify `[Motion Type] with [amplitude] at [speed]`
  (e.g., `"The camera pushes in with small amplitude at slow speed toward the folded letter in her hands."`).
- **Facial Scale Strategy**: Small faces (<15% frame height) degrade in H3. Pair wide shots with motivated cuts to MCU or CU for character acting.

---

## 6. Facial Acting & Micro-Beats

Consult [`assets/cinematography-bible.md`](cinematography-bible.md) Sections F & G:
- Never use generic states ("the character looks sad").
- Follow the anatomical sequence: **Stimulus → Freeze → Eyes → Brows → Mouth → Head → Body → Secondary Motion**.
- Describe secondary motion (hair, clothing, props) settling with physical delay.

---

## 7. Seamless Continuation Blueprint (g2+)

For generations after g1:
- In Director's Brief: add the continuation block before `Timeline`:
  > *"This is a seamless continuation from the previous generation. SHOT 1 begins from the exact ending pose, camera angle, and lighting of the previous clip."*
- `SHOT 1` begins with continuing action and motion matching the end of the prior clip.
- All timestamps remain generation-local (starting at 0.0s).

---

## 8. Dialogue Format

Stable speaker IDs `(S1)`, `(S2)` assigned in order of first vocal event. Delivery and identity anchors go OUTSIDE the `<d>` tag; exact spoken words go INSIDE with a language tag:

```
Emily (S1) turns and says, <d>[English] Look at that!</d>
```

- Preserve dialogue verbatim.
- Dialogue crossing cuts: `<scenetrans>` at connecting points.
- Speech truncated by end of shot: `<cutoff>`.
- Off-screen voice: `says in an off-screen voiceover: <d>[English] ...</d> while lips remain closed.`

---

## 9. Audio Direction

Each shot must direct its own soundscape:
- **Foley**: footsteps, fabric rustle, tactile interactions
- **Ambient**: acoustic space, wind, distant birds, room tone
- **Impact & Voice**: punctuation of key dramatic beats
- **Silence**: dramatic pauses before reveals

