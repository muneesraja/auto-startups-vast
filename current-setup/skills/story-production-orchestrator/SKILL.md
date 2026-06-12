---
name: story-production-orchestrator
version: 1.0.0
description: Master orchestrator that creates Kanban boards for story production and dispatches tasks to the 6 specialist STV profiles. Loaded by the default aurora profile. Supports v1.0-native mode (14 decomposed tasks) as default.
tags: [orchestration, kanban, multi-agent, dispatcher, v2.0]
metadata:
  hermes:
    related_skills: [story-direction, comfyui-ops, qc-image-review, flux-t2i-prompting, flux-edit-prompting, ltx-motion-prompting]
---

# Story Production Orchestrator (v1.0)

## Quick-start (one sentence)

When a user says "produce {story_name} story", this skill runs a profile readiness pre-flight check, creates a 14-card Hermes Kanban board with atomic parent dependencies, dispatches tasks to the 6 specialist STV profiles (`stv-director`, `stv-t2i-writer`, `stv-i2i-writer`, `stv-motion-writer`, `stv-reviewer`, `stv-ops`), and monitors progress with a character-sheet user approval gate.

---

## What changed in v2.0/v1.0

| Area | v0.1-hybrid (old) | v1.0-native (new) |
|---|---|---|
| Execution | 4 tasks wrapping monolith | 14 decomposed cards |
| T3 Assignee | `stv-t2i-writer` (failed ops work) | `stv-ops` (correctly renders sheets) |
| Linking | Post-hoc `hermes kanban link` (racy) | Atomic `--parent` on task creation |
| Pre-flight | Basic CLI assignee check | Strict profile readiness (`.env`, symlinks, provider) |
| Failure limit | Dispatcher default (2) | Tasks overridden with explicit budgets (80-100 turns) |
| Human gate | Post-hoc blocking | T4 created with `--initial-status blocked` |

---

## 1. Role

You are the **master orchestrator**. You do NOT do the work yourself. You:

1. Run the profile readiness gate (`verify_profiles.py`) to verify environment, symlinks, and providers for all 6 profiles.
2. Verify ComfyUI is reachable and OpenRouter API key is set.
3. Create a Kanban board for the story (`hermes kanban init` + `hermes kanban boards create <slug> --switch`).
4. Build the task graph (14 cards for v1.0-native).
5. Create the tasks with atomic parent links (`hermes kanban create --parent <parent-id>`).
6. Dispatch the ready tasks (`hermes kanban dispatch`).
7. Monitor progress via task completion logs (NOT active polling).
8. Surface the **one** human gate (character sheet approval) to the user when T3 completes.
9. On gate unblock, downstream tasks auto-promote.

You are NOT the writer. You are NOT the operator. You are NOT the QC. You **route**.

---

## 2. Trigger

The orchestrator activates when the user issues a request like:
- "produce rabbit race story"
- "make a video for the cherry story"
- "render the wolf film"
- "I have a new story: <text>, can you produce it?"

The orchestrator reads the story text (or path to `Story.md`) and the story's working directory.

---

## 3. Pre-Flight

Before creating any cards on the board, the orchestrator runs:

### 3a. Profile Readiness Check
Checks all 6 STV profiles (`stv-director`, `stv-t2i-writer`, `stv-i2i-writer`, `stv-motion-writer`, `stv-reviewer`, `stv-ops`):
- Directory exists under `~/.hermes/profiles/`
- `.env` exists with required keys (`MINIMAX_API_KEY`, `OPENROUTER_API_KEY`, `COMFYUI_URL`, `COMFYUI_USER`, `COMFYUI_PASS` depending on the profile)
- Skills symlinked inside `skills/creative/`
- `config.yaml` model provider is set to `custom:minimax-anthropic`

### 3b. Environment Variables
- `COMFYUI_URL` and credentials must be configured.
- `OPENROUTER_API_KEY` must be configured for the reviewer.

### 3c. Story path exists
The `<story-slug>/Story.md` must be present.

If any check fails, **ABORT** with exact instructions on how to fix the profile.

---

## 4. Board Generation

The default mode is `v1.0-native` (14 tasks).

### v1.0-native Board (14 tasks)

