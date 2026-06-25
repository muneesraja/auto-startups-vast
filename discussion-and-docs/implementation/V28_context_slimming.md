# V28 — Context Slimming: Per-Agent Blueprint Projection

## Overview

To prevent API timeouts, hangs, and excessive latency when using models with smaller context windows/limits (such as MiniMax-M3) as fallback reasoning or generation models, we implement **Context Slimming**. Instead of injecting the entire `director_visual_blueprint.json` (which can scale past 150,000 characters) to every downstream agent, we project specific, minimal subsets of the blueprint tailored to each agent's direct needs.

## Architectural Changes

1. **Blueprint Projections Utility (`blueprint_projections.py`)**:
   - A single utility module containing projection logic for each downstream agent.
   - Trims verbose fields (such as generation paths, nested prompt statuses, image/video URLs, and unused prompt details).

2. **Agent-Specific Slicing**:
   - **Step 3 (Character Prompter)**: Receives only `meta` styles/aesthetics and the character names/descriptions.
   - **Step 4.5 (Spatial Mapper)**: Receives per-shot `shot_id`, `characters_present`, `ff.description`, `lf.description`, and `continuation_from_previous`.
   - **Step 4 (FF Prompter)**: Receives per-shot `shot_id`, `ff` description/framing/expressions, `characters_present`, `continuation_from_previous`, plus scene environment context.
   - **Step 5 (LF Delta Planner)**: Receives per-shot descriptions and scene environment contexts.
   - **Step 5.5 (LF Prompter)**: Receives per-shot `lf` description/framing/expressions/delta, `characters_present`, `use_ff_as_lf_reference`, plus scene context and character appearances.
   - **Step 6 (Motion Prompter)**: Receives per-shot metadata, duration, characters, director notes, and descriptions.

3. **Config timeout alignment**:
   - Ensure reasoning model timeout is robust (e.g. 120s or 300s).

---

## Verification Plan

### Automated Tests
- Run `pytest skills/story-to-video-cloud/tests/` to ensure no regression in schemas or flow execution.
- Create tests validating the outputs of the new blueprint projection functions.
