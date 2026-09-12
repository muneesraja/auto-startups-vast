# MiniMax H3 Prompt Bible (story-maker-v5)

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

## Canonical Format: The 6-Section Ref2VA Contract

Story Maker V5 uses Minimax H3's official **Ref2VA 6-Section Contract** as the canonical standard. It provides explicit token binding between reference images (`<Picture 1>`), characters (`<Subject 1>`), and tail continuation videos (`<Video 1>`).

Output ONLY these six sections, in this exact order, with lowercase field names followed by a colon. No preamble, no markdown fences, no commentary.

```text
subject_definitions:
<Subject N> is the <character/prop> in <Picture 1>, with <concrete appearance features>.
<Picture 1> is the storyboard reference for [Shot 1] through [Shot N], defining viewpoint, placement, and shot order.
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
[Shot 1] <composition, actor state, micro-beat acting, camera motion, audio/dialogue. NO timestamp on Shot 1. For g2+, state seamless continuation from <Video 1>.>
[Shot 2] At MM:SS.mmm, <transition phrase>. <new information, micro-beat acting, camera motion, audio/dialogue.>
...
<Identity/count locks as inline prose: "Never generate duplicate characters or extra limbs.">

overall_soundscape:
<1-4 sentences: diegetic ambience + physical action sounds + room tone across 15s. Harvest screenplay ALL-CAPS sound cues.>

non_diegetic_music:
<1-3 sentences: score the characters CANNOT hear — instrumentation, tempo, rhythm, dynamics. N/A if no score.>
```

---

## Dynamic Shot Pacing (1 to 8 Shots)

Canonical taxonomy: [`production-rules.md`](production-rules.md) §1. Never
enforce static 2-shot or 4-shot limits — the shot count is chosen from the
dramatic pacing:

1. **Master Take / Oner (1 Shot)** — unbroken continuous beat; panels become
   temporal milestones. Mandatory extreme detail.
2. **Slow-Paced / Emotional / Intimate / Tension (1–2 Shots)**:
   - Typical durations: 6.0s to 15.0s per shot.
   - **MANDATORY SUPER HIGH DETAIL**: To prevent a 15-second generation from feeling static, frozen, or boring, the `detailed_description:` MUST be richly detailed (≥120 words for a oner, ≥250 for 2 shots):
     - **Multi-phase micro-beat progression**: describe internal evolution across the shot (e.g. `initial stillness → breathing catches and chest heaves → eyes widen in dawning horror → subtle lower lip tremor → tear breaks and spills down cheek → head slowly sinks in defeat`).
     - **Continuous evolving camera movement**: motivated 3D camera formula (`Slow Push In with subtle parallax drift`, `Gentle Arc Shot orbiting the subject`, `Controlled Crane Down`).
     - **Living atmospheric environment**: continuous background motion (drifting dust motes through light shafts, dancing oil lamp flame reflections, wind fluttering garment hems and hair, shifting tree shadow patterns).
     - **Layered acoustic evolution**: footsteps halting, labored breath hitched in throat, creaking wood, rustling fabric, rising wind tone.
3. **Moderate Dramatic Pace / Dialogue / Discovery (3 to 4 Shots)**:
   - Typical durations: 3.5s to 5.0s per shot. Balanced cuts and character reactions.
4. **Fast-Paced / Action / Comedy / Chase / Climax (5 to 8 Shots Maximum)**:
   - Typical durations: 1.5s to 3.0s per shot. Rapid, punchy kinetic cutting matching the 3x3 storyboard grid.

---

## 2. Which strings are literal control tokens (do not vary these)

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

Stable speaker IDs `(S1)`, `(S2)` assigned in order of first vocal event. Delivery and identity anchors go OUTSIDE the `<d>` tag; exact spoken words go INSIDE with a language/delivery bracket:

```
Emily (S1) turns and says, <d>[English] Look at that!</d>
```

- Preserve dialogue verbatim.
- Dialogue crossing cuts: `<scenetrans>` at connecting points.
- Speech truncated by end of shot: `<cutoff>`.
- Off-screen voice: `says in an off-screen voiceover: <d>[English] ...</d> while lips remain closed.`

### Delivery-class bracket

The bracket inside `<d>` carries a language plus optional comma-separated
delivery modifiers — the validator accepts the full form:

```
<d>[English, singing] too maaake meee siiiing?</d>
<d>[English, crying] <pants> Maybe all you wanted was to break me!</d>
<d>[Hum] daaaa-daa-da-da-da-daaaa.</d>
```

### Vocal performance tags (inside `<d>`)

Community-tested tags H3 understands in spoken lines
(`Research/micro-expressions-minimax/guide.md`). Open-ended set — the
validator warns on unknown tags but does not error:

| Tag | Effect | Example |
|---|---|---|
| `<pause>` / `<long pause>` | Beat of silence | `Okay, so. <pause> This is just me talking.` |
| `<breath>` `<inhale>` `<exhale>` `<deep breath>` | Audible breathing | `<deep breath> Okay. I can do this.` |
| `<catches breath>` | Out of breath | `Wait... <catches breath> hold on.` |
| `<i>word</i>` | Emphasize 1–4 words | `I was <i>not</i> expecting that.` |
| `<whisper>…</whisper>` | Whisper delivery | `<whisper> Don't tell anyone.</whisper>` |
| `<humming>…</humming>` | Humming a tune | `<humming> da-da-da.</humming>` |
| `<laughs>` / `<chuckle>` | Laughing | `<laughs> that's actually funny.` |
| `<sighs>` `<sniff>` `<gasp>` | Sigh / sniff / sharp intake | `<sighs> I really tried.` |
| `<uh>` `<stutter>` | Hesitation / stutter | `<stutter> I ca can't believe that.` |
| `<coughs>` `<clears throat>` `<smacks lips>` | Throat/mouth sounds | `<clears throat> So anyway...` |
| `<pant>` / `<pants>` | Panting | `Run... <pants> run now!` |
| `<softer>` | Quieter delivery | `<softer> I don't think I can say it.` |
| `<mhm>` `<phew>` | Agreement / relief | `<phew> That was close.` |

Performance direction stays OUTSIDE the tag — put the emotional/physical
arc in prose before the `<d>`, then let the tags shape the delivery:
`<Subject 1> starts to cry, desperately sobbing as he delivers the line.
<Subject 1> (S1) says, <d>[English, crying] <pants> Maybe all you wanted
was to break me!</d>`

### Humming / singing to a melody reference

When a `<Audio N>` music/melody reference is attached, bind it to the
vocalization explicitly:

```
<Subject 1> (S1) hums the melody of <Audio 1> in his own voice from
beginning to end, <d>[Hum] daaaa-daa-da-da-da-daaaa.</d>
```

The audio ref carries the tune; the `<d>[Hum]` line carries the shaped
vocalization. Singing uses `[Language, singing]` and does not require a
melody ref.

### High-resolution skin caveat

At high resolution H3 can exaggerate skin saturation and features
(wrinkles, pores). Counter it in `subject_definitions:` appearance prose:
`skin soft, even, natural color; pores visible without harsh contrast`.

---

## 9. Audio Direction

Each shot must direct its own soundscape:
- **Foley**: footsteps, fabric rustle, tactile interactions
- **Ambient**: acoustic space, wind, distant birds, room tone
- **Impact & Voice**: punctuation of key dramatic beats
- **Silence**: dramatic pauses before reveals

