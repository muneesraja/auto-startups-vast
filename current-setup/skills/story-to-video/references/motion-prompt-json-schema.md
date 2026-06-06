# motion_prompt.json Schema Reference

The `motion_prompt.json` file is the intermediate artifact between the agent (prompt composer) and the video generation script (`generate_video.py`) in Phase 3. The agent composes this file to direct scene animation.

## Schema Version: 1.0

```json
{
  "version": "1.0",
  "model": "ltx-2.3-i2v",
  "workflow_template": "ltx-23-i2v-dev",
  "created_at": "<ISO-8601 timestamp>",
  "global": {
    "negative_prompt": "pc game, console game, video game, cartoon, childish, ugly",
    "seed_base": 42,
    "width": 1280,
    "height": 720,
    "duration": 5,
    "fps": 25
  },
  "shots": [
    {
      "scene": 1,
      "shot": 1,
      "motion_prompt": "<motion prompt text describing temporal action, camera motion, and secondary movements>",
      "motion_image": "scene_001_shot001_final.png",
      "negative_prompt": "<optional negative prompt override>",
      "duration": 5,
      "fps": 25,
      "seed": 839957834091742,
      "filename_prefix": "video_001_shot001",
      "overrides": {
        "i2v_strength": 0.7,
        "t2v_switch": false,
        "lora_strength": 0.5
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
| `model` | string | Yes | Model identifier. Examples: `"ltx-2.3-i2v"` |
| `workflow_template` | string | Yes | Name of the template in `assets/workflow-templates/`. Example: `"ltx-23-i2v-dev"` |
| `created_at` | string | No | ISO-8601 timestamp of when this file was composed. |
| `global` | object | Yes | Default configuration settings applied to all shots. |
| `shots` | array | Yes | Array of video shot objects to generate. |

### Global Settings

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `negative_prompt` | string | No | `""` | Default negative prompt applied to all shots. |
| `seed_base` | int | No | `42` | Base seed value if shot-specific seed is omitted. |
| `width` | int | Yes | `1280` | Output video width (should be divisible by 32). |
| `height` | int | Yes | `720` | Output video height (should be divisible by 32). |
| `duration` | int | Yes | `5` | Video clip duration in seconds. |
| `fps` | int | Yes | `25` | Output frame rate. |

### Shot Object

| Field | Type | Required | Description |
|---|---|---|---|
| `scene` | int | Yes | Scene number matching the story manifest. |
| `shot` | int | Yes | Shot number matching the story manifest. |
| `motion_prompt` | string | Yes | **Full motion prompt text** describing physical actions, environmental dynamics, and camera movements. **Never describe what's already visible in the static image.** |
| `motion_image` | string | Yes | Local file path or filename of the static scene still. The script resolves this and uploads it to ComfyUI. |
| `negative_prompt` | string | No | Shot-specific negative prompt. Overrides `global.negative_prompt` if set. |
| `duration` | int | No | Shot-specific clip duration. Defaults to `global.duration`. |
| `fps` | int | No | Shot-specific frame rate. Defaults to `global.fps`. |
| `seed` | int | No | Noise seed for this shot. Defaults to `global.seed_base`. |
| `filename_prefix` | string | Yes | Output filename prefix for the generated video (e.g., `"video_001_shot001"`). |
| `overrides` | object | No | Optional workflow parameter overrides. |

### Overrides Reference (LTX 2.3 I2V)

| Override Key | Type | Default | Description | Notes |
|---|---|---|---|---|
| `i2v_strength` | float | `0.7` | Image-to-video influence scale | Lower values (e.g., 0.5) allow more creative movement; higher values (e.g., 0.8) stick closer to the input image. |
| `t2v_switch` | bool | `false` | Enable pure Text-to-Video generation | Set to `true` to ignore the input image entirely and generate from prompt only. |
| `lora_strength` | float | `0.5` | Strength of the loaded distilled LoRA | Controls how strongly the distilled LoRA affects composition. |
| `upscale_seed` | int | `42` | Seed for the secondary latent upscale sampler | Set this to vary noise patterns on the high-res upscale pass. |
