# Phase 3: Scene Animation (LTX 2.3 I2V)

This phase covers generating animated video clips (with optional synchronized audio) from static scene images using the primary `motion_prompt.json` descriptor file and the LTX 2.3 Image-to-Video (I2V) ComfyUI workflow template.

---

## 1. Using the Video Generator Script

The `generate_video.py` script orchestrates Phase 3 video generation by parsing motion prompts, uploading the static stills, building the ComfyUI API nodes, queueing requests, and downloading the finished mp4 videos.

### Basic Commands

```bash
# Generate all video shots from motion_prompt.json
python3 generate_video.py --prompts motion_prompt.json

# Generate a specific video shot
python3 generate_video.py --prompts motion_prompt.json --shot video_001_shot001

# Dry-run (compile workflow nodes and check overrides without queueing)
python3 generate_video.py --prompts motion_prompt.json --dry-run

# Skip already-generated videos
python3 generate_video.py --prompts motion_prompt.json --skip-existing

# Override ComfyUI URL and output directory
python3 generate_video.py --prompts motion_prompt.json \
  --url https://comfyui.example.com \
  --output-dir /path/to/story-output
```

### Script Execution Workflow

1. **Schema Check:** Reads and validates `motion_prompt.json`.
2. **Template Resolution:** Loads `ltx-23-i2v-dev.json` from the template directory.
3. **Local Still Resolving:** Finds the local static still image specified in `motion_image` (checks current path, then `scenes/` directory).
4. **ComfyUI Upload:** Uploads the image to the ComfyUI instance's `/input` folder via the multipart upload endpoint, receiving the unique filename on the server.
5. **Workflow Building:** Replaces parameters (`__PROMPT__`, `__MOTION_IMAGE__`, `__WIDTH__`, `__HEIGHT__`, `__DURATION__`, `__FPS__`, `__SEED__`) in the template JSON and applies overrides (`i2v_strength`, `lora_strength`, `t2v_switch`).
6. **Execution Polling:** Submits the prompt payload to ComfyUI, polling `/history/{prompt_id}` until execution finishes.
7. **Asset Download:** Scans output history (parsing `gifs`, `videos`, and `images` keys of the SaveVideo node) and downloads the raw `.mp4` into the `videos/` subdirectory of the vault.

---

## 2. Motion Prompting Rules

Motion prompts describe **temporal movement and changes over time**, not the appearance of the still image. Because the I2V model sees the input image directly, describing static details wastes prompt tokens and causes visual distortion.

### The Golden Rules

1. **Never describe static elements** (colors, clothes, characters, environment). Focus on the verbs.
2. **Write present-tense actions** ("walks", "turns", "lifts") instead of past tense or vague actions.
3. **Control the camera explicitly** (e.g., `slow dolly-in`, `pan right`, `static frame`).
4. **Translate emotions into physical cues** (e.g., "shoulders slump, head tilts down" instead of "looks sad").
5. **Keep it under 200 words** (4–8 sentences, single flowing paragraph) to fit the text encoder budget.

### Prompt Comparison

| ❌ Poor Prompt (Descriptive) | ✅ Good Prompt (Temporal Action) |
|---|---|
| "A brown rabbit with a blue vest stands in the forest next to a green turtle. The rabbit is happy and the sun is shining." | "Rabbit throws his head back laughing, ears bouncing mockingly as his paw points forward. Tortoise slowly tilts his head up in resolve. Camera holds steady in a medium shot." |
| "A mouse running fast. The mouse is grey. 4k resolution, cinematic." | "Mouse dashes forward, kicking up tiny clouds of dust. He glances back in alarm. The camera tracks rapidly alongside him at a low angle." |

---

## 3. Motion Prompt Schema

The `motion_prompt.json` file dictates the animation parameters for the story. It uses the following structure:

```json
{
  "version": "1.0",
  "model": "ltx-2.3-i2v",
  "workflow_template": "ltx-23-i2v-dev",
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
      "motion_prompt": "Rabbit points mockingly and laughs. Tortoise blinks slowly. The camera pans gently left.",
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

## 4. Models and Hugging Face Setup

The `ltx-23-i2v-dev` workflow requires four main model files, which can be downloaded using the `ltx-23-i2v-dev.sh` shell script:

1. **Transformer Checkpoint (29.1GB):** `ltx-2.3-22b-dev-fp8.safetensors` (Downloaded from `Lightricks/LTX-2.3-fp8`)
2. **Distilled LoRA (6GB):** `ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors` (Downloaded from `Comfy-Org/ltx-2.3`)
3. **Gemma 3 Text Encoder (9.4GB):** `gemma_3_12B_it_fp4_mixed.safetensors` (Downloaded from `Comfy-Org/ltx-2`)
4. **Spatial Upscale Model (1GB):** `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` (Downloaded from `Lightricks/LTX-2.3`)

Run the script on your worker instance to download the required models:
```bash
./scripts/workflows/ltx-23-i2v-dev.sh
```

---

## 5. File Structure of Phase 3 Outputs

After generation completes, the workspace is structured as follows:

```
story-to-video/{story-slug}/
├── characters/             # Character reference sheets
├── scenes/                 # Phase 2 Still Scenes
│   ├── scene_001_shot001_final.png
│   └── ...
├── videos/                 # Phase 3 Generated Videos
│   ├── video_001_shot001_00001.mp4
│   └── ...
├── motion_prompt.json      # Composed motion prompts
├── prompt.json             # Composed scene prompts
└── story_manifest.json     # Story master manifest
```
