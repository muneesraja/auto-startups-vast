# Agent 5 — Minimax Video Prompter (Ref2VA Canonical Contract)

**Input (per generation):** the generation's rendered storyboard sheet
(`storyboard_sheet_<scene>_<gen>.webp` — **Read the image**; describe what was
actually drawn, not what you wished for), `storyboard_<scene>.md`,
`developed_story.md` (character/location appearance), the episode context
(what the previous generation/scene ended on), and
[`assets/minimax-h3-prompt-bible.md`](../assets/minimax-h3-prompt-bible.md).
**Output:** `<run_dir>/video_prompts/<scene>_<gen>.txt` — the exact text sent
to Minimax H3 with the sheet attached as the reference image. Then run
`python3 scripts/validate.py video_prompts/<scene>_<gen>.txt --schema video_prompt --run-dir <run_dir> --scene <scene>`
and fix until it passes.

---

## The 6-Section Ref2VA Contract (Load-Bearing)

Write one 6-section Ref2VA prompt per generation, following Minimax H3's official
vision-language conditioning contract. Output ONLY these six sections, in this exact
order, with lowercase field names followed by a colon. No preamble, no markdown fences,
no commentary.

```text
subject_definitions:
<Subject N> is the <character/prop> in <Picture 1>, with <concrete appearance features>.
<Picture 1> is the storyboard reference for [Shot 1] through [Shot N], defining viewpoint, placement, and shot order.
<Video 1> is the previous generation's rendered tail and continuation starting point (only when attached for g2+).

summary:
[reference generation] One-sentence summary of the target story beat and how each reference guides it.
# For g2+ with tail video attached:
# [video continuation + reference generation] The video seamlessly continues from <Video 1> as <action continues>...

retention_analysis:
<Subject 1> (appears in [Shot 1], [Shot 2]): fully_preserved - <features locked>.
<Picture 1> (storyboard reference): fully_preserved - composition, lighting, and panel sequence.
<Video 1> (continuation starting point): fully_preserved - ending pose, staging, lighting, and motion state (for g2+).

detailed_description:
<1-2 sentence high-end visual style declaration before [Shot 1].>
[Shot 1] <composition, character state, micro-beat acting, camera motion, audio/dialogue, reference effect. NO timestamp on Shot 1.>
[Shot 2] At MM:SS.mmm, <transition>. <new information, micro-beat acting, camera motion, audio/dialogue.>
...
<Identity/count locks as inline prose: "Never generate duplicate characters or extra limbs.">

overall_soundscape:
<1-4 sentences: diegetic ambience, room tone, physical foley across the 15s. Harvest ALL-CAPS screenplay sound cues.>

non_diegetic_music:
<1-3 sentences: score the characters cannot hear — instrumentation, tempo, rhythm, dynamics; or N/A.>
```

---

## Dynamic Shot Pacing (2 Minimum to 8 Maximum)

Never force a rigid shot count. Match the shot count dynamically to the dramatic pacing of the scene:

1. **Slow-Paced / Emotional / Intimate / Tension (2 Shots Minimum)**:
   - Typical durations: 7.5s + 7.5s, or 6.0s + 9.0s.
   - **MANDATORY FOR 2-SHOT SCENES — SUPER HIGH DETAIL**:
     A long shot in an AI video generator can easily feel frozen, drifting, or boring if under-specified. When writing a 2-shot scene, the `detailed_description:` MUST be richly textured (targeting 250–450 words total) with:
     - **Multi-phase micro-beat progression**: divide the shot into internal emotional/physical phases (e.g. `initial stunned freeze → breathing catches and chest heaves → eyes widen in dawning horror → subtle lower lip tremor → tear breaks and spills down cheek → head slowly sinks in defeat`).
     - **Continuous evolving camera movement**: never static! Use motivated motion with the 3D formula (e.g. `Slow Push In with subtle parallax drift`, `Gentle Arc Shot orbiting the subject`, `Controlled Crane Down`).
     - **Living atmospheric environment**: explicitly direct continuous background motion (drifting dust motes through light shafts, dancing oil lamp flame reflections, wind fluttering garment hems and hair, shifting tree shadow patterns).
     - **Layered acoustic evolution**: footsteps halting, labored breath hitched in throat, creaking wood, rustling fabric, rising wind tone.
