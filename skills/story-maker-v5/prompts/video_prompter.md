# Agent 5 — Minimax Video Prompter (Ref2VA Canonical Contract)

**Input (per generation):** the generation's rendered storyboard sheet
(`storyboard_sheet_<scene>_<gen>.webp` — **Read the image**; describe what was
actually drawn, not what you wished for), `storyboard_<scene>.md`,
`developed_story.md` (character/location appearance), the episode context
(what the previous generation/scene ended on), the `<run_dir>/audio/` folder
when it exists (role-tagged files attach as `<Audio 1>` references — see
`tools/audio_refs.py` and SKILL.md "Audio references"), and
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
<Video 1> is the previous generation's rendered tail and continuation starting point (only when a tail is attached — see the Boundary Rule below).
<Audio 1> is the <role> audio reference supplied for this generation (only when the audio manifest lists one).

summary:
[reference generation] One-sentence summary of the target story beat and how each reference guides it.
# For continuation generations with tail video attached:
# [video continuation + reference generation] The video seamlessly continues from <Video 1> as <action continues>...

retention_analysis:
<Subject 1> (appears in [Shot 1], [Shot 2]): fully_preserved - <features locked>.
<Picture 1> (storyboard reference): fully_preserved - composition, lighting, and panel sequence.
<Video 1> (continuation starting point): fully_preserved - ending pose, staging, lighting, and motion state (continuation boundaries only).
<Audio 1> (<role> reference): <marker> - <what the audio guides, e.g. voice timbre and delivery for (S1)> (only when attached).

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

## Dynamic Shot Pacing (1 to 8 shots)

Canonical taxonomy in [`assets/production-rules.md`](../assets/production-rules.md) §1.
Validator expectations that matter here:

- **1-shot master take (oner)**: legal and mandatory for unbroken beats;
  `detailed_description:` must carry extreme texture (validator expects
  ≥120 words for 1-shot and ≥250 for 2-shot generations) with multi-phase
  micro-beats, evolving camera motion, living background motion, and layered
  acoustics — a long under-specified shot drifts or freezes.
- **2 shots**: same high-detail mandate (≥250 words target).
- **3–4 shots**: balanced pace; validator warns when total
  `detailed_description:` falls below ~350 words.
- **5–8 shots**: rapid kinetic cutting (1.5–3.0s per shot).

---

## Section Rules & Token Binding

### 1. `subject_definitions:`
- **Token binding is load-bearing**: Declare `<Subject 1>`, `<Subject 2>`, etc. and map each explicitly to `<Picture 1>` (e.g. `<Subject 1> is Young Ollie in <Picture 1>, a small otter-like Pookoo with fluffy chocolate-brown fur, a russet head tuft, and huge emerald-green eyes...` — full worked example in [`assets/example-ollie.md`](../assets/example-ollie.md) §7).
- Describe characters **by concrete visual appearance** — never internal IDs like `char_06` (validator rejects internal IDs). Include face, hair, skin tone, garments, accessories, and palette.
- **`<Picture 1>` is mandatory**: Must define `<Picture 1>` as the storyboard sheet reference mapping to the shot range (e.g. `<Picture 1> is the storyboard reference for [Shot 1] through [Shot 4], defining viewpoint, placement, and shot order.`).
- **The Boundary Rule decides `<Video 1>`** (`tools/boundary.py`): a tail is
  attached exactly when this generation is NOT the episode's first AND the
  boundary is a continuation — i.e. this generation's shot-1 transition is
  not `hard_cut` and, when it opens a scene, the previous scene's handoff
  transition is not `hard_cut`. Match the declaration to reality:
  - Tail attached → declare `<Video 1> is the previous generation's rendered
    tail and continuation starting point.`
  - Fresh cut → no `<Video 1>`; the validator errors if you declare one, and
    errors if you omit it when a tail is attached.
- **`<Audio 1>`** (only when `audio/` contains a file scoped to this
  generation — see `tools/audio_refs.py`): declare its role in
  `subject_definitions:` (e.g.
  `<Audio 1> is the voice reference for (S1)'s delivery.` or
  `<Audio 1> is the approved dialogue master for this generation's spoken
  lines.`), give it a `retention_analysis:` line, and reference it in the
  shot where the audio applies. **Every ref has exactly one declared job.**

