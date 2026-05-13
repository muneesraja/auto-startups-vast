# LTX 2.3 — Image-to-Video Prompting Guide

> This reference document contains everything Hermes needs to write high-quality LTX 2.3 Image-to-Video (I2V) prompts. **Read this before writing any `scene_NNN.txt` file.**

---

## The Golden Rule

> **Never describe what's already visible in the image.**

The input image already defines the subject, setting, composition, and lighting. Your prompt defines the **temporal evolution** — what happens next. Every word spent re-describing static elements is a word wasted, and can create "prompt-conditioning tension" where the model receives conflicting information.

### What This Means in Practice

| ❌ Wastes tokens (describes statics) | ✅ Adds value (describes motion/change) |
|---|---|
| "A brown rabbit stands in a forest clearing" | "The rabbit throws his head back in laughter, ears bouncing" |
| "A tortoise with a green shell and blue bandana" | "The tortoise lifts his head slowly, extending one paw forward" |
| "Sunset over mountains, beautiful golden light" | "The last sliver of sun dips below the ridge as shadows lengthen" |
| "A woman in a red coat standing in the rain, cinematic, 4k" | "She turns her head to the left as rain intensifies, creating ripples in puddles" |

---

## Prompt Structure

Write a **single flowing paragraph** of **4–8 sentences** (under **200 words**). Follow this order:

### 1. Main Action (Subject → What They Do)
Start with the core movement. Use **specific, present-tense verbs**.

- ✅ "Rabbit throws his head back, paw pointing forward"
- ✅ "She shifts her weight and makes direct eye contact with the camera"
- ❌ "The character is in motion" (too vague)
- ❌ "Dynamic action scene" (means nothing to the model)

### 2. Environmental Dynamics (How the World Changes)
Describe how light, weather, atmosphere shift during the clip.

- ✅ "Warm light from the rising sun filters through fog, catching ripples in the water"
- ✅ "Dappled sunlight shifts through the oak leaves as a breeze stirs the wildflowers"
- ❌ "Beautiful lighting" (not actionable)

### 3. Camera Movement (How the Frame Moves)
Specify camera behavior **relative to the subject**. This is critical — without it, LTX may produce a static "Ken Burns" zoom or no movement at all.

- ✅ "The camera slowly pushes in from a medium wide to a close-up"
- ✅ "Camera tracks alongside the subject at a low angle"
- ❌ "Cinematic camera work" (meaningless)

---

## Camera Motion Keywords

LTX 2.3 interprets standard cinematography terms. Use these:

### Movement
| Keyword | Effect |
|---------|--------|
| `slow dolly-in` / `camera pushes in` | Gradual move toward subject |
| `camera pulls back` / `dolly out` / `zooms out` | Moving away from subject |
| `pan left` / `pan right` | Horizontal camera rotation |
| `pan across` | Sweeping horizontal movement |
| `tilt up` / `tilt down` | Vertical camera rotation |
| `tracking shot` / `camera tracks alongside` | Following subject laterally |
| `orbit` / `circles around` | Rotating around subject |
| `handheld` / `handheld shake` | Realistic camera instability |
| `static frame` / `camera holds steady` | No camera movement |
| `crane up` / `crane down` | Vertical elevation change |

### Framing / Angle
| Keyword | Effect |
|---------|--------|
| `close-up` / `extreme close-up` | Tight on face/detail |
| `medium shot` / `medium close-up` | Waist-up or chest-up |
| `wide shot` / `establishing shot` | Full scene view |
| `low angle` / `worm's eye` | Camera below subject, looking up |
| `high angle` / `bird's eye` | Camera above subject, looking down |
| `over-the-shoulder` | From behind one subject toward another |
| `overhead` / `top-down` | Directly above |

---

## Motion Intensity Modifiers

Control the speed and energy of movement with adjectives:

| Modifier | Intensity |
|----------|-----------|
| `subtle` / `barely perceptible` | Minimal |
| `gentle` / `soft` | Light |
| `gradual` / `steady` | Medium-slow |
| `rhythmic` / `even` | Consistent pace |
| `brisk` / `quick` | Medium-fast |
| `rapid` / `sharp` | Fast |
| `explosive` / `sudden` | Maximum impact |

**Example:** "The camera performs a *gentle* orbit" vs "The camera *rapidly* tracks alongside"

---

## Physical Cues Over Emotional Labels

LTX 2.3 cannot interpret abstract emotions. Always translate emotions into **observable physical actions**.

| ❌ Emotional Label | ✅ Physical Description |
|---|---|
| "looks sad" | "lowers gaze, shoulders slump slightly" |
| "is happy" | "corners of mouth lift, eyes brighten, chin rises" |
| "feels scared" | "pupils widen, takes a step backward, hands tremble" |
| "is angry" | "jaw clenches, nostrils flare, fists tighten at sides" |
| "feels determined" | "eyes narrow, chin lifts, posture straightens" |
| "is surprised" | "eyebrows shoot up, mouth opens slightly, head tilts back" |
| "feels nervous" | "fingers fidget, gaze darts sideways, weight shifts foot to foot" |

---

## What to Avoid

### ❌ Never Do This

1. **Re-describe static elements** — The image already shows them. Don't waste tokens.

2. **Multiple camera setups / jump cuts** — Describe ONE continuous shot. Phrases like "then the camera cuts to..." or "scene changes to..." create incoherent output.

3. **Too many actions in 3-5 seconds** — Trying to cram walking + turning + speaking + picking something up will produce jerky, warped motion. Keep it simple.

