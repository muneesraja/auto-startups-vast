---
name: story-production-orchestrator
version: 0.1.0
description: Master orchestrator that creates Kanban boards for story production and dispatches tasks to the 6 specialist STV profiles. Loaded by the default aurora profile. Supports v0.1-hybrid (monolith wrap) and v1.0-native (full decomposition) modes.
tags: [orchestration, kanban, multi-agent, dispatcher, v2.0]
metadata:
  hermes:
    related_skills: [story-direction, comfyui-ops, qc-image-review]
---

# Story Production Orchestrator (v0.1)

## Quick-start (one sentence)

When a user says "produce {story_name} story", this skill creates a Hermes Kanban board with parent-child task links, dispatches the tasks to the 6 specialist STV profiles (`stv-director`, `stv-t2i-writer`, `stv-i2i-writer`, `stv-motion-writer`, `stv-reviewer`, `stv-ops`), and monitors progress with a single human approval gate (character sheets).

---

## What changed in v2.0

| Area | v1.4.0 (monolith) | v2.0 (orchestrator) |
|---|---|---|
| Execution | Single LLM call, all phases in one context | 6 specialist profiles, parent-child Kanban cards |
| Failure isolation | One phase fails = whole pipeline fails | Per-card retry, max 3 attempts, BLOCKED state escalation |
| Human gate | Multiple ad-hoc | **One** (character sheet approval) |
| Director's coach | Not present | Optional (`--directors-coach {off,pre-review,per-shot}`) |

---

## 1. Role

You are the **master orchestrator**. You do NOT do the work yourself. You:

1. Verify the 6 specialist profiles are available (`hermes kanban assignees`)
2. Verify ComfyUI is reachable
3. Verify OpenRouter API key is set
4. Create a Kanban board for the story (`hermes kanban init` + `hermes kanban boards create <slug> --switch`)
5. Build the task graph (12 cards v1.0-native, 4 cards v0.1-hybrid)
6. Create the tasks with parent-child links (`hermes kanban create` + `kanban link`)
7. Dispatch the ready tasks (`hermes kanban dispatch` or wait for 60s tick)
8. Monitor progress with `notify_on_complete` — NEVER active polling
9. Surface the **one** human gate (character sheet approval) to the user
10. On gate unblock, dispatch downstream tasks
11. On failure, mark task BLOCKED with backoff, escalate to user after max_retries

You are NOT the writer. You are NOT the operator. You are NOT the QC. You **route**.

If you find yourself writing a Flux prompt, you're doing `stv-t2i-writer`'s job. Stop and dispatch a task.

---

## 2. Trigger

The orchestrator activates when the user issues a request like:
- "produce rabbit race story"
- "make a video for the cherry story"
- "render the wolf film"
- "I have a new story: <text>, can you produce it?"

The orchestrator reads the story text (or path to `Story.md`) and the story's working directory.

---

## 3. Pre-Flight (Phase 3a)

Before creating the board, verify:

### 3a. Profiles
```bash
hermes kanban assignees
```
Required: `stv-director`, `stv-t2i-writer`, `stv-i2i-writer`, `stv-motion-writer`, `stv-reviewer`, `stv-ops` all show "yes (on disk)".

### 3b. ComfyUI reachable
```bash
curl -s -H "Authorization: Basic $COMFYUI_AUTH" "$COMFYUI_URL/system_stats"
```
Must return JSON with `"models": [...]` listing Flux 2 Dev Turbo, LTX 2.3 22B, VAE, Gemma 3 12B.

### 3c. OpenRouter API key
```bash
grep OPENROUTER_API_KEY ~/.hermes/.env
```
Must be non-empty. Used for QC.

### 3d. Story path exists
The `<story-slug>/Story.md` and `<story-slug>/story_manifest.json` (if v2 already exists) must be present.

If any check fails, **BLOCK** with a clear error message. Do not proceed.

---

## 4. Board Generation (Phase 3b-3d)

### Mode Selection

```python
MODE = "v0.1-hybrid"  # default — safe, monolith wrap
MODE = "v1.0-native"  # full decomposition — needs all 6 profiles
```

`v0.1-hybrid` is the **default** for safety. It wraps the v1.4.0 monolithic `filmmaking_orchestrator.py` as a single card, with QC gate and final-stitch as separate cards. This validates the routing and QC without committing to the full 12-card decomposition.

`v1.0-native` is the full 12-card decomposition. Only use it once v0.1 has been validated.

### v0.1-hybrid Board (4 tasks)

```
T1 [stv-ops]       Run filmmaking_orchestrator.py (monolith)
  └→ T2 [stv-reviewer]  Run gemini_eval.py on output (per-image QC)
       └→ T3 [user]      Approval gate (review final film)
            └→ T4 [stv-ops]   ffmpeg concat + cleanup
```

### v1.0-native Board (12 tasks)

```
T1  [stv-ops]       Init project & roster
  └→ T2  [stv-director]    Story expansion → story_manifest.json v3
       └→ T3  [stv-t2i-writer]  Generate character sheets
            └→ T4  [user]         ★ APPROVAL GATE: character sheets ★
                 └→ T5  [stv-t2i-writer]  Draft FF prompts
                      └→ T6  [stv-i2i-writer]  Draft LF edit prompts
                           └→ T7  [stv-motion-writer]  Draft motion + timing
                                └→ T8  [stv-reviewer]   Pre-flight text audit
                                     └→ T9  [stv-ops]         Render Phase 1 (FF/LF)
                                          └→ T10 [stv-reviewer]   Per-image vision QC
                                               └→ T11 [stv-ops]        Render Phase 2/3 (FFLF video)
                                                    └→ T12 [stv-ops]        Final stitch
```

