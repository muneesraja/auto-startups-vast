# V6 Standalone Cinematic Skill — Progress Document

## Status: Completed

This document tracks the progress of making `story-to-video-cinematic` a fully standalone skill, moving other skills to `skills/deprecated/`, and running the prompt enhancement test for the `dog-chase-eagle` story.

---

## Implementation Checklist

- `[x]` Obtain user approval for the standalone migration & test plan
- `[x]` Copy template `ltx-23-fflf-seed-hunter.json` to local assets
- `[x]` Copy filmmaking scripts (`comfyui_api.py`, `workflow_builder.py`, `gemini_eval.py`, `filmmaking_utils.py`, `continuation_pipeline.py`, `fflf_executor.py`)
- `[x]` Clean up `sys.path.append(...)` lines in all 6 cinematic scripts
- `[x]` Update `cinematic_orchestrator.py` template loading locations
- `[x]` Move the other 10 skills in `skills/` to `skills/deprecated/`
- `[x]` Create `cinematic_prompt.json` and `director_log.json` for the `dog-chase-eagle` story
- `[x]` Test and output the LLM-enhanced prompts for `dog-chase-eagle`
- `[x]` Run unit tests for prompt enhancer
- `[x]` Run pipeline verification tests