4. **Vague quality tags** — Words like "cinematic", "4k", "high quality", "masterpiece", "amazing" do nothing. Describe the actual lighting, lens, or motion instead.

5. **Negative prompts** — LTX 2.3 is not optimized for negative prompting. Focus entirely on positive, descriptive language about what you want to see.

6. **Text/signage in motion** — The model struggles with rendering readable text. If your scene has a sign, don't describe the text changing.

7. **Abstract or flowery language** — "A symphony of colors dances across the canvas of the sky" → Instead: "Warm orange light spreads across the horizon as clouds drift slowly left."

8. **Emotional labels without physical cues** — "The character is sad" means nothing visually. See the Physical Cues table above.

---

## Complete Prompt Examples

### Example 1: Character Action (Medium Shot)
**Scene:** Rabbit laughing at Tortoise in a forest clearing

```
Rabbit throws his head back in exaggerated laughter, ears bouncing with each 
chuckle as his paw points mockingly forward. Tortoise slowly lifts his head, 
expression shifting from patience to resolve, and extends one small paw in a 
steady gesture of challenge. The dappled sunlight shifts through the oak 
leaves above as a gentle breeze stirs the wildflowers at their feet. The 
camera holds steady at eye level in a medium shot, capturing the size 
contrast between the two characters.
```

### Example 2: Environmental + Camera Movement (Wide Shot)
**Scene:** A race starting with a crowd

```
Fox swings the checkered flag high overhead in one decisive motion as dust 
kicks up from the dirt path. A blur of brown fur streaks forward from the 
starting line while a small green figure takes one deliberate step. The crowd 
of animals on the sidelines erupts with raised paws and fluttering wings. The 
camera tracks slowly right along the race path at a low angle, following the 
initial burst of movement as morning light catches the rising dust particles.
```

### Example 3: Subtle Motion (Close-Up)
**Scene:** Rabbit sleeping under a tree

```
The chest rises and falls in slow, deep breaths. One ear twitches lazily, 
then settles back against the tree bark. A faint smirk lingers on the face. 
Above, leaves rustle gently in a warm breeze, casting shifting shadow 
patterns across the sleeping figure. The camera performs a barely perceptible 
slow dolly-in, gradually tightening from a medium close-up to a close-up 
over the duration of the clip.
```

### Example 4: Triumph Moment (Wide → Medium)
**Scene:** Tortoise crossing the finish line

```
One small foot crosses the painted finish mark as the banner overhead ripples 
in the breeze. The crowd surges forward from the sidelines with raised arms 
and open mouths. In the far background, a distant figure sprints desperately 
but hopelessly toward the camera. Confetti begins to drift down through the 
warm sunset light. The camera starts wide to capture the finish line moment, 
then slowly pushes in toward the winner's humble, steady expression.
```

---

## Recommended ComfyUI Settings (for reference)

These are the recommended baseline settings when the user runs LTX 2.3 I2V in ComfyUI:

| Setting | Recommended Value |
|---------|-------------------|
| **CFG Guidance Scale** | 3.0–4.0 (start at 3.5) |
| **Sampling Steps** | 30–50 (50 for quality, 30 for speed) |
| **Sampler / Scheduler** | Euler / Normal |
| **Resolution** | Must be divisible by 32 (e.g., 768×1280 portrait, 1280×720 landscape) |
| **Frame Count** | Must be divisible by 8 + 1 (e.g., 97 frames) |
| **Frame Rate** | 24 FPS (standard) or 25 FPS |
| **Clip Duration** | 3–5 seconds for best temporal consistency |

### Tips for ComfyUI
- **Jittery output?** Lower CFG (try 2.5–3.0)
- **Ignores prompt?** Raise CFG slightly (try 4.0–5.0)
- **Slideshow effect?** Add more specific motion verbs and camera movement to prompt
- **Drift/morphing?** Use first/last frame anchoring (see below)

---

## First/Last Frame Anchoring (Advanced)

For multi-shot sequences or maximum temporal stability:

1. **Feed starting image** at frame index 0 with strength 0.95–1.0
2. **Feed ending image** (if available) at frame index -1 with strength 0.7–0.8
3. This creates a deterministic path for intermediate frames
4. The text prompt should describe the **transition** between the two frames
5. If frames are too visually different, add a "middle frame" at 50% duration to guide interpolation

---

## LTX 2.3 Key Capabilities

- **Audio-Video Sync:** Can generate synchronized audio with video in a single pass
- **Native Portrait:** Trained with native 9:16 support (up to 1080×1920)
- **Enhanced Text Encoder:** 4x larger text connector — better prompt adherence for complex multi-element descriptions
- **Rebuilt VAE:** Better preservation of fine details (hair, facial features, edges)
- **Trainable:** Supports LoRA and IC-LoRA training for custom motion/style/likeness

---

## Quick Checklist for Writing a Prompt

Before saving a `scene_NNN.txt`, verify:

- [ ] **No static descriptions** — nothing that re-describes the visible image
- [ ] **Present tense** — all verbs are present tense ("walks" not "walked")
- [ ] **4-8 sentences** — single flowing paragraph, under 200 words
- [ ] **Specific verbs** — "throws", "tilts", "rustles", not "moves", "does", "goes"
- [ ] **Camera direction** — at least one sentence about camera movement or framing
- [ ] **Physical cues** — emotions expressed through body language, not labels
- [ ] **One continuous shot** — no scene changes or jump cuts
- [ ] **Motion focus** — what changes, not what exists
