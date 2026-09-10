# Anime/Cartoon Studio Playbook — Story Maker V4

This playbook is the production layer between story and H3 prompts. It makes
Agents 1–4 behave like a compact animation studio: director, storyboard artist,
layout artist, animation supervisor, background artist, and sound director.
It avoids named-studio imitation; every style choice must be expressed as craft.

## 1. Production target

Choose one concrete target before writing scenes:

- **2D anime**: line weight, cel shading, painted backgrounds, hold cycles,
  impact frames, speed lines, expressive eye/mouth shapes.
- **3D cartoon**: appealing silhouettes, squash and stretch, weighted contacts,
  subsurface skin, fabric motion, cinematic staging.
- **Hybrid**: clean 2D characters over dimensional 3D backgrounds, consistent
  light direction, controlled grain/halation.

Never prompt "in the style of Pixar/Disney/Ghibli". Instead specify shape,
line, material, lighting, color, timing, and motion behavior.

## 2. Character acting sheet

For each scene's `acting_beat`, define the visible performance arc:

1. **Start pose**: silhouette, weight, gaze, hand state.
2. **Anticipation**: the small physical signal before action.
3. **Action**: one dominant readable movement.
4. **Reaction**: face/body response within 0.5–1.5s.
5. **Settle**: final pose that can hand off to the next shot/generation.

H3 follows explicit sequential action better than abstract emotion. Write
"ears lift, eyes widen, body freezes, then he bolts left" instead of "he gets scared".

## 3. Layout and readability

Every scene's `layout_strategy` should answer:

- What is the first read at thumbnail size?
- Which shape or color separates the hero from the background?
- Where are foreground, midground, and background layers?
- What is the eye path from frame entry to story point?
- Is the character's silhouette readable without internal detail?

Use one `visual_motif` per scene: a shape, color, or light pattern that evolves
with emotion (cold blue enclosure → warm gold opening, circles → sharp angles).

## 4. Anime timing grammar

H3 has 5–15 seconds. Treat each generation like a tiny animation sequence:

- **Hold → burst → reaction** for action beats.
- **Hold → micro-expression → line** for dialogue beats.
- **Establish → intrusion → response** for reveals.
- **Anticipation → contact → follow-through → settle** for physical beats.

Use 3–5 shots per 15s generation by default. Dense 6+ shot montages are only for
chaos, panic, or rhythmic comedy. Do not cut when a camera move or pose change
communicates the same beat.

## 5. Scene-card contract

Agent 2 must fill the V4 scene-production fields:

- `style_target`: concrete animation craft and finish.
- `acting_beat`: start pose/emotion → action → end pose/emotion.
- `layout_strategy`: staging, eye path, silhouette, depth layers.
- `visual_motif`: recurring shape/color/light language.
- `sound_world`: recurring ambience, foley, and score texture.

These fields guide Agents 3–5. The validator rejects scenes missing them.

## 6. Storyboard sheets as layout, not illustration captions

A sheet is a production layout: each panel must be readable as camera staging.
For every panel specify camera height, lens feel, subject placement, pose,
action direction, and emotion. Keep text out of the image. Put timing and sound
only in the H3 text prompt.

## 7. H3 prompt adaptation

When Agent 5 turns the sheet into Ref2VA text:

- The style sentence names the production target, not a studio.
- Each shot names composition, subject position, action, camera motion, and sound.
- Use `<Picture 1>` as the layout/sequence anchor.
- Use `<Video 1>` for g2+ tail continuation.
- Use exact animation beats: anticipation → action → reaction → settle.
- Give every shot a diegetic sound cue; silence is a deliberate choice.
