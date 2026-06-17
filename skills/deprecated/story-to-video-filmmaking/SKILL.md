---
name: story-to-video-filmmaking
version: 1.4.0
description: "Turn story manifests into cinematic videos using agent-composed prompts (filmmaking_prompt.json) and config-driven workflow templates. Uses the LTX 2.3 FFLF (First Frame Last Frame) Seed Hunter multi-stage workflow, supporting smart frame generation, multi-roll seed hunting, spatial upscaling, motion quality evaluation (V2 prompt: FF+LF anchored, 3 frames/video, a/b/c ranked, LF-arrival weighted), seamless continuation chaining, edit-instruction LF prompting, pre-flight FF↔LF audit, and opt-in per-image quality gating."
triggers:
  - filmmaking
  - FFLF pipeline
  - seed hunting
  - cinematic video
  - story filmmaking
---

# v1.4.0 — Production Learnings Release (2026-06-11)

Three changes from the elephant story (2026-06-11) post-mortem:

1. **LF Edit-Instruction Pattern** — `last_frame_prompt` is now a Flux edit instruction (CONTEXT / KEEP UNCHANGED / CHANGE / CAMERA / MOOD), not a fresh scene description. Fixes the 71% FF≈LF failure rate.
2. **Per-Image Quality Gate** — Opt-in. Scores each generated still against its character reference sheet via Gemini 3.1 Flash Lite. Catches character drift (Flux diluting chibi proportions, expression drift, etc.) before it propagates. ~$0.0005/image.
3. **Pre-Flight FF↔LF Audit** — Text-only audit that runs in 2 seconds with no API calls. Detects FROZEN / SUBTLE / RADICAL LF risks before GPU time is spent. Standalone tool (`scripts/prompt_audit.py`) + orchestrator flag (`--preflight-audit`).

See `references/fflf-production-learnings.md` § LF Edit-Mode Prompting / Per-Image Quality Gate / Pre-Flight FF↔LF Audit for full details and calibration data. See `references/filmmaking-prompt-schema.md` for the new schema fields.

---

# Story-to-Video-Filmmaking Pipeline

Turn story manifests into cinematic, high-fidelity videos using agent-composed prompts, smart frame generation, and the LTX 2.3 FFLF (First Frame Last Frame) Seed Hunter ComfyUI workflow.

> **Image-only?** If the user wants scene stills / no video, this is the wrong skill. Use `story-to-video` (the stills-only pipeline) instead. Recurring confusion: "2 minutes of images" → stills pipeline; "2 minutes of video" → this one. Always confirm if the wording is ambiguous.

> **Single-shot shortcut:** If you just need ONE image (T3 character sheet, T5 single frame, a quick test), use `story-to-video/scripts/generate_scene.py --shot <prefix>` instead of the full orchestrator. It's faster, gives per-shot output, and handles Flux 2 Dev Turbo's `__REFERENCE_1__` switch wiring correctly. The full orchestrator (`filmmaking_orchestrator.py`) is for batch generation with continuation chains and Phase 2-5 stitching. See `comfyui-ops/SKILL.md` § Critical Patterns for details.

## Trigger

- User has a `story_manifest.json` and wants to produce a coherent animated film.
- User wants to use the FFLF multi-stage seed-hunting pipeline for superior motion control and upscaling.
- User wants to establish continuity between consecutive shots in a scene.

## Quick Start (Working CLI Invocation)

The orchestrator has a hardcoded `DEFAULT_BASE_URL` in `scripts/comfyui_api.py` pointing to an old Mandi Qwen instance that is usually unreachable. **Always pass `--url` and `--auth` explicitly** to the current ComfyUI instance, or the run dies on the first `curl_json` with a confusing empty-stdout JSON error.

Working invocation pattern (use as the template for every run):

```bash
cd <story_dir>
python3 /root/.hermes/skills/creative/story-to-video-filmmaking/scripts/filmmaking_orchestrator.py \
    --prompts filmmaking_prompt.json \
    --url "https://<your-comfyui>.trycloudflare.com" \
    --auth "vastai:$(grep ^COMFYUI_AUTH /root/.hermes/.env | cut -d= -f2)" \
    --skip-existing 2>&1 | tee _orchestrator_run.log
```

