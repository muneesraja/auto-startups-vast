# Changelog — Story Maker V4

All notable changes to `story-maker-v4` (and its evolutionary context from `story-maker-v3` and `story-maker-v4p`) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [4.2.0] - 2026-09-10

### Highlights
- **Animation Screenplay Format (Agent 1)**: Replaced free-form prose narrative output with industry-standard animation screenplay format. `developed_story.md` now contains proper sluglines (`INT./EXT. LOCATION - TIME`), lean 1–3 line action paragraphs, ALL-CAPS sound effects, formatted dialogue with parentheticals, and montage sequences.
- **Screenplay Format Bible (`assets/screenplay-format.md`)**: New comprehensive reference guide for animation screenwriting conventions, based on master-class analysis of *Swapped* (Netflix/Skydance Animation, dir. Nathan Greno).
- **Deterministic Screenplay Validator (`--schema screenplay`)**: Added `validate_screenplay()` checking sluglines, prose walls, dialogue cues, sound cues, and required metadata sections.
- **Downstream Screenplay Authority**: Agents 2, 3, and 5 now extract scene boundaries, dialogue, acting beats, and foley cues directly from the screenplay rather than inventing them.

### Added
- `assets/screenplay-format.md` — Animation Screenwriting Bible with format rules, anti-patterns, and few-shot examples from `Research/ollie`.
- `validate_screenplay()` in `tools/validators.py` — deterministic screenplay format validator.
- `--schema screenplay` registered in `scripts/validate.py`.
- `tests/test_screenplay_validator.py` — 8 unit tests for screenplay validation.

### Changed
- `prompts/story_developer.md` — Agent 1 now requires screenplay format; validation step added before beat board.
- `prompts/scene_writer.md` — Agent 2 uses screenplay sluglines as canonical scene boundary anchors.
- `prompts/storyboard_planner.md` — Agent 3 extracts dialogue, acting beats, and sound cues from screenplay.
- `prompts/video_prompter.md` — Agent 5 harvests ALL-CAPS sound cues into `foley_and_sfx` stem.
- `SKILL.md` — Version bumped to 4.2.0; Agent 1 section updated with screenplay validation.
- `ARCHITECTURE.md` — Agent 1 validator updated from `None (free-form)` to `--schema screenplay`.

---

## [4.1.0] - 2026-09-10

### Highlights
- **Script Intake Normalizer (`Agent 1`)**: Added `preserve_script` intake mode allowing authored screenplays (e.g. *Kutty Karupu*) to be processed without destructive rewriting or scene flattening, alongside duration modes (`preserve_script`, `compress`, `expand`, `exact`).
- **Canonical Machine-Readable Dual Models**: Added companion `story.json` entity and constraint manifest alongside human-readable markdown files.
- **Critique Gate (GATE 0) Severity Tiers**: Replaced circular PASS/FAIL auditing with `BLOCKER`, `MAJOR` (with required `Disposition: RESOLVED | ACCEPTED_AS_INTENDED`), `MINOR`, and `NOT_APPLICABLE` filtering.
- **Approved Render Manifest (`render_manifest.json`)**: Added `scripts/build_manifest.py` and sha256 checksum staleness checks in `scripts/render_all.py` to prevent accidental GPU execution on stale or modified artifacts.
- **Storyboard Template Consolidation**: Consolidated `prompts/storyboard_sheet_template.md` and `prompts/image_prompter.md` with proven 9-panel prompt principles (plain prose reading order, Reference Priority hierarchy, Action Contract for static poses, and Final Continuity Checklist).
- **Discrepancy Authority & 4-Layer Audio Hierarchy**: Established clear authority rules (sheet = visual authority; storyboard = editorial authority) and formalized audio sections into `diegetic_dialogue`, `foley_and_sfx`, `environmental_ambience`, and `non_diegetic_music`.
- **Deterministic Validators**: Added `--schema constraints` and `--schema manifest` to `scripts/validate.py` and `tools/validators.py`.

---

## [4.0.0] - 2026-09-09

### Highlights
- **Directorial & Cinematography Discipline**: Transitioned from rigid micro-shot slicing to dynamic, director-led shot depth planning (master takes, asymmetric two-shots, action arcs).
- **Anime Studio Playbook**: Integrated production metadata for animation styling, layout composition, and visual motifs into the core scene schema.
- **H3-Native Style LoRAs**: Added official presets, installation scripts, and ComfyUI workflow support for stylized aesthetics (storybook, flat geometric, vintage editorial, concept art).
- **Refined Ref2VA Prompting Contract**: Formalized the 6-section MiniMax H3 reference-to-video-audio prompt specification with strict word budgets, 3D camera motion syntax, and facial fidelity rules.

