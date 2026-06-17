# Flux 2 Klein 9B Prompting Guide

Flux 2 Klein 9B is a distilled flow-matching model using the Qwen3 8B text/image encoder. It is optimized for 4-step generation and has a unique reference-guided character consistency pattern.

---

## Model Characteristics & Constraints

| Parameter | Value | Behavior & Best Practice |
|---|---|---|
| **Steps** | `4` | Distilled model; 4 steps is optimal. Do NOT increase steps, as it yields no quality gain and increases latency. |
| **CFG** | `1.0` | Must be exactly 1.0. Higher CFG values cause severe noise artifacts and color degradation. |
| **Negative Prompt** | *None* | Flux does not support native negative prompts. The workflow uses `ConditioningZeroOut` for the negative input. The agent should NOT populate the `negative_prompt` field. |
| **Resolution** | `1344×768` | Fixed native 16:9 resolution. Locked via INTConstant nodes in the template. |
| **Max References** | `4` | Hard creative and technical VRAM limit. Do not place more than 4 characters in a scene prompt. |

---

## Prompt Formulation

Flux uses a natural-language Qwen text encoder. Do **NOT** use booru-style tag lists or clip-style keyword salads. Use descriptive, grammatically correct English sentences.

### SCALIST-Adapted Formula for Flux

Structure the prompt by flowing through these six categories:

1. **Subject**: The characters present, described by name, age/identity, and unique features.
2. **Action/Pose**: What the characters are doing, their postures, and their relationships.
3. **Style/Medium**: E.g., "3D Pixar-style animation, rich textures, claymation-feel" or "watercolor illustration".
4. **Context/Setting**: Environment detail, time of day, atmosphere.
5. **Lighting**: E.g., "warm golden light", "dappled forest sunlight", "cinematic soft shadows".
6. **Camera/Technical**: E.g., "medium shot", "eye-level camera", "depth of field".

---

## Character Consistency & Reference Sheets

Flux uses the `ReferenceLatent` node chain. Each reference sheet is used to anchor character identities.

### Reference Selection Rule
- Only include reference sheets for characters **actively mentioned in the shot action**. Do NOT attach refs for characters listed at the scene level but off-screen in a particular shot.
- The order of reference sheets must match the order characters are introduced in the prompt (and their overall visual importance).
- If a scene has >4 characters in the story manifest, **the agent MUST split the scene into multiple shots** or **exclude background characters** to keep reference sheets $\le 4$.
- **NEVER duplicate a reference** to pad to the 2-slot minimum. The workflow builder auto-handles this. Duplicate refs cause the model to hallucinate duplicate characters.

### Identity Description Pattern
To ensure the model correctly maps reference images to characters, you must explicitly associate each character's prompt description with their reference sheet role.

Use the **Reference Mapping Header** at the start of your prompt:

```text
Characters in this scene must match the provided reference images exactly:
- [Character A ID] (first reference): [Short visual description from identity_spec]
- [Character B ID] (second reference): [Short visual description from identity_spec]
```

#### Example Prompt
```text
Characters in this scene must match the provided reference images exactly:
- Toby (first reference): A young orange tiger cub with bright orange fur and no stripes at all, big blue eyes.
- Taro (second reference): An older lean tiger with magnificent black stripes across bright orange fur, confider golden eyes.

Toby stands in the sunlit clearing, looking down at his own stripe-less belly in confusion, while Taro stands beside him with his stripes gleaming. Warm jungle clearing with mottled sunlight streaming through the canopy. 3D Pixar-style animation, cinematic lighting, rich textures, depth of field.
```

---

## Establishing Shots (Zero References)

For shots that establish the environment or show landscapes where no characters are present, you should use the zero-reference Text-to-Image (T2I) pipeline:

### How to configure:
1. Set `"references": []` in the shot object in `prompt.json`.
2. Do **NOT** include the Reference Mapping Header in the prompt text.
3. The workflow builder will automatically detect `num_refs == 0` and switch the template from `flux-2-klein-image-edit` to `flux-2-klein-t2i`.

### Zero-Reference Prompt Example:
```text
Wide panoramic establishing shot of a lush tropical jungle — tall bamboo stalks, broad banana leaves, colorful wildflowers, golden sunlight streaming through a thick emerald canopy, misty air. 3D Pixar-style animation, rich textures, balanced white balance, natural color grading.
```

---

## Performance & Quality Pitfalls

### 0. The "Literal Metaphor" Pitfall
- **Bad**: `"large floppy ears shaped like banana leaves"` → model renders **actual banana leaves** attached to or growing out of the ears.
- **Good**: `"large broad floppy ears, rounded at the edges"` → describes the ear shape without metaphor.
- **Rule**: Never use food/object metaphors ("banana-leaf ears", "pillar-like legs", "button nose") in identity_specs or prompts. The model takes them literally and renders the referenced object. Use purely anatomical/shape descriptors instead.

### 1. The "Keyword Salad" Pitfall
- **Bad**: `1tiger, stripes, forest, sunlight, pixar style, 8k, detailed, photorealistic`
- **Good**: `A confident, striped tiger stands in a dense, sun-dappled jungle. 3D Pixar-style animation with soft lighting.`

### 2. The "Negative Prompting" Pitfall
- Since the model doesn't use negative conditioning, writing "no stripes on belly" or "not dark" in the prompt will cause the model to generate stripes or make the scene dark (because it sees those words in the positive text).
- **Correct strategy**: Describe what IS present instead of what is NOT. Write: "plain orange fur" or "brightly lit clearing".