2. **Moderate Dramatic Pace / Dialogue / Discovery (3 to 4 Shots)**:
   - Typical durations: 3.5s to 5.0s per shot. Balanced visual variety and editorial rhythm.
3. **Fast-Paced / Action / Comedy / Chase / Climax (5 to 8 Shots Maximum)**:
   - Typical durations: 1.5s to 3.0s per shot. Rapid, punchy kinetic cutting.

---

## Section Rules & Token Binding

### 1. `subject_definitions:`
- **Token binding is load-bearing**: Declare `<Subject 1>`, `<Subject 2>`, etc. and map each explicitly to `<Picture 1>` (e.g. `<Subject 1> is Vikram in <Picture 1>, a 24-year-old...`).
- Describe characters **by concrete visual appearance** — never internal IDs like `char_06` (validator rejects internal IDs). Include face, hair, skin tone, garments, accessories, and palette.
- **`<Picture 1>` is mandatory**: Must define `<Picture 1>` as the storyboard sheet reference mapping to the shot range (e.g. `<Picture 1> is the storyboard reference for [Shot 1] through [Shot 4], defining viewpoint, placement, and shot order.`).
- **`<Video 1>` for `g2+`**: When rendering a continuation generation, declare `<Video 1> is the previous generation's rendered tail and continuation starting point.`

### 2. `summary:`
- Must open with bracketed task-type prefix:
  - For `g1`: `[reference generation]`
  - For `g2+` (with tail attached): `[video continuation + reference generation]`

### 3. `retention_analysis:`
- One line per defined label from `subject_definitions:`.
- Visual markers: `fully_preserved` | `partially_preserved` | `attribute_transfer` | `weak_reference`.
- `<Picture 1>` must declare: `fully_preserved - composition, lighting, and panel sequence.`
- `<Video 1>` (for `g2+`) must declare: `fully_preserved - ending pose, staging, lighting, and motion state.`

### 4. `detailed_description:`
- **Style statement before `[Shot 1]`**: 1-2 sentences declaring craft, lighting, and texture.
- **`[Shot 1]` has NO timestamp**: It begins implicitly at `00:00.000`.
- **Shots 2+ have explicit timestamps**: `[Shot 2] At MM:SS.mmm, <transition phrase>.` Timestamps must match the storyboard generation block exactly.
- **Refer to subjects by token**: Use `<Subject 1>`, `<Subject 2>` throughout the shot descriptions.
- **Transition phrases**: Use canonical transitions (`Hard cinematic cut.`, `Cut on the action.`, `Cut to the reaction.`, `Match cut on <element>.`, `Whip pan transition.`).
- **Dialogue formatting**:
  - Stable speaker IDs: `(S1)`, `(S2)`.
  - Delivery instructions outside tags, spoken words inside `<d>[Language] ...</d>`:
    `<Subject 1> (S1) turns and whispers in anguish, <d>[Tamil] Amma... </d>`
  - Voiceover: `speaks in an off-screen voiceover: <d>[English] ...</d> while lips remain closed.`
- **Identity/count locks as inline prose**: E.g. `Never generate duplicate characters, extra limbs, or distorted anatomy.`
- **Cross-Generation Seam Alignment**:
  - For `g2+`, `[Shot 1]` must explicitly state: `Continuing seamlessly from <Video 1>, <Subject 1> begins from the exact ending pose, camera angle, and lighting of the previous clip...`
  - Ensure the physical posture, framing, and environment match the end of `gK`!

### 5. `overall_soundscape:`
- Diegetic ambience, room tone, and physical foley across the full 15 seconds.
- **Harvest Screenplay Sound Cues**: Scan `developed_story.md` action lines for ALL-CAPS sound cues (`SNAP!`, `POP`, `CREAK`, `WHUMP`, `SPLASH`) and incorporate them directly.
- Do not repeat spoken dialogue or non-diegetic score terms here.

### 6. `non_diegetic_music:`
- Score the characters cannot hear. Describe instrumentation, tempo, rhythm, and dynamics (e.g. `Low cello drone with rising Vedic chants and subtle string swells`).
- Use `N/A` if the scene relies purely on diegetic silence/soundscape.
