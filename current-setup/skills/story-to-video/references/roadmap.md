# Improvements Roadmap

## Done ✅
- [x] **Manifest v2 schema**: shots array, facial_expression per shot, mood (renamed from emotion), total_shots_budget, personality_traits per character
- [x] **Manifest v3 schema**: per-shot `characters_present` override to solve ghost-character problem
- [x] **Facial expression vocabulary**: 20+ emotions mapped to 3-region visual descriptors (mouth + eyes + brow)
- [x] **Qwen Image Edit prompting guide**: Anchor phrase, three-region face rule, expression patterns, pitfalls, length guidelines, **Reddit community research** (8 threads, 600+ comments — offset fixes, LoRA reviews, multi-ref strategies, inpaint masking, max-quality workflow, 2509-vs-2511 comparison, face dataset tips)
- [x] **Flux 2 Dev Turbo prompting guide**: SCALIST formula, ReferenceLatent chain, 8-step distilled model, guidance=4.0, 1344×768, color-grading suffix, mandatory prompt checklist
- [x] **Phase 0B approval gate**: Character sheet review with inline images, per-character approval, auto-reject for non-neutral expressions
- [x] **ComfyUI T2I character sheet fallback**: When Gemini credits unavailable, generate character sheets via Flux 2 Dev Turbo in T2I mode (0 references). 1×4 layout preferred over 2×7 for consistency. I2I reference anchoring for regenerations.
- [x] **Character design pitfalls documented**: "Literal food" pitfall (back views render as actual food), "Human body" pitfall (model adds human parts to non-human chars), "Multi-view inconsistency" (use 1×4 layout + I2I anchoring)
- [x] **Evaluation v2**: 5-category scoring with facial_expression (0.25 weight), character sheet evaluation with expression_neutrality
- [x] **Manifest-driven script**: `generate_scene.py` loads `story_manifest.json` via `--manifest` flag
- [x] **Auto image check**: Script queries `/object_info/LoadImage` dynamically at start
- [x] **ComfyUI API pitfalls**: All 10 documented with fixes in `references/comfyui/api-pitfalls.md`
- [x] **Workflow template**: `assets/workflow-api-template.json` — standalone reusable JSON
- [x] **Auto-mapping ref selection**: `build_ref_mapping()` derives character→filename from naming convention `{character_id}_reference_sheet.png`. No more hardcoded `DEFAULT_REF_IMAGES` — works for any story.
- [x] **End-to-end test (teddy bear story)**: 5 chars, 6 scenes, full Phase 0→1→2 pipeline. Character sheets generated via paid Gemini key, uploaded to ComfyUI, all 6 scenes generated with correct per-scene refs. Character consistency holds in early scenes but drifts in later multi-char scenes (4+ chars).
- [x] **Evaluate-and-refine loop integration**: `generate_scene.py` now supports `--evaluate`, `--max-iterations`, `--cleanup-iters`, and `--evaluate-only` flags
- [x] **Vision evaluation via Gemini 2.5 Flash**: Direct Google API call (free tier, `responseMimeType: application/json`, `temperature: 0.2`)
- [x] **Raw sub-scores with weighted average**: Vision model returns 4 category scores; script computes weighted average (character_accuracy=0.40, scene_composition=0.25, action_depicted=0.20, style_consistency=0.15)
- [x] **Chain-of-thought evaluation prompt**: "Describe what you see first, then score" for audit trail and reduced hallucination
- [x] **Pass threshold**: score ≥ 7 AND no critical issues (AND, not OR)
- [x] **Prompt refinement**: Refined prompts are JSON-sanitized before ComfyUI injection (escape quotes, newlines, backslashes)
- [x] **Pipeline summary**: Auto-generates `pipeline_summary.json` at story root after full run
- [x] **Cleanup iteration files**: `--cleanup-iters` flag deletes non-best iteration files after scene passes
- [x] **Standalone evaluator**: `evaluate_scene.py` can be run independently for spot-checking images
- [x] **Bulk queue + poll pattern**: Queue all shots at once, poll for completion in background. More efficient than sequential `execute_code` batches for 20+ shots. Uses `python3 -u` for unbuffered output.
- [x] **Flux 2 Dev Turbo workflow template**: Dynamic single-chain ReferenceLatent with ComfySwitchNode for I2I/T2I toggle. Auto-prunes/spawns refs. Template: `flux-2-dev-turbo.json`
- [x] **Pluffy Bun story**: 7 scenes, 50 shots, 2 characters (Puffy + General Jalapeño), 3D Pixar-style pastel. Full pipeline executed successfully.
- [x] **OpenRouter Gemini 3.1 Flash Lite eval provider**: `--provider openrouter` with `reasoning.effort: "medium"` (~2K-4K thinking tokens). Priority: OpenRouter > Gemini API. Eval JSON includes `reasoning`, `provider`, `model`, `thinking_tokens` fields. Cost: ~$0.12/50 shots.
- [x] **Provider abstraction in gemini_eval.py**: `resolve_provider()` auto-detects from env (`OPENROUTER_API_KEY` > `GEMINI_API_KEY`). `call_openrouter_vision()` uses OpenAI-compatible format with thinking support. Both `evaluate_scene.py` and `generate_scene.py` support `--provider` flag.
- [x] **Face structure reference fix pattern**: When model doesn't apply face details from reference sheet, add explicit `CRITICAL FACE DETAIL:` block describing the face plate/cutout structure. Proven: scene_005_shot002 6.85→8.95, scene_007_shot002 8.3→9.5.
- [x] **Batch regeneration script**: `regenerate_refined.py` — loads refined prompts from eval JSONs, builds workflows, queues on ComfyUI with Basic Auth, polls for completion, downloads results. Tested with 9 shots on pluffy-bun.
- [x] **Eval refinement loop end-to-end**: Full cycle tested — evaluate → identify failures → regenerate with refined prompts → re-evaluate. Pluffy-bun: 71%→86%→90% pass rate across 3 iterations.
- [x] **Custom node dependency documented**: `comfyui-kjnodes` required for `flux-2-dev-turbo` template (ImageResizeKJv2, GetImageSizeAndCount, ColorMatchV2, GrowMaskWithBlur). Without it, I2I shots fail with `missing_node_type`.
- [x] **Multi-image reference evaluation**: Always send reference sheets from `prompt.json` alongside generated image (max 4 images). Auto-detects `characters/` directory. `--references-dir` flag for explicit path.
- [x] **Landscape scoring fix**: `character_accuracy`/`facial_expression` → `null` for no-character shots, excluded from weighted score. Prevents false negatives on environment shots.
- [x] **ComfyUI Basic Auth support**: `--auth` flag on `generate_scene.py` + `auth` parameter on all `comfyui_api.py` functions + `upload_image()` helper.
- [x] **Reference contamination pitfall discovered**: Sending previous failed generation as ComfyUI reference causes score regression (scene_004_shot004: 6.93→3.8). Fix: character refs only + stronger prompt → 9.60. Documented in SKILL.md and eval-pitfalls.md.
- [x] **Pluffy Bun final stats**: 50/50 evaluated, 49/50 pass (98%), avg 8.5. scene_004_shot004 fixed via regeneration best practices.
- [x] **Image cleanup**: Removed 34 duplicate/intermediate scene images (45.3MB), keeping only the best version per shot.
- [x] **LTX 2.3 I2V integration**: Expand the `story-to-video` skill to video generation. Created the `ltx-23-i2v-dev` workflow template, implemented `generate_video.py` orchestration script, created `motion-prompt-json-schema.md` schema doc, and added a model downloader script (`ltx-23-i2v-dev.sh`).


