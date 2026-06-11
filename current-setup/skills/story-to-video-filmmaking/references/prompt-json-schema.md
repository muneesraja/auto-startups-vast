# prompt.json Schema Reference

The `prompt.json` file is the intermediate artifact between the agent (prompt composer) and the script (executor). The agent writes this file; `generate_scene.py` reads it.

## Schema Version: 1.0

```json
{
  "version": "1.0",
  "model": "<model-id>",
  "workflow_template": "<template-name>",
  "created_at": "<ISO-8601 timestamp>",
  "global": {
    "style": "<art style directive>",
    "negative_prompt": "<default negative prompt>",
    "seed_base": 42,
    "width": 1280,
    "height": 720
  },
  "shots": [
    {
      "scene": 1,
      "shot": 1,
      "prompt": "<full scene prompt text>",
      "negative_prompt": "<shot-specific negative prompt, overrides global>",
      "references": ["ref_image_1.png", "ref_image_2.png"],
      "seed": 42,
      "filename_prefix": "scene_001_shot001",
      "eval_context": {
        "characters_present": ["character_id_1", "character_id_2"],
        "setting": "<scene setting description>",
        "mood": "<scene mood>",
        "expected_expressions": {
          "character_id_1": "happy wide smile, eyes bright",
          "character_id_2": "neutral calm expression"
        },
        "action": "<what should be happening>"
      }
    }
  ]
}
```

## Field Reference

### Top-Level Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | string | Yes | Schema version. Currently `"1.0"`. |
| `model` | string | Yes | Model identifier. Used for logging and documentation. Examples: `"qwen-image-edit-2511"`, `"hidream-o1-dev-2604"` |
| `workflow_template` | string | Yes | Name of the workflow template JSON file (without extension) in `assets/workflow-templates/`. Examples: `"qwen-image-edit-2511"`, `"hidream-o1-dev-i2i"` |
| `created_at` | string | No | ISO-8601 timestamp of when the agent composed this file. |
| `global` | object | Yes | Default settings applied to all shots (can be overridden per-shot). |
| `shots` | array | Yes | Array of shot objects to generate. |

### Global Settings

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `style` | string | Yes | — | Art style directive (e.g., `"children's book watercolor illustration"`). |
| `negative_prompt` | string | No | `""` | Default negative prompt applied to all shots. **For Flux 2 Klein**: Leave empty (`""`) as Flux uses ConditioningZeroOut and ignores negative text. |
| `seed_base` | int | No | `42` | Base seed. Individual shots can override. |
| `width` | int | Yes | — | Output image width in pixels. |
| `height` | int | Yes | — | Output image height in pixels. |

### Shot Object

| Field | Type | Required | Description |
|---|---|---|---|
| `scene` | int | Yes | Scene number (from manifest). |
| `shot` | int | Yes | Shot number (from manifest). |
| `prompt` | string | Yes | **Full prompt text** for this shot. This is the agent's creative output. The agent composes this by reading the manifest, character specs, and the model's prompting guide. **For Flux 2 Klein**: Include the Reference Mapping Header and append color grading suffix tokens (staying under the 250 token budget). |
| `negative_prompt` | string | No | Shot-specific negative prompt. Overrides `global.negative_prompt` if set. Ignored by Flux models. |
| `references` | array[string] | Yes | List of reference image filenames available on the ComfyUI instance. Variable length — adapts to model's reference slot count. Qwen: max 3 (legacy padding), HiDream: max 12 (dynamic pruning/spawning). May be empty (`[]`) for establishing shots with no characters — the workflow builder will auto-switch to the T2I template. |
| `seed` | int | No | Seed for this shot. Defaults to `global.seed_base` if not set. |
| `filename_prefix` | string | Yes | Output filename prefix (e.g., `"scene_001_shot001"`). |
| `overrides` | object | No | Optional workflow parameter overrides. Only applies to templates with `_overrides_map` metadata (such as HiDream and Flux). Each key is an override name; value is written directly to the corresponding node input. |
| `eval_context` | object | No | Metadata for Gemini Vision evaluation. Not used by the script for generation — only passed to the evaluator. |

### Overrides Reference (HiDream O1 Dev)

| Override Key | Type | Default | Description | Notes |
|---|---|---|---|---|
| `image_edit` | bool | `true` | Toggle I2I edit mode vs T2I generation | When `false`, references are bypassed — pure text-to-image |
| `cfg` | float | `1.0` | Classifier-free guidance scale | Dev model: keep at 1.0. Full model: 3.0–5.0 |
| `steps` | int | `28` | Sampling steps | Dev: 28, Fast: 16, Full: 50 |
| `denoise` | float | `1.0` | Denoise strength | 1.0 = full generation, 0.5 = partial edit |
| `noise_scale` | float | `7.6` | Diffusion noise scaling factor | Dev: 7.5–7.6, Full: 8.0 |
| `noise_clip_std` | float | `2.5` | Noise clipping standard deviation | Usually keep at 2.5 |
| `scheduler` | string | `"normal"` | Scheduler type | `normal`, `simple`, `karras` |
| `width` | int | `2560` | Output width (must be multiple of 32) | Use HiDream native resolutions |
| `height` | int | `1440` | Output height (must be multiple of 32) | Use HiDream native resolutions |

### Overrides Reference (Flux 2 Klein 9B)

