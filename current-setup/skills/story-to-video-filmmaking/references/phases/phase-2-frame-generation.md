# Phase 2: Smart Frame Generation

This phase covers generating the keyframe still images (First Frame and Last Frame) required for the FFLF video generation pipeline. By using a continuation-aware strategy, we optimize GPU compute by only generating images that are actually needed.

---

## 1. The Smart Frame Generation Matrix

Instead of naively generating both first and last frames for every single shot, the pipeline dynamically adapts to shot relationships:

| Shot Type | First Frame (FF) | Last Frame (LF) | Image Sourcing Logic |
|---|---|---|---|
| **`chain_start`** | ✅ Generated | ✅ Generated | First shot in a scene or after a break. |
| **`continuation`** | ❌ Extracted | ✅ Generated | Inherits FF from the tail of the preceding shot's video. |
| **`independent`** | ✅ Generated | ✅ Generated | Standalone shot. No visual continuity with neighboring shots. |
| **`bridge`** | ❌ Extracted | ✅ Generated | Transitions between scene chains while maintaining flow. |

### Optimization Benefits
For a typical 3-scene, 8-shot story structure:
* **Naive Approach**: Generates 8 FF and 8 LF images = **16 ComfyUI calls**.
* **Smart Approach**: Generates 3 FF (for scene starts) and 8 LF images = **11 ComfyUI calls**.
* **Result**: **62.5% fewer FF images generated** and **31% fewer total ComfyUI calls**.

---

## 2. Execution via `generate_frames.py`

The script `generate_frames.py` runs Phase 2. It parses the composed `filmmaking_prompt.json`, checks shot types, manages reference sheets, and queues image generations sequentially.

### CLI Usage

```bash
# Generate keyframe stills for all shots in filmmaking_prompt.json
python3 generate_frames.py --prompts filmmaking_prompt.json

# Generate keyframe stills for a specific shot only
python3 generate_frames.py --prompts filmmaking_prompt.json --shot film_001_shot001

# Perform a dry-run (classifies shots and reports image plan without generating)
python3 generate_frames.py --prompts filmmaking_prompt.json --dry-run

# Run with evaluation and coherence checks enabled
python3 generate_frames.py --prompts filmmaking_prompt.json --evaluate

# Skip shots that already have generated keyframes in the directory
python3 generate_frames.py --prompts filmmaking_prompt.json --skip-existing
```

---

## 3. Visual Coherence Checks (FF ↔ LF)

When a shot requires generating both FF and LF stills (or when we have an extracted FF and a generated LF), they must represent a logical start-and-end transition.

If the visual gap between FF and LF is too large (e.g. character shifts outfits, background details warp, or a camera jump cut occurs), the video sampler will fail to interpolate smoothly and will produce visual glitching or morphing.

### Coherence Evaluation Prompt
The generated images are sent to the vision evaluator (OpenRouter Gemini 3.1 Flash Lite) with the following parameters:
1. **Spatial Continuity** (0-10): Is the environment/setting consistent?
2. **Character Continuity** (0-10): Are characters identical and recognizable in both frames?
3. **Logical Trajectory** (0-10): Can the motion prompt realistically connect frame A to frame B?
4. **Interpolation Difficulty**: One of `easy`, `medium`, `hard`, or `impossible`.

### Refinement Loop
* **Threshold for Success**: Overall score $\ge 7$ AND difficulty $\neq$ `"impossible"`.
* **If it fails**: The evaluator provides specific issues and fix instructions.
* **Anchor Strategy**: The pipeline treats the First Frame (FF) as the anchor. If coherence fails, the script adjusts the `last_frame_prompt` to align with the generated FF's visuals and regenerates the Last Frame (LF) (up to 3 retries, incrementing the seed).

---

## 4. File Structure of Phase 2 Outputs

Keyframe outputs are stored in the story directory:

```
story-to-video-filmmaking/{story-slug}/
├── characters/                # Neutral character reference sheets
├── scenes/                    # Keyframe Still Images
│   ├── film_001_shot001_ff.png
│   ├── film_001_shot001_lf.png
│   ├── film_001_shot002_lf.png  # (Shot 2 is continuation; FF is extracted)
│   └── ...
└── feedback/                  # Evaluation and coherence reports
    ├── film_001_shot001_coherence.json
    └── ...
```
