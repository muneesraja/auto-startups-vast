# Workflow Alias Maintenance

## Rule

The `WORKFLOW_ALIASES` dictionary in `current-setup/skills/vast-ai/scripts/vastai-provision.py` maps friendly names to **actual filenames** in `scripts/workflows/`.

**Every alias target MUST point to a real file that exists in `scripts/workflows/`.**

## Current Valid Files (update this when adding workflows)

```
scripts/workflows/
├── _hf_download.sh          # Shared helper (not a workflow)
├── ltx-23-i2v-distilled.sh
├── ltx-23-i2v-keyframe.sh
├── ltx-23-prompt-relay.sh
├── qwen-image-edit.sh
└── wan-22-i2v-keyframe.sh
```

## When Adding a New Workflow

1. Create the `.sh` file in `scripts/workflows/` following the naming convention: `<model-family>-<version>-<variant>.sh`
2. Add aliases to `WORKFLOW_ALIASES` in `vastai-provision.py` — the alias values must exactly match the filename
3. Update this file's listing above
4. Update `SKILL.md` workflow aliases section if the workflow is user-facing

## When Removing or Renaming a Workflow

1. Update ALL aliases in `WORKFLOW_ALIASES` that reference the old filename
2. Update this file's listing
3. Verify no broken references: `grep -r "old-filename" current-setup/skills/ scripts/`
