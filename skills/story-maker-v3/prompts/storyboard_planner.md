# Agent 3 — Storyboard Planner

**Input:** `<run_dir>/scenes.md` (one scene at a time) + `developed_story.md`.
**Output:** `<run_dir>/storyboard_<scene>.md` for each scene — the constrained 4×2
album plan (each LTX session still contains 4 panels, laid out as a 2×2 sub-block).
Then run
`python3 scripts/validate.py storyboard_<scene>.md --schema storyboard --scenes-path <run_dir>/scenes.md`
and fix until it passes.

## Job

For one scene, lay out **exactly 8 panels** in a **4 rows × 2 columns** album grid.
Each LTX Director session is still 4 panels, but it is rendered as a **2×2 sub-block**
inside the 4×2 sheet (session 1 = rows 1-2, session 2 = rows 3-4). Adjacent panels
in a session share a boundary frame. A new session block is a cut. You are
**planning, not drawing**: you compute numeric depth, positions, durations, and
motion deltas. The depth numbers are load-bearing — Agent 5 derives all camera
motion from them.

## Rules (the validator enforces every one)

- **Exactly 4 rows × 2 cols = 8 cells.** No more, no fewer. Each LTX session is a
  2×2 sub-block (rows 1-2 or rows 3-4).
- **Every cell has all 15 fields** (see the table below). No blanks.
- **`depth_per_char` is an integer 1-5**: 1 = closest to camera (foreground),
  5 = farthest (background). This is the field that makes motion deterministic.
  Compute it deliberately — it drives the camera.
- **`position_xy` = `[x, y]` with each coordinate in [0.0, 1.0]** (0=left/top,
  1=right/bottom). One coordinate pair per character present.
- **`duration_seconds` is an integer in [9, 15]**. Use 16-20 ONLY if this panel's
  clip will carry a genuine multi-beat Prompt Relay arc (then flag it; Agent 5 will
  set `allow_beats`). Default 10. The **sum of all 8 cell durations must equal the
  scene's `target_seconds`** (the validator checks this against scenes.md).
- **`characters_present` ⊆ scene `cast`.** Never invent a `char_NN` not in the
  scene's cast. A panel may show a subset of the cast (a solo close-up has one).
- **Continuity within a session.** Adjacent panels in the same LTX session must be a
  readable progressive morph: same cast/geography/lighting, evolving pose. A new
  session block may open on a new setup — it does NOT need to morph from the
  previous session's last panel.
- **Visible motion between adjacent columns.** If the same character or prop appears
  in two adjacent panels of a session, it must change position, expression, head
  angle, or limb pose enough that the frames read as consecutive animation keys,
  not duplicated stills. Write the `spatial_relation` and `must_not_show` fields so
  the painter cannot freeze the character.
- **Both delta tables + the handoff block are mandatory.**

## Output format (load-bearing — verbatim)

```
# Scene <scene_id> — <scene_title>
target_seconds: <int>
cast: [char_01, char_02, char_03]
location_ref_id: <lid>

## Row 1 (LTX session 1)
| col | shot_id | duration_seconds | characters_present | depth_per_char | camera_angle | position_xy | looks_at | expression | mood | intent | facing | angle | spatial_relation | must_not_show |
| 1 | s1_p1 | 10 | [char_01] | {char_01:2} | eye_level | {char_01:[0.5,0.5]} | char_02 | stern | tense | confront | forward | 15deg | char_01 centered in row-1 col-1, simple background | no second character, no props |
| 2 | s1_p2 | 10 | [char_01,char_02] | {char_01:3,char_02:2} | over_shoulder | {char_01:[0.3,0.5],char_02:[0.7,0.5]} | char_01 | alarmed | rising | defend | left | 0deg | char_02 now enters from right side, 40% gap between them | no third character |
| 3 | s1_p3 | 10 | [char_01,char_02] | {char_01:3,char_02:2} | eye_level | {char_01:[0.3,0.5],char_02:[0.7,0.5]} | char_02 | amused | playful | mock | right | 5deg | char_02 leans 15deg closer to char_01 than previous panel | no third character |
| 4 | s1_p4 | 10 | [char_01,char_02,char_03] | {char_01:3,char_02:2,char_03:4} | wide | {char_01:[0.3,0.5],char_02:[0.7,0.5],char_03:[0.5,0.8]} | char_03 | sad | somber | reveal | forward | 0deg | char_03 appears in deep background between char_01 and char_02 | no extra characters |

## Row 2 (LTX session 2)
| col | shot_id | duration_seconds | characters_present | depth_per_char | camera_angle | position_xy | looks_at | expression | mood | intent | facing | angle | spatial_relation | must_not_show |
| 1 | s1_p5 | 10 | [char_03] | {char_03:2} | close_up | {char_03:[0.5,0.5]} | none | tearful | sad | pity | forward | 0deg | char_03 centered close, blurred background | no other characters |
| 2 | s1_p6 | 10 | [char_01,char_02] | {char_01:2,char_02:2} | two_shot | {char_01:[0.4,0.5],char_02:[0.6,0.5]} | char_02 | guilty | tense | regret | left | 10deg | char_01 and char_02 face each other in row-2 col-2 | no char_03 |
| 3 | s1_p7 | 10 | [char_01] | {char_01:2} | medium | {char_01:[0.5,0.5]} | none | resolved | determined | resolve | forward | 0deg | char_01 alone in center of frame | no other characters |
| 4 | s1_p8 | 10 | [char_01,char_02] | {char_01:2,char_02:3} | wide | {char_01:[0.4,0.5],char_02:[0.6,0.6]} | char_02 | calm | calm | settle | right | 0deg | char_02 now one step back and to the right of char_01 | no third character |

## Inter-column motion deltas (row 1)
| from -> to | depth_delta | camera_motion_hint |
| s1_p1->s1_p2 | char_01: 2->3 (+1 recede) | push_in |
| s1_p2->s1_p3 | char_01: 3->3 (hold) | pan |
| s1_p3->s1_p4 | char_03: 4->4 (hold) | static |

## Inter-column motion deltas (row 2)
| from -> to | depth_delta | camera_motion_hint |
| s1_p5->s1_p6 | char_03: 2->2 (hold) | static |
| s1_p6->s1_p7 | char_01: 2->2 (hold) | static |
| s1_p7->s1_p8 | char_02: 2->3 (+1 recede) | push_in |

## Scene-end handoff -> scene s2
on_screen: [char_01, char_02]
positions: {char_01:[0.4,0.5], char_02:[0.6,0.6]}
facing: {char_01: left, char_02: right}
mood: calm
transition: hard_cut
```

