# Phase 3: FFLF Video Generation & Seed Hunting

This phase is handled by the `fflf_executor.py` script. The FFLF Seed Hunter workflow operates in multiple stages to optimize both motion quality and resolution, rather than performing a single-pass run.

---

## 1. Multi-Stage Video Generation Flow

The LTX 2.3 FFLF Seed Hunter workflow is divided into three distinct execution stages:

```
                  ┌───────────────────────────────┐
                  │ Upload Keyframes Still Images │
                  └───────────────┬───────────────┘
                                  ▼
      ┌───────────────────────────────────────────────────────┐
      │ Stage 1 (Seed Hunt): 3× Parallel Low-Res Samplers     │ (finish_mode = OFF)
      │ Generates: preview_0.mp4, preview_1.mp4, preview_2.mp4│
      └───────────────────────────┬───────────────────────────┘
                                  ▼
      ┌───────────────────────────────────────────────────────┐
      │ Select Best Motion (Auto-Evaluator or Interactive)    │
      └───────────────────────────┬───────────────────────────┘
                                  ▼
      ┌───────────────────────────────────────────────────────┐
      │ Stage 2: Spatial Upscale (2x Latent Upsampler)        │ (finish_mode = ON)
      └───────────────────────────┬───────────────────────────┘
                                  ▼
      ┌───────────────────────────────────────────────────────┐
      │ Stage 3: Full-Res Canvas Render (1080p or 720p)       │ (finish_mode = ON)
      └───────────────────────────────────────────────────────┘
```

### 1.1 Stage 1: Seed Hunting
Three samplers run concurrently on ComfyUI with seeds $S$, $S+1$, and $S+2$ (based on `seed_base`). By running `finish_mode = OFF`, the workflow builder strips the downstream upscaling/combining nodes, executing only the fast Stage 1 preview samplers.
This produces **three low-resolution, low-fps preview videos** displaying different motion behaviors for the exact same keyframe inputs.

### 1.2 Motion Selection
The pipeline evaluates which of the three previews exhibits the best motion path:
* **Auto Mode**: The `motion_evaluator.py` script extracts 5 evenly spaced frames from each video via FFmpeg and sends them to Gemini to rate motion fluidity, natural movement, FF→LF trajectory, and prompt adherence.
* **Interactive Mode**: The execution pauses, lists the paths to the 3 preview videos, and awaits user selection.

### 1.3 Stage 2 & 3: Final Render
Once the best preview index $N$ is chosen:
1. The script updates the workflow, setting `finish_mode = ON` and `selected_gen_index = N`.
2. The workflow queues on ComfyUI, passing the selected Stage 1 latent to the Stage 2 upscaler.
3. Stage 3 renders the final canvas, VAE decodes the latents, and saves the full-resolution video.

---

## 2. Executor Modes

The `fflf_executor.py` script provides three operational modes to fit different GPU resource constraints and user requirements.

### 2.1 Default Auto Mode
Fully automated. Runs Stage 1, auto-evaluates the three previews using Gemini, selects the best motion quality, and automatically invokes Stages 2 & 3.

```bash
python3 fflf_executor.py --prompts filmmaking_prompt.json
```

### 2.2 Interactive Mode (`--interactive`)
Pauses execution after Stage 1. Prints the preview paths so you can play them, then asks you to choose the index.

```bash
python3 fflf_executor.py --prompts filmmaking_prompt.json --interactive
```

### 2.3 Fast Mode (`--fast`)
Bypasses seed hunting entirely. Immediately queues a single ComfyUI call with `finish_mode = ON` and `selected_gen_index = 0`. Runs Stage 1 (first seed), 2, and 3 in a single pass without evaluations. **Use this for rapid prototyping.**

```bash
python3 fflf_executor.py --prompts filmmaking_prompt.json --fast
```

---

## 3. Command Line Interface Reference

```bash
# Basic generation
python3 fflf_executor.py --prompts filmmaking_prompt.json

# Process a specific shot only
python3 fflf_executor.py --prompts filmmaking_prompt.json --shot film_001_shot001

# Perform a dry-run (compile template and print details, no queue)
python3 fflf_executor.py --prompts filmmaking_prompt.json --dry-run

# Skip shots that already have a final video output file
python3 fflf_executor.py --prompts filmmaking_prompt.json --skip-existing

# Customize ComfyUI worker endpoint and output directory
python3 fflf_executor.py --prompts filmmaking_prompt.json \
  --url http://127.0.0.1:8188 \
  --output-dir ./videos
```
