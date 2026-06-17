# V5 LLM-Powered Ideogram Prompt Enhancer — Progress Document

## Status: In Progress

This document tracks the progress of adding an LLM-powered prompt generation phase to the cinematic pipeline.

---

## Problem

The current pipeline uses template-based prompt composition (`compose_character_sheet_prompt()` and `compose_scene_prompt()` in `ideogram_generator.py`) which produces generic Ideogram 4 JSON prompts. This results in suboptimal image quality because:
- No `color_palette` arrays
- No `art_style` vs `photo` key distinction
- Shallow element descriptions without action/emotion/spatial detail
- Hardcoded bounding boxes regardless of scene composition
- No pixel verification for aspect-ratio-aware positioning

## Research Source

Analysed the [awesome-ideogram-4.0-prompts](https://github.com/EvoLinkAI/awesome-ideogram-4.0-prompts/) repository (cloned to `temp/awesome-ideogram-prompts/`). Key discovery: **Case 15 — JSON Caption Generator** provides a complete system prompt for LLM→Ideogram JSON transformation with bbox pixel verification, vertical landmark guides, and framing rules.

---

## Implementation Checklist

- `[x]` Obtain user approval for the enhancement plan
- `[x]` Create `skills/story-to-video-cinematic/scripts/llm_prompt_enhancer.py`
- `[x]` Create system prompts for character sheets and scene stills
- `[x]` Integrate into `ideogram_generator.py` (fallback-safe)
- `[x]` Update `wave_executors.py` to pass LLM flag
- `[x]` Add `prompt_enhancer` config field to schema
- `[x]` Create reference doc `ideogram-llm-prompt-patterns.md`
- `[x]` Update examples and SKILL.md
- `[x]` Write unit tests with mocked API
- `[x]` Run verification tests
