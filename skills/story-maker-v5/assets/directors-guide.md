# Director's guide (story-maker-v5)

A concise directing cheat sheet for the authoring agents. Each section connects
story intent → visual/auditory choices using the vocabulary already in the skill.
This is not a film school textbook — it's the "why" behind the "what" the
prompts ask you to write.

The companion question bank ([`directing-questions.md`](directing-questions.md))
contains 200+ questions organized by these same 7 sections. The critique agent
(Agent 6) evaluates the full director plan against those questions before any
image generation begins (GATE 0).

## 1. Story & Visual Storytelling

### Story structure (compressed for short-form)
Every story — even a 30-second ad — needs a spine:
- **Setup** → establish world, character, and the status quo
- **Escalation** → introduce conflict, obstacle, or change
- **Climax** → the turning point, the moment of maximum tension
- **Resolution** → payoff, new equilibrium, or button

For 30-second ads: establish world (3-5s) → introduce conflict (5-10s) → payoff (10-20s) → button (20-30s). The button is the memorable last beat — the image or line that sticks.

### Goals, conflict, stakes
Every scene needs:
- **Goal**: what the character wants in this scene (visible, not internal)
- **Conflict**: what stands in the way (obstacle, antagonist, environment, self)
- **Stakes**: what happens if they fail (emotional, physical, relational)

If a scene has no goal, no conflict, and no stakes, it's padding — cut it.

### Show vs. tell
Write what the camera can see: who enters/exits, where they stand, what they
touch, how the light shifts. Never write inner thoughts. A character's fear is
shown by trembling hands, wide eyes, a step backward — not by "she felt afraid."

### Scene objectives
Every scene has ONE visible objective that advances the story. Name it in the
`beat:` field. If you can't state it in one sentence of visible action, the
scene isn't ready to storyboard.

### Emotional beats
Name the beat and the emotion it evokes in the audience:
- Wonder → reveal, push in, music swell
- Tension → hold, static shot, silence or drone
- Joy → movement, warm light, upbeat tempo
- Fear → dark, handheld, dissonant sound
- Relief → exhale, pull out, soft strings

The beat board (`beat_board.md`, Agent 1b) is where these emotion→visual mappings
get applied structurally. Each beat carries an `emotion:` field that downstream
agents use to choose shot size, camera movement, composition, pacing, and sound.

### Pacing
Event density per beat drives pacing:
- **Tender/dialogue beats**: 6-15s in a single shot, camera breathing with the action
- **Action beats**: 1.5-3s micro-shots, cuts on action, sound driving each cut
- **Reveal beats**: hold longer than comfortable, then cut on the reaction

## 2. Shot Design

For the complete vocabulary, taxonomy, and emotional mappings, see [`cinematography-bible.md`](cinematography-bible.md) (Sections A, B, and C).

### Shot sizes (the "why")
The 7 foundational shot sizes (`extreme_wide`, `wide`, `full`, `medium`, `medium_closeup`, `closeup`, `extreme_closeup`) balance spatial context against emotional proximity. Closeups (`CU`/`MCU`) drive character acting and dialogic intensity; wide shots (`WS`/`EWS`) anchor geography, scale, and environmental isolation.

### Camera angles (the "why")
The 12 primary camera angles (`eye_level`, `low_angle`, `high_angle`, `birds_eye`, `worms_eye`, `dutch_angle`, `over_the_shoulder`, `pov`, `three_quarter_front`, `three_quarter_back`, `profile`, `top_down`) establish psychological dynamics. Low angles build awe and authority; high angles evoke helplessness; three-quarter angles give depth and dimensional volume.

### Camera positions
Front, side/profile, 3/4 front, 3/4 back, behind, top-down. Vary position across shots in a generation — avoid monotonous front-facing shots. The 3/4 front angle is the workhorse of character animation: it shows face AND body depth simultaneously.

