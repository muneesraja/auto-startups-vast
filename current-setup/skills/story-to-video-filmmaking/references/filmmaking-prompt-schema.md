# Filmmaking Prompt JSON Schema

The `filmmaking_prompt.json` file is the central instruction sheet for the `story-to-video-filmmaking` pipeline. It is composed by the agent in Phase 1.5, representing the cinematic breakdown of the story manifest.

Unlike the legacy `prompt.json` (which only specifies static scene stills) or `motion_prompt.json` (which only covers basic timelines and single-frame I2V), the filmmaking prompt schema coordinates **dual-keyframe generation (First Frame & Last Frame)** and **continuation-aware shot chaining**.

## JSON Schema Structure

```json
{
  "version": "1.0",
  "model": "ltx-2.3-fflf-seed-hunter",
  "workflow_template": "ltx-23-fflf-seed-hunter",
  "global": {
    "image_workflow_template": "flux-2-dev-turbo",
    "resolution_preset": "1080p",
    "custom_width": null,
    "custom_height": null,
    "fps": 25,
    "segment_duration": 5,
    "overlap_seconds": 1.0,
    "input_ref_strength": 0.8,
    "end_ref_strength": 0.8,
    "seed_base": 42,
    "auto_select_motion": true,
    "continuation_mode": "auto_chain",
    "style": "Cinematic 3D Pixar-style, soft volumetric lighting"
  },
  "shots": [
    {
      "scene": 1,
      "shot": 1,
      "shot_type": "chain_start",
      "first_frame_prompt": "establishing shot of a fantasy village at dawn, warm golden light, a girl stands at the edge of the frame looking outward",
      "last_frame_prompt": "same village, camera has pushed closer, the girl turned to face the camera with a confused expression",
      "first_frame_image": "scene_001_shot001_ff.png",
      "last_frame_image": "scene_001_shot001_lf.png",
      "motion_prompt": "A continuous fluid shot — camera slowly pushes in toward the girl as she turns her head to face us and tilts it curiously",
      "filename_prefix": "film_001_shot001",
      "continues_from": null,
      "break_continuity": false,
      "characters_present": ["girl"],
      "references": ["girl_reference_sheet.png"],
      "overrides": {
        "input_ref_strength": 0.7,
        "end_ref_strength": 0.8,
        "segment_duration": 5
      }
    }
  ]
}
```

## Field Reference

### Global Parameters

* **`version`** (string): Schema version. Always `"1.0"`.
* **`model`** (string): Target model family. Always `"ltx-2.3-fflf-seed-hunter"`.
* **`workflow_template`** (string): ComfyUI API template name. Always `"ltx-23-fflf-seed-hunter"`.
* **`global`** (object): Global defaults applied to all shots.
  * **`image_workflow_template`** (string): Workflow template to use for Phase 2 image generation (default: `"flux-2-dev-turbo"`).
  * **`resolution_preset`** (string): `"1080p"` (1920×1088) or `"720p"` (1280×704).
  * **`fps`** (int): Frame rate (default: `25`).
  * **`segment_duration`** (int): Duration per segment in seconds (default: `5`).
  * **`overlap_seconds`** (float): Duration of overlapping context buffer for continuation stitching (default: `1.0`).
  * **`input_ref_strength`** (float): Start frame keyframe guide strength (default: `0.8`).
  * **`end_ref_strength`** (float): End frame keyframe guide strength (default: `0.8`).
  * **`seed_base`** (int): Starter seed integer.
  * **`auto_select_motion`** (bool): Auto-choose best Stage 1 preview motion via Gemini evaluator.
  * **`continuation_mode`** (string): `"auto_chain"` or `"independent"`.
  * **`style`** (string): Text string describing global cinematic aesthetic.

### Shot Parameters

* **`scene`** (int): Scene index.
* **`shot`** (int): Shot index within the scene.
* **`shot_type`** (string): How frames are resolved. One of:
  * **`chain_start`**: First shot in a scene chain. Generates both FF and LF stills.
  * **`continuation`**: Shot that inherits its starting frames from the preceding video's tail. Generates ONLY the LF still.
  * **`independent`**: Standalone shot. Generates both FF and LF stills.
  * **`bridge`**: Last shot before a scene transition that must flow visually.
* **`first_frame_prompt`** (string or null): Detailed Flux/Qwen prompt to generate the starting composition. (Required if `shot_type` is `chain_start` or `independent`).
* **`last_frame_prompt`** (string): Detailed Flux/Qwen prompt to generate the ending composition. (Always required).
* **`first_frame_image`** (string or null): Filename for the generated FF still. (Required if `shot_type` is `chain_start` or `independent`).
* **`last_frame_image`** (string): Filename for the generated LF still. (Always required).
* **`motion_prompt`** (string): Brief description of the physical motion connecting FF to LF. (Keep under 60 words).
* **`filename_prefix`** (string): Base name for outputs. Format: `film_{scene_3_digits}_shot{shot_3_digits}`.
* **`continues_from`** (string or null): Prefix of the preceding shot (e.g. `"film_001_shot001"`) if chaining.
* **`break_continuity`** (bool): Forces the shot to start fresh as `independent` even if it is part of a scene.
* **`characters_present`** (array): Names of characters in the shot.
* **`references`** (array): Filenames of character sheet references.
* **`overrides`** (object): Local overrides to global parameters for this shot (e.g., overriding duration or strength values).