### Field notes

- **Header names are exact.** The parser matches `## Row 1 (LTX session 1)`,
  `## Row 2 (LTX session 2)`, `## Inter-column motion deltas (row 1)`,
  `## Inter-column motion deltas (row 2)`, and `## Scene-end handoff -> scene <next>`.
  Keep these strings verbatim.
- **`shot_id` = `sN_pM`** where M is the panel's session-major index 1..8
  (p1..p4 = session 1, p5..p8 = session 2). The renderer resolves `sN_pM` → `panel_<r><c>`.
- **`col`** is 1..2 within each visual row; the 4 panels of a session occupy two
  visual rows (a 2×2 block).
- **`camera_angle`**: free text from a fixed vocabulary — `eye_level`,
  `over_shoulder`, `wide`, `close_up`, `two_shot`, `medium`, `low_angle`,
  `high_angle`, `dutch`. (No validation on this token; keep it consistent.)
- **`facing`**: `forward` | `left` | `right` | `back` | `away`.
- **`angle`**: a camera tilt like `0deg`, `15deg`, `-10deg`.
- **`spatial_relation`**: one concise phrase describing *where* the key elements
  are in relation to each other. Use distances and screen positions. This is the
  anti-deformation field — e.g. `horse stops 3m left of swing, father still in
  saddle, swing ropes not touching horse`, `parrot on girl's shoulder, dog on
  ground below swing`.
- **`must_not_show`**: a comma list of exactly what the image must NOT contain —
  e.g. `no body contact, no dismounted rider, no fully resolved smile, no horse
  touching swing ropes, no invented characters`. This is the anti-beat-jump and
  anti-hallucination field.
- **Delta tables:** one row per adjacent pair in the row (3 rows for a 4-col row).
  `depth_delta` is human-readable: `cid: A->B (+N recede)` / `(-N approach)` /
  `(hold)`. `camera_motion_hint` is the depth-delta→camera mapping
  (see motion_prompter.md): recede(+)→`push_in`, approach(−)→`pull_out`,
  hold→`static`/`pan`, cast grows→motivated `pan`/`turn`.
- **Handoff block:** `on_screen`, `positions`, `facing`, `mood`, `transition`
  (`hard_cut` | `match_cut`). The next scene's row 1 panel 1 should be drawable
  from this handoff (match-cut) or open fresh (hard_cut). For the LAST scene, still
  emit the block pointing at a sentinel or `transition: hard_cut` with the final
  state.

## Compute, don't draw

- Decide depth per character per panel from the staging: who steps forward, who
  retreats, who enters the frame. Depth CHANGES between adjacent panels are what
  drive the camera — make them intentional, not arbitrary.
- Sum the 8 `duration_seconds` and reconcile to the scene `target_seconds` BEFORE
  writing. Adjust panel durations (within [9,15], or [9,20] for a flagged arc) until
  the sum matches.

## Validate

```
python3 scripts/validate.py <run_dir>/storyboard_<scene>.md --schema storyboard \
  --scenes-path <run_dir>/scenes.md
```
Read `<run_dir>/storyboard_<scene>.md.validation.json`; fix every error and re-run
until `ok:true`. The validator catches: wrong cell count, missing fields, depth
outside 1-5, position outside [0,1], duration outside [9,20], invented characters,
missing `spatial_relation`/`must_not_show`, row/scene duration sum mismatch,
missing delta tables, missing handoff, and cross-checks the scene total + location
against scenes.md.