## In Progress
- [ ] **`--upload-url` flag**: Add to `generate_story_assets.py` so Step B (generate sheets) + Step C (upload to ComfyUI) happen in one command. Replaces the old "auto-upload" concept — upload belongs with generation, not consumption.
- [ ] **Negative prompt node**: Add `TextEncodeQwenImageEditPlus` node for negative prompts to suppress unwanted features (e.g., "gold jewelry on rabbit")
- [ ] **Fox reference sheet**: Generate the missing character ref and upload
- [ ] **Character consistency late scenes**: Multi-character scenes (4+ chars like Scene 6) show character drift — some characters don't match their reference sheets. Likely caused by only 3 ref slots (4th+ character gets no visual anchor). Investigate: stronger identity text in prompt, negative prompts for wrong features, or split multi-char scenes.

## Multi-Reference Expansion (5 refs per scene)

**Goal:** Support up to 5 reference images per scene — a mix of character sheets and background references. This enables richer scenes with multiple named characters + environment anchors.

### Current State
| Model | Max Refs | Template | Notes |
|---|---|---|---|
| Flux 2 Dev Turbo | 4 | Dynamic single-chain | Works well, VRAM-friendly |
| Flux 2 Klein | 4 | Dynamic chain | Similar to Dev Turbo |
| HiDream O1 Dev | 12 | Dynamic 4+spawn | Already supports 5+ |

### Expansion Plan

**Phase 1: Extend Flux 2 Dev Turbo to 5 refs**
- Modify `flux-2-dev-turbo.json` template: increase `_max_references` from 4 to 5
- Test VRAM impact — each ReferenceLatent chain adds ~200-400MB VRAM
- If VRAM exceeds 24GB on 3090: implement smart pruning (drop lowest-priority refs)
- Update `_spawn_dev_turbo_refs()` to handle 5th slot
- Estimated effort: 1-2 hours (template change + testing)

