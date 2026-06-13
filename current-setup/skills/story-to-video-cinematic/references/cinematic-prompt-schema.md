# Cinematic Prompt Schema (v2.0)

The prompt manifest schema (`cinematic_prompt.json`) for the `story-to-video-cinematic` pipeline. Evolved from `filmmaking_prompt.json` to support character sheets and Flux Klein edit instructions.

## Schema Example

```json
{
  "version": "2.0",
  "pipeline": "cinematic",
  "models": {
    "image_generator": "ideogram-4-t2i",
    "image_editor": "flux-2-klein-image-edit",
    "video_engine": "ltx-23-fflf-seed-hunter"
  },
  "global": {
    "style": "Cinematic 3D Pixar-style, soft volumetric lighting, warm color palette",
    "resolution_preset": "1080p",
    "fps": 25,
    "segment_duration": 5,
    "input_ref_strength": 0.8,
    "end_ref_strength": 0.8,
    "seed_base": 42,
    "auto_select_motion": true,
    "continuation_mode": "auto_chain"
  },
  "characters": {
    "girl": {
      "description": "A 10-year-old girl with short brown hair, big green eyes, wearing a blue dress with white polka dots",
      "style_notes": "chibi proportions, 3D rendered, large head-to-body ratio",
      "edit_prompt_descriptor": "the young girl with brown hair and blue polka-dot dress"
    },
    "wizard": {
      "description": "An elderly wizard with long white beard, pointed purple hat, flowing violet robes",
      "style_notes": "realistic proportions, weathered face, kind eyes",
      "edit_prompt_descriptor": "the elderly wizard in purple robes"
    }
  },
  "shots": [
    {
      "scene": 1,
      "shot": 1,
      "shot_type": "chain_start",
      "first_frame_prompt": "establishing shot of a fantasy village at dawn...",
      "last_frame_prompt": "same village, camera pushed closer...",
      "motion_prompt": "Camera slowly pushes in toward the girl...",
      "filename_prefix": "film_001_shot001",
      "characters_present": ["girl"],
      "primary_character": "girl",
      "edit_pass": {
        "ff_edit_prompt": "Replace the young girl with brown hair in the scene with the character from reference 1, matching their exact appearance. Keep the background, lighting, and composition identical",
        "lf_edit_prompt": "Replace the young girl with brown hair in the scene with the character from reference 1, matching their exact appearance and confused expression. Keep the background and lighting identical"
      },
      "references": [],
      "lf_references": [],
      "continues_from": null,
      "overrides": {}
    }
  ]
}
```

## Schema Reference

### Top-Level Fields

- `version`: String. Schema version, must be `"2.0"`.
- `pipeline`: String. Pipeline name, must be `"cinematic"`.
- `models`: Object. Specifies the model family used for each stage:
  - `image_generator`: `"ideogram-4-t2i"`
  - `image_editor`: `"flux-2-klein-image-edit"`
  - `video_engine`: `"ltx-23-fflf-seed-hunter"`
- `global`: Object. Contains global pipeline configurations.
- `characters`: Object mapping character ID string to character config.
- `shots`: Array of Shot Objects.

---

### Character Object

- `description`: String. Detailed physical description of the character. Used by Ideogram 4 to generate character sheets and scene frames.
- `style_notes`: String (optional). Styling hints like "chibi proportions" or "pastel colors".
- `edit_prompt_descriptor`: String. A short physical descriptor of the character (e.g. `"the girl with brown hair"`) used by the system to auto-compose Flux Klein edit prompts.

---

### Shot Object

- `scene`: Integer. Scene index.
- `shot`: Integer. Shot index.
- `shot_type`: String. One of:
  - `"chain_start"`: Start of a continuation chain (generates both FF and LF stills).
  - `"independent"`: Standalone shot (generates both FF and LF stills).
  - `"continuation"`: Continues from previous shot (uses previous video tail frame as FF, generates LF still).
  - `"bridge"`: Similar to continuation.
- `first_frame_prompt`: String (required for root shots). Text prompt for First Frame generation.
- `last_frame_prompt`: String (required). Text prompt for Last Frame generation.
- `motion_prompt`: String (required). Prompt describing the motion to interpolate between keyframes.
- `filename_prefix`: String. Output filename prefix (e.g., `film_001_shot001`).
- `characters_present`: Array of Strings (optional). List of character ID keys present in this shot.
- `primary_character`: String (optional). The primary character ID key whose character sheet should be used for the Flux Klein edit pass.
- `edit_pass`: Object (optional). Overrides for auto-generated edit prompts:
  - `ff_edit_prompt`: String. Custom edit instruction for FF.
  - `lf_edit_prompt`: String. Custom edit instruction for LF.
- `continues_from`: String (optional). Filename prefix of the preceding shot.
- `overrides`: Object (optional). Parameter overrides (e.g., `segment_duration`, `seed_base`).
