# LTX 2.3 Director Bible (story-maker)

Single source of truth for LTX 2.3 I2V planning and motion prompting. Condensed from [LTX I2V guide](https://docs.ltx.video/open-source-model/usage-guides/image-to-video), [Prompting guide](https://docs.ltx.video/api-documentation/implementation-guides/prompting-guide), [Models / fal duration enums](https://fal.ai/models/fal-ai/ltx-2.3/image-to-video/api), and community I2V practice (physics-not-emotion, one motion idea, micro-actions).

## Research notes (I2V prompting)

**Official / API**

- I2V prompts describe **what happens next** (motion, camera, audio). The start image already provides appearance and composition — do not restate them.
- **Pro** durations: **6, 8, 10** seconds (primary). **Fast** may allow 12–20 only at 1080p @ 25fps; do not make those the default.
- Pipeline default clip length: **8** seconds.

**Community (aligned with official)**

- Describe **physics / observable action**, not abstract emotion.
- **Camera filmmaking terms** beat style adjectives (`dolly in`, `tracking`, `static locked-off`).
- Break complex motion into **ordered micro-actions** inside one primary idea.
- Keep **one subject focus, one primary motion idea, one camera behavior** — do not write a full competing scene script.

**Tension resolved (detail vs overload)**

- Freeze usually comes from **vague / idle / mood-only** text, not from too many *physical micro-beats*.
- Prefer **dense timed physical beats within one arc** over short vague lines.
- Avoid **extra story turns, style stacks, and appearance re-description** (that is the bad kind of length).

## One clip = one beat

- Each LTX generation is **one continuous clip** with native audio.
- Plan **one primary action arc** per shot. Prefer **fewer longer shots** over many short fragments.
- **reel_v2:** storyboard panels are coverage cards; LTX duration lives on **`video_shots`** (panels ≠ clips).
- Target **18–28 shots** for a ~5 min film (scene-first planning).

## Image-to-video prompt rules

The still image is the visual anchor. The LTX motion prompt describes **what changes** after that still.

| Include | Avoid |
|---------|-------|
| Motion and physical action (jaw, breath, hands, fabric, wind) | Character appearance, wardrobe, hair restated |
| Camera movement (filmmaking terms) | Re-describing the environment layout |
| Dialogue in quotes, music, SFX, ambience | Contradicting the still image |
| Role + position referents ("the child", "the figure on the left") | Character names (LTX cannot bind names to pixels) |
| Present tense, single flowing paragraph | "First frame", "last frame", FFLF language |
| Sequential micro-beats inside one primary idea | Multiple unrelated major story turns |

### Anti-freeze (mandatory)

- Every clip needs **continuous visible change** for the full duration: primary action + face/hands/prop follow-through + environment micro-motion (breath, fabric, particles, light flicker, leaves, steam).
- Forbid vague one-liners and idle language that produce Ken-Burns freeze (`holds still`, `rests`, mood-only adjectives with no body change).
- Use temporal markers: `over the first two seconds…`, `then…`, `by the midpoint…`, `in the final seconds…`.

### Dialogue = static camera

For `ltx_shot_type: dialogue`, default **static / locked-off** camera. LTX native audio carries the performance; animate lips, expression, and **active gestures** (lean, reach, react) — not a frozen portrait. Prefer **8 or 10s** for natural line delivery (optional longer only if splitting is worse).

### Required paragraph structure (vision motion prompter)

1. **Open:** `A cinematic scene of ...` — brief role + setting anchor of what is **already visible** (not full appearance re-description).
2. **Sequential motion beats** — ordered physical micro-actions matching `duration_seconds` and `frame_strategy`.
3. **Camera** — movement from `camera_intent` (static for dialogue only).
4. **Audio** — dialogue in quotes, music, SFX, ambience.
5. **Closing quality line** — pace-aware (see vision motion prompter):
   - `slow`: `Deliberate emotional animation. Soft natural motion.`
   - `medium`: `Natural character animation. Expressive animated motion.`
   - `fast`: `Snappy energetic animation. Quick dynamic motion.`

Do **not** use `Smooth cinematic motion` — it causes slow Ken-Burns drift on every clip.

### Pace and energy

Director assigns `pace: slow | medium | fast` per shot. Motion prompts must match — fast beats get snappy verbs; slow beats get deliberate ones. Every clip needs visible state change, not idle holding.

**Multi-character:** one primary actor per clip; use spatial labels, not names.

### Prompt density by duration (primary band)

| Duration | Sentences | Beats |
|----------|-----------|-------|
| **6s** | ~6–8 | opener + **3** timed motion beats + camera + audio + quality line |
| **8s** | ~7–9 | opener + **3–4** timed motion beats + camera + audio + quality line |
| **10s** | ~8–11 | opener + **4–5** timed motion beats + camera + audio + quality line |
| Optional 3–5s | scale down | never fewer than **2** strong physical beats |
| Optional 11–15s | scale up | still **one** primary idea; prefer split if multiple major actions |

## Shot duration (director / video_shots)

**Primary (preferred):** `{9, 10, 12, 15}` — default **10**. **Minimum 9s** so start→end / multi-guide landings are not rushed. Max **15s** per Director unit when Prompt Relay beats justify it.
Snap planning values with `snap_ltx_duration` toward the primary set; clamp into `9–15`.

| Case | Duration |
|------|----------|
| Default | **10** |
| Dense continuous action | **9–10** |
| Slow / establishing / multi-beat | **12** |
| Long Prompt Relay arc | **15** |
| Multi major actions / hard cut / subject change | **Split** into separate units |

| Complexity | Prefer | Notes |
|------------|--------|-------|
| simple | 6–8 | single gesture, reaction, insert |
| moderate | 8 | standard action or short dialogue |
| complex | split → multiple 6–10 | optional 11–15 only if one continuous idea |

Compute from content when possible:
- **Dialogue:** ~2.5 words/sec + breath padding; prefer 8 or 10.
- **Action:** one primary arc; fill with micro-beats, then choose 6/8/10.

### reel_v2 panels vs clips

- Panel `duration_seconds` = editorial/board rhythm only.
- Scene `duration_budget_seconds` + `video_shots[].duration_seconds` = LTX wall-clock.
- A 10-panel sheet-scene often budgets **~24–32s** (≈ 3–4 clips at 6/8/10), scaled to target runtime.
- **Cast-coherent groups:** each `video_shot` is anchored on a start still. Later panels may join only when their `characters_present` ⊆ the anchor panel's cast. Empty establishing panels are solo (or empty-only) clips — never invent named heroes into an empty plate in one I2V. Split when cast grows; pipeline normalize enforces this.

## Assistant-director render knobs (storyboard director path)

Per clip the AD picks enums; code maps to ComfyUI floats. Default output resolution is **1920×1088** (`VIDEO_WIDTH` / `VIDEO_HEIGHT`).

**Renderer:** with `STORY_MAKER_VIDEO_BACKEND=director_v2`, clips render through **LTX Director** (guide keyframes + Prompt Relay). Legacy `templates` backend still accepts a flat `motion_prompt`.

Director working resolution is **1280×704** (`DIRECTOR_VIDEO_WIDTH` / `DIRECTOR_VIDEO_HEIGHT`) — 1280×720 is invalid under the latent `divisible_by=32` grid. Template backends may still use `VIDEO_WIDTH`/`VIDEO_HEIGHT` (default 1920×1088).

### Director prompt layers (AD output)

| Field | Role |
|-------|------|
| `scene_global_prompt` / `global_prompt` | Look / lighting / location context |
| `motion_segments[]` | Timed Prompt Relay beats (`start_ratio`/`end_ratio`/`prompt`) |
| `guide_frames[]` | Still guides with `placement`: `start` / `middle` / `end` |
| `motion_prompt` | Flat join of beats — legacy fallback |
| `render_units[]` | Preferred scene-level AD output (one unit = one Director job) |

Prefer **2–5** motion segments on 9–15s units; each distinct action ≈ **≥2s**. Multi-guide units may place a middle panel as a waypoint; end guides settle the destination composition.

AD owns **`duration_total_seconds`** and every unit’s `duration_seconds`. Scene-paper timing is editorial context only.

### Free-form `beats[]` timeline (alternative to `motion_segments`/`guide_frames`)

The ComfyUI Director timeline is a single ordered list of `image` (guide) and `text` (Prompt Relay) segments with arbitrary frame offsets — `motion_segments`/`guide_frames` is just one fixed-shape way of populating it (guides pinned at ratio 0.0/mid/1.0, text spanning the whole 0.0→1.0 range). `beats[]` exposes the underlying free-form shape directly:

- **Keyframes are instants, not durations.** A `guide` beat is a still pinned wherever it falls in the ordered list (optionally held for a short `anchor_seconds`, default 0). Never express "hold this still for N seconds" as a guide — that is what produces Ken-Burns freeze. Duration belongs on `text` beats.
- **Budget = sum of `text` beat durations.** `duration_budget_seconds` (≤ **20s** ceiling, vs. **15s** for the classic ratio layers) is the total of the `text` beats only; guides don't consume it.
- **Leading/trailing text is allowed.** A `text` beat before the first guide is an un-anchored, T2V-style opening — weaker identity lock (no pixel guide yet), appropriate for "empty plate, subject enters" but not for a hero close-up. A `text` beat after the last/`end` guide is a valid trailing reaction beat.
- **≤4 guide beats.** Beyond that the model's remaining creative space shrinks and it defaults to unwanted scene cuts (community LTX finding). 3 guides (`start` → `bridge` → `end`) is the standard long-gap recipe (see below).
- Per-beat `guide_strength` overrides the `motion_class` default when the AD needs a specific value for that instant (e.g. a loose bridge, a hard-landing end).

Use `beats[]` when a unit needs a directed transition across a long gap, leading/trailing text, or per-beat timing control the ratio model can't express. Use the classic `motion_segments`/`guide_frames` layer for everything else — it is simpler and already well-tuned.

### Long-gap bridge recipe (fixes "random character enters" between dissimilar keyframes)

Root cause: LTX has no persistent-character concept — every subject is re-cast from the surrounding text + nearest guide each denoise. When two consecutive guide stills differ a lot (camera angle, subject scale, pose), the ratio model's un-anchored 0.5-ratio interpolation window gives the model open creative space, and it fills that space by inventing a transitional subject (a runner, an extra figure) to bridge the visual gap — this is a documented LTX FLF/multi-keyframe failure mode, not a bug in this pipeline.

Fix: never leave a long gap un-anchored and un-narrated. For any edge where the next panel's composition is a large jump from the current one:

1. Insert a **`bridge` guide** — a still genuinely *between* the two compositions (partial camera swing, mid-pose), not another extreme. This anchors the interpolation window that was previously empty.
2. Write the **transition beat** (the `text` beat spanning that window) to describe only the camera/scene move across the gap, and explicitly close the cast: *"no new people or animals enter; camera travels over empty ground"* (or scene-appropriate equivalent). This is the "additional text input that drives to the next frame" — it replaces open creative space with a directed instruction.
3. Tune strengths for the jump: bridge guide loose (~0.5–0.6, room to move through it), `end` guide high (~0.85–0.95, must land precisely on the destination composition).
4. If the gap is too large even for a bridge (or no continuous camera/action motivates crossing it), use a hard cut (`cut_before: true`) with the shared boundary still as a match-cut handoff instead — never force a 4+ panel morph across unrelated compositions.

This mirrors the `director_transition_after: continue | match_cut` authoring field — `continue` implies you've provided (or should provide) a bridge; `match_cut` is the deliberate-cut alternative.

### `motion_class` → LTX Director guide strength

| motion_class | strength | Intent |
|--------------|---------:|--------|
| talking | 0.80 | Hold face / likeness on dialogue |
| walking | 0.70 | Gentle locomotion |
| horse_riding | 0.65 | Mount motion |
| forest_exploration | 0.70 | Ambient roam |
| large_reveal | 0.60 | Wide reveal / motivated pan |
| fast_action | 0.55 | Freer motion |
| general | 0.70 | Default |

FLF last-frame guide strength stays ≥ `max(0.85, i2v_strength + 0.05)`.

### `guidance` → CFG (sampler passes)

| guidance | cfg |
|----------|----:|
| balanced | 1.0 |
| prompt_follow | 1.2 |
| strong | 1.5 |

Do not exceed **1.5** in production.

## Crowds and extras

- **`characters` roster** = named heroes only.
- **`characters_present`** = named foreground heroes in this shot.
- **`background_population`** (per scene) = ambient extras (classmates, crowd) — environment only, no char sheets, no `characters_present` entries.

### Cast-lock (every beat, either layer style)

Never name a subject in a beat's prompt that is not visible in the guide still active for that window — naming an absent character/animal is precisely how LTX gets license to invent it mid-clip. For every beat: only reference what the nearest guide actually shows; give secondary heroes already in frame an explicit status line even when they're not the focus ("father holds his walking pace, does not turn") instead of leaving them undirected; on transition/bridge beats add an explicit cast-closure line. Optionally reinforce with `locked_cast` (character/role names) and `negative_prompt` on the unit.

### Attention-to-detail vocabulary

Direct every visible element, not just the lead — an undirected element is exactly what the model fills in with an invented subject:
- **Primary hero:** ordered physical micro-actions (jaw, hands, gait, fabric).
- **Secondary heroes:** explicit state, not silence.
- **Ambient/nature (only if visible in the active guide):** bounded, single-direction motion — "one bird glides left-to-right across the upper frame and exits" beats "birds fly"; "water ripples gently in place" beats "water moves"; "leaves sway slightly in the breeze" beats "trees move".
- **Camera:** its own clause, filmmaking terms, never contradictory instructions in one clause.
- **Transitions:** every unit boundary is `continue` (bridge guide + transition beat) or a hard cut (shared boundary still, match-cut) — never an undirected morph.

## Grok still = LTX starting frame

The still must encode identity, pose, and layout. Use **animation-ready held poses** (start of a 6–8s action, not a dead end pose), **spatial placement**, and **16:9 landscape**. Mitigate Ken-Burns stillness with slight depth-of-field / film-still language (not documentary clarity).

**Story developer (upstream):** Named heroes who interact in one continuous beat must already be drawable in that beat's start frame. Prefer cut-based entrances (solo beat → shared-frame beat) over "empty plate then named hero walks in" as a single I2V moment. Consecutive continuous beats should imply drawable evolution (pose / prop / camera), not only co-presence.

**Story developer expansion:** When the author story is thin vs target duration, invent distinct non-alike scenes (setup contrast, obstacle showcase, contrast cut, hubris pause, quiet pass, reversal, payoff) — never pad with repeated walk/run on the same backdrop. Adjacent scenes must differ in landmark, action, tone, lead focus, or pace. Each scene gets a Purpose line for downstream scene paper.

### Upstream authoring (scene paper → plan → AD)

`reel_v2` scene paper owns **Director keyframes + morphs**:

- **Panels** = guide stills (`start` / `middle` / `end`).
- **`### Motion spine`** = ordered P01→P02→…→PN connecting motion (high-level scene thought for Prompt Relay).
- **`#### Bridge → Panel N+1`** = per-edge recipe (`continue` / `long_gap_bridge` / `match_cut`, cast evolution, cast-lock, Relay seeds).
- **`### Director chain sketch`** = intended multi-guide unit groupings and cut points.

Production plan stamps these into `director_motion_spine`, `director_bridge_to_next`, connecting `motion_intent`, and existing `director_*` fields. The Assistant Director owns wall-clock durations and final Prompt Relay / `beats[]` wording — fold spine and bridges into timed text and rationale, never into `global_prompt`.

### Scene staging and shot-reverse-shot geography

Before coverage, define a scene-wide geography:

- **`staging`** = one prose map of the environment **left-to-right** with fixed landmarks and the action axis.
- **`blocking`** = where each named hero stands and which way they face inside that staged space.
- Per-shot spatial fields:
  - `subject_position`
  - `facing_direction`
  - `eyeline`
  - `background_region`

These fields keep solo reverse shots coherent. If speaker A is frame-left facing screen-right with the stove wall behind, the reverse on speaker B should flip frame side/facing and show the opposite room region (window / island side), not the identical backdrop.

### 180-degree rule

Hold all dialogue / reaction coverage on one side of the scene axis unless there is an intentional axis-crossing beat. Reverse shots should preserve:

- opposite frame side
- consistent off-screen eyeline toward the partner
- matching screen direction
- non-identical reverse-side backdrop region

### Panoramic backgrounds

Scene background plates are generated at **2:1** (`2048x1024` default) as style anchors. Shot stills and LTX clips remain **16:9**.

### frame_strategy

| Strategy | Starting still | Motion |
|----------|----------------|--------|
| `empty_then_enter` | Empty plate (no entering subject) | Subject enters — **named characters only when `characters_present` is empty** |
| `at_rest_then_react` | Subject at rest | Trigger then reaction |
| `in_action_continuous` | Mid-activity hold | Motion continues |

Grok Edit reference limits (provider-aware — see `get_image_ref_limit()` in `config.py`):

| Backend | Max refs per edit |
|---------|-------------------|
| fal `xai/grok-imagine-image/edit` | 3 |
| Replicate `openai/gpt-image-2` | 13 |
| Replicate `bytedance/seedream-4` | 10 |
| Replicate `xai/grok-imagine-image` | 1 |

Override with `IMAGE_REF_LIMIT` in `.env` if needed.

## Audio

LTX generates synced audio in-prose: `"Help!" she cries`, soft ukulele enters, surf laps, thunder rumbles distant.

## What fails

- Multiple unrelated simultaneous major actions
- Appearance re-description (conflicts with start still)
- Abstract mood-only prompts with no physical motion
- Vague short prompts that leave the model with nothing to animate (freeze / Ken-Burns)
- Overloading one clip with 4+ major story turns (split instead)
- Camera movement on dialogue shots (use static camera, but animate faces and gestures)
- Uniform `pace: slow` across a whole scene — flatten story rhythm
- Identical framing on consecutive shots (same wide master repeated)
- Closing line `Smooth cinematic motion` on every clip
- Treating 1–3s micro-cuts as first-class Pro LTX durations
- Chaining 4+ visually dissimilar panels into one continuous unit with no bridge guide (invites invented transitional subjects — use the long-gap bridge recipe or a hard cut instead)
- Naming a character/animal/crowd in a beat that isn't visible in the active guide still (cast-lock violation)
- Holding a guide still for a long duration to fake a static shot (use a short `anchor_seconds`, not a text-free gap — long unguided gaps invite invention, not stillness)

## Long-form films

Target runtime (e.g. 5 min) = **many shots + ffmpeg concat**. Per-scene budgets from narrative outline must reconcile with shot / video_shot sums (±15%).
