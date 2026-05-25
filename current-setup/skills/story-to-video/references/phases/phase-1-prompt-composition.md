# Phase 1.5: Prompt Composition (Agent)

After character sheet approval and reference upload, the agent composes `prompt.json` — the intermediate artifact that bridges the story manifest and the generation script.

## What the Agent Does

1. **Read `story_manifest.json`** — extract scene structure, characters, expressions, settings, moods
2. **Read the model's prompting guide** — adapt prompt style to the target model:
   - For Qwen: [references/models/qwen-image-edit-prompting-guide.md](../models/qwen-image-edit-prompting-guide.md)
   - For HiDream: [references/models/hidream-prompting-guide.md](../models/hidream-prompting-guide.md)
   - For Flux 2 Klein: [references/models/flux-2-klein-prompting-guide.md](../models/flux-2-klein-prompting-guide.md)
3. **Select the workflow template** — set `workflow_template` field to match the model
4. **Enforce reference constraints at prompt-composition stage**:
   - For Flux 2 Klein, **scenes are strictly limited to 4 characters maximum**.
   - If a scene contains more than 4 characters in the story manifest, the agent **MUST split the shot** or **exclude background characters** to keep reference sheets <= 4.
   - Flag this decision explicitly in `eval_context` (e.g. by setting `excluded_characters` or noting it in `action`) so evaluators account for intentional character exclusions.
5. **For each shot, compose a detailed prompt** that includes:
   - Character visual identity descriptions (from manifest `identity_spec`)
   - Facial expressions using 3-region descriptors (mouth + eyes + brow)
   - Scene setting, lighting, and mood
   - Action being depicted
   - Camera angle
   - Art style directive
6. **Select reference images** — list the character reference sheet filenames per shot
7. **Populate `eval_context`** — include expected expressions, characters, setting for Gemini evaluation
8. **Write `prompt.json`** to the story working directory
9. **Optionally present to user for review** before generation

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
2. Include only characters present in the shot. **Do NOT pad reference lists manually** — the script handles pruning and spawning automatically.
3. Order by visual importance (most important character first)
4. Verify refs exist on the ComfyUI instance before composing

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

To add a new model: create a workflow template JSON with `__PROMPT__`, `__REFERENCE_N__`, `__SEED__`, `__WIDTH__`, `__HEIGHT__`, `__FILENAME_PREFIX__` placeholders.
