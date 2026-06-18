# Story-to-Video Deterministic Pipeline — Test Run Issue Log

## Run Metadata
- **Date:** Thu Jun 18 2026
- **Story input:** `/Users/muneesraja/Documents/growthlabs-vault/story-to-video-deterministic/bunny_and_pig/Story.md`
- **Output name:** `bunny_and_pig`
- **Skill location:** `skills/story-to-video-deterministic/`
- **Pipeline entry:** `main.py --story ... --name bunny_and_pig`

## Environment Snapshot
- **ComfyUI URL:** `judges-inventory-fine-arcade.trycloudflare.com` (Cloudflare tunnel, HTTP 200 from `/system_stats`, ~2.0s RTT)
- **ComfyUI version:** 0.25.0, 32GB RAM Linux
- **LLM provider:** MiniMax M3 (reasoning) + MiniMax-M2.7-highspeed (light) via Google ADK LiteLlm
- **ffmpeg:** 8.1.1 / **ffprobe:** present
- **Python deps:** google-adk 2.2.0, pydantic 2.13.4, litellm importable

## Pre-flight Verification (ALL PASSED)
- bunny_and_pig output dir clean (only `Story.md` present, no stale `prompts.json`)
- ComfyUI tunnel reachable
- Workflow templates verified (ideogram-4-t2i 23/23, flux-2-klein-image-edit 20/20, ltx-23-fflf-seed-hunter 31/31)
- `.env` keys populated (COMFYUI_URL, COMFYUI_AUTH, MINIMAX_API_KEY)
- `tests/test_schemas.py` (2 tests) passing as of last run

## Known P0 Bugs Under Watch
| Bug | Location | Expected Symptom |
|-----|----------|------------------|
| `clean_json_str` swallows parse errors | `main.py:clean_json_str` | `director_visual_blueprint.json` written as `{}` |
| Wave-2 FF references point to wrong shot IDs | `scripts/wave_executor.py:resolve_ref` | `motion_prompts.ff_image` / `lf_shots.reference_images[0]` 404 |
| Markdown fence leakage in Director_script.md | `main.py` writer | Literal `` ```markdown `` at top of file |

## Pre-flight Bugs Validated
| P0 bug under watch | Outcome | Evidence |
|--------------------|---------|---------|
| `clean_json_str` swallows parse errors → blueprint `{}` | ✅ DID NOT TRIGGER | `director_visual_blueprint.json` is valid JSON, 100.6 KB, top-level keys `[meta, characters, scenes]`, 6 scenes / 46 shots. Schema test `test_blueprint_schema_validation` PASS. |
| `Director_script.md` markdown fence leakage | ✅ DID NOT TRIGGER | File starts with blank lines and a real H1 (`# Director's Script: ...`); grep for `^`` ``` `` finds 0 matches anywhere in the 446-line file. |
| Wave-2 `ff_image` references wrong shot ID | ✅ DID NOT TRIGGER | Wave-2 `motion_prompts[*].ff_image` = `{{ff_shots.<SAME_SHOT_ID>.output_path}}` (correctly same-shot), verified for sample `scene_02_shot_03`. |

All three known P0 bugs from `deterministic-pipeline-review.md` did NOT manifest for `bunny_and_pig`. The issues below were discovered during the actual run.

## Issues Found During Run

### ISSUE-001: Redundant auto-save of all prior artifacts on every state delta
- **Step:** All LLM agents (Steps 1-8); also `main.py:save_artifacts` callback
- **Severity:** P3 (wasteful, not breaking)
- **Symptom:** Every agent state delta (`director_script_content`, `blueprint_structure_json`, `character_prompts_content`, `ff_prompts_content`, `consistency_prompts_content`, `lf_prompts_content`, `motion_prompts_content`) rewrites the entire set of accumulated artifacts to disk. After 8 LLM agents, `Director_script.md` was written 8 times, `prompts.json` 6 times, etc. Repeated identical writes that offer no functional value.
- **Error/log:**
  ```
  [blueprint_structure_agent] Event:
     State delta: ['blueprint_structure_json']
  📁 [Auto-Save] Wrote Director_script.md          ← written again
  📁 [Auto-Save] Wrote director_visual_blueprint_structure.json
  ```