> [!CAUTION]
> **Do not populate the `negative_prompt` field**: The Flux pipeline utilizes `ConditioningZeroOut` for negative conditioning. Adding negative text to `negative_prompt` has no effect but creates visual noise and confusion in prompt.json. Always leave the `negative_prompt` field empty (`""`).

### 3. Red-Saturation Bias & Color Correction
- FLUX.2 Klein has a known tendency to output overly warm, reddish, or sunburned skin tones and landscapes.
- **Mandatory suffix fix**: Always append a color grading suffix to the style block of every prompt:
  `"balanced white balance, natural color grading, true-to-reference skin tones"`

### 4. Aspect Ratio Distortion
- Flux is highly sensitive to aspect ratio. The template locks dimensions to `1344×768` (16:9). Do not try to bypass this via overrides; always prompt with composition cues (e.g., "horizontal landscape view", "wide panoramic view") that fit a 16:9 container.

### 4. Characters Too Close Together
- Without explicit spatial cues, the model places all characters side-by-side in the center of the frame.
- **Always include positioning/spacing cues** for multi-character shots:
  - "Toby on the far left foreground, Taro on the far right background"
  - "Toby in the lower-left, sitting alone; Taro is distant and small in the upper-right background"
  - "characters separated by several paces of grass between them"
- **Use camera framing** that implies distance:
  - "wide shot with Toby in foreground left, Taro pouncing in distant background right"
  - "Toby sits close to camera in foreground, Taro is a small figure far behind"

### 5. Deformed Characters (Extra Tails, Extra Limbs)
- Flux, like all diffusion models, can generate extra tails, extra limbs, or fused body parts.
- **Do NOT use negative-style language** (e.g., "no extra tail" → model sees "tail" and generates one). Describe what IS:
  - "with exactly one clean unbroken tail swaying gently"
  - "four well-formed paws firmly planted"
  - "symmetrical balanced body, well-proportioned"
- **Anchoring technique**: At the end of the character description, add one line of positive body-anchoring:
  - `"Toby has one short stubby tail, four small paws, two round ears, and a compact well-formed body."`
- This is especially critical for non-standard poses (tumbling, mid-leap) where the model is more likely to hallucinate extra limbs.

### 6. Extra Characters / Ghost Characters
- When a reference image is loaded but the character isn't described in the action, the model often "finds a place" for that character — creating phantom third tigers.
- **Root cause**: Attaching a reference for a character not in the shot action.
- **Fix**: Only attach references for characters actively doing something in the shot. See "Shot-level Character Filtering" in Phase 1.5 docs.
- **Explicit count cue** (use sparingly): For 2-character scenes, you may add `"exactly two tigers appear in this scene"` near the start of the prompt after the reference mapping header.

---

## Mandatory Prompt Checklist (Pre-Flight)

Before writing each shot prompt to `prompt.json`, the agent **MUST** verify all of the following. If any item is missing, compose it before finalizing the prompt.

### For EVERY shot:

| # | Check | What to include | Example |
|---|---|---|---|
| ✅ | **Reference mapping header** | Anchor phrase + per-character ref mapping | `"Characters in this scene must match the provided reference images exactly: - Toby (first reference): ..."` (Skip for zero-reference shots) |
| ✅ | **Shot-level character filter** | Only characters *actively in the shot action* get refs | If Toby is alone, only `["toby_reference_sheet.png"]` — no Taro ref (Empty `[]` for zero-reference shots) |
| ✅ | **Spatial positioning** (multi-char) | Explicit left/right/foreground/background placement | `"Toby foreground left, Taro background right"` |
| ✅ | **Positive body-anchoring** | Describe the correct body, NOT what to avoid | `"one clean unbroken tail, four well-formed paws"` |
| ✅ | **Token budget** | Prompt ≈ 50–180 tokens, hard cap 250 | If >250 tokens → abbreviate identity specs, drop repeated setting details |
| ✅ | **Camera framing** | Shot type + implied distance between chars | `"wide shot"`, `"medium shot, separated by several paces"` |
| ✅ | **Color-grading suffix** | Color bias correction tokens at prompt end | `"balanced white balance, natural color grading"` |

### For MULTI-CHARACTER shots (2+ characters), ALSO verify:

| # | Check | What to include | Example |
|---|---|---|---|
| ✅ | **Spacing/depth cues** | Physical distance between characters in the prompt | `"several paces apart"`, `"Toby close to camera, Taro distant behind"` |
| ✅ | **Explicit count cue** | State the exact number of characters (sparingly, for prone-to-ghost scenes) | `"exactly two tigers appear in this scene"` |
| ✅ | **Distinct visual anchors** | Each character has at least 2 unique visual traits mentioned | Toby: "plain orange fur, blue eyes" vs Taro: "sharp black stripes, golden eyes" |

### Abbreviation Guide (to stay within token budget)

After the **first shot** of a scene, you can abbreviate repeated elements:
- **Style**: Drop after first shot in a scene (model carries context). Just `"3D Pixar-style"` instead of full style string.
- **Setting**: Shorten to key nouns. `"jungle clearing"` instead of `"brightly lit jungle clearing with tall grass, wildflowers..."`.
- **Identity specs**: After first mention, use short key features only. `"Toby: plain orange cub, blue eyes"` instead of full `identity_spec`.
- **Never abbreviate**: Facial expressions, body-anchoring, spatial positioning, color-grading suffix.