| Override Key | Type | Default | Description | Notes |
|---|---|---|---|---|
| `cfg` | float | `1.0` | Guidance scale | Keep at 1.0 — distilled model; higher values cause artifacts |
| `steps` | int | `4` | Sampling steps | 4 is optimal for Klein distilled; more steps give no quality gain |
| `seed` | int | random | Noise seed | Direct write to `RandomNoise` node |
| `megapixels_scale` | float | `1.0` | Reference image scaling factor | Applies to slot 1 only; spawned refs inherit 1.0; ignored in T2I mode |

> [!NOTE]
> **Width and height are not overridable for Flux 2 Klein.** Resolution is locked to **1344×768** (Flux native 16:9, ~1MP) via hardcoded `INTConstant` nodes. This prevents incompatible aspect ratio combinations and ensures optimal quality. Use HiDream if you need different resolutions.

### Overrides Reference (Flux 2 Dev Turbo)

| Override Key | Type | Default | Description | Notes |
|---|---|---|---|---|
| `guidance` | float | `4.0` | Controls prompt adherence | Default is 4.0. Range 2.5–6.0. Higher values increase prompt follow but can saturate colors. |
| `steps` | int | `8` | Sampling steps | 8 is optimal; more steps give minimal quality gain |
| `seed` | int | random | Noise seed | Direct write to `PrimitiveInt` seed node |
| `color_match_strength` | float | `0.0` | Post-process color matching | Range 0.0–1.0. Applies ColorMatchV2 of target back to ref image. |

> [!NOTE]
> **Width and height are not overridable for Flux 2 Dev Turbo.** Resolution is locked to **1344×768** (Flux native 16:9, ~1MP) via EmptyImage (196). This ensures optimal quality.

### Eval Context (for Gemini Vision evaluation)

| Field | Type | Required | Description |
|---|---|---|---|
| `characters_present` | array[string] | No | Character IDs expected in the scene. |
| `setting` | string | No | Expected scene setting. |
| `mood` | string | No | Expected mood/atmosphere. |
| `expected_expressions` | object | No | Map of `character_id` → expected facial expression description. |
| `action` | string | No | What should be happening in the scene. |

## Model-Specific Notes

### Qwen Image Edit 2511 (`workflow_template: "qwen-image-edit-2511"`)

- **Max references**: 3 images
- **Prompt style**: Include "Characters in this scene must match the provided reference images exactly" as anchor
- **Expression format**: Use 3-region descriptors (mouth + eyes + brow)
- **Negative prompt**: Supported via separate conditioning node
- See `references/models/qwen-image-edit-prompting-guide.md` for full best practices

### HiDream O1 Dev (`workflow_template: "hidream-o1-dev-i2i"`)

- **Max references**: 12 images (dynamic — script spawns LoadImage nodes as needed)
- **Min references**: 1 image (required for latent size calculation)
- **Overrides**: Supports per-shot `overrides` object for CFG, steps, noise_scale, image_edit toggle, etc.
- **Resolution**: 2560×1440 (native 16:9, trained resolution)
- **Prompt style**: Natural language paragraphs using SCALIST framework (Subject, Composition, Action, Location, Image style, Specs)
- **Negative prompt**: **Leave empty** (Dev model, CFG 1.0 — negative prompt causes artifacts)
- **Steps**: 28, SamplerLCM, noise_scale 7.6
- See `references/models/hidream-prompting-guide.md` for full best practices

### Flux 2 Klein 9B (`workflow_template: "flux-2-klein-image-edit"` or `"flux-2-klein-t2i"`)

- **Max references**: 4 images for `flux-2-klein-image-edit` (dynamic ReferenceLatent chain); 0 images for `flux-2-klein-t2i`
- **Min references**: 0 images (setting `references: []` in prompt.json auto-switches to the `flux-2-klein-t2i` template)
- **Overrides**: Supports per-shot `overrides` object for CFG, steps, noise seed, and megapixels scale (megapixels scale is I2I only).
- **Resolution**: 1344×768 (native 16:9, locked in workflow)
- **Prompt style**: Natural language paragraphs. For I2I, include Reference Mapping Header. For both, append a color-grading suffix (`"balanced white balance, natural color grading"`). Keep within **250 tokens** warning budget (ideal: 180).
- **Negative prompt**: **Do not use** (leave empty `""`; model uses ConditioningZeroOut or empty CLIPTextEncode natively)
- **Steps**: 4, SamplerCustomAdvanced, CFG 1.0
- See `references/models/flux-2-klein-prompting-guide.md` for full best practices

### Flux 2 Dev Turbo (`workflow_template: "flux-2-dev-turbo"`)

- **Max references**: 4 images (dynamic single-chain ReferenceLatent; prunes when <1, spawns when >1)
- **Min references**: 0 images (setting `references: []` auto-switches to T2I mode via ComfySwitchNode)
- **Overrides**: Supports per-shot `overrides` object for guidance, steps, seed, and color_match_strength
- **Resolution**: 1344×768 (native 16:9, locked in workflow)
- **Prompt style**: Natural language prose. Keep within **350 tokens** warning budget (ideal: 250). For I2I, include Reference Mapping Header. Append color-grading suffix (`"balanced white balance, natural color grading"`).
- **Negative prompt**: **Do not use** (leave empty `""`)
- **Steps**: 8, BasicGuider, guidance=4.0
- See `references/models/flux-2-dev-turbo-prompting-guide.md` for full best practices

## Example

See `assets/examples/qwen/prompt-example-little-tiger.json` for a complete example using the little-tiger story.
