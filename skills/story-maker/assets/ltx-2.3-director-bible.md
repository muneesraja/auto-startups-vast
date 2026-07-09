# LTX 2.3 Director Bible (story-maker)

Single source of truth for LTX 2.3 I2V planning and motion prompting. Condensed from [LTX I2V guide](https://docs.ltx.video/open-source-model/usage-guides/image-to-video), [Prompting guide](https://docs.ltx.video/api-documentation/implementation-guides/prompting-guide), and [Models API](https://docs.ltx.video/models).

## One clip = one beat

- Each LTX generation is **one continuous clip** with native audio.
- Plan **one primary action arc** per shot. Prefer **fewer longer shots** over many short fragments.
- Target **18–28 shots** for a ~5 min film (scene-first planning).

## Image-to-video prompt rules

The Grok still image is the visual anchor. The LTX motion prompt describes **what changes** after that still.

| Include | Avoid |
|---------|-------|
| Motion and physical action | Character appearance, wardrobe, hair |
| Camera movement (filmmaking terms) | Re-describing the environment layout |
| Dialogue in quotes, music, SFX, ambience | Contradicting the still image |
| Role + position referents ("the child", "the figure on the left") | Character names (LTX cannot bind names to pixels) |
| Present tense, single flowing paragraph | "First frame", "last frame", FFLF language |
| Sequential beats: "does X, then Y, then Z" | Multiple unrelated simultaneous actions |

### Dialogue = static camera

For `ltx_shot_type: dialogue`, default **static / locked-off** camera. LTX native audio carries the performance; animate lips, expression, and **active gestures** (lean, reach, react) — not a frozen portrait. Assign **8–16s** for natural line delivery.

### Required paragraph structure (vision motion prompter)

1. **Open:** `A cinematic scene of ...` — brief role + setting anchor of what is **already visible** (not full appearance re-description).
2. **Sequential motion beats** — ordered actions matching `duration_seconds` and `frame_strategy`.
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

**Prompt length:**

| Duration | Sentences | Beats |
|----------|-----------|-------|
| 5–8s | 4–5 | opener + 1–2 motion + camera/audio + quality line |
| 8–12s | 5–7 | opener + 2 motion + camera + audio + quality line |
| 13–16s | 7–10 | opener + 2–3 motion + camera + audio + quality line |

## Shot duration (director)

Director assigns **4–16 seconds** per shot, snapped to **8n+1 @ 25fps** at timeline enrich time:

| Complexity | Duration | Example |
|------------|----------|---------|
| simple | 5–8s | picks up shell, single reaction |
| moderate | 8–12s | chase + splash, short dialogue |
| complex | 12–16s | one camera beat with 2–3 micro-beats; extended dialogue |

Compute from content when possible:
- **Dialogue:** ~2.5 words/sec + 1–2s breath padding; prefer 8–16s.
- **Action:** beats x complexity constant, then snap.

## Crowds and extras

- **`characters` roster** = named heroes only.
- **`characters_present`** = named foreground heroes in this shot.
- **`background_population`** (per scene) = ambient extras (classmates, crowd) — environment only, no char sheets, no `characters_present` entries.

## Grok still = LTX starting frame

The Grok `image_prompt` must encode identity, pose, and layout. Use **animation-ready held poses**, **spatial placement**, and **16:9 landscape**. Mitigate Ken-Burns stillness with slight depth-of-field / film-still language (not documentary clarity).

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

- Multiple unrelated simultaneous actions
- Appearance re-description (conflicts with Grok still)
- Abstract mood-only prompts with no physical motion
- Overloading 16s with 4+ major story turns
- Ken-Burns / zero-motion clips (retry with stronger sequential motion)
- Camera movement on dialogue shots (use static camera, but animate faces and gestures)
- Uniform `pace: slow` across a whole scene — flatten story rhythm
- Identical framing on consecutive shots (same wide master repeated)
- Closing line `Smooth cinematic motion` on every clip

## Long-form films

Target runtime (e.g. 5 min) = **many shots + ffmpeg concat**. Per-scene budgets from narrative outline must reconcile with shot sums (±15%).
