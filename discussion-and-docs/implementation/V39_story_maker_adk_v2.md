# V39 — Story Maker V2 ADK Multi-Agent Architecture

## Summary

Upgraded `skills/story-maker/` from a single-planner asyncio script to an ADK `Workflow` graph with specialized sub-agents, parallel prompter fan-out, dynamic shot reference strategy, and graph-native generation nodes.

## Architecture

| Phase | Agents / Nodes | Artifact |
|-------|----------------|----------|
| Planning | story_planner → audio_planner → scene_asset_planner | story_plan.json, audio_plan.json, scene_assets.json |
| Prompters (parallel) | character_sheet_prompter ∥ shot_reference_strategist ∥ motion_prompter | generation_specs.json |
| Validate | reference_integrity → validate_generation_specs | — |
| Generate | backgrounds → sheets → shot images → videos → concat | final_film.mp4 |

## Key additions

- **Shot Reference Strategist** — per-shot `generation_mode`, `reference_strategy`, `reference_slots`, Grok `image_prompt`
- **Scene backgrounds** — optional env plates for multi-shot scene consistency
- **Reference integrity** — 7-ref Grok limit, char sheets + background ordering
- **Resume router** — resumes from earliest missing artifact
- **I2V motion prompter** — LTX 2.3 native audio prose (not FFLF)

## Files

- `agents/` — 6 LlmAgents
- `prompts/` — split system prompts (story, audio, scene assets, char sheet, shot strategist, motion i2v)
- `schemas/plan.py` — StoryPlan, AudioPlan, SceneAssetsPlan
- `schemas/generation.py` — GenerationSpecs, ShotImageSpec, MotionSpec
- `scripts/nodes/` — resume_router, save, merge, reference_integrity, validate, generation
- `main.py` — Workflow graph + Runner

## Usage

```bash
cd skills/story-maker
python3 main.py --story "..." --name my_story
python3 main.py --story "..." --name my_story --stop-before-generation
python3 main.py --story "..." --name my_story --fresh
```

## Tests

```bash
cd skills/story-maker
python3 -m unittest discover -s tests -v
```