**Phase 2: Background/environment reference support**
- Add `background_ref` field to manifest scene-level (e.g., `"background_ref": "cream_world_panorama.png"`)
- Agent generates environment reference sheets (T2I panoramas of key locations)
- Environment refs count toward the 5-ref limit
- Prompt composition: environment ref goes LAST (lowest priority), after character refs
- Update Phase 1.5 docs with background ref selection rules

**Phase 3: Smart per-scene ref selection algorithm**
- Priority scoring for refs per shot:
  1. Characters with facial expressions in the shot (highest priority)
  2. Characters mentioned in the shot action
  3. Background/environment ref (if scene-level `background_ref` set)
  4. Characters only in scene-level `characters_present` but not in shot action (lowest, exclude)
- When >5 refs needed: drop lowest-priority refs, flag in `eval_context.excluded_characters`
- Agent decision tree:
  ```
  shot_refs = []
  for char in shot.characters_present:
      if char has expression or in action: shot_refs.append(char, priority=HIGH)
  if scene.background_ref: shot_refs.append(bg, priority=LOW)
  if len(shot_refs) > 5: drop lowest priority, note in eval_context
  ```

**Phase 4: Multi-character testing**
- Test with 5-character story (e.g., "Hare and Tortoise" has 5 chars)
- Measure character consistency at 5 refs vs 4 refs
- If quality drops: consider HiDream (12 refs) for 5+ character scenes
- Document optimal ref count per model

### Files to Modify
- `assets/workflow-templates/flux-2-dev-turbo.json` — increase `_max_references`
- `scripts/workflow_builder.py` — `_spawn_dev_turbo_refs()` handles 5th slot
- `references/phases/phase-1-prompt-composition.md` — background ref rules, priority scoring
- `references/story-manifest-format.md` — add `background_ref` to scene schema
- `SKILL.md` — update capabilities table

## Post-Execution Debug (Little Tiger, Flux 2 Klein Run — May 25)

### 🔴 Critical: Reference Duplication
- **21/42 shots** had `toby_reference_sheet.png` duplicated to pad the 2-slot minimum
- Causes model to hallucinate duplicate characters (two Tobys)
- **Fix applied**: Updated Phase 1.5 docs — "NEVER duplicate refs, builder handles it"
- **Remaining**: Verify `workflow_builder.py` correctly handles single-ref pruning for Flux (template min = 2 slots)

### 🔴 Critical: Shot-level Character Filtering
- **7 shots** attached Taro's reference when Taro was NOT in the shot action (close-ups, solo shots)
- Model invented phantom third tigers to "use" the unused reference
- **Fix applied**: Added "Shot-level Character Filtering (CRITICAL)" section to Phase 1.5 docs
- **Remaining**: Consider adding `characters_present` per-shot override to manifest v3 schema

### 🟡 Major: No Spatial/Positioning Cues
- Characters placed side-by-side with zero distance cues
- **Fix applied**: Added "Characters Too Close Together" pitfalls (#4) to Flux prompting guide
- **Remaining**: Add spatial positioning as mandatory checklist item in prompt composition

### 🟡 Major: No Anti-Deformation Anchoring
- Extra tails, deformed limbs in several shots
- **Fix applied**: Added "Deformed Characters" pitfalls (#5) with positive anchoring technique to Flux guide
- **Remaining**: Add body-anchoring line as mandatory in prompt template

### 🟡 Major: Prompts Too Long (1,000–1,500 chars / 250–350+ tokens)
- Flux guide says 50-150 tokens ideal, but actual prompts were 2–3x over
- Full identity_spec repeated every shot, full scene setting, full style directive
- **Fix needed**: Token budget system — abbreviate identity specs after first mention, abbreviate style to short form, don't re-describe settings if already in previous shot of same scene
- **Remaining**: Add prompt length validation and auto-truncation to composition guidelines

## Nice-to-Have
- [ ] **Parallel generation**: Queue multiple scenes at once (ComfyUI handles queuing)
- [ ] **Seed sweep**: Generate multiple seeds per scene for best-pick selection
- [ ] **Image review step**: Auto-send generated images to Discord for review before proceeding
- [ ] **Variation prompts**: Support "variation of scene X with changes Y" for iterating
- [ ] **Custom node mapping**: Allow different ComfyUI setups (not hardcoded node IDs)
- [ ] **Negative prompt support**: Second `TextEncodeQwenImageEditPlus` node for suppressing unwanted features (e.g., "gold jewelry", "extra fingers") — especially useful for iteration 2+ refine loops

## Future
- [ ] **FFmpeg assembly**: Auto-stitch clips with transitions and audio
- [ ] **Voiceover**: TTS narration per scene synced to video length