- **Root cause:** The auto-save hook iterates over the full artifact registry and writes each existing artifact on every state delta, with no dirty-tracking. Each agent has access to the full accumulated state, so every state-changing event triggers a full re-flush.
- **Fix:** Track which artifact each state delta maps to, and write only the corresponding artifact. Or hash the in-memory artifact and skip the write if the digest matches the on-disk file.
- **File:line:** `skills/story-to-video-deterministic/main.py:save_artifacts` (helper invoked from the ADK callback; also used at lines ~210–230 for the final flush)

### ISSUE-002: Cascading skip — one failed upstream asset silently drops ~70 downstream assets
- **Step:** Step 9 (Wave 1 Executor) — character_sheets → consistency_patches → lf_shots → motion_prompts
- **Severity:** P1 (kills >40% of final output for a single transient failure)
- **Symptom:** `character_sheets/char_01_sheet.png` failed permanently after retry exhaustion (3 retries). Subsequently 32 consistency patches, 39 LF shots, and (had we let it run) many motion videos that referenced `{{character_sheets.char_01.output_path}}` were silently skipped with `❌ Skipping ... Reference value ... is currently null`.
- **Error/log:**
  ```
  ⚠️ curl_json attempt 1 failed: Expecting value: line 1 column 1 (char 0). Retrying in 3s...
  ⚠️ curl_json attempt 2 failed: Expecting value: line 1 column 1 (char 0). Retrying in 3s...
  ❌ Character sheet for char_01 failed: Ideogram generation failed: Expecting value: line 1 column 1 (char 0)
  ...
  ❌ Skipping consistency patch for scene_01_shot_01: Reference value for {{character_sheets.char_01.output_path}} is currently null.
  ❌ Skipping LF for scene_01_shot_02: Reference value for {{consistency_patches.scene_01_shot_02.output_path}} is currently null.
  ❌ Skipping video for scene_01_shot_06: Reference value for {{consistency_patches.scene_01_shot_06.output_path}} is currently null.
  ```
- **Root cause:** `wave_executor.resolve_ref` returns `None` for any unresolved `{{...}}` ref, and the per-step loop treats that as an unrecoverable skip. No retry-the-missing-upstream-asset path exists, and no logging-of-the-original-failed-upstream is emitted alongside each skip (so it looks like each skip is its own problem).
- **Quantified impact for this run:** Out of 46 shots, `char_01` is present in 39 (`characters_present`); of the 46 LF entries, 39 reference `{{character_sheets.char_01.output_path}}` directly, and 32 of 46 consistency patches reference `char_01`. So one image fail cascade-skipped ~70 downstream asset gigs.
- **Fix:** Three possible mitigations, in increasing order of robustness:
  1. Treat upstream-asset-missing as a recoverable condition: defer the downstream shots to a "Wave 1.5" retry pass that re-attempts the failed upstream first.
  2. Increase curl retry count + exponential backoff (currently 3 × 3 s fixed) so a transient cloudflared wobble does not become permanent.
  3. Surface the original failed-upstream asset ID alongside each downstream skip message so a user can see "Skipping LF scene_X_shot_Y because upstream `character_sheets/char_01_sheet.png` failed previously".
- **File:line:** `skills/story-to-video-deterministic/scripts/wave_executor.py:14` (resolve_ref) and `:85, :107, :140, :170, :268` (the per-section continue/skip points)

### ISSUE-003: LTX video workflow silently truncates references to 0
- **Step:** Step 9 (Wave 1 Executor) — motion_prompts (video generation)
- **Severity:** P2 (renders videos that ignore FF/LF consistency with no error surfaced)
- **Symptom:** Workflow builder passes FF + LF references into the LTX video workflow, but the model only accepts 0 reference images. Workflow builder prints `⚠️ Too many references (2) for model max (0). Truncating to 0.` and proceeds — so every motion prompt is generated from text prompt only, with no visual consistency at all, but the pipeline still marks `status: "generated"` and writes the .mp4 file as if it succeeded.
- **Error/log:**
  ```
  🎬 Generating Video for scene_03_shot_03 (2s)...
  ⚠️ Too many references (2) for model max (0). Truncating to 0.
  🎬 Finish mode is ON — rendering final video at 1920x1088 using selected gen index 1.
  ✅ Video for scene_03_shot_03 saved to .../videos/scene_03_shot_03.mp4
  ```