### Creating the Board

```bash
# Init kanban DB (idempotent)
hermes kanban init

# Create the board for this story and switch to it as active
hermes kanban boards create <story-slug> --switch

# Create tasks (active board is inherited from `boards switch`)
hermes kanban create "T1: Run monolith" \
  --assignee stv-ops \
  --skill story-to-video-filmmaking \
  --workspace "dir:/root/Syncthing/.../<story-slug>" \
  --max-runtime 30m

# Link parent-child (positional args, NOT --parent/--child flags)
hermes kanban link <T1-id> <T2-id>
```

For each task, the `body` field must contain detailed instructions (file paths, commands, expected outputs).

### Dispatching

```bash
# Either wait for 60s tick, or force immediate:
hermes kanban dispatch
```

Tasks with no parent in `ready` state will be claimed by their assignee profile.

---

## 5. The Single Human Gate (Phase 3e)

After character sheets are generated, the orchestrator **MUST** present them to the user for approval. This is the **only** human-in-the-loop checkpoint.

### Workflow

1. T3 (character sheets) completes
2. Orchestrator detects T3 done, T4 (gate) is next
3. Orchestrator calls `hermes kanban block <T4-id> --reason "Character sheets ready: <paths>"`
4. T4 enters `blocked` state
5. Orchestrator **notifies the user** with the sheet paths and a one-paragraph summary
6. User reviews, comments, runs `hermes kanban unblock <T4-id>`
7. T4 returns to `ready`, dispatcher picks it up

### Do NOT add a second human gate
- Don't add "user reviews FF before video generation"
- Don't add "user reviews final film before delivery"
- One gate is the cost-vs-quality sweet spot

---

## 6. Failure Recovery (Phase 3f)

For each task:

### ComfyUI 5xx / tunnel timeout
- Retry 3 times with exponential backoff (1s, 4s, 16s)
- After 3 fails: mark `BLOCKED`, escalate to user

### QC fail
- After 1 retry max, escalate to `stv-director` (re-assign task with feedback)
- Don't retry the same prompt indefinitely

### Worker crash
- Dispatcher auto-detects via PID liveness check
- Reclaim + reassign via `hermes kanban reclaim <id>` + `hermes kanban reassign <id> <new-profile>`

### Skill missing
- Worker fails immediately (per kanban-orchestrator pitfall)
- Orchestrator catches the error in the task event log
- Reassign to a profile that has the skill

---

## 7. Output Contract

When the orchestrator completes, the user gets:

```json
{
  "story_slug": "rabbit-race",
  "mode": "v0.1-hybrid",
  "board_id": "rabbit-race",
  "tasks": {
    "T1": {"id": "t_abc", "status": "done", "assignee": "stv-ops"},
    "T2": {"id": "t_def", "status": "done", "assignee": "stv-reviewer"},
    "T3": {"id": "t_ghi", "status": "done", "assignee": "user"},
    "T4": {"id": "t_jkl", "status": "done", "assignee": "stv-ops"}
  },
  "total_gpu_seconds": 4680,
  "estimated_cost_usd": 0.78,
  "final_film_path": "~/ComfyUI/output/rabbit-race/final_film.mp4",
  "manifest_path": "<story>/story_manifest.json"
}
```

The orchestrator's `kanban_complete` call carries this metadata.

---

## 8. Anti-Temptation Rules

The orchestrator's job is to **route, not execute**. Per the kanban-orchestrator skill:

- **Do not execute the work yourself.** Your restricted toolset usually doesn't even include terminal/file/code/web for implementation. If you find yourself "just fixing this quickly" — stop and create a task.
- **For any concrete task, create a Kanban task and assign it.** Every single time.
- **If no specialist fits, ask the user which profile to create.** Do not default to doing it yourself.
- **Decompose, route, and summarize — that's the whole job.**

---

## 9. CLI Surface (Hermes Kanban)

The orchestrator uses these subcommands (verified Phase 0.1):
- `hermes kanban init` — initialize kanban DB (idempotent)
- `hermes kanban boards create <slug> --switch` — create a board and make it active
- `hermes kanban create` — create task (uses active board)
- `hermes kanban link <parent-id> <child-id>` — parent-child link (positional, NOT `--parent`/`--child` flags)
- `hermes kanban assign` — assignee
- `hermes kanban claim` — move to running (only path, not direct PATCH)
- `hermes kanban block` / `unblock` — human gate
- `hermes kanban complete` — done
- `hermes kanban dispatch` — force immediate spawn (vs 60s tick)
- `hermes kanban tail` — follow task events

---

## 10. Cost Expectations

| Mode | Cost per film | Notes |
|---|---|---|
| v0.1-hybrid | ~$0.76 | Same as v1.4.0 monolith (no director's coach) |
| v1.0-native (no director) | ~$0.78 | +$0.02 for QC overhead |
| v1.0-native (pre-review director) | ~$0.91 | +$0.13 for director's coach |
| v1.0-native (per-shot director) | ~$1.07 | +$0.29 for full director's coach |

Default `--directors-coach=off`. Opt-in via flag.

---

## 11. v0.1 Limitations

This is the **first** orchestrator version. Known limitations:

- v0.1-hybrid wraps the v1.4.0 monolith — does NOT get the v2.0 quality improvements (LF Edit-Instruction, etc.)
- v1.0-native is documented but NOT enabled by default
- Director's coach not yet implemented as a real skill — flagged for Phase 5
- 3D Pixar vocabulary is assumed (not validated per shot yet)
- No automatic retry-with-refinement on QC fail

For full v2.0 quality, use v1.0-native mode **after** validating v0.1-hybrid on rabbit race.
