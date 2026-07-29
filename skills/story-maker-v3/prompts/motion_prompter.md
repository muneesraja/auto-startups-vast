# Agent 5 — Motion Prompter (vision step)

**Input:** the 8 upscaled panel images for a scene
(`<run_dir>/panels/<scene>/upscale_<r><c>.png`) which you **Read** to see what was
actually drawn, plus `<run_dir>/storyboard_<scene>.md` (Agent 3's depth plan) and
`assets/ltx-2.3-director-bible.md`.
**Output:** `<run_dir>/motion_<scene>.json` — the LTX Director timeline. Then run
`python3 scripts/validate.py motion_<scene>.json --schema motion` and fix until it
passes.

You are the vision step: you look at the rendered panels and translate Agent 3's
numeric plan into a Director `render_units[]` timeline. **You emit enums only** —
the Python renderer maps enums to ComfyUI floats via `ltx_render_params`. You never
set `workflow` (I2V-vs-FLF2V is a code rule; see below).

## Job

For a 2-row scene you emit **one `render_unit` per panel**, in row-major order:
`unit_id` = `sN_rR_cC` (e.g. `s1_r1_c1` … `s1_r2_c4` → 8 units). Each unit is one
LTX Director job. Within a row the units form a **continuous FLF2V chain**: the END
guide of unit K is the START guide of unit K+1 (shared boundary panel). A new row is
a cut — row 2 unit 1 does NOT chain from row 1's last panel.

## The workflow rule (code, not your choice)

- A unit with **one guide frame** (start only) → the renderer builds an **I2V**
  timeline (`build_i2v_timeline`).
- A unit with **two guide frames** (start + end) → the renderer builds an **FLF2V**
  timeline (`build_flf_timeline`, last-frame strength ≥ 0.85).
- To chain a row seamlessly, give every interior unit a start+end pair where
  `end(K).panel_id == start(K+1).panel_id`. The validator enforces this within a
  row. The first unit of a row may be I2V (start only) or FLF2V (start+end); choose
  FLF2V when you want it to land precisely on a known end panel.

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
      "unit_id": "s1_r1_c1",
      "duration_seconds": 13,
      "motion_class": "talking",
      "guidance": "balanced",
      "global_prompt": "<per-unit look context, may repeat scene_global>",
      "guide_frames": [
        {"panel_id": "s1_p1", "placement": "start"},
        {"panel_id": "s1_p2", "placement": "end", "is_end_frame": true}
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

- **`unit_id`** = `sN_rR_cC`. The renderer parses `r(\d+)` to detect row breaks
  (a row change resets the FLF2V chain — that is a deliberate cut, not an error).
- **`duration_seconds`**: integer in **[9, 15]** (use 16-20 only for a genuine
  multi-beat arc you flag in the storyboard; Agent 3 will have allowed it). The
  **sum of all unit durations must equal the scene's `target_seconds`** — copy the
  per-panel durations from `storyboard_<scene>.md` and reconcile before writing.
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
row 1 with panels p1..p4: unit c1 guides `p1`(start)→`p2`(end); unit c2 guides
`p2`(start)→`p3`(end); unit c3 guides `p3`(start)→`p4`(end). That shared boundary
panel is what makes the FLF2V chain seamless. Row 2 starts fresh at `p5` — that row
break is a cut, not a chain error.

## Prompting (implement the bible)

Each unit's motion text follows the bible's required paragraph structure:

1. **Open** — `A cinematic scene of ...` role + setting anchor of what is already
   visible in the start panel (do NOT re-describe appearance; the still has it).
2. **Sequential motion beats** — ordered physical micro-actions matching
   `duration_seconds`, timed with `over the first two seconds…` / `then…` /
   `by the midpoint…` / `in the final seconds…`.
3. **Camera** — the depth-delta-derived motion (push_in / pull_out / static / pan),
   in filmmaking terms. **Static camera for `talking`/dialogue units**; animate
   faces, lips, and gestures instead.
4. **Audio** — dialogue in quotes, music, SFX, ambience (LTX generates synced
   audio in-prose).
5. **Closing quality line** — pace-aware: `slow` → "Deliberate emotional
   animation. Soft natural motion."; `medium` → "Natural character animation.
   Expressive animated motion."; `fast` → "Snappy energetic animation. Quick
   dynamic motion." **Never** use "Smooth cinematic motion" (causes Ken-Burns
   freeze).

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
outside [9,20], invalid `motion_class`/`guidance` tokens, missing/empty
`guide_frames` or `motion_segments`, out-of-order segment ratios, a broken
within-row FLF2V chain (`start(K+1) != end(K)`), and a unit-duration sum that does
not equal the scene `target_seconds`. Fix every error and re-run until `ok:true`
before Stage D render.