# V4 Repository Restructuring Plan — Progress Document

## Status: Completed & Verified

This document tracks the progress of the folder structure cleanup. All implementation steps, path configurations, documentation updates, and automated tests are fully complete and verified.

---

## Restructuring Overview

The repository folder layout was successfully revamped:
- Renamed `current-setup/skills/` to `skills/` at the root.
- Moved ComfyUI workflows under `workflows/`:
  - JSON templates live in `workflows/comfyui/`
  - Setup scripts live in `workflows/setup/`
- Removed empty `current-setup/` and `scripts/workflows/` folders.
- Cleaned up root `scripts/` and deleted obsolete monolithic `scripts/vastai-provision.py`.

---

## Implementation Checklist

- `[x]` Obtain user approval for the restructuring plan
- `[x]` Create `workflows/comfyui/` and `workflows/setup/` subdirectories
- `[x]` Move `current-setup/skills/` to `skills/` at the root
- `[x]` Move `current-setup/comfyui-workflows/*.json` to `workflows/comfyui/`
- `[x]` Move `scripts/workflows/*.sh` to `workflows/setup/`
- `[x]` Update configuration files:
  - `skills/vast-ai/scripts/config.py`
  - `skills/runpod-ai/scripts/runpod-provision.py`
- `[x]` Update workflow setup scripts:
  - `workflows/setup/cinematic-pipeline-setup.sh`
  - `workflows/setup/*.sh` (all 15 download scripts: updated GITHUB_BASE)
- `[x]` Update general scripts and config:
  - `skills/story-production-orchestrator/scripts/build_kanban_board.py`
  - `.gitignore`
- `[x]` Update skill reference documentation:
  - `skills/auto-startups-vast/SKILL.md`
  - `skills/workflow-researcher/SKILL.md`
  - `skills/vast-ai/SKILL.md`
  - `skills/runpod-ai/SKILL.md`
  - `README.md`
- `[x]` Create `skills/auto-startups-vast/scripts/relink_skills.sh`
- `[x]` Run validation tests (`verification_test.py`) to confirm no relative paths are broken
