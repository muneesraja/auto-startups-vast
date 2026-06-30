# LTX 2.3 Director Bible (story-maker)

Condensed from [LTX I2V guide](https://docs.ltx.video/open-source-model/usage-guides/image-to-video), [Prompting guide](https://docs.ltx.video/api-documentation/implementation-guides/prompting-guide), and [Models API](https://docs.ltx.video/models).

## One clip = one beat

- Each LTX generation is **one continuous clip** with native audio.
- Plan **one primary action arc** per shot. Split complex story beats into multiple shots.
- Prefer **more shorter shots** over fewer overloaded long shots.

## Image-to-video prompt rules

The Grok still image is the visual anchor. The LTX motion prompt must describe **what happens next**:

| Include | Avoid |
|---------|-------|
| Motion and physical action | Character appearance, wardrobe, hair |
| Camera movement (filmmaking terms) | Re-describing the environment layout |
| Dialogue in quotes, music, SFX, ambience | Contradicting the still image |
| Role + position referents ("the child", "the figure on the left") | Character names (LTX cannot bind names to pixels) |
| Present tense, single flowing paragraph | "First frame", "last frame", FFLF language |
| Open by continuing from the held still | Describing the scene as if no image exists |

**Paragraph order:** (1) continue from still → (2) primary motion → (3) camera → (4) audio → (5) settling end state.

**Multi-character:** one primary actor per clip; use spatial labels, not names.

**Prompt length:** 4–8 sentences scaled to duration:

| Duration | Sentences | Beats |
|----------|-----------|-------|
| 4–6s | 3–4 | 1 action + camera + audio |
| 7–10s | 4–6 | 2 beats |
| 11–15s | 6–8 | 2–3 beats max |

## Shot duration (director)

Director may assign **4–15 seconds** per shot:

| Complexity | Duration | Example |
|------------|----------|---------|
| simple | 4–6s | picks up shell, single reaction |
| moderate | 7–10s | chase + splash |
| complex | 11–15s | one camera beat with 2–3 micro-beats (split if two major actions) |

API Fast supports up to **20s**; local ComfyUI snaps frames to **8n+1** at 25fps.

## Grok still = LTX starting frame

The Grok `image_prompt` must encode identity, pose, and layout — LTX will not re-establish them. Use **animation-ready held poses** and **spatial placement** for multi-character shots.


Use concrete terms: static wide, slow dolly in, handheld tracking left, gentle push-in, crane up, over-the-shoulder.

## Audio

LTX generates synced audio in-prose: `"Help!" she cries`, soft ukulele enters, surf laps, thunder rumbles distant.

## What fails

- Multiple unrelated simultaneous actions
- Appearance re-description (conflicts with Grok still)
- Abstract mood-only prompts with no physical motion
- Overloading 15s with 4+ major story turns

## Long-form films

Target runtime (e.g. 5 min) = **many shots + ffmpeg concat**. Expand sparse stories into acts/scenes/shots until summed shot durations land near target (±15%).