### Focus as storytelling (the "why")
Focus is not just an optical property; it is internal editing within a single continuous take. For the vocabulary, see [`cinematography-bible.md`](cinematography-bible.md) Section C-bis:
- **`shallow_focus`**: The cinematic default for character intimacy. Throwing the background into gentle blur strips away visual distractions and forces viewer empathy into micro-acting (eyes, brows, mouth).
- **`deep_focus`**: Keeps foreground, midground, and background all in sharp register. Essential for ensemble tension and environmental storytelling where foreground action and background consequences play simultaneously.
- **`rack_focus`**: Shifts optical focus between narrative planes mid-take without cutting. The primary visual vehicle for cause-and-effect reveals: starting on an object or speaker in the foreground, then shifting focus to a reacting character in the background.
- **`soft_focus`**: Diffuses contrast for dreamlike reverie, nostalgic flashback, hallucination, or psychological detachment.

---


## 3. Camera Movement (the "why")

The director's principle: **the camera moves because the story demands it — not because movement is cool.**

For the complete catalog of 22 native camera movements, composite moves (Dolly Zoom, Crane, Orbit, Steadicam), and the mandatory 3D formula (`[Motion Type] with [amplitude] at [speed]`), see [`cinematography-bible.md`](cinematography-bible.md) Section D.

- **Push In**: Realization, growing emotion, intimacy — "We're getting closer to the truth"
- **Pull Out**: Revelation, context, withdrawal — "Now we see the whole picture" or "leaving them behind"
- **Tracking**: Following action, building momentum — "We're moving with them"
- **Arc Shot**: Revealing, circling, shifting perspective — "Let's look at this from another angle"
- **Crane Up/Down**: Grandeur, liberation, scale change — "The world opens up"
- **Whip Pan**: Energy, urgency, transition — "Quick — look over there!"
- **Static Shot**: Stillness, observation, letting action breathe — "Watch this. Don't look away."
- **Handheld / Shake**: Immediacy, chaos, documentary reality — "We're really here, it's really happening"

**When NOT to move:** Static shots let the action carry the frame. If the character's performance is the point, hold still. A push-in during a tender moment says "this matters"; a push-in during every moment says nothing.

**Equipment feel:** When selecting camera movements, consider the physical rig feel (see [`cinematography-bible.md`](cinematography-bible.md) Section D Equipment Feel Cheatsheet). A `Shake Slightly` conveys handheld documentary urgency and lived-in tension; a `Tracking Shot with smooth Push In at slow speed` evokes the gliding elegance of a Steadicam; a `Static Shot` locks the camera onto sturdy sticks to let performances breathe.

---

## 4. Composition

Composition is how you arrange everything inside the frame. In animation you control literally everything — so there's no excuse for accidental composition.

For the complete 12 composition rules (`rule_of_thirds`, `center`, `symmetry`, `leading_lines`, `negative_space`, `depth`, `silhouette`, `frame_within_frame`, `visual_hierarchy`, `headroom`, `look_room`, `screen_direction`), see [`cinematography-bible.md`](cinematography-bible.md) Section H.

**One clear subject per frame.** If the audience doesn't know where to look, the composition has failed. Use `visual_hierarchy` to make the subject unmissable — lighting, color contrast, leading lines, or scale.

---

## 5. Editing & Cuts (motivated-cut thinking)

### The question→answer pattern
> Character looks toward the sky.
> CUT.
> We see a huge airplane.

The first shot creates a question ("what are they looking at?"). The second
shot answers it. That's a motivated cut.

### The motivated-cut checklist
Before cutting, ask: Does this cut…
- Answer a question the previous shot raised?
- Reveal new information (subject, space, state, viewpoint, time)?
- Change the emotional register?
- Move the story forward?

If none of these, **don't cut** — use camera motion instead.

