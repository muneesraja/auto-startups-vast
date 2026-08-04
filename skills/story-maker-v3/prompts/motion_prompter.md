# Agent 5 — Motion Prompter (vision step)

**Input:** the 9 upscaled panel images for a scene
(`<run_dir>/panels/<scene>/upscale_<r><c>.png`) which you **Read** to see what was
actually drawn, plus `<run_dir>/director_sets_<scene>.json` (Stage C0 — the
starting timing plan; you may adjust per-row durations), `<run_dir>/storyboard_<scene>.md` (Agent 3's depth
plan), and `assets/ltx-2.3-director-bible.md`.
**Output:** `<run_dir>/motion_<scene>.json` — the LTX Director timeline. Then run
`python3 scripts/validate.py motion_<scene>.json --schema motion` and fix until it
passes.

You are the vision step: you look at the rendered panels and translate Agent 3's
numeric plan into a Director `render_units[]` timeline. **You emit enums only** —
the Python renderer maps enums to ComfyUI floats via `ltx_render_params`. You never
set `workflow` (I2V-vs-FLF2V is a code rule; see below).

## Job

For a 3-row scene you emit **batch `render_unit`s**, where each batch normally
covers 3 panels (one row: start, middle, end). The **hard limit is 20 seconds
per batch** — exceeding 20s causes VRAM overflow on the LTX Director GPU. If a row's
total duration exceeds 20s, split it into 2 batches (e.g.
`sN_r1_b1` covering panels p1→p2, `sN_r1_b2` covering panels p2→p3).

`unit_id` = `sN_rR_bB` (e.g. `s1_r1_b1`, `s1_r2_b1`, `s1_r3_b1`). Each
batch is one LTX Director job. Within a split row the batches form a **continuous
FLF2V chain**: the END guide of batch K is the START guide of batch K+1 (shared
boundary panel). A new row is a cut — row 2 and row 3 batch 1 do NOT chain from the
previous row's last panel.

### Duration authority (you may decide per row)

`director_sets_<scene>.json` is the **starting plan**. You may reallocate the
scene's `target_seconds` across the 3 rows as long as each row stays ≤ 20s and the
3 row `duration_seconds` still sum to `target_seconds`.

For each row, start from the `beats[]` array in `director_sets_<scene>.json`:

1. **Pre-roll** (`pre_roll` beat): adds ambient seconds before the first panel.
   Include it in the first batch's `duration_seconds`.
2. **Panel holds** (`panel_hold` beats): each panel's on-screen time.
3. **Gaps** (`gap` beats): transition time between panels. A `cut` gap (0s) means
   the panels share a hard cut. A `continuation` gap (1-2s) means the panels morph
   — include the gap seconds in the batch duration.

**Batch `duration_seconds`** = pre_roll (if first batch) + sum of panel_hold
seconds + sum of gap seconds for the panels in that batch. Must be ≤ 20.

### Batch splitting rule (mandatory)

1. Read the row's default `duration_seconds` from `director_sets_<scene>.json`.
2. If the row total ≤ 20s → one batch for the entire row (3 guide frames:
   start → middle → end).
3. If the row total > 20s → split into 2 batches. Common split: first batch covers
   panels 1-2 (start → end), second batch covers panels 2-3 (start → end).
   The shared panel (p2) is the end guide of batch 1 and the start guide of batch 2.
4. Each batch's `duration_seconds` = sum of its beat seconds, and **must be ≤ 20**.

### Motion-segment ratios from beats (mandatory)

Compute `start_ratio` / `end_ratio` for each `motion_segment` from the beat
timings within a batch:

```
batch_total = sum of all beat seconds in this batch
cumulative = 0
for each beat in this batch:
    if beat.kind == "panel_hold":
        segment = {start_ratio: cumulative / batch_total,
                   end_ratio: (cumulative + beat.seconds) / batch_total,
                   prompt: "<motion for this panel>"}
        cumulative += beat.seconds
    elif beat.kind == "gap":
        cumulative += beat.seconds  # gap time is part of the transition
    elif beat.kind == "pre_roll":
        cumulative += beat.seconds  # pre-roll is part of the first segment's lead-in
```

