# V3 Cinematic Pipeline Progress Document

Progress log documenting the V3 upgrade of the `story-to-video-cinematic` pipeline.

## 1. Summary of Upgrades

The pipeline was upgraded to version **3.1.0** containing the following features:

### 1.1. Script Modularization
The monolithic `cinematic_orchestrator.py` (~830 lines) was split into 5 focused modules:
1. `cinematic_orchestrator.py` (~270 lines): Slim coordinator managing options, flattening inputs, resolving continuity chains, and managing wave progress.
2. `wave_executors.py` (~390 lines): Contains `WaveExecutorMixin` providing implementation methods for Waves 0 to 7.
3. `prompt_composer.py` (~50 lines): Houses purely functional prompt composition logic.
4. `quality_gates.py` (~220 lines): Implements five visual evaluation gates (QA, Composition, Likeness, Delta, Video coherence).
5. `pipeline_logger.py` (~200 lines): Implements human-readable log file capturing and atomic status tracking JSON serialization.

### 1.2. Wave 2 split (Race Condition Fix)
To prevent the race condition where Last Frame (LF) derivations could read un-edited First Frame (FF) server names, Wave 2 was split into:
* **Wave 2a**: Performs Flux Klein editing on First Frames (FF).
* **Wave 2b**: Performs Flux Klein derivation on Last Frames (LF) using the newly updated edited FF server path.

### 1.3. Evaluation Gates (Gates 1–5)
Five visual gates verify generations against reference assets using Gemini or OpenRouter models:
- **Gate 1 (QA)**: Character sheets contain clean multi-view angles.
- **Gate 2 (Composition)**: Raw scene stills align with prompt layout/elements.
- **Gate 3 (Consistency)**: Character-edited stills preserve background elements and match character references.
- **Gate 4 (LF Delta)**: First Frame vs Last Frame change is subtle and follows direction.
- **Gate 5 (Video)**: Stitched final video matches story intent and shows transition/motion consistency.

### 1.4. Pipeline Tracker (`pipeline_status.json`)
Saves atomic, crash-resilient JSON progress tracker containing status, outputs, progress percentage, quality scores, and failure details.

### 1.5. Director Log (`director_log.json`)
Requires agents to dump their pre-run scene layout choices, continuity decisions, and prompt rationales to assist post-run audits and diagnostics.

---

## 2. Automated Tests & Validation

Ran automated test suite in `verification_test.py`:
- All workflow building, cloning, and rewiring checks pass.
- `test_pipeline_logger` successfully validated atomic json initialization and updates.
- `test_prompt_composer` verified overrides and derivation suffix insertion.
- `test_wave_2_split` validated that mixin method bindings exist.

```
🎉 All automated tests passed successfully!
```

---

## 3. V3.1.1 Review Fixes (2026-06-16)

Post-implementation review identified 10 issues. All have been fixed:

### 3.1 Critical Fixes

**C-01 — Ideogram JSON prompt composition wired up**
- `wave_executors.py` now imports and calls `compose_character_sheet_prompt()` and `compose_scene_prompt()` from `ideogram_generator.py` in Wave 0 and Wave 1 respectively.
- `ideogram_generator.py` → `compose_scene_prompt()` now handles 1, 2, and 3 characters using split bounding boxes (centred / left-right halves / thirds).
- The Ideogram JSON structure (`high_level_description`, `style_description`, `compositional_deconstruction` with `bbox`) is now actually sent to the CLIPTextEncode node.

**C-02 — SKILL.md hardcoded paths removed**
- All 16 `file:///Users/muneesraja/...` links replaced with relative paths. SKILL.md now works on any machine including the VPS.
- Also added link to new example 11 and to `ideogram-prompt-engineering.md` reference.

**C-03 — Ideogram JSON prompting example created**
- New `examples/11-ideogram-json-prompts.md` documents the full JSON prompt structure, bounding box coordinate system, bbox pattern table, and 3 worked examples (character sheet / single-char scene / multi-char scene).

### 3.2 Important Fixes

**I-01 — verification_test.py path fix**
- Line 122 changed from CWD-relative open() to `script_dir`-relative path.

**I-04 — 06-full-story-dryrun.md updated**
- Wave roadmap updated: "Wave 2" split into "[Wave 2a] Klein FF Edits" and "[Wave 2b] Klein LF Derivations".
- Wave count updated from 7 to 8. Added Note callout explaining the race-condition rationale.

**I-03 — cinematic-prompt-schema.md model IDs documented**
- Added recommended model ID table for OpenRouter and Gemini for image gates (1–4) and video gate (5).

### 3.3 Minor Fixes

**M-01 — pipeline-architecture.md swap count**: "max 7 loads" → "max 8 loads for V3.1".

**M-03 — cinematic_orchestrator.py shlex safety**: `subprocess.run(cmd_str, shell=True)` replaced with `shlex.split()` + `shell=False`.

**M-04 — wave_executors.py error propagation**: Two `sys.exit(1)` calls replaced with `raise RuntimeError(...)`. Orchestrator `execute()` now wraps entire pipeline in `try/except RuntimeError/finally: self.logger.close()` to guarantee log file flush on any exit.

### 3.4 Verification Results (Post-fix)

```
🎉 All 6 automated tests passed successfully!
✅ Ideogram JSON composition: 1/2/3-character layouts all produce valid JSON with correct bbox splits
```