### Cut types beyond the 8-value grammar
The skill's 8 transitions cover the most common cases. For special situations:
- **Jump cut**: time compression within the same framing (rare in animation)
- **Smash cut**: extreme contrast — quiet to loud, calm to chaos
- **Cross-cutting**: parallel action (two storylines intercut) — plan as alternating generations
- **Cutaway**: context shot away from the main action
- **Insert**: detail shot of an object or action

### Transition types
- **Fade**: time passage, scene end — slow, deliberate
- **Dissolve**: memory, transition, dream — two images blending
- **Wipe**: energy, style — one image pushes another off
- **Object wipe**: a foreground object crosses the frame and hides the cut

### When NOT to cut
If only the framing or angle changes — push in, pan, arc — the camera can do
that in one shot. Cutting for a framing change is a wasted cut. The validator
errors on same-characters + same-shot_size + hard_cut for exactly this reason.

---

## 6. Animation Direction

Animation is not "the character turns around." Animation is a sequence of
micro-beats: **hear sound → freeze → eyes move → head turns → body follows →
reaction.** Those little beats are what make animation feel alive.

For the exhaustive anatomical acting vocabulary (18 eye reactions, 10 brow reactions, 16 mouth/jaw reactions, 12 head reactions, 18 body postures) and worked micro-beat sequences, see [`cinematography-bible.md`](cinematography-bible.md) Sections F & G.

Write `action:` as a sequence of comma-separated micro-beats in time order,
not a single verb.

### Animation principles (quick reference)
- **Anticipation**: wind-up before action (pull back before a throw, crouch before a jump)
- **Follow-through**: continue after the action stops (hair swings after the head turns)
- **Squash & stretch**: impact deformation (a bouncing ball squashes on contact)
- **Timing**: weight + speed — heavy things move slowly, light things move fast
- **Spacing**: acceleration/deceleration — ease in, ease out, never linear
- **Exaggeration**: push poses beyond realism for emotional clarity
- **Weight**: the audience feels mass through how something moves

### Character acting
- **Eyes lead, then brows, then mouth** — the face reacts in sequence, not all at once
- **Body language**: posture, gesture, lean — the body tells the story the face doesn't
- **Reaction beats**: the timing between stimulus and response IS the performance

### Beat breakdown in `action:`
Instead of: `action: The baby turns around.`
Write: `action: The baby freezes, eyes dart to the sound, head turns, body follows, mouth drops open.`

### Secondary motion
Cloth, hair, ears, tail — follow the primary action with a delay. Secondary
motion sells the weight and reality of the movement.


## 7. Sound + Editing

Sound can make an average animation feel 10× better. A character punching
someone isn't just IMAGE → punch. It's: **anticipation → movement → impact →
sound → reaction → silence/music hit.**

### Sound layers
- **Foley**: footsteps, fabric, props — the texture of physical existence
- **Ambient sound**: room tone, wind, distant traffic — the space around the action
- **Impact sounds**: punches, door slams, cracks — the punctuation of action
- **Music**: diegetic (radio, singing — characters hear it) vs non-diegetic (score — only the audience hears it)
- **Silence**: the pause before a reveal, the breath after impact — silence is a sound choice, not the absence of one

### Sound bridges
Audio from the next shot begins before the visual cut (L-cut: picture changes
first, audio lags; J-cut: audio arrives first, picture follows). The skill's
`audio_led` transition type implements the J-cut.

### Music synchronization
The pattern: **anticipation → movement → impact → sound → reaction → silence/music hit.**
The music hit lands ON the impact or the reaction, not randomly. Time it to
the shot's emotional peak.

### Directing sound in the skill
- `audio:` field per shot → foley, ambient, impact, dialogue delivery
- `overall_soundscape:` section → diegetic ambience across the full generation
- `non_diegetic_music:` section → score (instrumentation, tempo, rhythm, dynamics only)

## 8. Spatial Geography (2.5D continuity)

