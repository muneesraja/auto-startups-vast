# MiniMax H3 Ref2VA format — V4 canonical contract

Derived from MiniMax's official `VIDEO_PROMPT_WRITING_GUIDE_ref_en.md` and the
shared base guide. Use this exact ordered structure for every V4 generation
prompt. It is validated before a paid render.

Write every section in English. Preserve original language only inside
`<d>[Language] ...</d>` dialogue/lyrics and inside quoted visible on-screen text.

```text
subject_definitions:
<Subject 1> is the reusable visible subject, with concrete identity features and reference provenance.
<Picture 1> is the storyboard reference for [Shot 1]..., defining viewpoint, placement, and shot order.
<Video 1> is the previous generation's rendered tail and continuation starting point (only when attached).

summary:
[reference generation] One sentence naming the target story beat and how each reference guides it.
# For a generation after g1: [video continuation + reference generation] ...

retention_analysis:
<Subject 1> (appears in [Shot 1], [Shot N]): fully_preserved - what remains locked.
<Picture 1> (storyboard reference): fully_preserved - composition and panel sequence.
<Video 1> (continuation starting point): fully_preserved - ending pose, staging, lighting, and motion state.

detailed_description:
<Style + initial composition, stated before [Shot 1].>
[Shot 1] <composition, appearance/position, environment/lighting, action/state change, camera, sound, reference effect.>
[Shot 2] At 00:03.000, <new information; full visual/auditory state, camera, and reference effect.>
<Inline identity/count locks.>

overall_soundscape:
<1-4 sentences: ambience, foley, impacts, and non-verbal human sounds. Never repeat dialogue.>

non_diegetic_music:
<1-3 sentences: instrumentation, tempo, rhythm, dynamics; or N/A.>
```

Rules that the validator treats as contract, not style:

- `[Shot 1]` has no timestamp. Later shots use generation-local, strictly
  increasing `At MM:SS.mmm` timestamps matching the storyboard.
- Every defined label keeps one meaning across all six sections. No section may
  invent an undefined `<Subject N>`, `<Picture N>`, `<Video N>`, or `<Audio N>`.
- `retention_analysis` has one entry per defined label. Visual labels use
  `fully_preserved`, `partially_preserved`, `attribute_transfer`, or
  `weak_reference`; audio labels use `fully_copy`, `partially_copy`,
  `reference`, or `weak_reference`.
- A cut introduces new subject, space, state, viewpoint, or time. Use camera
  motion for framing-only change.
- For g2+, the renderer attaches the previous rendered tail. Define `<Video 1>`
  for it, use `[video continuation + reference generation]`, and open Shot 1
  from the observed ending state.
- Each shot must describe current composition, subject appearance/position,
  environment/lighting, action/state change, camera movement, and current
  sound. Do not collapse shots into plot summary.
- Keep dialogue words verbatim inside `<d>`; put speaker identity and delivery
  outside it. Voiceover must say the on-screen lips remain closed.
