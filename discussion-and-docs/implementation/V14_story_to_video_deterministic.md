# V14 — Story to Video Deterministic Skill Implementation Start

**Date:** 2026-06-17  
**Status:** In Progress / Implementing  

---

## 1. Objectives

Implementation of the approved plan to create a fully scripted, deterministic story-to-video pipeline under `skills/story-to-video-deterministic` using the Google Agent Development Kit (ADK) and ComfyUI for generation.

## 2. Project Directory Layout

We are initializing the package skeleton with the following structure:
- `skills/story-to-video-deterministic/`
  - `SKILL.md`
  - `main.py`
  - `config.py`
  - `schemas/`
    - `blueprint.py`
    - `prompts.py`
  - `agents/`
    - `step1_director_script.py`
    - `step2a_blueprint_structure.py`
    - `step2b_blueprint_visuals.py`
    - `step3_character_prompter.py`
    - `step4_ff_prompter.py`
    - `step5_consistency_prompter.py`
    - `step6_lf_prompter.py`
    - `step7_motion_prompter.py`
  - `tools/`
    - `file_tools.py`
    - `comfyui_tools.py`
  - `scripts/`
    - `wave_organizer.py`
    - `wave_executor.py`
  - `system_prompts/` (markdown system prompts)
  - `requirements.txt`

## 3. Implementation Process

- [ ] Set up package files and directory structure.
- [ ] Define data models using Pydantic in `schemas/`.
- [ ] Build the ComfyUI and file tools.
- [ ] Implement the SequentialAgent steps using google-adk.
- [ ] Implement wave organizing and execution scripts.
- [ ] Test the integration.