> **Auth format (2026-06-12 fix):** `--auth` is `user:pass` where user defaults to `vastai` and pass is the 64-char hex token from `COMFYUI_AUTH` in `/root/.hermes/.env`. The placeholder `--auth "<username>:<password>"` is misleading — there is no human-readable password, only the hex token. Copy it with: `echo "vastai:$(grep ^COMFYUI_AUTH /root/.hermes/.env | cut -d= -f2)"`. For single-shot work, `generate_scene.py` accepts the same format. Verify with `bash /root/.hermes/skills/creative/comfyui-ops/scripts/quickstart_auth.sh` before any long run.

> **Success gate:** After any T2/T3/T5/T11 run, check the output files exist with `bash /root/.hermes/skills/creative/story-to-video-filmmaking/scripts/done_check.sh <min_kb> <file1> [file2 ...]`. Exit 0 = DONE, exit 1 = NOT DONE. This is the objective "are we done?" signal — don't iterate further if it exits 0.

> **Output directory resolution (2026-06-11 fix):** By default the orchestrator writes `scenes/`, `videos/`, `motion_eval/`, and looks up `characters/` (reference sheets) **in the same folder as `filmmaking_prompt.json`** — i.e. project-local. Pre-2026-06-11 the default was a hardcoded path to the skill root, which silently cross-contaminated output across multiple stories. The fix detects when the user did not pass `--output-dir` and derives it from the `--prompts` file's directory. If you want a custom output location, pass `--output-dir /path/to/folder` explicitly. To force the old behavior (NOT recommended), pass `--output-dir /root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video-filmmaking`.

> **Background runs:** Pair with `background=true` + `notify_on_complete=true`. Per the polling-pref lesson, do NOT sit and watch progress; let it run and report back on completion.

|> **Skill copy ambiguity:** A duplicate copy of this skill may exist at `/root/repos/auto-startups-vast/current-setup/skills/story-to-video-filmmaking/scripts/` — they are kept in sync, but **always invoke from the `.hermes` path** so skill patches take effect.

## Task Body Template (for orchestrator workers)

> **New 2026-06-12.** After the panda-pippin T3 burned 185 turns, we standardized the task body every STV worker receives. The full template lives at `references/STV_TASK_BODY_TEMPLATE.md`. The four mandatory sections are:

1. **SETUP** — Source `/root/.hermes/.env`, verify `COMFYUI_URL`/`USER`/`PASS`, run `quickstart_auth.sh` (one-shot auth+connectivity check, kills the f-string bug).
2. **USE EXISTING HELPERS** — `curl_json()`, `wait_for_prompt()`, `download_output()`, `upload_image()`, `WorkflowBuilder`, `fflf_executor`, `UploadManifest`. Never write your own curl with auth inline.
3. **SUCCESS CRITERIA** — File-based, objective. Use `scripts/done_check.sh <min_kb> <file1> ...` as the gate.
4. **STOP CONDITION** — When `done_check.sh` exits 0, post done and exit. Do NOT iterate further.

**Anti-pattern reminder:** The previous T3 run looped 80+ turns debugging a Python f-string that had embedded `"` characters. The fix: use `curl_json(method, endpoint, url, auth=(user, pass))` and pass `auth` as a tuple — never substitute a token into an f-string.

## FFLF Template Pre-Flight Check (run before any production run)

The shipped `assets/workflow-templates/ltx-23-fflf-seed-hunter.json` historically had 5 wiring bugs (bare model paths, missing audio VAE, missing CFGGuider model, 0-indexed ImpactSwitch, wrong video output file). They are pre-patched in the canonical copy as of 2026-06-11, but **on a fresh instance the template may have been re-shipped clean OR re-deployed broken** — verify before queueing.

Run `scripts/check_fflf_template.py` — it scans for the 5 bug signatures and exits non-zero if any are present, printing the exact nodes that need patching. Reference: `references/fflf-production-learnings.md` documents the full fix for each bug.

## Pre-flight FF↔LF Audit (run after composing filmmaking_prompt.json, before Phase 2)

The 2026-06-11 elephant story exposed a 71% failure rate on FF↔LF keyframes (10/14 shots had FF≈LF problems). The pre-flight audit catches the obvious text-level causes **before any GPU time is spent** — takes 2 seconds, costs $0.