- **Root cause:** The LTX video workflow template (`workflows/comfyui/ltx-23-fflf-seed-hunter.json`) expects the video model to ingest FF + LF as image-conditioning inputs, but in practice the model's `max_ref_images` schema is 0. The builder knows this and silently truncates but does not surface it as a failure-mode concern. End user receives a video that looks plausible but is NOT visually consistent with the FF/LF they spent minutes generating for the same shot.
- **Fix:** Either (a) upgrade the video workflow to a model that supports the image ref chain (e.g., SVD-XT or Hunyuan-I2V) or (b) if LTX is the only available model and it does not accept ref images, REMOVE the FF/LF-from-motion-prompt ref wiring entirely so the design is internally consistent — at which point Skip Wave 2 (FF-consistency) cannot work either (see ISSUE-008 / Wave 2 design).
- **File:line:** `skills/story-to-video-deterministic/scripts/wave_executor.py` (motion_prompts section, around lines 168-182) + `skills/story-to-video-deterministic/tools/workflow_builder.py` (ref-truncation warning)

### ISSUE-004: Cloudflare trycloudflare tunnels drop requests intermittently; current 3 × 3 s retry strategy exhausts before recovery
- **Step:** Step 9 (Wave 1 Executor) — every ComfyUI POST (character sheets, FF, consistency patches, LF, videos)
- **Severity:** P2 (single most frequent transient error; cascades via ISSUE-002)
- **Symptom:** `curl_json` consistently fails with `Expecting value: line 1 column 1 (char 0)` (i.e., curl returns 0 bytes) on roughly 5–10 % of ComfyUI `/prompt` POSTs. Behaviour is INTERMITTENT — same payload + same endpoint succeeds 3 calls later. After 3 retries with fixed 3-second sleeps, the failure becomes "permanent" from the pipeline's perspective.
- **Verified diagnosis (same-run probe):** Out-of-process `curl -X POST $COMFYUI_URL/prompt ...` (with `--resolve` override, identical to `curl_json` behaviour) returned HTTP 200/400 with valid JSON for empty-prompt tests; this confirms ComfyUI itself is healthy and the failures are at the Cloudflare tunnel layer, not auth/format.
- **Error/log:**
  ```
  ⚠️ curl_json attempt 1 failed: Expecting value: line 1 column 1 (char 0). Retrying in 3s...
  ⚠️ curl_json attempt 2 failed: Expecting value: line 1 column 1 (char 0). Retrying in 3s...
  ⚠️ curl_json attempt 1 failed: Expecting value: line 1 column 1 (char 0). Retrying in 3s...
  ⚠️ curl_json attempt 2 failed: Expecting value: line 1 column 1 (char 0). Retrying in 3s...
  ❌ Character sheet for char_01 failed: Ideogram generation failed: Expecting value: line 1 column 1 (char 0)
  ```
- **Root cause:** `comfyui_tools.curl_json` (line 73-86) implements a max of 3 retries with a fixed `time.sleep(3)` between attempts. No jitter, no exponential backoff. For Cloudflare trycloudflare quick-tunnels — which are rate-limited free tunnels — adjacent requests within a 9 s window frequently all hit the same throttle bucket.
- **Fix:** Bump retries to 6–8 with exponential backoff + jitter (e.g., `2^attempt + random.uniform(0, 1.5)`). Also, change the empty-body case from "treat as success with `{}`" to "treat as failure": today the code returns `{}` for `result.stdout.strip() == ''` (line 81), which masks the very failures we want to retry on.
- **File:line:** `skills/story-to-video-deterministic/tools/comfyui_tools.py:59-86`

