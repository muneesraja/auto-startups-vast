# Story Production Orchestrator — v0.1 README

> **Status:** v0.1 ready for use. Tested on synthetic smoke-test story (June 12, 2026).

## What it does

Create a Hermes Kanban board for story production and dispatch tasks to the 6 specialist STV profiles. Supports two modes:

- **v0.1-hybrid (default):** 4-task board wrapping the v1.4.0 monolithic pipeline. Safe, validates routing + QC.
- **v1.0-native:** 12-task board with full v2.0 decomposition. Use after v0.1 has been validated.

## Quick Start

```bash
# 1. Make sure your story is in the work directory
ls /root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video-filmmaking/<story-slug>/
# Should contain: Story.md, story_manifest.json (optional for v0.1)

# 2. Run the orchestrator
python3 ~/.hermes/skills/creative/story-production-orchestrator/scripts/build_kanban_board.py \
    /root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video-filmmaking/<story-slug> \
    --mode v0.1-hybrid

# 3. Watch progress
hermes kanban boards switch <story-slug>   # make this board active
hermes kanban list                          # see all 4 tasks
hermes kanban tail <task-id>                # follow a specific task

# 4. When T3 hits the human gate, you'll get a notification
hermes kanban show t_<id>                   # see the gate status
hermes kanban unblock t_<id>                # approve and unblock
```

## What works (v0.1)

✅ **Pre-flight checks** — verifies all 6 profiles exist, ComfyUI reachable, OpenRouter key set
✅ **Board creation** — `hermes kanban boards create <slug> --switch`
✅ **Task creation** — 4 (v0.1) or 12 (v1.0) tasks with proper assignees, skills, bodies
✅ **Parent-child linking** — `hermes kanban link <parent> <child>` (positional args, NOT --parent/--child flags)
✅ **Auto-dispatch** — `hermes kanban dispatch` triggers immediate spawn (or wait 60s for tick)
✅ **Worker skill load** — verified worker can load assigned skill and enter running state
✅ **Human approval gate** — `kanban block <id> <reason>` → `kanban unblock <id> --reason <text>` works for `ready`/`running` tasks
✅ **Failure recovery** — `kanban reclaim <id>` aborts running worker and returns task to `ready`

## What's deferred (v1.0 / v2.1)

- ⏳ **v1.0-native 12-task board** — documented but not yet used in production. Run `--mode v1.0-native` after v0.1 has proven stable.
- ⏳ **Director's coach opt-in** — `--directors-coach {off,pre-review,per-shot}` is in the CLI but the per-shot vision logic is not yet implemented.
- ⏳ **Auto-retry on QC fail** — currently 1 retry max, then escalate. v2.1 will add prompt-refinement loop.
- ⏳ **Motion eval gate** (v2.1) — 5-image motion analysis via Flash Lite, too expensive for v0.1.
- ⏳ **Per-card cost tracking** — total cost is reported on completion, not per-card.

## Architecture

The v0.1 board is a 4-task linear pipeline:

```
T1 [stv-ops]       Run filmmaking_orchestrator.py (monolith)
  └→ T2 [stv-reviewer]  Run gemini_eval.py on output (per-image QC)
       └→ T3 [user]      Approval gate (review final film)
            └→ T4 [stv-ops]   ffmpeg concat + cleanup
```

The 6-profile roster is documented in `~/.hermes/profiles/` (v0.1-hybrid mode uses just `stv-ops` and `stv-reviewer`; the v1.0-native mode uses all 6).

## Cost Expectations

| Mode | Cost per film | Notes |
|---|---|---|
| v0.1-hybrid | ~$0.76 | Same as v1.4.0 monolith (no director's coach) |
| v1.0-native (no director) | ~$0.78 | +$0.02 for QC overhead |
| v1.0-native (pre-review director) | ~$0.91 | +$0.13 for director's coach |
| v1.0-native (per-shot director) | ~$1.07 | +$0.29 for full director's coach |

Default `--directors-coach=off`. Opt-in via flag.

## Smoke Test Results (2026-06-12)

Tested with `/tmp/smoke-test-story` (2-shot synthetic "red ball" story):

✅ Board `smoke-test` created via `boards create --switch`
✅ 4 tasks created with correct assignees (stv-ops, stv-reviewer, user, stv-ops)
✅ 3 parent-child links created via `kanban link <parent> <child>` (positional)
✅ Auto-dispatch triggered, T1 worker spawned and entered `running` state
✅ T1 worker loaded `story-to-video-filmmaking` skill (verified via `kanban show` skills field)
✅ T1 reclaimed cleanly (worker aborted, task returned to `ready`)
✅ Block/unblock cycle verified on a ready task (`t_53932bca` test task)

## Common Pitfalls

1. **Block doesn't work on `todo` tasks** — block requires `ready` or `running` state. Use `--initial-status blocked` when creating a task to start it in `blocked`.
2. **`kanban link` is positional, not flags** — `hermes kanban link <parent_id> <child_id>`, NOT `--parent X --child Y`.
3. **Active board is inherited** — `hermes kanban boards switch <slug>` once, then all subsequent `kanban create`/`list`/`show` commands use that board. Use `kanban list` (no `--board`) to verify.
4. **`--workspace dir:<path>`** — must use `dir:` prefix, not just the path. `dir:/tmp/story` works, `/tmp/story` does not.
5. **Reclaim requires running state** — `kanban reclaim` aborts a running worker. If the worker has already completed or never started, reclaim fails.
6. **Cloudflare tunnel + urllib = 403** — the v1.4.0 monolith uses `curl_json` correctly. Don't refactor to `requests` or `urllib`.

## References

- Implementation plan: `~/.hermes/plans/2026-06-12_054422-stv-multkan-v2.md`
- Cross-cutting spec: `~/.hermes/plans/2026-06-12_054422-stv-multkan-v2-cross-cutting-spec.md`
- Architecture decision: `~/.hermes/plans/2026-06-12_054422-stv-multkan-v2-architecture-decision.md`
- 3 LLM plans: `/tmp/plan-agy.md`, `/tmp/plan-glm51.md`, `/tmp/plan-kimi-k26.md`
- Kanban orchestrator skill: `~/.hermes/skills/devops/kanban-orchestrator/`
- v1.4.0 monolith: `~/.hermes/skills/creative/story-to-video-filmmaking/`

## v2.0 Migration Plan

| Story | Mode | Status |
|---|---|---|
| wolf | v1.4.0 (no migration) | 4/14 shots done, finishing with `--skip-existing` |
| rabbit race | v0.1-hybrid | Maiden flight for v0.1 (validates routing) |
| future stories | v1.0-native | After v0.1 is proven stable |

Wolf stays on v1.4.0 to avoid mid-flight migration. Rabbit race is the v0.1 maiden flight. Once v0.1 is proven, the next story can be v1.0-native.