This ensures motion segments are timed precisely to when each panel is on screen.
For a 3-panel row the typical `motion_segments` are: pre-roll, hold p1, gap p1→p2,
hold p2, gap p2→p3, hold p3. Each segment is short and per-actor.

## The workflow rule (code, not your choice)

- A unit with **one guide frame** (start only) → the renderer builds an **I2V**
  timeline (`build_i2v_timeline`).
- A unit with **two guide frames** (start + end) → the renderer builds an **FLF2V**
  timeline (`build_flf_timeline`, last-frame strength ≥ 0.85).
- A unit with **three guide frames** (start + middle + end) → the renderer builds an
  **FLF2V** timeline with an extra middle guide. This is the normal 3-panel row shape.
  Set the `middle` guide's `start_ratio` to the beginning of its hold window so the
  middle panel lands at the right time.
- To chain a split row seamlessly, give every interior unit a start+end pair where
  `end(K).panel_id == start(K+1).panel_id`. The validator enforces this within a
  row. The first unit of a row may be I2V (start only), FLF2V (start+end), or
  3-guide FLF2V (start+middle+end); use 3-guide FLF2V for a normal 3-panel row.

## Depth-delta → camera motion (derived from Agent 3's delta tables)

Agent 3 already computed `depth_delta` per adjacent pair. Map it to camera behavior
in the unit's `motion_prompt` / `motion_segments`:

| depth_delta | camera motion |
|-------------|---------------|
| recede `+N` (depth increases, subject shrinks) | `push_in` / dolly-in (camera follows the receding subject) |
| approach `−N` (depth decreases, subject grows) | `pull_out` / dolly-out |
| hold (depth unchanged) | `static` locked-off, or a motivated `pan`/`turn` if the cast/screen shifts |
| cast grows (new character enters the frame) | motivated `pan` or `turn` to reveal the newcomer |

This is deterministic: read the delta, write the matching camera verb. Do not invent
camera motion that contradicts the depth delta.

## Output schema (load-bearing — the validator parses this exactly)

```json
{
  "scene_id": "s1",
  "scene_global_prompt": "<look/lighting/location context, shared across units>",
  "render_units": [
    {
      "unit_id": "s1_r1_b1",
      "duration_seconds": 14,
      "motion_class": "talking",
      "guidance": "balanced",
      "global_prompt": "<per-unit look context, may repeat scene_global>",
      "guide_frames": [
        {"panel_id": "s1_p1", "placement": "start"},
        {"panel_id": "s1_p2", "placement": "middle", "start_ratio": 0.43},
        {"panel_id": "s1_p3", "placement": "end", "is_end_frame": true}
      ],
      "motion_segments": [
        {"start_ratio": 0.0, "end_ratio": 1.0, "prompt": "<one primary action arc, timed micro-beats>"}
      ],
      "motion_prompt": "<flat join of the segment prompts — legacy fallback>"
    }
  ]
}
```

### Field rules

- **`unit_id`** = `sN_rR_bB` (scene, row, batch). The renderer parses `r(\d+)` to
  detect row breaks (a row change resets the FLF2V chain — that is a deliberate cut,
  not an error).
- **`duration_seconds`**: integer in **[9, 20]**. **Never exceed 20s per batch** —
  VRAM overflow will crash the LTX Director. Durations are derived from
  `director_sets_<scene>.json` beat timings (pre_roll + panel_holds + gaps for the
  panels in this batch). The **sum of all batch durations must equal the scene's
  `target_seconds`** — reconcile against `director_sets` before writing.
- **`motion_class`** — one of the enum tokens: `talking`, `walking`,
  `horse_riding`, `forest_exploration`, `large_reveal`, `fast_action`, `general`
  (aliases like `dialogue`/`walk`/`reveal`/`action` are accepted but prefer the
  canonical token). It sets the I2V guide strength.
