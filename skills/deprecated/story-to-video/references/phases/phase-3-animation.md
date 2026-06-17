# Phase 3: Scene Animation (LTX 2.3 Director)

This phase covers generating animated video clips from static scene images using the primary `motion_prompt.json` descriptor file and the **LTX 2.3 Director** ComfyUI workflow template. LTX 2.3 Director acts as our primary Phase 3 engine, enabling multi-keyframe interpolation, segment-level Prompt Relay temporal control, and a high-fidelity two-stage spatial upscaler. The legacy `ltx-23-i2v-dev` template remains supported as a backward-compatible fallback.

---

## 1. Using the Video Generator Script

The `generate_video.py` script orchestrates Phase 3 video generation by parsing motion prompts, uploading keyframe stills, building ComfyUI API nodes, queueing requests, and downloading the finished mp4 videos.

### Basic Commands

```bash
# Generate all video shots from motion_prompt.json (v2 or v1)
python3 generate_video.py --prompts motion_prompt.json

# Generate a specific video shot (matches filename_prefix)
python3 generate_video.py --prompts motion_prompt.json --shot video_001_shot001

# Dry-run (compile workflow nodes and check overrides without queueing on ComfyUI)
python3 generate_video.py --prompts motion_prompt.json --dry-run

# Skip already-generated videos
python3 generate_video.py --prompts motion_prompt.json --skip-existing

# Override ComfyUI URL and output directory
python3 generate_video.py --prompts motion_prompt.json \
  --url https://comfyui.example.com \
  --output-dir /path/to/story-output
```

### Script Execution Workflow

1. **Schema Check:** Reads and validates `motion_prompt.json` (auto-detects Director v2 schema vs. legacy v1).
2. **Template Resolution:** Loads the workflow template JSON (e.g., `ltx-23-director` or `ltx-23-i2v-dev`).
3. **Local Still Resolving:** Resolves all local static still images specified in `motion_image` or the `keyframes` array (checks current path, then `scenes/` directory).
4. **ComfyUI Upload:** Uploads all resolved images to the ComfyUI instance's `/input` folder via the multipart upload endpoint.
5. **Timeline payload construction:** For LTX Director, builds the `timeline_data` payload containing segments, start/end bounds, image filenames, and strengths.
6. **Workflow Building:** Merges parameters (`__PROMPT__`, `__TIMELINE_DATA__`, `__WIDTH__`, `__HEIGHT__`, `__DURATION__`, `__FPS__`, `__SEED__`, `__DURATION_FRAMES__`) into the template JSON.
7. **Execution Polling:** Submits the prompt payload to ComfyUI, polling `/history/{prompt_id}` until execution finishes.
8. **Asset Download:** Scans output history (parsing `gifs`, `videos`, and `images` keys of the SaveVideo node) and downloads the raw `.mp4` into the `videos/` subdirectory of the vault.

---

## 2. Keyframe Composition and Prompting Rules

Unlike standard Image-to-Video models which strictly force the input image at frame 0, LTX Director treats images as **Guide Keyframes** (attractors) that pull the generated motion toward that visual state at specific timeline intervals.

### Guide Keyframe Target Layouts

- **Single Keyframe (Classic I2V)**: Place a still at `time: 0` with `guide_strength: 1.0`. The clip begins matching the still and diffuses into movement.
- **Dual Keyframe (Scene Transition)**: Place still A at `time: 0` and still B at `time: 5.0` (end). The model generates a smooth interpolation transition between them.
- **Mid-Shot Keyframe**: Place a still at `time: 3.0` with a blank gap leading up to it. The model will generate the motion leading up to that exact composition.

### Prompt Engineering Guidelines

- **Global Prompt**: Describes style, lighting, and general aesthetic (applied to all segments). Do not repeat style info in segments.
- **Segment Prompt (Local)**: Describes physical action and camera behavior during that segment.
- **Present Tense**: Use active present-tense actions (e.g. `"runs forward"`, `"glances back"`, `"speaks slowly"`).
- **Temporal Segment Granularity**: Maintain a minimum segment length of **0.5 seconds**. Avoid cramming complex motion into segments under 2 seconds.

---

## 3. Motion Prompt Schema (v2.0)

The `motion_prompt.json` file controls the animation parameters. The v2 schema introduces keyframe and segment structures for LTX Director:

```json
{
  "version": "2.0",
  "model": "ltx-2.3-director",
  "workflow_template": "ltx-23-director",
  "global": {
    "global_prompt": "Cinematic 3D Pixar style, soft volumetric lighting, warm pastel palette, 4k",
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
      "motion_prompt": "Rabbit laughs and tortoise reacts.",
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
          "prompt": "Rabbit throws his head back laughing, ears bouncing"
        },
        {
          "start": 2.5,
          "end": 5.0,
          "prompt": "Tortoise slowly rolls his eyes in annoyance, camera pulls back"
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

*Note: For backward compatibility, if `workflow_template` is set to `ltx-23-i2v-dev`, the script parses the legacy v1 schema (`motion_image` field and single prompt) and executes the old single-pass I2V workflow.*

---

## 4. Models and Hugging Face Setup

The `ltx-23-director` workflow requires a broader suite of models compared to standard I2V. These are managed and downloaded via the `ltx-23-director-subgraphs.sh` script:

1. **Transformer Checkpoint (29.1GB):** `ltx-2.3-22b-dev-fp8.safetensors` (Downloaded from `Lightricks/LTX-2.3-fp8`)
2. **Distilled LoRA (2.6GB):** `ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors` (Downloaded from `Kijai/LTX2.3_comfy`)
3. **Tiny VAE (23MB):** `taeltx2_3.safetensors` (Downloaded from `Kijai/LTX2.3_comfy`)
4. **Audio VAE (365MB):** `LTX23_audio_vae_bf16.safetensors` (Downloaded from `Kijai/LTX2.3_comfy`)
5. **Video VAE (1.5GB):** `LTX23_video_vae_bf16.safetensors` (Downloaded from `Kijai/LTX2.3_comfy`)
6. **CLIP Model 1 (9.4GB):** `gemma_3_12B_it_fp4_mixed.safetensors` (Downloaded from `Comfy-Org/ltx-2`)
7. **CLIP Model 2 (2.3GB):** `ltx-2.3_text_projection_bf16.safetensors` (Downloaded from `Kijai/LTX2.3_comfy`)
8. **Spatial Upscaler Model (1GB):** `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` (Downloaded from `Lightricks/LTX-2.3`)

Run the script on your worker instance to provision the environment:
```bash
./workflows/setup/ltx-23-director-subgraphs.sh
```

---

## 5. File Structure of Phase 3 Outputs

After generation completes, the output files are structured under the vault as follows:

```
story-to-video/{story-slug}/
├── characters/             # Character reference sheets
├── scenes/                 # Phase 2 Still Scenes
│   ├── scene_001_shot001_final.png
│   └── ...
├── videos/                 # Phase 3 Generated Videos
│   ├── video_001_shot001.mp4
│   └── ...
├── motion_prompt.json      # Composed motion prompts (v2.0 or v1.0)
├── prompt.json             # Composed scene prompts
└── story_manifest.json     # Story master manifest
```