```
T1  [stv-ops]         Init project + verify ComfyUI/models
  └→ T2  [stv-director]     Story expansion → story_manifest.json v3
       └→ T3  [stv-ops]          Render character sheets
            └→ T4  [user]             ★ APPROVAL GATE: character sheets ★
                 └→ T5  [stv-t2i-writer]   Draft FF prompts
                      └→ T6  [stv-i2i-writer]   Draft LF edit prompts
                           └→ T7  [stv-motion-writer] Draft motion prompts
                                └→ T8  [stv-reviewer]    Pre-flight text audit
                                     └→ T9  [stv-director]    Director final review
                                          └→ T10 [stv-ops]         Render FF+LF stills
                                               └→ T11 [stv-reviewer]    Per-image vision QC
                                                    └→ T12 [stv-ops]         Render FFLF video
                                                         └→ T13 [stv-ops]         Continuity chain
                                                              └→ T14 [stv-ops]         Final stitch
```

### Creating the Board

```bash
# Init kanban DB (idempotent)
hermes kanban init

# Create the board and switch to it
hermes kanban boards create <story-slug> --switch

# Create task (atomic parent link, initial status)
hermes kanban create "T4: ★ APPROVAL GATE: character sheets ★" \
  --assignee user \
  --workspace "dir:/root/Syncthing/.../<story-slug>" \
  --parent <T3-id> \
  --initial-status blocked \
  --body "..."
```

---

## 5. The Single Human Gate

After character sheets are generated, the orchestrator **MUST** present them to the user for approval. This is the **only** human-in-the-loop checkpoint.

### Workflow

1. T3 (character sheets) completes.
2. T4 (approval gate) is already created as `blocked` on the board.
3. Orchestrator notifies the user with the reference sheet paths.
4. User reviews and runs `hermes kanban unblock <T4-id>`.
5. T4 enters `done`, auto-promoting T5.

---

## 6. Failure Recovery

### ComfyUI Timeout / Errors
- GPU tasks have `--max-retries 3` specified on card creation to tolerate transient failures.
- Non-transient issues escalate to `stv-ops` or block the task for manual intervention.

### Task Backfill
- If a task runs out of its iteration budget, it blocks. The orchestrator or user can update/reassign it via `hermes kanban edit` or `hermes kanban reassign`.

---

## 7. Output Contract

When the orchestrator completes, the user gets:

```json
{
  "story_slug": "panda-pippin",
  "mode": "v1.0-native",
  "board_id": "panda-pippin",
  "tasks": {
    "T1": {"id": "t_01", "status": "done", "assignee": "stv-ops"},
    "T2": {"id": "t_02", "status": "done", "assignee": "stv-director"},
    ...
    "T14": {"id": "t_14", "status": "done", "assignee": "stv-ops"}
  },
  "final_film_path": "/root/Syncthing/.../panda-pippin/final_film.mp4",
  "manifest_path": "/root/Syncthing/.../panda-pippin/story_manifest.json"
}
```

---

## 8. Anti-Temptation Rules

The orchestrator's job is to **route, not execute**.

- **Do not execute the work yourself.**
- **For any concrete task, create a Kanban task and assign it.**
- **Decompose, route, and summarize — that's the whole job.**

---

## 9. CLI Surface

The orchestrator uses these subcommands:
- `hermes kanban init` — initialize kanban DB
- `hermes kanban boards create <slug> --switch` — create active board
- `hermes kanban create` — create task (supports `--parent`, `--initial-status`, `--max-runtime`, `--max-retries`)
- `hermes kanban unblock <id>` — unblock gate
- `hermes kanban dispatch` — force dispatch tick

---

## 10. Cost Expectations

- `v1.0-native` costs ~$1.07 per film due to full multi-agent validation.
- GPU rendering cost is subject to ComfyUI node usage.

---

## 11. Profile→Skill Mapping

Always map STV profiles to these exact skill names during card creation:

| Profile | Skill Name (EXACT) |
|---|---|
| stv-director | `story-direction` |
| stv-t2i-writer | `flux-t2i-prompting` |
| stv-i2i-writer | `flux-edit-prompting` |
| stv-motion-writer | `ltx-motion-prompting` |
| stv-reviewer | `qc-image-review` |
| stv-ops | `comfyui-ops` |

---

## 12. Tight Task Body Template

Every task generated by the orchestrator must follow this structure:

```markdown
## Task: T<id> — <description>

### Setup
[Required environment sourcing and credentials]

### Helpers
[Specific scripts or modules allowed to be used]

### Success Criteria
[Specific, testable conditions and output files]

### Stop
[Clean exit condition]
```

For full v2.0 quality, use v1.0-native mode after validating v0.1-hybrid on rabbit race.
