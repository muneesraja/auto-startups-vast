# Phase 1.5: Prompt Composition (Agent)

After character sheet approval and reference upload, the agent composes `prompt.json` — the intermediate artifact that bridges the story manifest and the generation script.

## What the Agent Does

1. **Read `story_manifest.json`** — extract scene structure, characters, expressions, settings, moods
2. **Determine per-shot character presence** (v3 feature):
   - If a shot has `characters_present` set at the shot level → use that list
   - If not set → fall back to scene-level `characters_present`
   - Cross-check with the shot's `description` and `facial_expression` keys: if a character is in the scene-level list but has no expression AND isn't mentioned in the action, they're likely off-screen — set shot-level `characters_present` explicitly to exclude them
3. **Read the model's prompting guide** — adapt prompt style to the target model:
   - For Qwen: [references/models/qwen-image-edit-prompting-guide.md](../models/qwen-image-edit-prompting-guide.md)
   - For HiDream: [references/models/hidream-prompting-guide.md](../models/hidream-prompting-guide.md)
   - For Flux 2 Klein: [references/models/flux-2-klein-prompting-guide.md](../models/flux-2-klein-prompting-guide.md)
4. **Select the workflow template** — set `workflow_template` field to match the model
5. **Enforce reference constraints at prompt-composition stage**:
   - For Flux 2 Klein, **scenes are strictly limited to 4 characters maximum**.
   - If a scene contains more than 4 characters in the story manifest, the agent **MUST split the shot** or **exclude background characters** to keep reference sheets <= 4.
   - Flag this decision explicitly in `eval_context` (e.g. by setting `excluded_characters` or noting it in `action`) so evaluators account for intentional character exclusions.
6. **For each shot, compose a detailed prompt** that includes:
   - Character visual identity descriptions (from manifest `identity_spec`)
   - Facial expressions using 3-region descriptors (mouth + eyes + brow)
   - Scene setting, lighting, and mood
   - Action being depicted
   - Camera angle
   - Art style directive
   - **Spatial positioning** for multi-character shots (e.g., "Toby foreground left, Taro background right")
   - **Positive body-anchoring** to prevent deformations (e.g., "one clean tail, four well-formed paws")
   - **Color-grading suffix** (for Flux to fix red-saturation bias: `"balanced white balance, natural color grading"`)
   - **Caution**: For Flux, ensure the `negative_prompt` field is left empty (`""`) or omitted from the shot.
7. **Select reference images** — list the character reference sheet filenames per shot **based on shot-level character presence (step 2), NOT scene-level characters_present**, or set `references: []` (empty array) for environment-only/establishing shots with no characters. The workflow builder will automatically switch to the T2I pipeline.
8. **Populate `eval_context`** — include expected expressions, characters (shot-level), setting for Gemini evaluation
9. **Write `prompt.json`** to the story working directory
10. **Optionally present to user for review** before generation

---

## Prompt Length Budget

Each model has an optimal prompt token range. The agent MUST stay within budget:

| Model | Ideal Tokens | Max Tokens | Strategy |
|---|---|---|---|
| Qwen Image Edit | 50–150 | 200 | Concise SCALIST style |
| HiDream O1 Dev | 50–150 | 200 | Natural language paragraphs |
| Flux 2 Klein | 50–180 | 250 | Concise natural language + color suffix |

**How to stay within budget:**
1. **Abbreviate identity after first mention**: In the first shot of a scene, use the full `identity_spec`. For subsequent shots in the same scene, shorten to: `"Toby (small orange cub, no stripes, blue eyes)"` — just enough to anchor the reference.
2. **Style = short form after first shot**: Use the full style directive in Scene 1 Shot 1 only. After that, use: `"3D Pixar-style animation"` (4 words, not 30).
3. **Setting = scene-level, not shot-level**: Don't repeat the full setting description in every shot. For shot 2+, just reference changes: `"Same clearing, now with longer shadows"`.
4. **No redundancy**: If the action already implies the expression, don't repeat it in a separate expression line.

---

## prompt.json Schema

See [references/prompt-json-schema.md](../prompt-json-schema.md) for the full schema reference.

