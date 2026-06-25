# V34 — 6–12s Shot Duration & Conversational LF Prompting

Progress summary of the story-to-video-cloud pipeline update.

## Context & Objectives
We overhauled the shot duration constraints and prompting strategies to prevent LTX-2.3 video generation hallucinations and align with the updated ComfyUI video execution capability.

Key objectives:
1. Enforce a 6–12 second range for shot durations across all system prompts, schemas, tools, and tests.
2. Keep continuation shots (`continuation_from_previous = true` and Wave 2) to allow generating super long scenes.
3. Align FF shot prompter descriptions with the exact visual descriptors in character sheet references to ensure visual character consistency.
4. Re-architect the LF shot prompter to use conversational/natural Grok Edit prompts, highlighting environment updates and secondary motion details (e.g., sea waves pattern changes, wind blowing leaves, background crabs/birds moving).

## Implementation Details

### 1. Schema & Tool Duration Guardrails
- **`blueprint.py`**: Changed `duration_seconds` field constraints from `Field(ge=2, le=5)` to `Field(ge=6, le=12)`.
- **`comfyui_tools.py`**: Updated `generate_ltx_video` default duration to 8s and updated docstrings.
- **`wave_executor_workflow.py`**: Updated default fallback duration to 8s.

### 2. System Prompt Adjustments
- **`director_script.md`**: Update duration guardrails to min 6s, max 12s, default 8s (action), 6s (reaction), 10-12s (establishing/wide). Emphasized meaningful action planning. Kept continuation shot chain guidelines.
- **`blueprint_structure.md`**: Updated duration constraint verification rules to 6–12s. Updated examples.
- **`fflf_visual_planner.md`**: Updated delta guidelines for 6-12s.
- **`blueprint_visuals.md`**: Overhauled the delta taxonomy to match the 6-12s ranges: 6-7s (moderate), 8-9s (standard), 10-12s (large).
- **`lf_delta_planner.md`**: Updated duration-aware planning rules and removed the `no-change` delta type. Added rules to explicitly plan environmental micro-motions.
- **`ff_shot_prompter.md`**: Added a rule to echo character sheet appearance descriptors for visual consistency.
- **`lf_shot_prompter.md`**: Re-architected prompt layout to natural conversational style instructions including environmental details & secondary motion rules.
- **`motion_prompter.md`**: Updated motion prompt length guidance to 6-10 sentences to cover multi-beat action arcs over 6-12 seconds.

### 3. Tests
- Updated `test_schemas.py`, `test_blueprint_projections.py`, and `test_validate_prompts.py` fixtures and assertions to use 8s durations and correct boundary validation.

## Verification
- Ran all automated unit tests: `pytest` completed successfully with all 17 tests passing.
- Ran dry-run pipeline with `--stop-before-generation` on the baby-dolphin test story and verified:
  - Visual blueprint output uses 8-second durations.
  - FF prompts include character sheet appearance anchors.
  - LF prompts correctly use the natural conversational edit instructions and detail secondary environmental motions (e.g. waves changing, sand glistening, wind blowing).
  - Motion prompts are extended (6-10 sentences).
