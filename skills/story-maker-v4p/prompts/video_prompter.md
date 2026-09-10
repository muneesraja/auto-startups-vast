# Agent 5 — Minimax Video Prompter

**Input (per generation):** the generation's rendered storyboard sheet
(`storyboard_sheet_<scene>_<gen>.webp` — **Read the image**; describe what was
actually drawn, not what you wished for), `storyboard_<scene>.md`,
`developed_story.md` (character/location appearance), the episode context
(what the previous generation/scene ended on), and
[`assets/minimax-h3-prompt-bible.md`](../assets/minimax-h3-prompt-bible.md).
Official wording lives in [`assets/official/`](../assets/official/) — open
those only when writing a hard prompt.
**Output:** `<run_dir>/video_prompts/<scene>_<gen>.txt` — the exact text sent
to Minimax H3 with the sheet attached as the reference image (and a tail
`ref_video` when this is not the first generation of the run). Then run
`python3 scripts/validate.py video_prompts/<scene>_<gen>.txt --schema video_prompt --run-dir <run_dir> --scene <scene>`
and fix until it passes.

## Job

Write one 6-section Ref2VA prompt per generation. Do **not** use T2VA's
`integrated_multimodal_description` field. Do **not** emit the I2VA
first-frame instruction unless the attached image is a true start frame
(our storyboard sheet is not).

```
subject_definitions:
<Subject N> is the <character/environment> in <Picture 1>, with <appearance features to preserve>.
<Picture 1> is a storyboard reference for [Shot 1] and [Shot N], defining viewpoint, subject placement, and shot order.
<Video 1> is the continuation source: the last 3 seconds of the previous generation.

summary:
[reference generation] The target video shows <one-sentence story of this generation>.
# with a tail:
[reference generation + video continuation] The target video continues from <Video 1> and shows ...

retention_analysis:
<Subject 1> (appears in [Shot 1], [Shot 2]): fully_preserved - <features retained>.
<Picture 1> (storyboard reference): fully_preserved - composition, framing, and panel sequence.
<Video 1> (opening continuation): partially_preserved - motion and ending state carry into [Shot 1]; not a frame pin.

detailed_description:
<1-2 sentence style statement before [Shot 1].>
[Shot 1] <action, camera, audio. No timestamp on Shot 1.>
[Shot 2] At MM:SS.mmm, the shot cuts to <new information>. <action, camera, audio.>
...
<Identity/count locks as inline prose: "Never generate duplicate characters or extra babies.">

overall_soundscape:
<1-4 sentences: diegetic ambience, physical action sounds, non-verbal human sounds across the full generation.>

non_diegetic_music:
<1-3 sentences: score the characters cannot hear — instrumentation, tempo, rhythm, dynamics only. N/A if no score.>
```

## Section rules

### subject_definitions
- One `<Subject N>` per tracked character, plus `<Picture 1>` for the storyboard sheet.
- **One clear role per attached asset.** The picture is the file; the subject is reusable content.
- Describe characters **by appearance** — never `char_NN` (the validator rejects internal ids).
- Include concrete features: face, hairstyle, garments, accessories, palette.
- **Wall Reference (optional):** If a specific extracted wall plate from the 360° background video is attached as `<Picture 2>`, declare it: `<Picture 2> is the definitive wall reference plate for [Shot N], locking the background architecture and lighting.`
- **Tail:** if this generation will receive a 3s tail (`g2+` of the scene, or
  `g1` of a later scene), also define `<Video 1>` as the continuation source.
  First generation of the run: omit `<Video>`.

### summary
- Must open with a bracketed task-type prefix.
- First generation of the run: `[reference generation]`.
- Any generation with a tail: `[reference generation + video continuation]`.
- Use `+ audio reference` / `+ audio reuse` only when audio refs are attached.

### retention_analysis
- One line per label from `subject_definitions`.
- Visual markers: `fully_preserved` | `partially_preserved` | `attribute_transfer` | `weak_reference`.
- Tail `<Video 1>`: `partially_preserved` or `weak_reference` (continuity, not a frame pin).
- Audio markers (if `<Audio>` is defined): `fully_copy` | `partially_copy` | `reference` | `weak_reference`.

### detailed_description
- **Style statement before `[Shot 1]`** — 1-2 sentences, not inside any shot.
  Prefer official style words (`Cinematic`, `3D CG`, `2D-animated`, …) derived
  from the sheet. Target **350–500 English words** (dialogue-dense clips may
  run long to fit spoken lines).
