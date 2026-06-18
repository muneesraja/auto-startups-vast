# Story-to-Video Deterministic Pipeline - Plan & Implementation Review

**Reviewer:** opencode (automated code review)
**Date:** 2026-06-18
**Scope:** Plan at `discussion-and-docs/deterministic-implementation-resource/` + implementation at `skills/story-to-video-deterministic/`
**Method:** Code inspection of all source files, schema tests, and forensic inspection of the generated `panda_butterfly_test/` artifacts on disk.

---

## 1. What Is Implemented Well

### 1.1 Plan Quality (deterministic-implementation-resource)

- **Architecture is sound and complete.** The mermaid graph in `temp/implementation_plan.md:23-66` cleanly maps the 9-step pipeline with state-flow (`director_visual_blueprint.json` and `prompts.json` as shared stores) clearly. ADK `SequentialAgent` + pure-Python wave scripts is the right call - LLM where judgment is needed, plain Python where determinism matters.
- **Schema design is genuinely thoughtful.**
  - Namespaced `prompts.json` (`character_sheets`, `ff_shots`, `consistency_patches`, `lf_shots`, `motion_prompts`) prevents collisions between agents writing concurrently.
  - `{{...}}` template references (`prompts.json` defaults) decouple prompt generation from image generation - this is a clever move that lets the wave executor resolve paths at runtime instead of at LLM-call time.
  - Per-item `status` (`pending`, `generated`, `failed`, `skipped`, `pending_wave_1`) is the right primitive to enable resume-from-failure.
  - `delta_from_ff` taxonomy (`camera_change`, `subject_changes`, `environment_changes`, `particle_effects`) is the secret weapon - it forces the director to think in discrete, observable changes, which clicks perfectly with how LTX FFLF interpolates.
- **Delta taxonomy with safe ranges.** `temp/implementation_plan.md:343-354` gives concrete numbers (<=15 deg rotation, <=20% zoom, <=30% frame width move, 1 action change) instead of vague "be subtle" guidance. This is what separates a working FFLF pipeline from a broken one.
- **Few-shot examples in V13.** The four few-shot examples in `V13_story_to_video_deterministic.md:397-453` (Walk Forward, Head Turn, Camera Zoom, Two Characters Interacting) are the single most important quality anchor in the pipeline. They are concrete and cover duration-aligned change budgets (1-2 changes for 2s, up to 5 for 5s). These are correctly embedded into `system_prompts/lf_shot_prompter.md:32-88`.
- **Edge cases are pre-identified.** The plan enumerates 7 edge cases (`temp/implementation_plan.md:1081-1112`) - multi-character reference limit, continuation chain breaks, malformed LLM JSON, duration violations, landscape-only shots, dynamic reference scaling, structure/visual desync. Each is paired with a solution. This is rare foresight.
- **Duration guardrails are enforced at multiple layers** - in the system prompt (`system_prompts/director_script.md:7-15`) and in the Pydantic schema (`schemas/blueprint.py:45` uses `Field(ge=2, le=5)`). Defense in depth.

### 1.2 Implementation Quality (skills/story-to-video-deterministic)

- **The pipeline actually runs end-to-end through Step 8.** The `panda_butterfly_test/` artifacts on disk show: `Director_script.md` (4.1KB, well-formed content), `director_visual_blueprint_structure.json` (8.5KB, valid), `prompts.json` (18.5KB), `generator_wave_1.json` (7.6KB), `generator_wave_2.json`. Steps 1, 2a, 3-7, and 8 all produced concrete output. V13-V16 implementation logs corroborate this.
- **Generated prompts are high quality.** Inspecting the `panda_butterfly_test/prompts.json` content:
  - Character sheet prompts follow the correct Ideogram 4 multi-view bbox layout from `system_prompts/character_sheet_prompter.md:7-14` (front / three-quarter / side / back / face / gear / title bar).
  - FF shot prompts correctly place characters with bbox presets based on count (see `system_prompts/ff_shot_prompter.md:5-13`).
  - Consistency patches correctly handle 1-character (shot_01 has 2 refs: 1 char + 1 FF) and 2-character (shot_04 has 3 refs: 2 chars + 1 FF) cases.
  - Motion prompts follow the rules - they describe spatial displacement, not static visual details, and respect duration constraints.
  - LF prompts start with "In reference image 1, ..." as commanded by the few-shot examples in the system prompt.