The spatial plan (`spatial_plan_sN.md`, authored by Agent 3a) encodes the
scene's geography so independently rendered MiniMax H3 generations maintain
character-to-landmark continuity. It uses a **2.5D** coordinate system —
image-space X/Y plus landmark-relative Z — not a 3D engine.

### Coordinate system

| Axis | Range / unit | Meaning |
|---|---|---|
| X | `0–3840` px | Horizontal position in the 3840×2160 location panorama |
| Y | `0–2160` px | Vertical position in the 3840×2160 location panorama |
| Z | `≥ 0` m | Approximate metres from the anchor landmark |

- `X=0` and `X=3840` are adjacent (panorama wraps horizontally).
- Z is director-declared approximate depth, not measured geometry.
- Coordinates are for validation and inter-agent communication. Agent 4
  translates them into natural-language staging language for GPT Image 2.
- Agent 5 translates them into natural-language placement for MiniMax H3.

### Landmarks and zones

- A **landmark** is a fixed, recognizable scene element (a lamp, a door, a
  tree) with a `panorama_xy` position. The `primary_anchor` is the main
  reference landmark for distance/depth.
- A **zone** is a named region of the panorama with X/Y/Z ranges, a
  `relative_to` landmark, and a `distance_from_anchor_m`. Zones own
  non-overlapping horizontal slices of the panorama.

### Per-generation spatial state

Each normal story generation declares:
- `location_reference: attach | omit` — whether the location panorama is
  attached (`g1` always attaches; later generations attach only when
  re-establishing geography).
- `generation_geography` — one-line wide staging description that seeds the
  deterministic spatial continuity block materialized into the sheet prompt.
  (Legacy `anchor_view` is accepted as an alias.)
- `start_positions` / `end_positions` — where each character begins and ends.
- `movement_constraints` — `fixed_at`, `approach`, `retreat`, `never_enter`.

### Per-shot spatial state

Each shot declares:
- `on_screen_positions` — character positions with optional depth suffix.
- `camera_zone` — which zone the camera is in.
- `camera_facing` — `toward_<landmark>`, `away_from_<landmark>`, or
  `along_<axis>`.
- `camera_zoom` — one of `extreme_wide`, `wide`, `full`, `medium`,
  `medium_closeup`, `closeup`, `extreme_closeup`.
- `character_facing` — per-character body direction
  (`toward_<landmark>`, `away_from_<landmark>`, `toward_camera`,
  `away_from_camera`, `profile_left`, `profile_right`).
- `visible_landmarks` — which landmarks MUST appear. `[]` means the landmark
  must NOT appear in that panel.

### Spatial continuity block (deterministic)

No paid spatial anchor image is generated. Instead, `build_images.py`
deterministically materializes a `SPATIAL CONTINUITY LOCK` text block into
each normal storyboard-sheet prompt before the paid image call. The block
translates the spatial plan's structured fields (positions, camera, facing,
zoom, landmarks, movement) into panel-scoped natural-language staging
instructions. This avoids the identity drift that a separately generated
anchor image can introduce.

### Reference ordering (identity-first)

When a spatial plan exists, storyboard sheet references are ordered:
1. Previous sheet (cross-generation continuity) — skipped for `g1`.
2. Location panorama (conditional — `g1` or `location_reference: attach`)
3. Character sheets (identity retexture)
4. Named extras (`ref_images:` line)

### Spatial QA (Agent 7)

After sheets are generated, Agent 7 inspects each sheet against the spatial
plan and writes `spatial_qa_report.md` with PASS/WARN entries. WARN is
non-blocking — GATE 1 is not blocked by warnings. The user or agent may
regenerate a warned sheet.

### Limitations

This is a 2.5D constraint system, not a 3D engine. It does not perform:
- Camera-matrix math or perspective reprojection
- True 3D occlusion reasoning
- Pixel compositing or masking
- Deterministic layout solving

The coordinates are a communication and validation tool. GPT Image 2 and
MiniMax H3 receive natural-language translations, not raw pixel constraints.
