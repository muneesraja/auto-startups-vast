# Agent 5 — Minimax Video Prompter (Director's Brief Format)

**Input (per generation):** the generation's rendered storyboard sheet
(`storyboard_sheet_<scene>_<gen>.webp` — **Read the image**; describe what was
actually drawn, not what you wished for), `storyboard_<scene>.md`,
`developed_story.md` (character/location appearance), the episode context
(what the previous generation/scene ended on), and
[`assets/cinematography-bible.md`](../assets/cinematography-bible.md) (the complete
camera, facial acting, and animation vocabulary).
For prompt construction and reference rules, see
[`assets/minimax-h3-prompt-bible.md`](../assets/minimax-h3-prompt-bible.md).

**Output:** `<run_dir>/video_prompts/<scene>_<gen>.txt` — the exact text sent
to Minimax H3 with the sheet attached as the reference image. Then run
`python3 scripts/validate.py video_prompts/<scene>_<gen>.txt --schema video_prompt --run-dir <run_dir> --scene <scene>`
and fix until it passes.

---

## Job

Author one **Director's Brief** video prompt per generation. The Director's Brief format
delivers optimal conditioning density to MiniMax H3: character identities and style
are stated cleanly up front, and the `Timeline` is organized into scannable, per-shot blocks
with explicit camera, audio, and transition directions.

### Director's Brief Format Structure

```
subject_definitions:Reference

Use the provided storyboard as the exact visual guide for composition,
framing, character appearance, environment, and sequence progression.

Maintain the exact appearance of [Character 1]: [Full descriptive paragraph of face, hair, clothing, palette, and key textures].

Maintain the exact appearance of [Character 2]: [Full descriptive paragraph].

[Environment context — spatial layout, lighting, atmospheric quality, time of day].

[Behavioral constraints & anti-artifact guardrails — e.g., "The characters are completely harmless and playful. Never generate duplicate characters, extra limbs, or distorted anatomy."]

Generate a cinematic [duration]-second [pacing] sequence matching the [grid]-panel storyboard.

[Style declaration line 1: craft, medium, texture — textured gouache, watercolor wash, hand-painted digital storybook illustration]
[Style declaration line 2: lighting, palette, and mood]
[Style declaration line 3: animation physics and aesthetic]
[Quality declarations: Feature-film quality. Highly expressive facial animation. Natural body mechanics. Temporal consistency.]

[If g2+ generation:
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

---

## Core Cinematography & Directing Rules

Consult [`assets/cinematography-bible.md`](../assets/cinematography-bible.md) for every shot:

1. **Every SHOT must declare:**
   - A **Shot Size** from Section A (`extreme_wide`, `wide`, `full`, `medium`, `medium_closeup`, `closeup`, `extreme_closeup`)
   - A **Camera Angle** from Section B (`eye_level`, `low_angle`, `high_angle`, `birds_eye`, `worms_eye`, `dutch_angle`, `over_the_shoulder`, `pov`, `three_quarter_front`, `profile`, `top_down`)
   - A **Camera Position** from Section C (`front`, `three_quarter_front_left/right`, `side_left/right`, `three_quarter_back_left/right`, `behind`)
   - A **Camera Movement** from Section D using the 3D formula (`[Motion Type] with [small|large] amplitude at [slow|fast] speed`)

2. **Facial Acting Must Use Micro-Beats (Section G)**:
   - **Never** write "the character looks surprised/happy/sad."
   - Follow the anatomical reaction chain: **Stimulus → Freeze → Eyes (Section F.1) → Brows (Section F.2) → Mouth (Section F.3) → Head (Section F.4) → Body (Section F.5) → Secondary Motion**.
   - Example: *"Freezes mid-reach as amber eyes widen, brows lift in arched wonder, mouth parts softly in a breathy gasp, head tilts curiously, and her fingers gently curl forward while her braids swing forward over her shoulder and settle."*

3. **Multi-Angle Variety (MANDATORY)**:
   - Avoid monotonous front eye-level framing across adjacent shots.
   - Jump across the spatial circle: follow an eye-level wide with a low-angle medium close-up, a high-angle over-the-shoulder, or a profile tracking shot.
   - Every cut must add new visual or narrative information.

4. **Dynamic Shot Depth & Duration**:
   - Timeline shot counts and durations must match the dynamic storyboard exactly.
   - Support the full dynamic range: from a 15.0s unbroken master take (oner), to an asymmetric 2-shot dynamic (e.g. 11.5s master + 3.5s reaction; 9.0s dialogue + 6.0s response), to a 3-shot action arc (e.g. 6.0s + 2.5s + 6.5s).
   - Never mechanically chop generations into uniform slices. The duration must fit the physical action and emotional beats.

5. **Target Depth & Word Count**:
   - Combined SHOT descriptions in the `Timeline` must target **350–500 English words**.
   - No robotic references to storyboard panel numbers in shot descriptions (e.g. do NOT write "matches Panel 1"). Describe the cinematic scene directly.

6. **No Tag Stuffing & No Brand Names**:
   - Never write tags like `"4k"`, `"8k"`, `"masterpiece"`, `"unreal engine"`.
   - Never use commercial studio brand names like `"Pixar-quality"` or `"Disney style"`.
   - Describe concrete craft, medium, texture, and lighting instead: `"Hand-painted digital 2D storybook illustration with rich watercolor wash and textured gouache brushwork."`

6. **Dialogue Formatting**:
   - Stable speaker IDs: `(S1)`, `(S2)` in order of first vocal event.
   - Delivery instructions outside tags, spoken words inside `<d>[Language] ...</d>`:
     `Emily (S1) smiles and whispers, <d>[English] Look at that!</d>`
   - Dialogue crossing cuts: use `<scenetrans>` at connecting points.
   - Voiceover: `speaks in an off-screen voiceover: <d>[English] ...</d> while lips remain closed.`

7. **Audio Direction**:
   - Each SHOT must have its own dedicated `Audio:` line specifying Foley, acoustics, environment ambiance, and vocal sounds.

8. **Spatial Geography Contract**:
   - When a `spatial_plan_<scene>.md` exists, fold landmark relationships, zone positions, and character facing directly into the prose. Respect the 180° screen direction rule.

---

## Generation Continuity (g2+)

Continuity between adjacent generations is maintained via tail-video conditioning:
- For `g1`: opening generation of the scene.
- For `g2` and later:
  - Add the continuation block immediately before `Timeline`:
    ```
    This is a seamless continuation from the previous generation.
    SHOT 1 begins from the exact ending pose, camera angle, and lighting
    of the previous clip.
    ```
  - `SHOT 1` must explicitly describe continuing motion, matching the ending state of the previous generation.
  - Shot counts and timestamps must match the storyboard generation block exactly. All timestamps are generation-local (starting at 0.0s).
