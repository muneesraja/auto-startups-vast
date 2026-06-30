# LTX 2.3 Director Bible (story-maker)

Single source of truth for LTX 2.3 I2V planning and motion prompting. Condensed from [LTX I2V guide](https://docs.ltx.video/open-source-model/usage-guides/image-to-video), [Prompting guide](https://docs.ltx.video/api-documentation/implementation-guides/prompting-guide), and [Models API](https://docs.ltx.video/models).

## One clip = one beat

- Each LTX generation is **one continuous clip** with native audio.
- Plan **one primary action arc** per shot. Split complex story beats into multiple shots.
- Prefer **more shorter shots** over fewer overloaded long shots.

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

### Required paragraph structure (vision motion prompter)

1. **Open:** `A cinematic scene of ...` — brief role + setting anchor of what is **already visible** (not full appearance re-description).
2. **Sequential motion beats** — ordered actions matching `duration_seconds` and `frame_strategy`.
3. **Camera** — movement from `camera_intent`.
4. **Audio** — dialogue in quotes, music, SFX, ambience.
5. **Closing quality line (exact):** `Natural character animation. Smooth cinematic motion. Pixar-quality animation.`

**Multi-character:** one primary actor per clip; use spatial labels, not names.

**Prompt length:**

| Duration | Sentences | Beats |
|----------|-----------|-------|
| 4–6s | 4–5 | opener + 1–2 motion + camera/audio + quality line |
| 7–10s | 5–7 | opener + 2 motion + camera + audio + quality line |
| 11–15s | 7–9 | opener + 2–3 motion + camera + audio + quality line |

## Shot duration (director)

Director assigns **4–15 seconds** per shot, snapped to **8n+1 @ 25fps** at timeline enrich time:

| Complexity | Duration | Example |
|------------|----------|---------|
| simple | 4–6s | picks up shell, single reaction |
| moderate | 7–10s | chase + splash |
| complex | 11–15s | one camera beat with 2–3 micro-beats |

Compute from content when possible:
- **Dialogue:** ~2.5 words/sec + 1s breath padding.
- **Action:** beats x complexity constant, then snap.

## Grok still = LTX starting frame

The Grok `image_prompt` must encode identity, pose, and layout. Use **animation-ready held poses**, **spatial placement**, and **16:9 landscape**. Mitigate Ken-Burns stillness with slight depth-of-field / film-still language (not documentary clarity).

### frame_strategy

| Strategy | Starting still | Motion |
|----------|----------------|--------|
| `empty_then_enter` | Empty plate (no entering subject) | Subject enters — **named characters only when `characters_present` is empty** |
| `at_rest_then_react` | Subject at rest | Trigger then reaction |
| `in_action_continuous` | Mid-activity hold | Motion continues |

Grok Edit accepts **max 3** reference image URLs.

## Audio

LTX generates synced audio in-prose: `"Help!" she cries`, soft ukulele enters, surf laps, thunder rumbles distant.

## What fails

- Multiple unrelated simultaneous actions
- Appearance re-description (conflicts with Grok still)
- Abstract mood-only prompts with no physical motion
- Overloading 15s with 4+ major story turns
- Ken-Burns / zero-motion clips (retry with stronger sequential motion)

## Long-form films

Target runtime (e.g. 5 min) = **many shots + ffmpeg concat**. Per-scene budgets from narrative outline must reconcile with shot sums (±15%).
