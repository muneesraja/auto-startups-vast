# Story-to-Video Cinematic Pipeline (V11) — Dynamic Duration Estimator & Character sheet Proposal

This document records the progress of planning the **`story-to-video-cinematic`** pipeline for **`rabbit-forest-rescue`** using a dynamic duration estimation step.

---

## 1. Goal & Requirements

*   **Story**: `rabbit-forest-rescue` (8 shots parsed from [Story.md](file:///Users/muneesraja/Documents/growthlabs-vault/story-to-video-cinematic/rabbit-forest-rescue/Story.md)).
*   **Video Budget**: Under 2 minutes. Dynamic duration assigned per shot (2s to 8s) depending on spatial movement complexity to prevent FFLF hallucinations.
*   **Style**: 3D Pixar-style model aesthetic.
*   **Pipeline Models**: Flux Klein 9B, Ideogram 4, LTX 2.3.
*   **Variables**: Environment variables (`OPENROUTER_API_KEY`, `COMFYUI_AUTH`, `COMFYUI_URL`) configured in `.env`.

---

## 2. Character Reference Sheet Specifications

We propose three character turnaround sheets (transparent background, 7-element layout) using Ideogram 4:

1.  **Bramble**:
    *   *Prompt*: `Professional character reference sheet for Bramble the baby rabbit. Front view, 3/4 view, and side profile. A tiny cute baby rabbit with soft brown fur, oversized floppy ears, large dark expressive eyes, and a fuzzy white tail. Clean plain light-grey background, studio lighting, 3D Pixar-style rendering, high detail textures.`
    *   *Descriptor*: `the baby rabbit with oversized floppy ears`
2.  **Clover**:
    *   *Prompt*: `Professional character reference sheet for Clover the mother rabbit. Front view, 3/4 view, and side profile. A gentle adult female rabbit with soft grey fur, wearing a tiny knitted green collar around her neck, kind dark eyes. Clean plain light-grey background, studio lighting, 3D Pixar-style rendering, high detail textures.`
    *   *Descriptor*: `the grey mother rabbit wearing a green collar`
3.  **Hazel**:
    *   *Prompt*: `Professional character reference sheet for Hazel the father rabbit. Front view, 3/4 view, and side profile. A sturdy adult male rabbit with thick brown fur, strong build, intelligent eyes. Clean plain light-grey background, studio lighting, 3D Pixar-style rendering, high detail textures.`
    *   *Descriptor*: `the sturdy brown father rabbit`

---

## 3. Dynamic Duration Architecture

Rather than assigning a static 5s duration per shot, we will execute a dynamic estimation step using a new Python script: `scripts/estimate_durations.py`.

### Analysis & Estimation Prompts
The script will request `openai/gpt-4o-mini` via OpenRouter to evaluate each shot and output a JSON dictionary:
*   **2 seconds**: Expression shifts, nose twitching, head tilts, looking up (micro-motions).
*   **3 to 4 seconds**: Short camera pans, slow zoom-ins, extending a paw toward something.
*   **5 to 6 seconds**: Walking a short distance, thumping to warn others, prying up a root.
*   **7 to 8 seconds**: Long traversals or multi-step physical displacements.

The estimated durations will be directly written into the `overrides.segment_duration` parameter in `cinematic_prompt.json`.

---

## 4. Next Steps

1.  Obtain user approval on this updated implementation plan and the proposed character sheet prompts.
2.  Create `scripts/estimate_durations.py` and run it to produce `cinematic_prompt.json` and `director_log.json`.
3.  Present the calculated dynamic durations to you for final validation.
4.  Launch the Wave execution pipeline.