### 2. `summary:`
- Must open with bracketed task-type prefix:
  - First generation / fresh-cut boundary: `[reference generation]`
  - Tail attached (continuation boundary): `[video continuation + reference generation]`

### 3. `retention_analysis:`
- One line per defined label from `subject_definitions:`.
- Visual markers: `fully_preserved` | `partially_preserved` | `attribute_transfer` | `weak_reference`.
- `<Picture 1>` must declare: `fully_preserved - composition, lighting, and panel sequence.`
- `<Video 1>` (tail attached) must declare: `fully_preserved - ending pose, staging, lighting, and motion state.`

### 4. `detailed_description:`
- **Style statement before `[Shot 1]`**: 1-2 sentences declaring craft, lighting, and texture.
- **`[Shot 1]` has NO timestamp**: It begins implicitly at `00:00.000`.
- **Shots 2+ have explicit timestamps**: `[Shot 2] At MM:SS.mmm, <transition phrase>.` Timestamps must match the storyboard generation block exactly.
- **Refer to subjects by token**: Use `<Subject 1>`, `<Subject 2>` throughout the shot descriptions.
- **Transition phrases**: Use canonical transitions (`Hard cinematic cut.`, `Cut on the action.`, `Cut to the reaction.`, `Match cut on <element>.`, `Whip pan transition.`).
- **Dialogue formatting**:
  - Stable speaker IDs: `(S1)`, `(S2)` — and each ID must be **bound to a
    subject** in `subject_definitions:` (e.g. `(S1) is <Subject 1>'s voice.`).
    The validator errors on any `(SN)` used in `detailed_description:` that
    has no binding line.
  - Delivery instructions outside tags, spoken words inside `<d>[Language] ...</d>`:
    `<Subject 1> (S1) offers a sheepish grin under his father's glare,
    <d>[English] Hey, Dad... <pause> Thirsty? </d>`
  - The `<d>` bracket takes delivery modifiers: `<d>[English, singing]`,
    `<d>[English, crying]`, `<d>[Hum]` (see prompt bible §8).
  - **Vocal performance tags inside `<d>`** shape delivery: `<pause>`,
    `<breath>`, `<stutter>`, `<i>word</i>` emphasis, `<whisper>…</whisper>`,
    `<sighs>`, `<laughs>`, `<pants>`, `<softer>` — full table in
    [`assets/minimax-h3-prompt-bible.md`](../assets/minimax-h3-prompt-bible.md) §8.
    Keep the emotional arc in prose outside the tag; the tags shape the take.
  - Humming to a melody ref: `<Subject 1> (S1) hums the melody of <Audio 1>
    in his own voice, <d>[Hum] daa-da-da.</d>` (requires an attached
    `music`/`reference` audio ref).
  - Voiceover: `speaks in an off-screen voiceover: <d>[English] ...</d> while lips remain closed.`
- **Identity/count locks as inline prose**: E.g. `Never generate duplicate characters, extra limbs, or distorted anatomy.`
- **Cross-Generation Seam Alignment**:
  - When a tail is attached, `[Shot 1]` must explicitly state: `Continuing seamlessly from <Video 1>, <Subject 1> begins from the exact ending pose, camera angle, and lighting of the previous clip...`
  - Ensure the physical posture, framing, and environment match the end of `gK`!
  - Fresh-cut boundary (no tail): `[Shot 1]` simply opens the new setup — no continuation sentence, no `<Video 1>`.

### 5. `overall_soundscape:`
- Diegetic ambience, room tone, and physical foley across the full 15 seconds.
- **Harvest Screenplay Sound Cues**: Scan `developed_story.md` action lines for ALL-CAPS sound cues (`SNAP!`, `POP`, `CREAK`, `WHUMP`, `SPLASH`) and incorporate them directly.
- Do not repeat spoken dialogue or non-diegetic score terms here.

### 6. `non_diegetic_music:`
- Score the characters cannot hear. Describe instrumentation, tempo, rhythm, and dynamics (e.g. `Low cello drone with rising Vedic chants and subtle string swells`).
- Use `N/A` if the scene relies purely on diegetic silence/soundscape.