- **Pydantic schemas match the plan exactly.** `schemas/blueprint.py` and `schemas/prompts.py` are 1:1 with the plan's Component 2 spec, including the `Field(ge=2, le=5)` and `Field(ge=1, le=2)` validators. `tests/test_schemas.py` validates them and **both tests pass**.
- **ComfyUI tooling is robust.** `tools/comfyui_tools.py` deserves specific praise:
  - `_resolve_args` + `_resolve_hostname` (`comfyui_tools.py:11-44`) proactively handle Cloudflare tunnel DNS resolution failures via `nslookup` fallback - this is exactly the resilience the V15 hang-on-None bug demanded.
  - `wait_for_prompt` (`comfyui_tools.py:75-102`) correctly raises `ValueError` on `prompt_id=None` instead of hanging 40 minutes.
  - `download_output` (`comfyui_tools.py:104-149`) validates file magic bytes after download and deletes HTML/JSON error pages returned by tunnels.
  - `generate_flux_edit` supports **dynamic reference scaling** (`comfyui_tools.py:296-364`) - solving Edge Case 6 from the plan (the monkey-became-panda issue) by letting the consistency prompter attach 1-4 character references per shot.
- **`workflow_builder.py` correctly clones the Flux Klein 9B ReferenceLatent chain at runtime.** `workflow_builder.py:418-486` (`flux_klein_edit_dynamic` builder) clones `LoadImage` + `ImageScaleToTotalPixels` + `VAEEncode` + 2x `ReferenceLatent` (positive/negative) chains per additional character ref, then rewires the `CFGGuider` to use the chain tail. This is the exact solution the user described in `User-Plan.md:55-58`. Hard problem, cleanly solved.
- **ComfyUI execution output is sanitized.** `workflow_builder.py:870-874` strips metadata keys starting with `_` before sending to ComfyUI - preventing template metadata from leaking into the API call.
- **Agent pattern is uniform and readable.** All 8 agents in `agents/` follow an identical DRY-friendly shape: `get_system_prompt()` loads from disk, an async `instruction_provider(context)` concatenates system + state-injected additional instructions, an `LlmAgent` is wired with `output_key` for state passing. Each file is 30-54 lines.
- **Wave executor has resume semantics.** `scripts/wave_executor.py` checks `entry.get("status") == "generated"` before each generation step and persists `prompts.json` after every individual shot (`update_prompts_file` calls). Killing the pipeline mid-wave and re-running will skip completed shots.
- **Wave 2 FF extraction correctly uses ffmpeg via `extract_last_frame`** (`comfyui_tools.py:197-230`) which fetches frame count with `ffprobe` and selects frame `nb_frames - 1`. Robust fallback to 75 frames (3s @ 25fps) when ffprobe fails.

---

## 2. Bugs Found

### 2.1 CRITICAL - `director_visual_blueprint.json` written as empty `{}`

`panda_butterfly_test/director_visual_blueprint.json` is 2 bytes: `{}`. The Step 2b visual enrichment output is silently dropped.

**Root cause:** `main.py:200-208` calls `clean_json_str(blueprint_raw)` which only strips ```` ```json ```` and ```` ``` ```` prefixes (`main.py:117-124`). If Step 2b returns content wrapped in any other format (e.g. with a leading prose sentence, or ````markdown```` fence, or interleaved text), `json.loads` throws and the function logs `Error parsing JSON from agent output` and returns `{}`. The empty dict is then written to disk.

**Impact:**
- The blueprint file on disk is useless for downstream inspection or resumption.
- The structural blueprint (`director_visual_blueprint_structure.json`) is the only durable artifact of steps 2a/2b.
- The wave executor (`scripts/wave_executor.py:48`) reads `director_visual_blueprint.json` to derive `wave1_shot_ids` / `wave2_shot_ids`. With the file as `{}`, the executor would see zero shots and silently complete without generating anything. (In the test run, downstream Steps 3-7 still succeeded because they consumed the in-memory session state, not the disk file - but this is luck, not design.)

**Fix:** Make `clean_json_str` more robust - extract the first balanced JSON object from raw text using a brace-matching scan, or use LLM-agnostic JSON extraction (e.g. `json5` or the `google-genai` types `Content` -> first part with `json` MIME type). Also fail loudly (non-zero exit) when an expected state key produces `{}`.

