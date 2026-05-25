# Improvements Roadmap

## Done ✅
- [x] **Manifest v2 schema**: shots array, facial_expression per shot, mood (renamed from emotion), total_shots_budget, personality_traits per character
- [x] **Facial expression vocabulary**: 20+ emotions mapped to 3-region visual descriptors (mouth + eyes + brow)
- [x] **Qwen Image Edit prompting guide**: Anchor phrase, three-region face rule, expression patterns, pitfalls, length guidelines, **Reddit community research** (8 threads, 600+ comments — offset fixes, LoRA reviews, multi-ref strategies, inpaint masking, max-quality workflow, 2509-vs-2511 comparison, face dataset tips)
- [x] **Phase 0B approval gate**: Character sheet review with inline images, per-character approval, auto-reject for non-neutral expressions
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

## In Progress
- [ ] **`--upload-url` flag**: Add to `generate_story_assets.py` so Step B (generate sheets) + Step C (upload to ComfyUI) happen in one command. Replaces the old "auto-upload" concept — upload belongs with generation, not consumption.
- [ ] **Negative prompt node**: Add `TextEncodeQwenImageEditPlus` node for negative prompts to suppress unwanted features (e.g., "gold jewelry on rabbit")
- [ ] **Fox reference sheet**: Generate the missing character ref and upload
- [ ] **Character consistency late scenes**: Multi-character scenes (4+ chars like Scene 6) show character drift — some characters don't match their reference sheets. Likely caused by only 3 ref slots (4th+ character gets no visual anchor). Investigate: stronger identity text in prompt, negative prompts for wrong features, or split multi-char scenes.

## Nice-to-Have
- [ ] **Parallel generation**: Queue multiple scenes at once (ComfyUI handles queuing)
- [ ] **Seed sweep**: Generate multiple seeds per scene for best-pick selection
- [ ] **Image review step**: Auto-send generated images to Discord for review before proceeding
- [ ] **Variation prompts**: Support "variation of scene X with changes Y" for iterating
- [ ] **Custom node mapping**: Allow different ComfyUI setups (not hardcoded node IDs)
- [ ] **Negative prompt support**: Second `TextEncodeQwenImageEditPlus` node for suppressing unwanted features (e.g., "gold jewelry", "extra fingers") — especially useful for iteration 2+ refine loops

## Future
- [ ] **LTX 2.3 I2V integration**: Full pipeline from scenes → video clips in one command
- [ ] **FFmpeg assembly**: Auto-stitch clips with transitions and audio
- [ ] **Voiceover**: TTS narration per scene synced to video length
