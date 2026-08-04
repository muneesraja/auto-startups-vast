# Agent 3b — Director Set Planner

**Input:** `<run_dir>/storyboard_<scene>.md` (Agent 3) + `<run_dir>/scenes.md`.
**Output:** `<run_dir>/director_sets_<scene>.json` — the set timing plan.
Then run
`python3 scripts/validate.py <run_dir>/director_sets_<scene>.json --schema director_sets --scenes-path <run_dir>/scenes.md`
and fix until it passes.

## Job

For one scene, group the 9 storyboard panels into **3 sets of 3 panels each**
(set 1 = row 1 panels p1-p3, set 2 = row 2 panels p4-p6, set 3 = row 3 panels
p7-p9). For each set, define a default timing of when each panel appears on
screen using the fixed beat sequence below. These sets are the **starting plan**;
Agent 5 (motion prompter) may reallocate the scene's total seconds across the
three rows as long as each row stays ≤ 20s and the three `duration_seconds`
values still sum to `target_seconds`.

## Beat sequence (exactly 6 beats per set)

| Beat # | Kind          | Description                                      |
|--------|---------------|--------------------------------------------------|
| 0      | `pre_roll`    | Seconds of ambient footage before first panel    |
| 1      | `panel_hold`  | Panel 1 is held on screen                        |
| 2      | `gap`         | Transition between panel 1 and panel 2           |
| 3      | `panel_hold`  | Panel 2 is held on screen                        |
| 4      | `gap`         | Transition between panel 2 and panel 3           |
| 5      | `panel_hold`  | Panel 3 is held on screen                        |

## Timing constants (enforced by validator)

| Constant               | Value | Description                                  |
|------------------------|-------|----------------------------------------------|
| `PRE_ROLL_MAX`         | 2s    | Pre-roll can be 0-2s                         |
| `HOLD_MIN` / `HOLD_MAX`| 3-5s  | Each panel hold must be 3-5s                 |
| `GAP_CUT`              | 0s    | Hard cut / smash cut / jump cut = 0s gap     |
| `GAP_MAX`              | 2s    | Max gap for non-continuation transitions     |
| `GAP_CONTINUATION_MAX` | 2s    | Max gap for continuation transitions         |
| `SET_MAX`              | 20s   | One set's total must be ≤ 20s (LTX limit)    |

## Gap transitions

Each `gap` beat has a `transition` field:

- **`continuation`** — the next panel morphs from the previous (FLF2V chain).
  Gap: 1-2s.
- **`cut`** / **`smash_cut`** / **`jump_cut`** — hard cut. Gap: 0s.
- **`dissolve`** / **`fade`** — soft transition. Gap: 1-2s.

## Output schema (load-bearing — the validator parses this exactly)

```json
{
  "scene_id": "s1",
  "sets": [
    {
      "set_id": "s1_set1",
      "row": 1,
      "panels": ["s1_p1", "s1_p2", "s1_p3"],
      "duration_seconds": 14,
      "beats": [
        {"kind": "pre_roll", "seconds": 1},
        {"kind": "panel_hold", "seconds": 4, "panel_id": "s1_p1"},
        {"kind": "gap", "seconds": 0, "transition": "cut"},
        {"kind": "panel_hold", "seconds": 4, "panel_id": "s1_p2"},
        {"kind": "gap", "seconds": 1, "transition": "continuation"},
        {"kind": "panel_hold", "seconds": 4, "panel_id": "s1_p3"}
      ]
    },
    {
      "set_id": "s1_set2",
      "row": 2,
      "panels": ["s1_p4", "s1_p5", "s1_p6"],
      "duration_seconds": 14,
      "beats": [
        {"kind": "pre_roll", "seconds": 1},
        {"kind": "panel_hold", "seconds": 4, "panel_id": "s1_p4"},
        {"kind": "gap", "seconds": 1, "transition": "continuation"},
        {"kind": "panel_hold", "seconds": 4, "panel_id": "s1_p5"},
        {"kind": "gap", "seconds": 0, "transition": "cut"},
        {"kind": "panel_hold", "seconds": 4, "panel_id": "s1_p6"}
      ]
    },
    {
      "set_id": "s1_set3",
      "row": 3,
      "panels": ["s1_p7", "s1_p8", "s1_p9"],
      "duration_seconds": 13,
      "beats": [
        {"kind": "pre_roll", "seconds": 0},
        {"kind": "panel_hold", "seconds": 4, "panel_id": "s1_p7"},
        {"kind": "gap", "seconds": 0, "transition": "cut"},
        {"kind": "panel_hold", "seconds": 4, "panel_id": "s1_p8"},
        {"kind": "gap", "seconds": 0, "transition": "cut"},
        {"kind": "panel_hold", "seconds": 4, "panel_id": "s1_p9"}
      ]
    }
  ]
}
```

## Rules

1. **Exactly 3 sets per scene**, each with exactly 3 panels and 6 beats.
2. **Beat kinds must follow the exact sequence:**
   `pre_roll, panel_hold, gap, panel_hold, gap, panel_hold`.
3. **Each `panel_hold` beat has a `panel_id`** matching the storyboard's
   `shot_id` (e.g. `s1_p1`).
4. **`duration_seconds` of each set = sum of all beat seconds.** Must be ≤ 20.
5. **Sum of all 3 set `duration_seconds` = scene `target_seconds`** from
   `scenes.md`. Agent 5 may adjust the per-row allocation as long as this sum
   and the per-row ≤ 20s constraint are respected.
6. **Gap beats have a `transition` field** controlling the transition type.
7. **Pre-roll is 0-2s.** Use 0 for a hard open, 1-2 for a breath.

## Compute, don't guess

- Read the storyboard's delta tables to decide gap transitions: `hold` depth
  deltas → `continuation`; new setups → `cut`.
- Allocate hold durations based on narrative weight: dialogue panels 4-5s,
  action panels 3-4s, reveal panels up to 5s.
- Ensure each set total fits within `SET_MAX` (20s). Agent 5 can later adjust
  the per-row duration; your set is the default timing plan.

## Validate

```
python3 scripts/validate.py <run_dir>/director_sets_<scene>.json \
  --schema director_sets --scenes-path <run_dir>/scenes.md
```
The validator catches: missing sets, wrong panel count, wrong beat count,
wrong beat kind sequence, beat seconds outside allowed ranges, gap transition
mismatch (cut = 0s, continuation = 1-2s), set total ≠ beat sum, set total >
20s, and sum of set durations ≠ scene target_seconds. Fix every error and
re-run until `ok:true` before Stage C motion authoring.
