# Arc Planner — Season Arc

**Input:** `stories/<series>/series.md` + `stories/<series>/series_state.json`.
**Output:** `stories/<series>/season_arc.md`.

## Job

Map the series' episode ladder into a rough 5-stage DOME arc across the
season's episodes. Detail ONLY the next 1–2 episodes — the rest stay as
loglines. This is DOME dynamic expansion: commit to structure, defer
specifics until the writer needs them.

## Rules

- **5-stage arc.** The season maps to Discovery → Open → Maintain →
  Escalate → payoff. Assign each episode to a stage. The arc does not
  need to be perfectly symmetric — some stages span more episodes than
  others.
- **Detail only next 1–2.** For the next 1–2 episodes to be written,
  provide a logline + tension value + threads opened/closed. For all
  other episodes, keep the series logline only. Do NOT pre-commit beats,
  shot lists, or sidecars — that is the episode writer's job.
- **Tension curve.** Assign each episode a tension value 0–1. The curve
  should be roughly monotone-ish: rising through the season with local
  dips for breathing-room episodes. No two adjacent episodes should have
  identical tension unless intentionally flat.
- **Thread bookkeeping.** Every thread opened in an episode must have a
  planned close in a later episode OR an explicit `parked` note with a
  one-line reason. See
  [`references/series-continuity.md`](../references/series-continuity.md)
  §Thread bookkeeping. No thread may silently vanish.
- **Read the series state.** Pull `canon.cast[]`, `canon.world_rules[]`,
  and `unresolved_threads[]` from `series_state.json`. The arc must
  resolve or advance existing unresolved threads; it must not contradict
  canon.
- **No new cast.** Do not introduce new characters in the arc plan. If
  the story needs one, flag it for the showrunner to add to the series
  bible first.

## Output format

```markdown
# Season Arc — <Series Name>

## Arc Overview
<2-3 sentence summary of the season's 5-stage shape>

## Episode Map

### Episode 1 — <stage: Discovery>
logline: <one sentence>
tension: 0.20
threads_opened: [<thread id>: <one-line description>]
threads_closed: []
notes: <optional — e.g. "introduces char_01 and char_02">

### Episode 2 — <stage: Open>
logline: <one sentence>
tension: 0.35
threads_opened: [<thread id>: <description>]
threads_closed: [<thread id>]
notes: ...

### Episode 3 — <stage: Maintain>
logline: <from series ladder — not detailed>
tension: 0.30
threads_opened: []
threads_closed: []
notes: deferred — detail when this episode is next

...

## Thread Ledger
| Thread id | Opened ep | Status | Planned close |
|---|---|---|---|
| <id> | 1 | open | ep 4 |
| <id> | 2 | parked | "deferred to season 2" |
```

## What invalidates the ledger

Reordering episodes after any detailed episode has been rendered breaks
`episode_end_states` continuity (episode N+1 was written against episode
N's rendered end state). To reorder, re-draft the affected episodes from
the new predecessor's end state. Changing a `threads_closed` entry after
finalization silently drops a thread — the director's audit will catch
this as a canon violation.
