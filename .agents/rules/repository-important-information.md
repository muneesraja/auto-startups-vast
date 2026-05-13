---
trigger: always_on
---

Always go through the @vast-ai/SKILL.md before adding/modifying any script
Always go through the @workflow-researcher/SKILL.md before creating workflow download scripts from ComfyUI JSON files
Always go through the @story-to-video/SKILL.md before producing story illustrations, character sheets, or video prompts from stories

## Workflow Naming Convention (MANDATORY)

When creating or renaming ANY file in `scripts/workflows/` or `current-setup/comfyui-workflows/`, the name MUST follow this format:

  <model-family>-<version>-<variant>

Rules:
- All lowercase, hyphen-separated (kebab-case) — no underscores, no dots, no spaces
- Model family first: ltx, wan, qwen
- Version next (no dots, no v prefix): 23 = 2.3, 22 = 2.2
- Variant/mode last: i2v, t2v, keyframe, prompt-relay, image-edit
- The JSON workflow file and its download script MUST share the exact same base name
- Shared helper scripts MUST be prefixed with underscore: _hf_download.sh

Examples: ltx-23-i2v-keyframe.sh / ltx-23-i2v-keyframe.json
          ltx-23-prompt-relay.sh / ltx-23-prompt-relay.json
          wan-22-i2v-keyframe.sh

See @workflow-researcher/SKILL.md section 0.2 for the full reference table.