### 2.2 CRITICAL - `Director_script.md` contains literal ``` ```markdown ``` fences

The raw bytes of `Director_script.md` start with `` ```markdown\n `` and end with `` \n``` ``. `main.py:179-184` writes `state.get("director_script_content")` verbatim to disk with `f.write(director_script)` - no stripping.

**Root cause:** The Step 1 system prompt says "Write only the final script in clean markdown. Do not include introductory conversational text" but does NOT explicitly forbid markdown fences. MiniMax-M3 wrapped the response in fences, and the writer doesn't strip them.

**Impact:** The file looks malformed when read by humans or by the wave executor's downstream tools. Also confirms the same root cause as Bug 2.1 (LLM wrapping).

**Fix:** Add fence-stripping to a shared markdown sanitizer in `file_tools.py` and use that helper from `main.py`. Or add to the system prompts: "Do not wrap your output in markdown code fences."

### 2.3 CRITICAL - Wave 2 (`continuation_from_previous=true`) shots get broken FF references in `motion_prompts` and `lf_shots`

Inspecting the generated `panda_butterfly_test/prompts.json`:

| Shot ID | Wave | `motion_prompts.ff_image` (current) | Expected |
|---|---|---|---|
| `scene_01_shot_02` | 2 | `{{ff_shots.scene_01_shot_01.output_path}}` | `{{ff_shots.scene_01_shot_02.output_path}}` |
| `scene_01_shot_03` | 2 | `{{ff_shots.scene_01_shot_02.output_path}}` | `{{ff_shots.scene_01_shot_03.output_path}}` |

And `lf_shots[*].reference_images` for Wave 2 shots:
- `scene_01_shot_02` refs `{{consistency_patches.scene_01_shot_01.output_path}}` (should be `{{ff_shots.scene_01_shot_02.output_path}}`)
- `scene_01_shot_03` refs `{{consistency_patches.scene_01_shot_02.output_path}}` (should be `{{ff_shots.scene_01_shot_03.output_path}}`)