### Added
- **Production Asset Guides (`assets/`)**:
  - `anime-studio-playbook.md`: Guides staging, layouts, acting beats, and visual continuity for animated storytelling.
  - `cinematography-bible.md`: Authoritative reference for focal lengths, camera movement mechanics, shot progression, lighting moods, and spatial framing.
  - `minimax-h3-modes-guide.md`: Detailed guidance on MiniMax H3 operational modes, prompt weights, and reference conditioning limits.
  - `style-lora-presets.md`: Tested parameter configurations, trigger keywords, and strength brackets for H3 style LoRAs.
  - `ref2va-format.md`: Reference contract for multi-modal H3 reference inputs and prompt structuring.
- **Templates & Prompts (`prompts/`)**:
  - `character_sheet_realistic_template.md`: Dedicated template for realistic/live-action character Turnaround Sheets.
  - Stage A3-Pre in `SKILL.md`: Director's prerequisite for **Dynamic Shot Depth & Duration Planning** (Continuous Master Takes 10–15s, Asymmetric 2-Shots, Dynamic Action Arcs, and Rapid Montages).
- **Scene Schema Fields**:
  - Five new metadata keys per scene in `scene_writer.md`: `style_target`, `acting_beat`, `layout_strategy`, `visual_motif`, and `sound_world`.
- **Validation & Test Suites (`tests/` & `tools/`)**:
  - `tests/test_focus_validator.py`: Validates camera focus statements and depth-of-field constraints.
  - `tests/test_style_lora_workflow.py`: Automated verification of H3 ComfyUI LoRA graph patching.
  - 9 evaluation categories in `directing-questions.md` (200+ checks expanding across Story, Camera, Composition, Animation, Sound, Spatial, and H3 Anime Production).

### Changed
- **`SKILL.md` & `ARCHITECTURE.md`**:
  - Updated output layout targets to `outputs/story-maker-v4/<story>/epi-N/`.
  - Added warnings against tag stuffing and shallow descriptions in Ref2VA video prompts.
  - Standardized seamless continuation phrasing for multi-generation scene chains (`g2+`).
- **Prompt Engineering (`prompts/video_prompter.md`)**:
  - Enforced "One Job" rule across reference assets.
  - Targeted 350–500 words in `detailed_description`.
  - Prioritized medium close-up (MCU) and close-up (CU) framing for key acting/vocal beats to preserve facial fidelity in MiniMax H3.
  - Formalized 3D camera motion syntax: `[Motion Type] with [amplitude] at [speed]`.
- **Validators (`tools/validators.py`, `tools/spatial_prompt_builder.py`)**:
  - Enhanced schema validators for video prompt sections, shot timestamp continuity, and transition grammars.
  - Strengthened spatial plan coordinate contracts and orientation validations.

---

## Comparison: Version Differences

| Feature / Dimension | `story-maker-v3` | `story-maker-v4` | `story-maker-v4p` |
| :--- | :--- | :--- | :--- |
| **Release Base** | Initial MiniMax H3 R2V migration (replaced LTX 2.3) | Director's brief & anime-studio production pipeline | Panorama / 360° background consistency variant |
| **Pacing Strategy** | Rigid micro-shot focus (5–8 micro-shots / 15s, 1.5–3.0s each) | **Dynamic Shot Depth** (10–15s oners, asymmetric 2-shots, dynamic arcs) | Pacing baseline with room-rotation alignment |
| **Scene Metadata** | Basic beats, target durations, characters, locations | Adds `style_target`, `acting_beat`, `layout_strategy`, `visual_motif`, `sound_world` | Standard beat & location metadata |
| **Style LoRAs** | None (pure base model prompting) | **Native H3 Style LoRAs** (storybook, flat geometric, vintage, painterly) | Base model prompting |
| **Cinematography & Playbooks** | Standard director's guide (7 review sections) | **Cinematography Bible**, **Anime Playbook**, **H3 Modes Guide** (9 review sections) | Director's guide + official vendored MiniMax guides |
| **Background Continuity** | Soft tail-video conditioning (`--tail-ref-seconds 3.0`) | Soft tail-video conditioning + spatial planning contracts | **360° Background Video Sweep** (`tools/background_extractor.py`) & cardinal wall plate extraction |
| **3D / Layout Blocking** | 2.5D coordinate landmarks | 2.5D coordinate landmarks + dynamic camera staging | 2.5D coordinates + optional Blender gray clay blocking advice |