```json
{
  "version": "1.0",
  "model": "qwen-image-edit-2511",
  "workflow_template": "qwen-image-edit-2511",
  "global": {
    "style": "high-quality 3D rendered animation...",
    "negative_prompt": "deformed, extra limbs, blurry",
    "seed_base": 42,
    "width": 1280,
    "height": 720
  },
  "shots": [
    {
      "scene": 1,
      "shot": 1,
      "prompt": "Full agent-composed prompt text here...",
      "negative_prompt": "shot-specific overrides",
      "references": ["toby_reference_sheet.png", "taro_reference_sheet.png"],
      "seed": 42,
      "filename_prefix": "scene_001_shot001",
      "eval_context": {
        "characters_present": ["toby", "taro"],
        "setting": "brightly lit jungle clearing",
        "mood": "bittersweet, gentle longing",
        "expected_expressions": {
          "toby": "puzzled slight frown, eyes downcast"
        },
        "action": "Toby stands alone looking at his stripe-less chest"
      }
    }
  ]
}
```

---

## Multi-Reference Image Selection

The number of reference image slots depends on the model:

| Model | Max References | Notes |
|---|---|---|
| Qwen Image Edit 2511 | 3 | Legacy template with static slot counts (pads to 3 by duplicating) |
| HiDream O1 Dev | 12 | Dynamic template (prunes unused slots when <4, spawns slots when >4 up to 12) |
| Flux 2 Klein 9B | 4 | Dynamic ReferenceLatent chain template (prunes when <2, spawns when >2 up to 4) |

**Reference selection rules (for the agent):**
1. Use `{character_id}_reference_sheet.png` naming convention
2. Include only characters **actively present and mentioned in the shot action** — NOT scene-level characters. See "Shot-level character filtering" below.
3. **NEVER duplicate a reference to pad minimum slots.** The workflow builder handles slot pruning/spawning automatically. Duplicating refs causes the model to hallucinate duplicate characters (e.g., attaching `toby_reference_sheet.png` twice generates two Tobys).
4. Order by visual importance (most important character first)
5. Verify refs exist on the ComfyUI instance before composing

### Shot-level Character Filtering (CRITICAL)

The story manifest defines `characters_present` at the **scene level**, but individual shots may focus on a subset. The agent MUST determine per-shot character presence:

1. **Read the shot's `description`**: If only one character is mentioned by name in the action, that character alone gets a reference — even if the scene has more characters.
2. **Check `facial_expression` keys**: If a character has no expression entry for a shot, they are likely off-screen or not the focus.
3. **Close-up / focus shots**: If a shot is "Close-up of Toby..." — only include Toby's reference. Adding Taro's reference when Taro is not in the action causes the model to invent extra characters.
4. **Override `eval_context.characters_present`**: Set this to the shot-level subset, NOT the scene-level list.

**Example of incorrect vs correct:**
- ❌ Scene 1 Shot 4 (Toby close-up): refs = `[toby, taro]`, characters_present = `[toby, taro]`
- ✅ Scene 1 Shot 4 (Toby close-up): refs = `[toby]`, characters_present = `[toby]`
- ❌ Scene 2 Shot 1 (Toby-alone scene): refs = `[toby, toby]` (duplicated to pad)
- ✅ Scene 2 Shot 1 (Toby-alone scene): refs = `[toby]` (single ref, builder handles the rest)

---

## Agent Workflow Overrides

For dynamic templates, the agent can specify an optional `overrides` object in `prompt.json` for per-shot parameter tuning (e.g. `image_edit` toggle, `cfg`, `steps`, `denoise`, `noise_scale`, `noise_clip_std`, `scheduler`, `width`, `height`). This gives the agent programmatic control over the generation process per shot. Required slot 1 is always preserved for latent size calculation in image-to-image mode.

---

## Available Workflow Templates

Workflow templates live in `assets/workflow-templates/`. Each is a ComfyUI API-format JSON with placeholder tokens.

| Template | Model | Steps | Slots | Status |
|---|---|---|---|---|
| `qwen-image-edit-2511` | Qwen Image Edit 2511 + Lightning LoRA | 4 | 3 refs | ✅ Active |
| `hidream-o1-dev-i2i` | HiDream O1 Dev FP8 | 28 | 4 refs | ✅ Active |
| `flux-2-klein-image-edit` | Flux 2 Klein 9B FP8 | 4 | 2 refs | ✅ Active |
| `flux-2-klein-t2i` | Flux 2 Klein 9B FP8 | 4 | 0 refs | ✅ Active |

To add a new model: create a workflow template JSON with `__PROMPT__`, `__REFERENCE_N__`, `__SEED__`, `__WIDTH__`, `__HEIGHT__`, `__FILENAME_PREFIX__` placeholders.
