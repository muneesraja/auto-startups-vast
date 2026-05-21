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
| `negative_prompt` | string | No | `""` | Default negative prompt applied to all shots. |
| `seed_base` | int | No | `42` | Base seed. Individual shots can override. |
| `width` | int | Yes | — | Output image width in pixels. |
| `height` | int | Yes | — | Output image height in pixels. |

### Shot Object

| Field | Type | Required | Description |
|---|---|---|---|
| `scene` | int | Yes | Scene number (from manifest). |
| `shot` | int | Yes | Shot number (from manifest). |
| `prompt` | string | Yes | **Full prompt text** for this shot. This is the agent's creative output — no templates, no placeholders. The agent composes this by reading the manifest, character specs, expressions, and the model's prompting guide. |
| `negative_prompt` | string | No | Shot-specific negative prompt. Overrides `global.negative_prompt` if set. |
| `references` | array[string] | Yes | List of reference image filenames available on the ComfyUI instance. Variable length — adapts to model's reference slot count (Qwen: max 3, HiDream: max 10). |
| `seed` | int | No | Seed for this shot. Defaults to `global.seed_base` if not set. |
| `filename_prefix` | string | Yes | Output filename prefix (e.g., `"scene_001_shot001"`). |
| `eval_context` | object | No | Metadata for Gemini Vision evaluation. Not used by the script for generation — only passed to the evaluator. |

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
- See `references/qwen-image-edit-prompting-guide.md` for full best practices

### HiDream O1 Dev 2604 (`workflow_template: "hidream-o1-dev-i2i"`)

- **Max references**: 10 images
- **Prompt style**: TBD (after workflow testing)
- **Negative prompt**: Supported (CFG 5.0 + negative prompt node)
- See `references/hidream-prompting-guide.md` for best practices (TBD)

## Example

See `assets/examples/prompt-example-little-tiger.json` for a complete example using the little-tiger story.