**Root cause:** The Step 6 (`lf_shot_prompter.py:36-39`) and Step 7 (`step7_motion_prompter.py:37-38`) instructions correctly tell the LLM to use `{{ff_shots.<own_shot_id>.output_path}}` for continuation shots. But the MiniMax M3 model reasoned that "FF of shot_02 = last frame of shot_01's video, so I'll point to shot_01." It confused the *semantic* FF (= previous video's last frame) with the *schema* FF slot (its own slot, which the Wave 2 executor populates with the extracted last frame at `wave_executor.py:217-225`).

**Impact:** When `wave_executor.py:173-177` runs Wave 2 video generation, `resolve_ref(entry["ff_image"], prompts)` will resolve to `ff_shots.scene_01_shot_01.output_path`, which after Wave 1 is the **Ideogram-generated first frame of shot_01**, not shot_01's video last frame. This means LTX FFLF will interpolate from shot_01's opening image to shot_02's LF - the exact opposite of continuity. The whole FFLF workflow's purpose is defeated for all Wave 2 shots.

Worse: this happens silently because `resolve_ref` happily returns whatever the `{{...}}` resolves to. There's no validator that enforces "Wave 2 shot's ff_image must reference its own ff_shots slot."

**Fix options:**
1. **Code-side guard** in `wave_executor.py`: after Wave 2 FF extraction, force-overwrite `prompts["motion_prompts"][waveshot_id]["ff_image"] = prompts["ff_shots"][waveshot_id]["output_path"]` and `prompts["lf_shots"][waveshot_id]["reference_images"][0] = prompts["ff_shots"][waveshot_id]["output_path"]`. Don't trust the LLM for reference plumbing.
2. **Schema-side**: add a validator that the `ff_image` of a motion prompt must reference the same shot ID's `ff_shots` or `consistency_patches` slot - fail validation otherwise.
3. **Prompt-side**: make the few-shot examples in `system_prompts/motion_prompter.md` and `lf_shot_prompter.md` show the `ff_image` JSON snippet alongside the prompt text, so the model sees the correct pattern.

### 2.4 HIGH - `wave_organizer` produces dead artifacts; `wave_executor` ignores them

`scripts/wave_organizer.py:60-83` writes `generator_wave_1.json` and `generator_wave_2.json` with structured payloads. But `scripts/wave_executor.py` never opens them - it reads `prompts.json` and `director_visual_blueprint.json` directly (`wave_executor.py:42-49`) and recomputes wave assignment via `wave1_shot_ids(blueprint)` / `wave2_shot_ids(blueprint)` helper functions (`wave_executor.py:293-307`).

**Impact:**
- The wave JSON files (`generator_wave_1.json` is 7.6KB on the test run) are pure sidebar artifacts - they exist on disk but have zero effect on execution.
- The plan's Component 6 (`temp/implementation_plan.md:1049-1055`) explicitly says: "Reads `generator_wave_N.json` and executes each step via ComfyUI API." This was not implemented as specified.
- Two sources of truth for what a wave contains will eventually diverge.

**Fix:** Either (a) make `wave_executor.py` actually read `generator_wave_{wave}.json` and process its entries, or (b) delete `wave_organizer.py` and the JSON artifacts entirely and document that wave assignment is computed on-the-fly by the executor. Option (a) matches the plan; option (b) is honest about the current design.

### 2.5 HIGH - LLM JSON parsing failures are silently swallowed, no retry

`main.py:127-129`:
```python
except Exception as e:
    print(f"Error parsing JSON from agent output: {e}\nRaw content: {s[:200]}...")
    return {}
```

Returns `{}` on any parse failure. Downstream `prompts_data` then has empty namespaces, the pydantic validation skips them (because all section fields default to `{}`), and `PromptsFile(**prompts_data)` succeeds vacuously. No exception is raised, no non-zero exit, no re-prompt of the failing agent.

This is exactly the failure mode the plan warned about in Edge Case 3 (`temp/implementation_plan.md:1091-1097`):
> "On validation failure, retry the LLM call up to 2 times with the error message appended. Use `after_model_callback` to validate JSON structure before it's used."

**Fix:** Wrap each agent's state extraction in a retry loop that re-runs the LlmAgent with the error message appended when JSON parsing fails. Implement the `after_model_callback` ADK hook for per-agent JSON validation before state propagates to the next agent. Today, a Step 2b failure cascades silently through Steps 3-7 - this is the root cause of Bug 2.1 (an empty `director_visual_blueprint.json` made it past validation).

### 2.6 MEDIUM - Model switch not propagated to docs

The plan (`temp/implementation_plan.md:84-97`), `SKILL.md:16-23`, and V14 specify `google/gemini-3.1-pro-preview` (reasoning) and `google/gemini-2.5-flash` (light) via OpenRouter. The actual `config.py:31-50` uses MiniMax M3 / MiniMax-M2.7-highspeed via the MiniMax API directly. V16 corroborates the switch.

**Impact:** Three sources of truth (plan, `SKILL.md`, V14) are now stale. The `OPENROUTER_API_KEY` env var in `config.py:11` is read but never used - dead config.

**Fix:** Update `SKILL.md` to name the actual models in use. Add a note in `temp/implementation_plan.md` (or a follow-up V17 entry) that the orchestrator model family changed from Gemini to MiniMax and explain why (cost, latency, quality, access). Remove `OPENROUTER_API_KEY` from `config.py:11` if truly unused.

### 2.7 MEDIUM - `file_tools.py` is largely dead code

`tools/file_tools.py` defines `read_json_file`, `write_json_file`, `read_markdown_file`, `write_markdown_file` and is exported via `tools/__init__.py`. But:
- All 8 agents declare `tools=[]` (`agents/step1_director_script.py:28`, etc.).
- `main.py` does file I/O with raw `json.dump` / `f.write` (`main.py:174-184`) instead of going through `file_tools`.

The plan said each agent would expose ADK `FunctionTool`s for file I/O (`temp/implementation_plan.md:600-634`): "Each agent reads/writes `prompts.json` to disk via `FunctionTools`." The chosen design - "agents emit JSON to `output_key` state; `main.py` consolidates to disk" - is actually simpler and arguably better. But the `file_tools.py` module is now orphan infrastructure.

**Fix:** Pick one approach. Either (a) delete `file_tools.py` because the actual design uses state + main.py consolidation, or (b) use `file_tools.write_json_file` from `main.py` and let agents optionally call `read_json_file` from disk in case they want fresh state at run time. Option (a) is simpler.

### 2.8 MEDIUM - Missing `__init__.py` at skill root

`temp/implementation_plan.md:380` lists `__init__.py` at the root of the skill package. It does not exist (verified via `ls -la` and `glob`). The skill works only because `main.py:11` does `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` and then uses absolute-style imports (`from config import ...`, `from agents.step1_director_script import ...`).

**Impact:** Cannot be imported as a package (`from skills.story_to_video_deterministic import ...` won't work). For now this is acceptable since the entry point is `python3 main.py`, but it makes the package non-discoverable from elsewhere in the monorepo.

**Fix:** Add `skills/story-to-video-deterministic/__init__.py` (empty) and switch `main.py`'s imports to relative-style if the package is meant to be importable.

### 2.9 MEDIUM - Tests cover only 1 of 4 promised areas

The plan's verification section (`temp/implementation_plan.md:1118-1132`) called for four test files:
- `tests/test_schemas.py` - EXISTS (2 tests, both pass).
- `tests/test_agents.py` - MISSING (mock-LLM verification of tool calls and state updates).
- `tests/test_wave_organizer.py` - MISSING (wave assignment correctness, e.g. given a blueprint with N scenes the right shots land in each wave).
- `tests/test_integration.py` - MISSING (end-to-end with a 1-scene, 2-shot story).

**Fix:** Add at minimum a `test_wave_organizer.py` covering (a) cut shots land in Wave 1, (b) continuation shots land in Wave 2, (c) all character sheets land in Wave 1, (d) wave 2 LF/motion entries match the expected shot set. The wave logic is pure functional Python so it's the easiest to unit-test and the highest-value test to add.

### 2.10 LOW - LTX FFLF references list includes FF image twice when present

`tools/comfyui_tools.py:393-404`:
```python
shot_for_builder = {
    ...
    "references": [lf_server],
    ...
}
if ff_server:
    shot_for_builder["references"].insert(0, ff_server)
```

This builds `references = [ff, lf]` when FF is present. Then `_build_workflow_legacy` and `build_dynamic_workflow` pad with duplicates up to 10 slots (`workflow_builder.py:347-348`: `references.append(references[0] if references else "example.png")`). The legacy builder also does NOT deduplicate, while the dynamic builder DOES deduplicate and warns (`workflow_builder.py:393-402`). For the LTX FFLF workflow (which uses legacy fallback if no `_reference_slots` and no recognized `_builder_mode`), this means duplicate references will be submitted.

**Fix:** Audit which builder the LTX FFLF template (`ltx-23-fflf-seed-hunter.json`) actually triggers - it has a builder_type `ltx_fflf_seed_hunter` that explicitly handles its own substitution, but if a future template lacks `_reference_slots`, the dedup warning won't fire. Move the dedup safeguard into `_build_workflow_legacy` as well.

### 2.11 LOW - Duplicate `workflow_builder.py` across skills

`skills/story-to-video-cinematic/scripts/workflow_builder.py` and `skills/story-to-video-deterministic/tools/workflow_builder.py` are two separate copies of what is essentially the same ComfyUI workflow templating engine. The deterministic version is a 884-line general-purpose implementation; the cinematic copy likely has diverged.

**Fix:** Extract `workflow_builder.py` into a shared `skills/_shared/tools/workflow_builder.py` (or `workflows/` package) and import it from both skills. Avoids the maintenance burden of two copies drifting apart.

### 2.12 LOW - Step 4 FF prompter incorrectly marks `character_sheets` for FF as `pending` not `pending_character_sheet`

Not a correctness bug per se, but `prompts.json` shows `ff_shots.scene_01_shot_01.generated_by = "step_4_ff_prompter"` while `lf_shots[*].generated_by = "lf_shot_prompter"` (without the `step_N_` prefix). The schema's `LFShotEntry.generated_by` defaults to `"step_6_lf_prompter"` (`schemas/prompts.py:38`) but the LLM emitted `"lf_shot_prompter"`. The schema won't catch this because `generated_by` is an opaque `str`, so downstream artifacts have inconsistent naming.

**Fix:** Either enforce a strict enum in the Pydantic schema for `generated_by`, or normalize on write. Low priority since this field is informational only.

---

## 3. Architectural Feedback (Opinionated)

### 3.1 Session-state passing vs. disk-state passing - pick one

The current design is a hybrid: agents write JSON to in-memory `output_key` state (`agents/step1_director_script.py:29` etc.), `main.py` then writes `prompts.json` to disk at the end, but the wave executor reads from disk and writes its own updates. If the ADK process crashes between step 5 and step 6, all of steps 1-5's work is lost because none of it was durably persisted (only at the end of the whole pipeline).

**Suggestion:** Each agent should write its own namespace to `prompts.json` immediately after producing it, using the `file_tools.write_json_file` ADK `FunctionTool` that already exists but is unused (see Bug 2.7). This way a crash at step 6 can resume from step 6's input on disk, not restart from step 1.

### 3.2 The director's "3-shots max continuation chain" rule isn't validated

The rule is in the system prompt (`system_prompts/director_script.md:17-20`): "A sequence of continuation shots can be at most 3 shots long ... before you MUST perform a camera cut." The `panda_butterfly_test` structure shows: shot_01 (cut) -> shot_02 (continuation) -> shot_03 (continuation) -> shot_04 (cut). That's 1 cut + 2 continuations = exactly 3 before the next cut. Correct.

But this rule is enforced only by LLM goodwill - there's no Pydantic validator that walks the shots list and rejects a continuation chain longer than 3. Add a `model_validator(mode="after")` in `Scene` or `Blueprint` that walks shot sequences and fails validation if a 4th consecutive `continuation_from_previous=true` is encountered. This is exactly the kind of invariant Pydantic is built to enforce.

### 3.3 Sub-Seconds Suggestion: split `extract_last_frame` next-frame-check into a pre-flight

`comfyui_tools.py:197-230` calls `get_video_frame_count` (which runs ffprobe) inside `extract_last_frame`. If ffprobe times out, it silently falls back to 75 frames. Better: pre-flight the ffprobe call once at pipeline startup, fail loudly if not installed, and cache frame counts per video in `prompts.json` so re-runs don't re-decode.

### 3.4 `InstructionProvider` pattern is good; consider extracting a helper

The 8 `agents/stepN_*.py` files have ~30 lines of nearly-identical boilerplate (`get_system_prompt` reading from disk + `instruction_provider` concatenating). A `make_agent(step_name, model_fn, output_key, additional_instr_fn)` helper would halve the code. The current shape is fine for clarity, but as soon as you add `after_model_callback` (per Bug 2.5) you'll want to centralize the wiring.

### 3.5 Director script prompt lacks explicit shot-count guidance

The panda test produced 5 shots across 1 scene, totaling 17 seconds. The plan's `User-Plan.md` and `temp/implementation_plan.md` never specify a *target* shot count for a story of length N. This means a 30-second story could produce 30 1-second shots (impossible; min is 2s) or 6 5-second shots. Either works, but the LLM's choice is unguided. Add guidance: "Target total duration scales with input story complexity; each story beat typically corresponds to 1-3 shots; never produce fewer than 3 shots for a story with explicit character interaction."

---

## 4. Summary Table

| Area | Status | Notes |
|---|---|---|
| Plan completeness | Strong | All 9 steps, schema, edge cases, verification plan explicitly documented |
| Pydantic schemas | Strong | 1:1 with plan; tests pass |
| Director Script (Step 1) | Strong | Output quality is high |
| Blueprint Structure (Step 2a) | Strong | 100% correct in test run |
| Blueprint Visuals (Step 2b) | **Broken on disk** | Bug 2.1 - `director_visual_blueprint.json` is `{}` |
| Character Sheets / FF / LF / Motion (3-7) | Strong prompts; wrong Wave-2 FF refs | Bug 2.3 - `motion_prompts` and `lf_shots` reference wrong slot for continuation shots |
| Wave Organizer (Step 8) | Works as side-effect only | Bug 2.4 - JSON artifacts ignored by executor |
| Wave Executor (Step 9) | Robust against None/hangs; brittle to ref bugs | V15 hang bug fixed; Bug 2.3 cascades here |
| ComfyUI Tools | Strong curl-based impl | DNS fallback + magic-byte validation is excellent |
| Workflow Builder | Strong | Dynamic Flux Klein ref-chain cloning is the standout feature |
| Tests | Weak | 1 of 4 promised test files; only schemas covered |
| Docs consistency | Weak | Models switched to MiniMax; plan + SKILL.md still say Gemini |

---

## 5. Prioritized Action Items

1. **(P0) Fix Bug 2.1** - make `clean_json_str` extract first balanced JSON object; fail non-zero when expected state key returns `{}`. This is the root of the silent blueprint-loss.
2. **(P0) Fix Bug 2.3** - in `wave_executor.py`, after Wave 2 last-frame extraction, overwrite `prompts["motion_prompts"][shot_id]["ff_image"]` and `prompts["lf_shots"][shot_id]["reference_images"][0]` to point at `prompts["ff_shots"][shot_id]["output_path"]`. Don't trust the LLM for plumbing.
3. **(P0) Fix Bug 2.2** - strip markdown fences before writing `Director_script.md`.
4. **(P1) Fix Bug 2.4** - make `wave_executor.py` consume `generator_wave_N.json`, or delete `wave_organizer.py` and the artifacts and update the plan.
5. **(P1) Fix Bug 2.5** - implement post-agent JSON validation with retry as planned; without this, future MiniMax JSON bugs will keep silently infecting downstream steps.
6. **(P2) Re-run the `panda_butterfly_test` end-to-end with a live ComfyUI** to produce actual image/video outputs and verify the bug fixes. The current `images/`, `videos/`, `character_sheets/` directories in the test output are empty.
7. **(P2) Fix Bug 2.9** - add `tests/test_wave_organizer.py` with at least 3 cases.
8. **(P2) Fix Bug 2.6** - update `SKILL.md` and `temp/implementation_plan.md` to reflect the MiniMax model switch.
9. **(P3) Fix Bugs 2.7, 2.8, 2.10, 2.11, 2.12** - dead code cleanup, missing init, dedup in legacy builder, share workflow_builder, normalize generated_by.
10. **(P3) Address Section 3.1** - persist each agent's namespace to disk immediately so resume-from-crash works.
11. **(P3) Address Section 3.2** - add Pydantic validator for the 3-shot-max continuation chain rule.

---

## 6. Files Inspected

Plan:
- `discussion-and-docs/deterministic-implementation-resource/User-Plan.md`
- `discussion-and-docs/deterministic-implementation-resource/temp/implementation_plan.md` (1154 lines)
- `discussion-and-docs/deterministic-implementation-resource/AI-Film-making.md` (referenced, not read in full)
- `discussion-and-docs/deterministic-implementation-resource/ideogram-character-sheet.json` (referenced)
- `discussion-and-docs/deterministic-implementation-resource/FLUX-prompting-guide/` (referenced)
- `discussion-and-docs/implementation/V13_story_to_video_deterministic.md`
- `discussion-and-docs/implementation/V14_story_to_video_deterministic.md`
- `discussion-and-docs/implementation/V15_story_to_video_deterministic.md`
- `discussion-and-docs/implementation/V16_story_to_video_deterministic.md`

Implementation:
- `skills/story-to-video-deterministic/SKILL.md`, `main.py`, `config.py`, `requirements.txt`
- `skills/story-to-video-deterministic/agents/__init__.py` and all 8 step files
- `skills/story-to-video-deterministic/schemas/blueprint.py`, `schemas/prompts.py`
- `skills/story-to-video-deterministic/tools/file_tools.py`, `comfyui_tools.py`, `workflow_builder.py`, `__init__.py`
- `skills/story-to-video-deterministic/scripts/wave_organizer.py`, `wave_executor.py`
- `skills/story-to-video-deterministic/system_prompts/*.md` (8 files)
- `skills/story-to-video-deterministic/tests/test_schemas.py` (ran with pytest - 2 passed)

Generated artifacts on disk (forensic):
- `/Users/muneesraja/Documents/growthlabs-vault/story-to-video-deterministic/panda_butterfly_test/Director_script.md`
- `.../director_visual_blueprint_structure.json`
- `.../director_visual_blueprint.json` (2 bytes - the bug)
- `.../prompts.json` (18.5KB)
- `.../generator_wave_1.json`, `.../generator_wave_2.json`
- `.../images/`, `.../videos/`, `.../character_sheets/` (all empty)

Test runs:
- `python3 -m pytest tests/ -v` -> 2 passed, 0 failed
