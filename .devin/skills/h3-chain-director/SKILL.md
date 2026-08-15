---
name: h3-chain-director
description: "Use when making long-form, fast-cut MiniMax H3 video via the seamless-chain workflow — story → micro-shot beat sheet → storyboard sheets → per-scene chain render → assemble."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [video, minimax-h3, comfyui, seamless-chain, story, storyboard, fast-cut, long-form, audio]
    related_skills: [minimax-h3-prompter, story-maker-v3]
---

# H3 Chain Director

## Overview

Turn a story brief into a 1–4 minute **fast-cut** video using the MiniMax H3 seamless-chain ComfyUI workflow (`workflows/comfyui/minimax-h3-seamless-chain-global-refs.json`). The skill orchestrates an **incremental, per-scene** pipeline: story → 5-stage arc → per-clip micro-shot beat sheet (6–9 cuts per clip) → 6-panel storyboard sheet per clip → one ComfyUI submission per scene, with a continuity ledger, deterministic validators, and single-pass critics between stages.

**The core idea — "chain of reels" + hinge shots.** Cuts live *inside* each generation (H3 Ref2VA's `detailed_description` supports `[Shot N] At MM:SS.mmm` cuts). The clip boundary is the *only* place continuity is forced, so a cut must never land on it: the last micro-shot of clip N and the first micro-shot of clip N+1 are **the same shot split across the boundary** (the *hinge*) — a held/simple-motion beat, then cut immediately after.

**Two tiers.** Tier 0 writes the story (series → episode). Tier 1 turns one episode into video. They are separate because Tier 0's output is exactly the artifact you already hand-author — `stories/<series>/episode-N.md` — so either tier can run alone.

## When to Use

**Trigger when the user:**
- Wants a long-form (1–4 min) video with fast cuts and audio
- References the seamless-chain workflow or "chained H3 clips"
- Has a story/episode file and wants it filmed
- Wants a music video with `source_track` audio continuity
- Wants to build a series with cross-episode character consistency

**Don't use for:**
- Single ≤15s clips (use `minimax-h3-prompter` + `story-maker-v3` directly)
- Non-H3 video models
- Pure image generation

## Pipeline (S0–S13 + gates)

### Tier 0 — series & episode writing

| Stage | Role | Artifact | Validator | Required? |
|---|---|---|---|---|
| **W0** Concept intake | — | brief | — | required |
| **W1** Series bible | Showrunner | `series.md` + `series_state.json` | canon schema, stable ids | required (new series) |
| **W2** Season arc | Arc planner | `season_arc.md` | tension curve, thread scheduling | required (new season) |
| **W3** Episode writer | Episode writer | `stories/<series>/episode-N.md` + `episode-N.meta.json` | `validate_story.py` | required (or skip if hand-written) |
| **W4** Story critics | Story critics | `episode-N.critique.md` | novelty, canon-lock, hook cadence | required (runs as audit if W3 skipped) |

**Key rule:** if the episode file already exists (hand-written), W3 is **skipped** and W4 runs as an **audit** of the human draft.

### Tier 1 — episode → video

| Stage | Role | Artifact | Validator | Required? |
|---|---|---|---|---|
| **S0** Brief | — | brief | — | required |
| **S1** Expander | Expander | `story.md` | — | required (skippable for re-cuts) |
| **S2** Bible lock | Bible keeper | `bible.json` | cast-lock, registry-first | required |
| **S3** Arc grid | Cutter | `ledger.arc` | frame grid, pacing | required |
| **S4** Beat sheet | Cutter | `ledger.clips[]` | pace/angle/hinge | required |
| **S5** Audio align | Sound/lyric | `ledger.audio` | wps, coverage | required for `source_track` (skip for `generated_audio`) |
| **S6** Critics | Critics | `critique.md` | continuity, retention, H3-format | required (collapsible into brief for short runs) |
| **S7** Sheet prompts | Sheet author | `sheet_prompts/clip_k.txt` | geometry, negatives | required |
| **S8** Assets | — | `assets/`, `sheets/` | registry-first, misses only | required |
| **GATE 1** | — | — | vision check: 6 panels, no text, same face | **human gate** |
| **S9** Plan | Prompt writer | `plan.json` | `validate_plan.py` (full) | required |
| **GATE 2** | — | — | low-res dial-in, then human go | **human gate** |
| **S10** Render loop | — | per-scene MP4s | auto-review (4 dims) | required |
| **S11** Ledger update | Reviewer | `ledger` (observed) | drift detection | required |
| **S12** Assemble | — | final video | — | required |
| **S13** QC | — | `qc.md` | `audit_cuts.py` | required |

### Fast path (≤45s or re-cuts)

W1/W2 skipped when a series bible already exists. W3 skipped when the episode file is hand-written (W4 still audits). S1 and S6 collapse into the brief. S5 skipped in `generated_audio` mode. S7/S8 can fall back to identity plates only.

### Three legal entry points

1. **"Make me a series"** → W0 (concept → bible → arc → episode → critique → film)
2. **"Make episode 4 of bamboo-the-dino"** → W2 (bible exists, arc extended, episode written)
3. **"Film this episode file"** → S0 (today's behaviour — episode prose → video)

## Micro-shot grammar (the fast-paced part)

Per clip (≈14.17s delivered), author **6–9 micro-shots**:

- Durations 1.0–2.5s; the **hinge** shot (first of every clip after clip 1) gets 1.5–3.0s and is a *continuation*, never a cut.
- **Action → reaction loop**: every action beat followed by a ≤1.5s reaction/face beat.
- **No two adjacent shots share framing+angle** (validator-enforced); rotate ECU / CU / medium / wide / OTS / low / high / POV.
- **Every shot carries one sound cue** — H3 generates audio natively and silence invites invention.
- **Exactly one dominant action per shot** (hard H3 constraint).
- `source_track` runs: cut timestamps **snap to beat onsets** (optional `beat_grid.py`).

Load `references/micro-shot-grammar.md` for the full grammar + worked example.

## Continuity ledger (`state.json`)

The ledger is the **single source of truth**; `plan_json` is *generated* from it (never hand-edited), which keeps the hashed fields of already-rendered clips frozen. `render.observed` is written by S11 from the rendered file, and is what the next clip's `hinge_in` and sheet are authored against — **planned state is never trusted over observed state**.

Load `references/ledger-schema.md` for the full field-by-field schema.

## Global asset registry (cross-cutting)

**Registry-first, always.** Before planning or generating any image, resolve `(series, entity_id, variant, lock_hash)`. An `approved` hit ⇒ **reuse the path, do not regenerate, do not re-review**. This is checked at S2 (bible lock) *and* S8 (asset build).

**A changed lock is a new variant/version, never an overwrite.** New episode puts the kid in a raincoat ⇒ `variant: "ep4_raincoat"` with its own `lock_hash`; `base` stays approved and reusable.

**`--force-regen` must name an `asset_id`.** A bare "regenerate all" is rejected by the CLI.

Load `references/asset-registry.md` for the full schema + 8 rules. CLI: `python3 scripts/assetctl.py {index|plan|resolve|add|approve|supersede|doctor|usage|list}`.

## Gates

- **GATE 1** — human visual sign-off of identity plates + all storyboard sheets. Only `draft` assets are shown; approving flips `status` and freezes the version.
- **GATE 2** — human go after a low-res dial-in pass (`--width 544 --height 320 --steps 5`), before full GPU spend.
- **Per-clip auto-review** inside S10 with a max-2-reroll policy (reroll seed → repair prompt → escalate to user).

## Presets

| Preset | Steps | LoRA | Sampler | Use case |
|---|---|---|---|---|
| **shipped-turbo** (default) | 5 | 0.95 | res_multistep + simple | fast, matches the shipped workflow |
| **reddit-quality** | 6 | 0.8 | euler + basic | higher quality, slower |

## The 5 workflow defects (the skill fixes or flags each)

1. **`<Picture 2>` cited but never wired** — `LoadImage 910` has zero output links. The validator flags this; the skill patches ref wiring at API time.
2. **No `prompt_prefix`** — all 14 shots duplicate identical blocks. The skill generates a `prompt_prefix` from the ledger.
3. **Hardcoded input filenames** (incl. a comma in the WAV name) — the skill resolves assets through explicit paths/registry metadata.
4. **No Review Gate** — correct for headless; the skill adds review at the Python layer (S11).
5. **Global references only** — the skill submits one scene at a time, swapping refs between submissions.

Load `references/workflow-anatomy.md` for the full node map + GUI fixes.

## Step-by-step runbook

### Tier 0 (if filming a new episode from scratch)

1. **W0 — Concept intake.** Ask the user for: series idea, audience, platform, episode length. Write a brief.
2. **W1 — Series bible.** Load `prompts/series_bible.md`. Write `series.md` + `series_state.json` with canon cast (stable `char_NN`/`loc_NN` ids), world rules, tone, episode ladder. Register cast/locations as `status: planned` in the global registry (`assetctl add --status planned`).
3. **W2 — Season arc.** Load `prompts/season_arc.md`. Write `season_arc.md` with a rough 5-stage arc; detail ONLY the next 1–2 episodes. Every opened thread has a planned close or explicit park.
4. **W3 — Episode writer.** Load `prompts/episode_writer.md`. Write `stories/<series>/episode-N.md` in the house style + `episode-N.meta.json` sidecar. **If the file exists, SKIP.**
5. **W4 — Story critics.** Load `prompts/story_critics.md`. Run `python3 scripts/validate_story.py episode-N.meta.json --prior-episodes stories/<series>/`. Fix until it passes.

### Tier 1 (filming an episode)

6. **S0 — Brief.** Confirm the episode file, target runtime, audio mode (`source_track` default), and series.
7. **S1 — Expander.** Load `prompts/expander.md`. Write `story.md` sized to the target runtime (14 clips × ~14s = ~196s default).
8. **S2 — Bible lock.** Load `prompts/bible.md`. Write `bible.json` with appearance locks, wardrobe, label assignment. **Registry-first:** resolve every cast id to `asset_id@version`. A lock mismatch is a hard error with a "create variant?" prompt.
9. **S3 — Arc grid.** Load `prompts/cutter.md`. Map the 5-stage arc to N clips on the 17k+5 frame grid (`length % 17 == 5`). Write `ledger.arc` + `ledger.clips[]` (without prompts yet).
10. **S4 — Beat sheet.** Author 6–9 micro-shots per clip + hinges. No adjacent framing+angle repeat. Write `ledger.clips[].shots[]`, `hinge_out`, `hinge_in`, `quads[]`.
11. **S5 — Audio align.** Load `prompts/sound.md`. Map lyric/dialogue lines to clip windows. Snap cut timestamps to beat onsets (optional: `python3 scripts/beat_grid.py --song <wav> --ledger state.json --apply`). Write `ledger.audio`.
12. **S6 — Critics.** Load `prompts/critics.md`. Run single-pass Continuity / Retention / H3-format critics. Fix until advisory or better.
13. **S7 — Sheet prompts.** Load `prompts/sheet.md`. Write `sheet_prompts/clip_k.txt` per clip: explicit 3×2 geometry, per-panel descriptions, inline negatives, ≤6 refs.
14. **S8 — Assets.** Run `python3 scripts/build_sheets.py --ledger state.json --series <series> --episode N`. Generates **misses only** (registry-first). Each success writes a version + cost to the registry.
15. **GATE 1.** Show the user all identity plates + storyboard sheets. Ask: "Do these look right? 6 panels, no text, same face?" Regenerate only affected sheets/panels. Approve via `assetctl approve --asset-id <id>`.
16. **S9 — Plan.** Load `prompts/clip_prompt.md`. Write `prompts_out/clip_k.txt` per clip (Ref2VA 6-section). Generate `plan.json` from the ledger (`chain_run.py` does this). Run `python3 scripts/validate_plan.py plan.json --ledger state.json --bible bible.json --song <wav> --ref-images <N>`. Fix until it passes.
17. **GATE 2.** Run a low-res dial-in: `python3 scripts/chain_run.py --ledger state.json --scene 1 --width 544 --height 320 --steps 5 --dry-run`. Show the user the `api_prompt.json`. Ask: "Ready to render?"
18. **S10 — Render loop.** For each scene k = 1..N:
    - `python3 scripts/chain_run.py --ledger state.json --scene k --song <wav> --refs anchor+sheet`
    - Auto-review the rendered segment (extract frames, vision read).
    - Accept | reroll seed | repair prompt | escalate. Max 2 rerolls.
    - **S11 — Ledger update.** Write `render.observed` from the rendered file. Update `hinge_in` for clip k+1. Re-author sheet k+1 if drift detected.
19. **S12 — Assemble.** `python3 scripts/assemble.py --run-name <run_name>`.
20. **S13 — QC.** `python3 scripts/audit_cuts.py --ledger state.json --run-dir output/h3_chains/<run_name>/`. Review the cut-rhythm audit. Report assets used, reused, generated, and total image spend.

## Pitfalls

- **H3 may not honour 6–9 cuts in 14s.** The prompter's own budget says 3–5 shots for 11–15s. If V5 smoke tests show drift, fall back to 4–5 cuts. `audit_cuts.py` measures the actual ceiling.
- **Per-clip sheet as `ref_image_1` could leak grid geometry.** The sheet prompt must state it's a storyboard whose panels are sequential shots, never a rendered layout.
- **Compatibility drift silently invalidates all clips.** The validator freezes `compatibility` once clip 1 is accepted; changing it forces a new `run_name`.
- **Sheets are non-reproducible (no seed).** File-based idempotency + GATE 1 + cheap per-sheet regeneration.
- **The episode writer drifts from your voice.** The writer prompt carries verbatim excerpts from existing episodes as house-style exemplars. W4 flags register drift.
- **Two registries in the repo.** `story-maker-v3`'s per-run registry and the new global one. The global one is additive. `assetctl doctor` reports divergence.

## File layout

```
.devin/skills/h3-chain-director/
  SKILL.md                          # this runbook
  references/                       # 8 reference docs (load on demand)
  prompts/                          # 12 role prompts (Tier 0 + Tier 1)
  scripts/
    validate_story.py               # Tier 0 validator
    validate_plan.py                # Tier 1 validator (plan + ledger)
    assets_registry.py              # global registry library
    assetctl.py                     # registry CLI
    build_sheets.py                 # identity plates + 3×2 sheets (registry-first)
    chain_run.py                    # per-scene orchestrator
    assemble.py                     # recovery-branch assemble-only
    beat_grid.py                    # optional: beat-synced cutting
    audit_cuts.py                   # S13: actual vs planned cut rhythm
```

## Reuse (import by path, do not copy)

- `skills/story-maker-v3/tools/comfyui_tools.py` — upload/queue/poll/download
- `skills/story-maker-v3/tools/minimax_workflow.py::ui_workflow_to_api` — UI→API conversion (keeps dynamic `ref_images.*` inputs)
- `skills/story-maker-v3/tools/image_pipeline.py` + `char_sheet_builder.py` + `config.py` — Replicate/fal gpt-image-2
- `.devin/skills/minimax-h3-prompter/references/ref2va-format.md` — the 6-section Ref2VA spec

Setup is covered by `workflows/setup/minimax-h3-seamless-chain-global-refs.sh`.