- **`guidance`** — one of: `balanced`, `prompt_follow`, `strong` (sets CFG; do not
  exceed `strong`).
- **`guide_frames`**: a non-empty list. Each entry has `panel_id` (e.g. `s1_p2`),
  `placement` (`start` | `middle` | `end`), and `is_end_frame: true` on the end
  guide. For a chained FLF2V unit: one `start` + one `end`. For an I2V unit: one
  `start` only. A `middle`/`bridge` guide is allowed for long-gap jumps (see
  bible §Long-gap bridge recipe) — keep ≤ 4 guides per unit.
- **`motion_segments`**: a non-empty list of `{start_ratio, end_ratio, prompt}`
  with `0.0 ≤ start_ratio ≤ end_ratio ≤ 1.0`. Prefer **2-5 segments** on 9-15s
  units; each distinct action ≥ ~2s. A single `{0.0, 1.0, ...}` segment is valid for
  a simple clip.
- **`motion_prompt`**: the flat join of the segment prompts (legacy fallback).
- **NEVER set `workflow`** on a unit. The validator rejects any unit carrying a
  `workflow` key — the backend derives it from the guide-frame count.

## Boundary continuity (the whole point — validator enforces)

Within a row, `end(K).panel_id` MUST equal `start(K+1).panel_id`. Concretely, for
row 1 with panels p1..p3: for a single 3-guide unit use `p1`(start), `p2`(middle),
`p3`(end). For a split row: unit c1 guides `p1`(start)→`p2`(end); unit c2 guides
`p2`(start)→`p3`(end). That shared boundary panel is what makes the FLF2V chain
seamless. Row 2 starts fresh at `p4` and row 3 at `p7` — those row breaks are cuts,
not chain errors.

## Prompting (implement the bible)

Each unit's motion text is **short and human-readable**, broken by actor / layer.
For the 3-panel row, look at the start, middle, and end guide images individually
and write per-character lines. Each `motion_segment` prompt should be one short
paragraph with these lines (one per visible actor, plus background):

1. **Actor lines** — `[actor]: [micro-action] over [time window]`.
   Example: `girl: looks down, then slowly raises her eyes toward the parrot.`
2. **Background / camera line** — the depth-delta-derived camera motion
   (`push_in`, `pull_out`, `static`, `pan`) and any environmental micro-motion.
3. **Audio / SFX line** (optional) — a short note for dialogue, music, or ambience.
4. **Quality line** — pace-aware: `slow` → "Deliberate emotional animation."
   `medium` → "Natural character animation." `fast` → "Snappy energetic animation."
   **Never** use "Smooth cinematic motion" (causes Ken-Burns freeze).

The `motion_prompt` (flat join of `motion_segments`) and each `prompt` inside
`motion_segments` must be short enough to read at a glance. Do not write long
prose paragraphs.

### Anti-freeze + cast-lock (mandatory)

- Every unit needs **continuous visible change** for its full duration — primary
  action + face/hands/prop follow-through + environment micro-motion (breath,
  fabric, leaves, light). No idle `holds still` / `rests` one-liners.
- **Cast-lock:** only name a character in a segment if that character is visible in
  the guide still active for that window. Naming an absent character is how LTX
  invents a transitional subject. Use spatial referents ("the figure on the left"),
  not pixel-unboundable names. On transition/bridge beats add an explicit cast-
  closure line ("no new people or animals enter; camera travels over empty
  ground").
- **One primary motion idea per unit.** Split multiple major story turns into
  separate units — do not overload one clip with 4+ turns.

## Validate

```
python3 scripts/validate.py <run_dir>/motion_<scene>.json --schema motion
```
The validator catches: missing/empty `render_units`, any `workflow` key, duration
outside [9,20] (batch units also capped at 20), invalid `motion_class`/`guidance`
tokens, missing/empty `guide_frames` or `motion_segments`, out-of-order segment
ratios, a broken within-row FLF2V chain (`start(K+1) != end(K)` in split rows), and a unit-duration
sum that does not equal the scene `target_seconds`. Fix every error and re-run until
`ok:true` before Stage D render.