```bash
# Standalone
python3 scripts/prompt_audit.py path/to/filmmaking_prompt.json

# Or via the orchestrator (advisory, does not block by default)
python3 scripts/filmmaking_orchestrator.py --prompts filmmaking_prompt.json --preflight-audit
```

Output: console table + `feedback/ff_lf_audit_preflight.md` with per-shot risks and re-authoring suggestions. The audit detects **frozen** (FF≈LF, no spatial delta), **subtle** (expression-only change, no body motion), and **radical** (LF in different scene, break_continuity not set) risks using text similarity + keyword analysis. Text-only — false positives are safe to dismiss, false negatives caught by the post-render SSIM audit. See `references/fflf-production-learnings.md` § "Pre-Flight FF↔LF Audit" for the full heuristic list and `references/phases/phase-1-prompt-composition.md` § "The Edit-Instruction LF Pattern" for the fix.

## Per-Image Quality Gate (opt-in, run during Phase 2)

Optional per-image evaluation step that runs after each still is generated. Uses Gemini 3.1 Flash Lite via OpenRouter to score the image against its target character reference sheet, with a hard pass/fail threshold and a single regeneration retry on failure. Catches character drift (Flux diluting chibi proportions, adding leaf hats, etc.) before it propagates into the video pipeline.

Enable per-run:
```bash
python3 scripts/filmmaking_orchestrator.py --prompts filmmaking_prompt.json --quality-gate
```

Or set `global.quality_gate.enabled: true` in `filmmaking_prompt.json`. Disabled by default. Cost: ~$0.0005 per image (~$0.014 for a 14-shot film with FF+LF). See `references/fflf-production-learnings.md` § "Per-Image Quality Gate" and `references/filmmaking-prompt-schema.md` for full config.

## LF Edit-Instruction Pattern (apply to all last_frame_prompts in Phase 1.5)

The `last_frame_prompt` field is a **Flux edit instruction** describing the delta from the FF, with explicit `KEEP UNCHANGED:` preserve list and `CHANGE:` delta list — NOT a fresh scene description. The pipeline calls Flux 2 Dev Turbo with the FF already in `references[]`, so the model is in I2I edit mode by default. The prompt format determines whether Flux preserves the FF (healthy motion) or re-imagines the scene (frozen or radical).

Template + vocabulary + elephant shot 3.2 before/after example: `references/phases/phase-1-prompt-composition.md` § "The Edit-Instruction LF Pattern". The single most important prompt-authoring rule for FFLF.

---

Two independent duration fields exist in the pipeline. They are NOT the same:

| Field | Lives in | What it controls |
|---|---|---|
| `story_manifest.json` → `shots[].duration_seconds` | The story manifest | **Per-shot story budget** — what the screenplay "wants" this beat to take. Sum across all shots = narrative duration target. |
| `filmmaking_prompt.json` → `shots[].overrides.segment_duration` | The filmmaking prompt | **What the FFLF video model actually renders** per shot. Sum across all shots = **actual video length**. |

**Rule:** The orchestrator uses `overrides.segment_duration` (or `global.segment_duration` if no override) to set the LTX render time. **`manifest.duration_seconds` is ignored at render time** — it's a planning document for the agent to know how much story each shot carries.

**Practical workflow when the user says "I want N seconds of video":**
1. Decide your shot list and rough spatial-delta (heuristic: 2-3s expression-only, 4-5s subtle, 5-7s trajectory, 7-8s full traversal).
2. Set `overrides.segment_duration` per shot to match the spatial delta.
3. Sum them → that's your actual video length.
4. **Reality check:** 14-15 quality FFLF shots at 5-8s each tops out at **~80-100 seconds** of usable video. If the user wants 120s exactly, you must (a) add more shots, (b) extend some shots beyond their natural duration (risky — model invents motion to fill the gap), or (c) accept that "just under 2 min" is the honest answer. Confirm with the user before padding.

**`global.segment_duration` (default 5s)** is a fallback used by any shot without an explicit `overrides.segment_duration`. Don't rely on it as your total-runtime knob — set per-shot values for any shot you care about.