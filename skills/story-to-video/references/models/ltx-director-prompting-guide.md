# LTX Director Prompting Guide

This guide describes the prompt engineering principles and timeline parameter controls optimized for the **LTX Director (LTX 2.3)** workflow.

---

## 1. Global vs Local (Segment) Prompts

LTX Director uses **Prompt Relay** to combine a persistent global environment context with precise, time-bounded local actions.

### Global Prompt (`global_prompt`)
- **Purpose**: Establishes the visual style, camera setup, scene lighting, environment details, and quality tags.
- **Inheritance**: The contents of the global prompt are automatically appended to all active segments. Do not repeat style instructions in individual segments.
- **Example**: 
  > `"Cinematic 3D Pixar animation style, warm volumetric lighting, soft pastel color palette, depth of field, high fidelity"`

### Local Prompts (Segment `text`)
- **Purpose**: Describes transient motion, character actions, expressions, and dynamic camera movements occurring within a specific time range.
- **Example**: 
  > `"A small fluffy red rabbit throws his head back in exaggerated laughter, ears bouncing up and down."`

---

## 2. Guide Keyframe Best Practices

Guide Keyframes are not just injected at frame zero. They act as **visual attractors (vector targets)**. The LTX engine diffuses motion backward and forward to smoothly converge on the keyframe's visual state at its designated time.

### Keyframe Target Layouts

| Layout Mode | Keyframe Config | Behavior |
|---|---|---|
| **Single Keyframe (Standard I2V)** | Still image at `time: 0.0` | Classical I2V behavior. Video starts exactly matching the still, then transitions into fluid motion based on text. |
| **Dual Keyframe (Scene Transition)** | Still A at `0.0`, Still B at `5.0` | Interpolation mode. Generates a seamless transition from Still A's layout to Still B's layout. |
| **Mid-Shot Keyframe** | Still at `3.0` | Pre-action generation. The model generates the motion leading up to the keyframe, hits it at 3.0s, and continues moving. |
| **Pure Text-To-Video (T2V)** | No keyframes | Generates entirely from text, sizing the canvas to `custom_width` and `custom_height`. |

### Guide Strength (`guide_strength` / `guideStrength`)
The scalar coefficient weighting determines how tightly the model adheres to the keyframe's visual structure.
- **`1.0` (Maximum Guidance)**: Rigid adherence. Use this for the starting frame (`time: 0.0`) of a scene to prevent any visual jump or drift from the still image.
- **`0.7 – 0.8` (Moderate Guidance)**: Balances keyframe layout with physics and motion. Great for mid-shot keyframes or target endings where some creative interpolation is needed.
- **`0.5` (Loose Guidance)**: Low attractor strength. The model treats the keyframe as a loose thematic guide and constructs its own composition.

---

## 3. Segment Timing Rules

### Granularity Bounding
- **Granularity Limit**: The absolute minimum segment length is **0.5 seconds**. Any timeline block narrower than 0.5s is ignored or skipped.
- **Action Density**: Do not pack multiple distinct actions into short segments. The diffusion transformer cannot resolve rapid physical changes in tight frame windows.
  - *Rule of thumb*: Allow **at least 2.0 seconds** per physical action or camera transition.

### Temporal Prompt Relay
- The local prompt for a segment influences cross-attention *only* during the designated frame range (e.g., from `start` to `end`).
- This creates clean temporal bounds:
  - **Segment 1 (0.0s – 2.5s)**: `Camera pans right slowly`
  - **Segment 2 (2.5s – 5.0s)**: `Character waves and smiles`
  - The camera pan stops and the character action begins exactly at the boundary.

---

## 4. Syntax & Subject Blocking

When drafting movement prompts, adhere to these guidelines for high-quality motion:
1. **Present Tense**: Write in active, present tense (e.g., `"walks"`, `"turns"`, `"speaks"` rather than `"will walk"` or `"having turned"`).
2. **Physical Verbs**: Use descriptive verbs indicating physical direction (e.g., `"bounces up"`, `"reaches forward"`, `"bows slowly"`).
3. **Camera Coordinates**: Define camera tracks alongside subject motion (e.g., `"subject runs forward while the camera tracks backward in a smooth dolly motion"`).
4. **Dialogue Articulation**: For speech-driven segments, explicitly prompt the mechanics of speaking:
   > `"The character's mouth opens and closes in natural articulation matching the vocal track, showing jaw movement and teeth."`

---

## 5. Two-Stage Pipeline Parameters

The template is configured for a **two-pass upscale stack** to produce high-resolution, sharp results without tearing or blurring.

```
Pass 1: Low-res Latent Generation (640x352 equivalent)
        ↓  (BasicScheduler: 8 steps, Denoise 1.0)
Pass 2: Latent Upscale (2.0x spatial scale)
        ↓  (BasicScheduler: 4 steps, Denoise 0.42)
Output: Full resolution (1280x704)
```

Adjust the following overrides in the `overrides` dict if you need to optimize speed vs. quality:

| Override Key | Default | Use Case |
|---|---|---|
| `steps_pass1` | `8` | Increase to `12` for complex motion trajectories. |
| `steps_pass2` | `4` | Increase to `6` to enhance fine details (fur, fabric, text). |
| `denoise_pass2` | `0.42` | Lower (e.g., `0.35`) if upscaling introduces artifacts. Raise (e.g., `0.50`) if upscale looks too blurry. |
| `lora_strength` | `0.5` | Model strength for the distilled LoRA. Keep at `0.5` for balanced motion speed and quality. |
