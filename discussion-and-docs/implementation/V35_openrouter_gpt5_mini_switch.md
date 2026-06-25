# V35 — OpenRouter GPT-5 Mini Model Migration

Progress summary of the story-to-video-cloud model selection update.

## Context & Objectives
To improve generation speed and reasoning capabilities, and to resolve the timeouts encountered with MiniMax models (e.g. `MiniMax-M3`), we migrated the orchestrator and prompter reasoning and light models to run `openai/gpt-5-mini` via OpenRouter.

Key objectives:
1. Support `OPENROUTER_API_KEY` directly in `config.py` for model initialization.
2. Route both reasoning and light models to `openai/gpt-5-mini` via OpenRouter if `OPENROUTER_API_KEY` is present.
3. Ensure timeouts for OpenRouter calls are set to a comfortable `300` seconds to prevent API timeouts during large shot-by-shot generation workflows.

## Implementation Details

### 1. Model Configuration Overhaul
- **`config.py`**:
  - Updated `get_reasoning_model()` to check for `OPENROUTER_API_KEY` first. If present, it initializes `LiteLlm` with `model="openai/gpt-5-mini"`, `api_base="https://openrouter.ai/api/v1"`, and a timeout of `300` seconds.
  - Updated `get_light_model()` to similarly prioritize `OPENROUTER_API_KEY` with `openai/gpt-5-mini` and a `300` seconds timeout.
  - Updated `get_validation_model()` to prioritize `OPENROUTER_API_KEY` with `google/gemini-3.1-flash-lite`.

### 2. Job Cleanup
- Cancelled the running pipeline task `task-1055` which was using `MiniMax-M3` to allow transition to `openai/gpt-5-mini`.

## Verification
- Ran all automated unit tests: `pytest` completed successfully with all 17 tests passing.
