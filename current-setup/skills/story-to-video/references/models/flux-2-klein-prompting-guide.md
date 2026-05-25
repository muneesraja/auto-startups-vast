# Flux 2 Klein 9B Prompting Guide

Flux 2 Klein 9B is a distilled flow-matching model using the Qwen 2.5 8B VL text/image encoder. It is optimized for 4-step generation and has a unique reference-guided character consistency pattern.

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
- Only include reference sheets for characters **actively present** in the shot.
- The order of reference sheets must match the order characters are introduced in the prompt (and their overall visual importance).
- If a scene has >4 characters in the story manifest, **the agent MUST split the scene into multiple shots** or **exclude background characters** to keep reference sheets $\le 4$.

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

## Performance & Quality Pitfalls

### 1. The "Keyword Salad" Pitfall
- **Bad**: `1tiger, stripes, forest, sunlight, pixar style, 8k, detailed, photorealistic`
- **Good**: `A confident, striped tiger stands in a dense, sun-dappled jungle. 3D Pixar-style animation with soft lighting.`

### 2. The "Negative Prompting" Pitfall
- Since the model doesn't use negative conditioning, writing "no stripes on belly" or "not dark" in the prompt will cause the model to generate stripes or make the scene dark (because it sees those words in the positive text).
- **Correct strategy**: Describe what IS present instead of what is NOT. Write: "plain orange fur" or "brightly lit clearing".

### 3. Aspect Ratio Distortion
- Flux is highly sensitive to aspect ratio. The template locks dimensions to `1344×768` (16:9). Do not try to bypass this via overrides; always prompt with composition cues (e.g., "horizontal landscape view", "wide panoramic view") that fit a 16:9 container.
