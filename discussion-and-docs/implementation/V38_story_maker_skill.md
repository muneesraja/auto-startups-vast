# V38 — Story Maker Skill (Simple I2V Pipeline)

## Summary

Added a new self-contained skill at `skills/story-maker/` — a simplified alternative to `story-to-video-cloud`. No FFLF, no blueprint/wave machinery. Linear pipeline: plan → character sheets → shot images → LTX 2.3 I2V videos → ffmpeg concat.

## Architecture

| Step | Tool | Output |
|------|------|--------|
| 1 Planner | ADK `LlmAgent` + `prompts/planner.md` | `plan.json` |
| 2 Character sheets | `xai/grok-imagine-image` (fal.ai) | `characters/*.png` |
| 3 Shot images | `xai/grok-imagine-image/edit` (fal.ai) | `images/*.png` |
| 4 Videos | ComfyUI LTX 2.3 I2V (`ltx-i2v.json`) | `videos/*.mp4` |
| 5 Combine | ffmpeg concat | `final_film.mp4` |

## Key files

- `main.py` — CLI + async orchestrator with resume flags
- `schemas/plan.py` — `Plan`, `Character`, `Scene`, `Shot`, `AudioCue`
- `prompts/planner.md` — pre-Director planning (style, shots, audio, transitions)
- `tools/fal_tools.py` — Grok T2I / Edit
- `tools/comfyui_tools.py` — `generate_ltx_i2v_video()`
- `tools/workflow_builder.py` — minimal `ltx_i2v` builder
- `tools/video_concat.py` — ffmpeg concat with audio re-encode
- `assets/workflow-templates/ltx-i2v.json` — API-ready I2V template

## Audio

LTX 2.3 generates audio natively. The planner embeds dialogue, music, SFX, and ambience in `motion_prompt` prose and a structured `audio` block per shot.

## Usage

```bash
cd skills/story-maker
python3 main.py --story "..." --name "my_story"
```

## Tests

```bash
cd skills/story-maker && pytest tests/
```