- `[Shot 1]` has **no timestamp**. Later shots: `[Shot N] At MM:SS.mmm` with strictly increasing generation-local times.
- **One dominant action and one main camera idea per shot.** Action in playback order.
- Shot count and timestamps must match the storyboard generation exactly — the validator enforces both.
- **Cuts:** `the camera cuts to` / `the shot cuts to`. Also the bible's transition table:
  `Hard cinematic cut.`, `Cut on the action.`, `Cut to the reaction.`, `Match cut on <element>.`, `Whip pan transition.`, `Audio leads the cut.`
- **A cut must add new information** (subject, space, state, viewpoint, time). If only framing/angle changes, describe a camera move instead of cutting.
- **Camera:** type + amplitude + speed as natural English — `The camera pushes in with small amplitude at slow speed toward ...`
- **Dialogue**: stable speaker IDs `(S1)`, `(S2)` in order of first vocal event; delivery/identity anchors outside the tag; exact words inside:
  `<Subject 2> (S1) turns and says, <d>[English] Stay close, Timi!</d>`
- **Off-screen:** exact phrase `says in an off-screen voiceover`, then lips remain completely closed.
- **Dialogue crossing a cut**: use `<scenetrans>` at the connecting points in both shots plus "continues seamlessly across the cut".
- **Visible on-screen text:** English double quotation marks, verbatim.
- **Identity/count locks as inline prose** — e.g. "Never generate a second baby or duplicate mother." H3 has no `negative_prompt` field.
- When `<Video 1>` is defined, Shot 1 continues from that tail's ending state.
- **Spatial contract** (when `spatial_plan_<scene>.md` exists): fold the
  spatial plan's per-shot state into the shot description as natural-language
  placement — never raw pixel coordinates or internal zone IDs. Describe:
  - **Relative character placement**: "the girl stays at the lamp's left,
    foreground" / "the dog pack is far right, deep background".
  - **Landmark relationship**: "the dog pack approaches the lamp from the
    deep road, never entering the lamp's light pool".
  - **Approach/retreat direction**: "the dogs slowly approach the lamp" /
    "the girl retreats from the lamp into the darkness".
  - **Camera geography**: "camera looks down the road toward the lamp" /
    "camera faces away from the lamp along the dark road".
  - **Camera zoom**: translate `camera_zoom` into framing language
    ("vast establishing wide", "tight close-up on the girl's face"). Keep
    zoom changes smooth within continuous shots; jump cuts may change zoom
    abruptly.
  - **Character facing**: translate `character_facing` into natural-language
    body direction ("the girl faces the lamp", "the dog pack faces away
    from the lamp into the darkness"). Maintain facing direction across
    continuous shots (180° rule — no reversing between continuous shots).
  - **Landmark visibility**: if the spatial plan sets `visible_landmarks: []`
    for a shot, explicitly state "the lamp is NOT visible in this shot".
  - **Spatial continuity across shots/generations**: keep character-to-
    landmark distances consistent with the spatial plan's start/end positions
    and movement constraints.

### overall_soundscape
- Diegetic ambience and physical action sounds across the full generation (1–4 sentences).
- Do not repeat dialogue or shot-synced sound events here.
- **Sound design layers** (see
  [`assets/directors-guide.md`](../assets/directors-guide.md) Section 7):
  - **Foley**: footsteps, fabric, props — the texture of physical existence
  - **Ambient**: room tone, wind, distant traffic — the space around the action
  - **Impact**: punches, door slams, cracks — the punctuation of action
  - **Silence**: the pause before a reveal, the breath after impact — silence
    is a sound choice, not the absence of one

### non_diegetic_music
- Score the characters **cannot hear**: instrumentation, tempo, rhythm, dynamic changes only — no abstract mood words.
- `N/A` when no score. Music audible to characters (radio, singing) is diegetic → belongs in `detailed_description`.
- **Music synchronization**: the pattern is
  **anticipation → movement → impact → sound → reaction → silence/music hit**.
  The music hit lands ON the impact or the reaction, not randomly. Time it to
  the shot's emotional peak.

## Generation continuity (tail-video conditioning)

No bridge prompts are authored. Continuity between adjacent generations is
handled at render time: `render_all.py` renders generations sequentially and
passes the previous generation's rendered tail (3s) as a `ref_video` to the
next generation. Official Ref2VA requires that attached video to be labeled:

- **g1 of the first scene of the run**: no video reference; no `<Video>` line;
  summary is `[reference generation]`.
- **g(K+1) and later, and g1 of a later scene**: declare `<Video 1>` as the
  continuation source, use `[reference generation + video continuation]`, cite
  it in Shot 1. `render_all.py` attaches the file automatically.
- **SHOT count and timestamps must match the storyboard generation block exactly.**
