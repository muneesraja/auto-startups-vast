# motion_prompt.json Schema Reference

The `motion_prompt.json` file is the intermediate artifact between the agent (prompt composer) and the video generation script (`generate_video.py`) in Phase 3. The agent composes this file to direct scene animation.

---

## Schema Version: 2.0 (LTX Director - Recommended)

Use this schema when targetting `workflow_template: "ltx-23-director"`. It allows multi-keyframe positioning, segment-level prompt relay timings, and global style injection.

```json
{
  "version": "2.0",
  "model": "ltx-2.3-director",
  "workflow_template": "ltx-23-director",
  "created_at": "<ISO-8601 timestamp>",
  "global": {
    "global_prompt": "Cinematic Pixar style, volumetric lighting, pastel colors, 4k",
    "seed_base": 42,
    "width": 1280,
    "height": 704,
    "duration": 5,
    "fps": 24
  },
  "shots": [
    {
      "scene": 1,
      "shot": 1,
      "motion_prompt": "Rabbit laugh and tortoise react.",
      "filename_prefix": "video_001_shot001",
      "keyframes": [
        {
          "image": "scene_001_shot001_final.png",
          "time": 0.0,
          "guide_strength": 1.0,
          "prompt": "Rabbit points mockingly at the tortoise"
        }
      ],
      "segments": [
        {
          "start": 0.0,
          "end": 2.5,
          "prompt": "Rabbit throws head back laughing, ears bouncing"
        },
        {
          "start": 2.5,
          "end": 5.0,
          "prompt": "Tortoise rolls eyes in annoyance, camera dollies back"
        }
      ],
      "overrides": {
        "lora_strength": 0.5,
        "steps_pass1": 8,
        "denoise_pass2": 0.42
      }
    }
  ]
}
```

---

## Schema Version: 1.0 (Legacy I2V Fallback)

Use this schema when targetting `workflow_template: "ltx-23-i2v-dev"`. It supports single-pass Image-to-Video generation using one static image at frame zero.

```json
{
  "version": "1.0",
  "model": "ltx-2.3-i2v",
  "workflow_template": "ltx-23-i2v-dev",
  "created_at": "<ISO-8601 timestamp>",
  "global": {
    "negative_prompt": "video game, cartoon, childish, ugly",
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
      "motion_prompt": "Rabbit throws head back laughing mockingly. Camera holds steady.",
      "motion_image": "scene_001_shot001_final.png",
      "filename_prefix": "video_001_shot001",
      "overrides": {
        "i2v_strength": 0.7,
        "lora_strength": 0.5
      }
    }
  ]
}
```

---

## Field Reference (v2.0 Additions)

### Global Settings

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `global_prompt` | string | No | `""` | A base styling prompt automatically prepended to all local segment prompts to maintain style consistency. |

### Shot Object

| Field | Type | Required | Description |
|---|---|---|---|
| `motion_image` | string | No | Optional. If specified without a `keyframes` array, the script auto-converts it to a single keyframe at `time: 0.0` for backward compatibility. |
| `keyframes` | array | No | Array of guide keyframe objects specifying image anchors along the timeline. |
| `segments` | array | No | Array of text segments defining timeline-bound prompt relay strings. |

### Keyframe Object

| Field | Type | Required | Description |
|---|---|---|---|
| `image` | string | Yes | Local filename of the scene still image (resolved from the local `scenes/` folder). |
| `time` | float | Yes | Time offset in seconds where the keyframe attractor is placed (e.g. `0.0`, `2.5`). |
| `guide_strength` | float | No | Attractor strength weight (`0.0` to `1.0`, default `1.0`). |
| `prompt` | string | No | Semantic description of the keyframe layout. |

### Segment Object

| Field | Type | Required | Description |
|---|---|---|---|
| `start` | float | Yes | Start time of the prompt segment in seconds (e.g., `0.0`). |
| `end` | float | Yes | End time of the prompt segment in seconds (e.g., `2.5`). |
| `prompt` | string | Yes | Specific motion prompt text for this segment. |
