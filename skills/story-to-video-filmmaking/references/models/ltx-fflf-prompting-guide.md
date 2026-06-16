# LTX 2.3 FFLF Prompting & Parameter Guide

This guide describes how to write prompts and configure parameters for the LTX 2.3 First Frame Last Frame (FFLF) workflow. It is compiled from Fox•Fur•Essence Films' production workflows.

---

## 1. The Core Prompting Philosophy

For FFLF workflows, **do not write long, descriptive prompt chains**.
The first frame and last frame images already specify the details of the character's clothing, the background, the lighting, and the textures. Redescribing these details in the video prompt creates competing instructions for the model, leading to pixel warping and frozen animations.

Instead, write **brief, motion-only prompts** that describe the trajectory between the two frames:

* **DO:** Focus exclusively on spatial displacement, camera moves, and physical actions.
* **DO:** Describe the camera motion explicitly (e.g., "camera slowly zooms in").
* **DO:** Use structural transition tags like `"a continuous fluid shot from beginning to end"` to suppress mid-clip jump cuts.
* **DON'T:** Describe the background, character features, colors, textures, or clothing.

### Example Comparisons

❌ **Bad (Descriptive, Over-constrained):**
> *"A beautiful young princess with long blonde hair and a sparkling pink gown stands on a cobblestone road in a magical kingdom. The sky is blue and there are green trees. The camera slowly zooms in as she walks forward toward the center and holds up a small mushroom."*

✅ **Good (Motion-focused, Concise):**
> *"A continuous fluid shot — the camera slowly zooms in as she walks forward to the center of the frame and turns toward the viewer, holding up a mushroom."*

---

## 2. Keyframe reference Strengths (The Goldilocks Zone)

The LTX 2.3 FFLF guide strength controls how strictly the video generator adheres to the input keyframes versus how much creative liberty it has to animate.

Tuning this parameter is critical to avoid two extreme failure modes:

```
  0.1 ---------- 0.4 ----------------- 0.5 ====== 0.8 ---------------- 0.9 ---------- 1.0
 [   Too Creative   ]                 [ Goldilocks Zone ]             [   Too Rigid, Frozen  ]
  Ignores input frames;                Smooth transitions;             Violent jump cuts;
  mismatched character details.        High visual fidelity.           Sequence frozen in place.
```

### The Rules:
* **Goldilocks Zone (0.5 – 0.8):** Keep both `input_ref_strength` (FF) and `end_ref_strength` (LF) in this range. The default value is **0.8**.
* **Under 0.5:** Too loose. The model will invent details, leading to morphing characters and layout drift.
* **Over 0.9:** Too tight. The model cannot find a path between frames, resulting in a frozen clip or a violent jump cut on the last frame.

---

## 3. Dynamic Continuation Prompting

When writing a prompt for a `continuation` shot, the motion prompt should describe movement that **starts from where the previous shot ended**.

* Do not re-describe the starting position — the extracted tail frame of the previous video already captures this.
* Focus purely on the *next stage* of movement.
* Use connecting motion words: `"continuing the movement, the camera pans right as..."` or `"maintaining forward momentum, the character..."`.
