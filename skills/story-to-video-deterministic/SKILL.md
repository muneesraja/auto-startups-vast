---
name: story-to-video-deterministic
version: 1.0.0
description: "Turn stories into highly consistent cinematic videos using a deterministic 9-step pipeline orchestrated by Google ADK and wave execution."
triggers:
  - deterministic
  - deterministic pipeline
  - story-to-video-deterministic
---

# v1.0.0 — Deterministic Story-to-Video Pipeline

This skill implements a fully scripted, deterministic story-to-video pipeline using Google ADK for structured orchestration and wave execution to minimize model swaps and ensure character consistency.

## Orchestration Flow
1. **Director Script** (google/gemini-3.1-pro-preview)
2. **Blueprint Structure** (google/gemini-3.1-pro-preview)
3. **Blueprint Visuals** (google/gemini-3.1-pro-preview)
4. **Character Sheet Prompter** (google/gemini-2.5-flash)
5. **FF Shot Prompter** (google/gemini-2.5-flash)
6. **Consistency Prompter** (google/gemini-2.5-flash)
7. **LF Shot Prompter** (google/gemini-3.1-pro-preview)
8. **Motion Prompter** (google/gemini-2.5-flash)
9. **Wave Organizer & Executor** (Pure Python, ComfyUI Job Runner)

## Usage
Run the pipeline programmatically or via python CLI by passing the story text:
```bash
python3 main.py --story "Your story content here" --name "story_output_dir_name"
```
