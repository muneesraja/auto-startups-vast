# V29 — Pipeline Speed Optimization: Fan-out Parallelization + Model Downgrades

## Overview

Implements two optimizations to reduce the prompt-generation pipeline wall-clock time from ~553s (~9 min) to ~307s (~5 min), a **~44% reduction**, before any image/video generation begins.

Based on ADK 2.0 docs review: `JoinNode`-based fan-out is the graph-native ADK pattern for parallelization. Memory, Context Compression, and `output_schema` enforcement were reviewed and ruled out as not applicable to our single-shot pipeline architecture.

---

## Changes

### 1. Fan-out Parallelization — `main.py`

After `save_blueprint_node`, the pipeline now fans out into **4 concurrent branches** instead of 6 serial steps:

| Branch | Nodes | Est. Wall Time |
| :--- | :--- | :--- |
| Branch 1 | `character_sheet_prompter` | ~25s |
| Branch 2 | `char_spatial_mapper` → `ff_shot_prompter` → `reference_integrity_ff` | ~52s |
| Branch 3 | `lf_delta_planner` → `lf_shot_prompter` → `reference_integrity_lf` | ~47s (with downgrade) |
| Branch 4 | `motion_prompter` | ~15s (with downgrade) |

A `JoinNode(name="join_prompts_node")` waits for all 4 branches before continuing to `save_prompts_node`.

**Resume routing updated**: `"prompts"` route now targets `save_blueprint_node` (the fan-out origin) instead of `character_sheet_prompter`, so all 4 branches fire correctly on resume.

### 2. Model Downgrades

| Agent | Before | After | Reason |
| :--- | :--- | :--- | :--- |
| `lf_delta_planner_agent` | `get_reasoning_model()` | `get_light_model()` | Output is 231B of simple enum values — no reasoning needed |
| `motion_prompter` | `get_reasoning_model()` | `get_light_model()` | 4-7 sentence descriptions; V28 slimmed context to 5KB, light model sufficient |

---

## Verification

```
pytest skills/story-to-video-cloud/tests/
```

**Status**: `17 passed` ✅ (no regressions from V28 baseline)

---

## Expected Performance

| Phase | V28 Baseline | V29 (expected) |
| :--- | :--- | :--- |
| Steps 1 + 1.5 + 2a + 2b | ~255s | ~255s (unchanged) |
| Post-blueprint steps | ~298s (serial) | ~47s (parallel critical path) |
| Total | **~553s** | **~302–322s** |
| Improvement | — | **~42–45% faster** |
