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

**Primary (preferred):** `{6, 8, 10}` — default **8**.  
**Optional:** `3–15` when budget math or a special beat requires it (not the default habit).  
Snap planning values with `snap_ltx_duration` toward the primary set; keep optional values only when already in `3–15`.

| Case | Duration |
|------|----------|
| Default | **8** |
| Brief action / reaction / cutaway | **6** |
| Standard continuous action | **8** |
| Slow / establishing / ambience | **10** |
| Optional edge | 3–5 or 11–15 |
| Multi major actions / subject change | **Split** into separate clips |

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

### Director prompt layers (AD output)

| Field | Role |
|-------|------|
| `global_prompt` | Look / lighting / location context (not beat-by-beat action) |
| `motion_segments[]` | Timed Prompt Relay beats (`start_ratio`/`end_ratio`/`prompt`, covering 0→1) |
| `motion_prompt` | Flat join of those beats — legacy fallback for template backend |
| `start_panel_id` / `end_panel_id` | Guide images (I2V start; FLF start + end-frame) |

Prefer **2–4** motion segments on 6–10s clips; each distinct action ≈ **≥2s**. FLF last beat should settle toward the end panel composition.

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

## Grok still = LTX starting frame

The still must encode identity, pose, and layout. Use **animation-ready held poses** (start of a 6–8s action, not a dead end pose), **spatial placement**, and **16:9 landscape**. Mitigate Ken-Burns stillness with slight depth-of-field / film-still language (not documentary clarity).

**Story developer (upstream):** Named heroes who interact in one continuous beat must already be drawable in that beat's start frame. Prefer cut-based entrances (solo beat → shared-frame beat) over "empty plate then named hero walks in" as a single I2V moment.

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

## Long-form films

Target runtime (e.g. 5 min) = **many shots + ffmpeg concat**. Per-scene budgets from narrative outline must reconcile with shot / video_shot sums (±15%).
