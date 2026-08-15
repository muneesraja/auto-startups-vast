# Cutter — Clip Grid & Micro-Shots

**Input:** `<run_dir>/story.md` + `<run_dir>/bible.json` + target runtime.
**Output:** `ledger.arc` + `ledger.clips[]` (shots, hinges, quads — no
prompts yet).

## Job

Cut the treatment into a clip grid on the 17k+5 frame grid, then split
each clip into 6–9 micro-shots with hinges linking clips. This is the
structural skeleton of the entire video — timing, framing, and
continuity beats live here.

## Rules

- **DOME 5-stage arc → N clips.** Map the treatment's DOME arc to N
  clips. Default: 14 clips × ~14s = ~196s. Assign each clip a `stage`
  and `tension` (0–1) in `ledger.arc`.
- **CONCOCT vaguest-first pacing.** Open with the widest/least-detailed
  shots; progressively tighten framing and increase shot density as
  tension rises. The cold-open is an ECU or establishing wide; the
  climax is rapid CU/MCU alternation.
- **Frame grid.** Every clip's raw frame count must satisfy
  `length % 17 == 5` (the 17k+5 grid: 124, 243, 362, …). See
  [`references/plan-json-format.md`](../references/plan-json-format.md)
  §The Frame Grid. Use `duration_seconds` (rounds up to grid) or set
  `length` directly for frame-exact control.
- **`anchor_mode=head` delivery math.** Clip 1 delivers raw frames;
  clips 2+ deliver `raw − context_length` (default ctx=22). Every
  non-final clip must deliver ≥ `context_length` frames. Compute
  `delivered_frames` per clip and verify the cumulative total hits the
  target runtime.
- **6–9 micro-shots per clip.** Each shot 1.0–2.5s. The hinge shot
  (first shot of clip 2+) is 1.5–3.0s and is a continuation, never a
  hard cut. See
  [`references/micro-shot-grammar.md`](../references/micro-shot-grammar.md).
- **Hinge rule.** The last micro-shot of clip N and the first of clip
  N+1 are the SAME shot split across the boundary. Author both sides:
  `hinge_out` (clip N) and `hinge_in` (clip N+1) reference the same
  beat. Cut immediately after the hinge resolves.
- **No adjacent framing+angle repeat.** No two consecutive shots share
  both `framing` and `angle`. Rotate through ECU, CU, MCU, medium,
  wide, EWS, OTS, POV and eye-level, high, low, dutch, bird's-eye,
  worm's-eye. The validator enforces this.
- **One action per shot.** Exactly one dominant action (hard H3
  constraint). Every action beat is followed by a ≤1.5s reaction/face
  beat.
- **Sound per shot.** Every shot carries exactly one sound cue (SFX,
  vocal hit, or beat). The sound role fills this in detail later; here,
  assign the cue type.
- **Quads.** Emit DOME temporal-KG quadruples `[subject, action, object,
  shot_index]` per clip for the continuity graph.

## Output format

Emit `ledger.arc` and `ledger.clips[]` following
[`references/ledger-schema.md`](../references/ledger-schema.md). Each
clip object includes: `index`, `id`, `shots[]` (with `n`, `t`, `framing`,
`angle`, `action`, `sound`, `cast[]`, `on_beat`, `panel`), `hinge_out`,
`hinge_in`, `quads[]`. Leave `seed`, `sheet`, `sheet_prompt`,
`prompt_file`, `prompt_hash`, and `render` as null/pending — downstream
roles fill those.

## What invalidates the ledger

Changing any clip's `length`/`frames` after rendering invalidates that
clip and all later clips (the prefix checkpoint grows from that point —
see
[`references/checkpoint-contract.md`](../references/checkpoint-contract.md)).
Changing a hinge beat after the downstream clip is rendered breaks the
visual continuity at the seam — both clips must be re-rendered. Changing
shot framing/angle after sheets are generated invalidates the sheet
prompts (the drawn panels no longer match the plan).