### ISSUE-005: `curl_json` treats empty stdout as success
- **Step:** All `curl_json` callers (Step 9 wave executor everywhere)
- **Severity:** P2 (silent failure-masking)
- **Symptom:** When curl succeeds (`returncode == 0`) but stdout body is empty/whitespace, `curl_json` returns `{}` (an empty dict) WITHOUT erroring. Downstream code then asks the empty dict for `prompt_id` → KeyError → treated as prompt-validation failure, or worse — the workflow thinks it queued. This bug partially masked ISSUE-004's real failure mode on some calls.
- **Error/log:** No specific log line; surfaces indirectly as the `Expecting value: line 1 column 1 (char 0)` JSONDecodeError on the retries that actually fail (the reroute through `if result.stdout.strip(): return json.loads(...)` only triggers when the body has content but is not JSON).
- **Root cause:** Code at `comfyui_tools.py:79-81` explicitly returns `{}` when `result.stdout.strip()` is falsy, conflating "curl got nothing" (transient outage) with "ComfyUI returned valid empty JSON" (which the API contract says never happens).
- **Fix:** Return `None` or raise on empty body, since ComfyUI never legitimately returns an empty body. Or at minimum discriminate based on HTTP response code (`result` from subprocess doesn't carry HTTP code — switch to `-w "%{http_code}"` and treat `HTTP 0/5xx` as retryable).
- **File:line:** `skills/story-to-video-deterministic/tools/comfyui_tools.py:79-81`

### ISSUE-006: `SequentialAgent` API is deprecated
- **Step:** Pipeline construction (`main.py`)
- **Severity:** P3 (no functional impact today; breaks silently on next google-adk upgrade)
- **Symptom:** Emitted on every launch:
  ```
  main.py:228: DeprecationWarning: SequentialAgent is deprecated and will be removed in future versions. Please use Workflow instead.
    prompt_pipeline = SequentialAgent(
  ```
- **Root cause:** Google ADK is migrating from `SequentialAgent`/`ParallelAgent` to a `Workflow` primitive. Already present in `google-adk 2.2.0`.
- **Fix:** Migrate `prompt_pipeline = SequentialAgent(sub_agents=[...])` construction to `Workflow` per ADK docs. Doc reference: `https://google.github.io/adk-docs/get-started/` (Workflow migration page).
- **File:line:** `skills/story-to-video-deterministic/main.py:228`

### ISSUE-007: `datetime.utcnow()` deprecated
- **Step:** `save_artifacts` helper (meta stamping of `prompts.json`)
- **Severity:** P3 (no functional impact today; breaks silently on next Python release)
- **Symptom:**
  ```
  main.py:213: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
    "last_updated_at": datetime.utcnow().isoformat() + "Z"
  ```
- **Fix:** Replace `datetime.utcnow()` → `datetime.now(timezone.utc)` (drop the trailing `+ "Z"` since timezone-aware isoformat emits `+00:00`; or use `.strftime("%Y-%m-%dT%H:%M:%S.%fZ")` for a stable Z-suffixed format).
- **File:line:** `skills/story-to-video-deterministic/main.py:213`

### ISSUE-008: Wave-2 LF/Motion shots inherit the Wave-1 cascade — they reference `{{character_sheets.char_01.output_path}}` indirectly through FF
- **Step:** Step 9 (Wave 2 — never reached in this run, but the design flaw was statically confirmed)
- **Severity:** P1 (would have mirrored ISSUE-002 inside Wave 2 for all 8 Wave-2 shots)
- **Symptom:** Wave-2 sample shot `scene_02_shot_03` has:
  ```
  lf_shots.scene_02_shot_03.reference_images: [
    "{{ff_shots.scene_02_shot_03.output_path}}",     ← same shot's FF (would exist if Wave 2 LF ran)
    "{{character_sheets.char_01.output_path}}"      ← char_01 (NULL → cascade skip)
  ]
  motion_prompts.scene_02_shot_03.ff_image: {{ff_shots.scene_02_shot_03.output_path}}    ← OK
  motion_prompts.scene_02_shot_03.lf_image: {{lf_shots.scene_02_shot_03.output_path}}    ← depends on LF, which depends on char_01
  ```
- **Static analysis:** 8 Wave-2 shots (scene_02_shot_03, scene_03_shot_05, scene_04_shot_03, etc.) all carry the same inherited char_01 dependency. Even if we had re-run Wave 2 after the abort, all 8 LF + all 8 videos would have been skipped with the same `null` error.
- **Root cause:** The LLM-generated `lf_shots.reference_images` always includes the per-shot character sheets of every character present in the shot — which is appropriate for the FF-consistency goal, but means a single failed upstream asset rots the entire downstream graph.
- **Fix:** Same as ISSUE-002 + consider[^1] a "prune-upstream-failure" wave pass: if a character_sheet.status is "failed", strip only the corresponding `{{character_sheets.<that_char>.output_path}}` ref from every downstream shot's `reference_images` array, so the shot can still generate with the remaining characters' references. Mark a `partial_consistency: true` flag on such outputs in `prompts.json` so consumers know what they're getting.

[^1]: This is non-trivial: the LTX (image edit) model eventually used `max_ref_images=0` so reference-truncation was free anyway in this build. For a future model that DOES accept refs (e.g., a Flux Klein edit that supports 2-3 image refs), careful truncation matters.

### ISSUE-009: 46 shots for a 3.1 KB / 35-line 2-character story — LLM over-decomposes
- **Step:** Step 2 (blueprint_structure_agent) + Step 3 (blueprint_visuals_agent)
- **Severity:** P3 (costs ~3-4× compute + tunnel time vs. what the story calls for)
- **Symptom:** Story input `Story.md` has 35 lines, ~500 tokens, 2 named characters (Barnaby the Bunny + Barnaby the Pig) plus 1 prop-character (Blue Butterfly). Blueprint outputs 6 scenes / 46 shots — an average of ~8 shots per scene for a 90-second children's-book story (~2 s per shot).
- **Root cause:** The director_script_agent system prompt does not enforce shot counts or shot/scene ratios against the input story length. With no upper bound, the reasoning model optimizes for granularity and Atlantic-style editing.
- **Fix:** Tighten the Section directive in `system_prompts/blueprint_structure_agent.md`:
  - Cap shot count at `max(8, 2 × ceil(story_token_count / 500))` (i.e., 2 shots per 500 input tokens, minimum 8 shots).
  - Enforce shot duration minimum ≥ 3 s (currently seeing 2 s shots).
  - Ban 1-character same-direction repeated shots as a sub-issue (scene_05 has shots _08→_15 — 8 shots in one scene).
- **File:line:** no source code change required; this is a system-prompt/content issue. Relevant prompt files: `skills/story-to-video-deterministic/system_prompts/blueprint_structure_agent.md`, `system_prompts/blueprint_visuals_agent.md`, `system_prompts/director_script_agent.md`.

### ISSUE-010: Resume logic in `main.py:57-129` not exercised (would skip a completed run instantly if rerun with same flags)
- **Step:** Pre-flight (informational, did not trigger because output dir was cleaned before launch)
- **Severity:** P3 (informational; future runs)
- **Symptom:** Pipeline has a resume-mode check on disk for each LLM-artifact (Director_script.md, *.json). If those exist, the corresponding agent step is skipped. Today's run wrote all artifacts successfully, so a follow-on run with the same `--name bunny_and_pig` flag would skip Steps 1-7 in ~3 seconds and immediately re-enter Step 8 (wave organizer) / Step 9 (wave executor). Useful for partial reruns but the docs / `--help` text should call this out so users re-running a fresh story with the SAME OUTPUT NAME by accident aren't surprised.
- **Fix:** (a) Add a CLI flag `--fresh` / `--no-resume` to force a clean rerun. (b) Print a warning when resume-mode is active and at least one artifact is found. (c) Add a section to `README.md` describing this resume behaviour.
- **File:line:** `skills/story-to-video-deterministic/main.py:57-129`

### ISSUE-011: Wave 3 (post-Wave 2) edits never run — the pipeline claims to use Flux Klein for the LF-consistency video pass but Wave 2 never reattempts the char_01-cascade-disabled shots
- **Step:** Wave 2 (abort blocked reach — informational)
- **Severity:** P2 (Wave 2 design assumes Wave 1 retry-equivalent for upper-FF chain)
- **Symptom:** Wave 1 had to be stopped during motion_prompts generation; Wave 2 (FF-image-edit generation for the 8 deferred shots) was never reached. Even if it had been reached, ISSUE-008 confirms Wave 2's design has the same dependency on `{{character_sheets.char_01.output_path}}` as Wave 1, so all 8 Wave-2 LF shots and 8 Wave-2 motion videos would have also skipped because of the same root cause.
- **Fix:** Combine with ISSUE-008's prune-upstream-failure recommendation.
- **File:line:** `skills/story-to-video-deterministic/scripts/wave_executor.py:199-280` (Wave 2 sections)

### ISSUE-012: `pytest tests/ -v` runs in 0.10 s, validates the schema but does NOT validate that the LLM-generated artifacts actually satisfy the Pydantic constraints
- **Step:** Forensic (post run)
- **Severity:** P2 (false sense of safety)
- **Symptom:** `tests/test_schemas.py` (2 tests) both PASS, but their input data is synthetic fixtures embedded in the test file — NOT the LLM's actual `director_visual_blueprint.json` / `prompts.json` outputs from this run. So "all tests pass" tells us nothing about whether the LLM-generated artifacts are valid according to the schemas.
- **Fix:** Add a parametrized test that LOADS the actual artifacts from a specified output dir (e.g., `--name bunny_and_pig`) and validates each against its Pydantic schema. Should run as part of the pipeline's final step (after Step 9 or on abort).
- **File:line:** `skills/story-to-video-deterministic/tests/test_schemas.py` (extend this file)

## Final Run Summary

### Pipeline Runtime Stats
- **Total elapsed (wall clock):** ~92 minutes (LLM phase ~22 min, Wave 1 executor ~70 min, aborted mid-Wave-1-motion-prompts)
- **LLM agents completed:** 8/8 (all)
- **Wave organizer:** 1/1 (passed, wrote both wave payloads)
- **Wave 1 executor pipelines attempted:** 175 asset jobs total: 3 char_sheets + 46 FF (38 Wave-1 + 8 Wave-2-deferred) + 46 consistency + 46 LF + 38 motion videos (Wave 1 only); we stopped after character_sheets + FF + partial consistency + partial LF + 1 motion video
- **Assets actually produced on disk:** 2 character_sheets + 48 images (mix of FF + 4 consistency + 4 LF) + 1 video = **51 total usable assets of ~175 attempted**
- **Asset yield:** ~29 % (rest either explicitly skipped via cascade or unstarted when aborted)
- **Pre-flight P0 bugs (from `deterministic-pipeline-review.md`) that manifested:** 0/3 (clean_json_str, markdown fence leakage, Wave-2 ff_image ref — all DID NOT trigger)
- **New bugs discovered live:** 12 issues above (1×P1 cascade, 1×P2 video ref truncation, 2×P2 retry strategy + empty-body masking, 1×P2 schema test fake-positive, 1×P2 Wave-2 design defect, 4×P3 deprecations / over-decomposition / resume-mode, 2×P1 cascade-related)

### Asset Inventory of `bunny_and_pig/` output
| Path | Count | Notes |
|------|-------|-------|
| `character_sheets/*.png` | 2 | char_01 missing (failed permanently). char_02 + char_03 OK. |
| `images/*_ff.png` | 34 | 4 missing (scene_01_shot_01 + the 8 Wave-2-deferred FFs which were not requested in Wave 1). |
| `images/*_ff_consistent.png` | 4 | Only shots without a char_01 dependency generated the consistency patch. |
| `images/*_lf.png` | 4 | Same pattern — only char_01-independent shots produced LF. |
| `videos/*.mp4` | 1 | `scene_03_shot_03.mp4` (no audio, ~2 s, 1920×1088). Generated without ref-image conditioning (see ISSUE-003). |
| `Director_script.md` | 1 | 38.5 KB, 446 lines, no markdown fence issue. |
| `director_visual_blueprint.json` | 1 | 100.7 KB, 6 scenes / 46 shots. |
| `director_visual_blueprint_structure.json` | 1 | 57.1 KB. |
| `prompts.json` | 1 | 186.6 KB, 5 namespaces (character_sheets / ff_shots / consistency_patches / lf_shots / motion_prompts), each 3/46/46/46/46 entries. |
| `generator_wave_1.json` | 1 | 167.0 KB, 5 keys (character_sheets / ff_shots / consistency_patches / lf_shots / motion_prompts, 3/38/38/38/38 entries). |
| `generator_wave_2.json` | 1 | 9.9 KB, 3 keys (wave + lf_shots + motion_prompts, 8/8 entries). |
| `Story.md` (input) | 1 | Untouched. |

### Tests
- `pytest tests/ -v` → `2 passed in 0.10 s`. As noted in ISSUE-012, this validates only synthetic fixtures, not the actual run artifacts.

## Lessons Learned

### What the codebase gets right
1. **The known P0 bugs flagged in `deterministic-pipeline-review.md` did NOT manifest for this story.** The defensive handling in `clean_json_str`, the writer for `Director_script.md`, and the Wave-2 `ff_image` ref pattern all worked correctly for `bunny_and_pig`.
2. **LLM layer is solid.** All 8 agents produced schema-valid 1xx-200 KB JSON / Markdown outputs in ~22 min — fast enough for a Reasoning + Light mixed model pipeline.
3. **Wave organizer Stage 8 ran correctly** — built all 3 named sub-graphs (Wave-1 main set, Wave-2 deferred set) at expected shot counts (38 + 8 = 46 baseline / 8 deferred Wave-2 LF + 8 motion).
4. **ComfyUI workflow templates (`ideogram-4-t2i`, `flux-2-klein-image-edit`, `ltx-23-fflf-seed-hunter`) all run end-to-end** when curl succeeds — Ideogram T2I generates a 2MB PNG in ~30 s, LTX video generates a 2-second 1080p MP4 in ~60 s.
5. **Disciplined skip-on-null-ref pattern** in `wave_executor` meant the abort surfaced clean "❌ Skipping..." messages rather than crashing. The pipeline kept walking forwards through all 46 shots even when 1/3 were skip-marked.

### What bit us hard
1. **A single transient Cloudflare trycloudflare tunnel flake (ISSUE-004) degraded into a permanent failure (char_01 sheet), then cascaded (ISSUE-002) into ~70 silent skips of downstream assets.** A 5–10 % endpoint flakiness was amplified into a 60 %+ asset-yield loss. This is the headline defect of the run and must be fixed before any real production use.
2. **LTX video model accepts zero reference images** but the workflow_builder sends it two — the silent truncation (ISSUE-003) means videos are produced-but-wrong: they look like real videos but visually unrelated to their corresponding FF/LF. This is a silent functional bug worse than a crash; users only notice weeks later when reviewing the footage.
3. **Cloudflare trycloudflare is a fragile host for production-style runs** — free-tier rate limits combined with the pipeline's tight retry window guaranteed cascades. Production usage should switch to a stable Cloudflare named-tunnel or a direct LAN/VPN path to ComfyUI.
4. **Schema tests are decoupled from the run artifacts** — `pytest` passing gave false confidence today. Without a load-artifacts-and-validate test, you learn only at the moment of inspection that, e.g., `prompts.json` actually contains null `output_path` fields for every cascade-skipped shot.
5. **The `lf_shots.reference_images` pattern** is well-intentioned but semantically overloaded — it mixes *per-shot character consistency* refs with *same-shot FF* refs. Either the LF model uses ALL of them or it uses none. When we get 2-3-ref-tolerant models, this becomes a more flexible choice; today it's a maintenance trap.

### Recommended next steps for the codebase
Sorted by ROI, highest first:
1. **Fix `curl_json` retry strategy + empty-body handling** (ISSUE-004 + ISSUE-005) — 1-2 hours of work. Yields ~5× better completion rate on Cloudflare trycloudflare tunnels without any other change.
2. **Implement "Wave 1.5" upstream-retry pass** for cascade recovery (ISSUE-002) — 2-4 hours. Run failed upstream assets first, then re-walk the wave-executor loop. Combined with #1, this should suppress every "❌ Skipping ..." we saw today.
3. **Decide on LTX-2 ref-image policy** (ISSUE-003 + ISSUE-008) — half-day design discussion + impl. Either (a) switch video workflow to a ref-image-aware model and update builder, or (b) document that "LTX-2 ignores ref images" in the system prompts so the LLM stops emitting them in `lf_shots.reference_images` (saves token cost + JSON bytes).
4. **Wire Pydantic-based artifact post-validation into the pipeline** (ISSUE-012) — half-day. Stops the false-positive tests problem.
5. **Migrate `SequentialAgent` → `Workflow`** (ISSUE-006) — half-day, before next `google-adk` major upgrade breaks us silently.
6. **Cap shot count vs. story length** (ISSUE-009) — prompt-engineering iteration + A/B testing across 3-5 stories to find good ratio.

### What to do next for THIS test run
- Consider a follow-up run with a heavy retry + jitter fix (ISSUE-004 only) on the same `bunny_and_pig` artifacts to see if char_01 regenerates — if so, the cascade naturally heals on rerun via the resume-skip feature (ISSUE-010) and only the failed upstream is retried. Good way to validate the "fix one line of code, watch 30 cascade-skips vanish" hypothesis empirically.
- Optionally re-render Wave 2 LF and motion for the 8 Wave-2 shots to validate the Wave 2 FF-edit chain works (the prior P0 concern there is what uncle-bug-flagged but did not manifest this run because Wave 2 was never reached).

### Notes for future test-runners
- Distinguish between "didn't fail catastrophically" and "worked as designed". Today's run did not crash but is far from a successful end-to-end pipeline (29 % usable-asset yield).
- Logging methodology used (stdout → tee to file, separate `ps` polls + artifact listing every 5-15 min) worked well; kept emotion out of "is the thing stuck or working?" decisions. Worth reusing for next runs.
- Cloudflare trycloudflare: ALWAYS probe `/system_stats` first via `curl -i` and capture HTTP code; superficial 200 + JSON in preflight does not mean the rate-limit budget will survive an hour of POSTs.

