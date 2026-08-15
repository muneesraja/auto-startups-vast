# H3 Seamless Chain — Workflow Anatomy

Structural reference for `workflows/comfyui/minimax-h3-seamless-chain-global-refs.json` (40 nodes, 61 links, 5 groups). Load this when editing or reasoning about the shipped chain graph.

---

## Node Map — Main Chain

Recursive body executes once per shot; `ChainLoopEnd` (1705) re-enters `ChainLoopStart` (1701) until the plan is exhausted.

| Step | Node | ID | Role |
|---|---|---|---|
| Plan | MiniMaxH3ChainPlan | 1700 | Holds the 14-shot JSON; emits `H3_CHAIN_PLAN` |
| Loop entry | MiniMaxH3ChainLoopStart | 1701 | `start_clip=1`, resume point; emits `flow` + `state` |
| Current shot | MiniMaxH3ChainCurrent | 1702 | Selects shot N; fans out prompt/seed/width/height/length/steps/audio |
| Generation | MiniMaxH3ReferenceToVideo | 110 | Ref2VA conditioning + initial latent; widgets `960×544×362`, `match` |
| Context | MiniMaxH3ChainContext | 1703 | Clip 1 bypass vs continuation; emits `trim_frames` + `is_continuation` |
| Guider | BasicGuider | 121 | Loop guider (model from patched stack) |
| Sampler | SamplerCustomAdvanced | 124 | Single loop body; noise/guider/sampler/sigmas/latent in |
| Decode video | VAEDecode | 130 | Current clip frames |
| Decode audio | VAEDecodeAudio | 131 | Current clip audio |
| Trim | MiniMaxH3LoopTrim | 132 | `trim_frames=0, fps=24, frame_lock=true`; drops overlap |
| Save | MiniMaxH3ChainSegmentSave | 1704 | Writes MP4 + `.prompt.txt` + checkpoint JSON + safetensors |
| Loop end | MiniMaxH3ChainLoopEnd | 1705 | Recurses; emits final `manifest` |
| Assemble | MiniMaxH3ChainAssemble | 1706 | `mode=plan`, `run_name=silver_estate_opening_80s_final`, `crf=256` |

### Muted Recovery Branch (mode=2 / BYPASSED)

| Node | ID | Role |
|---|---|---|
| MiniMaxH3ChainManifestLoad | 1707 | Loads all saved clips without rendering |
| MiniMaxH3ChainAssemble | 1708 | `run_name=silver_estate_opening_80s_recovered`; assembles from manifest |

Enable both only when all segments finished but final assembly did not (see Note 1901).

---

## Model Stack

`UNETLoader(1)` → `PathchSageAttentionKJ(1632)` → `MiniMaxH3MemoryEfficientSageAttentionPatch(1633)` → `SolAttnPatch(1634)` → `LoraLoaderModelOnly(1635)` → `MiniMaxH3SigmaShift(5)` → guider/scheduler.

| Node | ID | Widgets | Note |
|---|---|---|---|
| UNETLoader | 1 | `minimax_h3_ref2va_pruned_bf16.safetensors`, `default` | base diffusion model |
| PathchSageAttentionKJ | 1632 | `auto`, `true` | sage attention backend |
| MemoryEfficientSageAttentionPatch | 1633 | — | **BYPASSED (mode=4)**; fallback only |
| SolAttnPatch | 1634 | `1.5 / 0.2 / 0.9 / 4096`, `exact_kv_and_rows`, `2d_frame`, layers `33-35, 39-42` | attention patch |
| LoraLoaderModelOnly | 1635 | `minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors`, `0.95` | 4-step turbo |
| MiniMaxH3SigmaShift | 5 | `12`, `3` | sigma shift |
| KSamplerSelect | 122 | `res_multistep` | sampler |
| BasicScheduler | 123 | `simple`, `5`, `1` | steps=5, denoise=1 |
| CLIPLoader | 2 | `qwen3vl_32b_minimax_h3_int8_convrot.safetensors`, `minimax`, `default` | text encoder, type `minimax` |
| VAELoader | 3 | `minimax_h3_video_vae_fp16.safetensors` | video VAE |
| VAELoader | 4 | `minimax_h3_audio_vae_fp32.safetensors` | audio VAE |

---

## Groups

| # | Title | Contents |
|---|---|---|
| 1 | `MODEL STACK — RETAINED FROM ORIGINAL` | Nodes 1, 2, 3, 4, 5, 1632–1635, 122, 123 |
| 2 | `CHARACTER REFERENCES + ORIGINAL SONG` | LoadImage 910, 911; LoadAudio 940 |
| 3 | `TIMED H3 LOOP` | 1700–1705, 110, 120, 121, 124, 130, 131, 132 |
| 4 | `FINAL ASSEMBLY` | 1706 |
| 5 | `DISABLED RECOVERY PATH` | 1707, 1708 (muted) |

---

## Shipped Plan (node 1700)

| Field | Value |
|---|---|
| Shots | 14 (`clip_01` … `clip_14`) |
| `defaults.duration_seconds` | 15 |
| `defaults.steps` | 5 |
| Shot 14 override | `duration_seconds: 5` |
| Resolution | 960 × 544 (node 110 widgets) |
| `context_length` | 22 |
| `encode_mode` | video |
| `anchor_mode` | head |
| `crop` | disabled |
| `audio_mode` | source_track |
| `audio_context_length` | 0 |
| `base_seed` | 0 |
| `segment_crf` | 20 |
| `run_name` | `silver_estate_opening_80s_final` (node 1706) |

### Timing Math (24 FPS, context=22, anchor=head)

| Clip range | Raw frames/clip | Delivered/clip |
|---|---|---|
| clip 1 | 362 | 362 (first clip = raw) |
| clips 2–13 | 362 | 340 (raw − 22 context) |
| clip 14 | 124 | 102 (raw − 22 context) |

Raw total: `13×362 + 124 = 4830`. Delivered: `4830 − 13×22 = 4544` frames → `4544 / 24 = 189.3s` (3:09).

---

## Five Defects / Limits

| # | Defect | Evidence | GUI Fix |
|---|---|---|---|
| 1 | `<Picture 2>` cited in every prompt but never wired | LoadImage 910 (face ref) has **0 outgoing links**; only 911 → 110 `ref_images.ref_image_0` | Wire 910 → 110 `ref_images.ref_image_1`; or merge face+body into one sheet on 911 |
| 2 | No `prompt_prefix` — all 14 shots duplicate identical `subject_definitions` / `retention_analysis` / `non_diegetic_music` | Plan JSON has only `defaults` + `shots`; no `prompt_prefix` key | Add `prompt_prefix` at plan top; strip duplicated blocks from each shot prompt |
| 3 | Hardcoded input filenames, incl. comma in `The silver estate was a memory now,.wav` | Node 940 widgets; nodes 910/911 widgets | Use ComfyUI file-picker or a `LoadAudio`/`LoadImage` with relative paths; rename file to remove comma |
| 4 | No Review Gate | No gate node between SegmentSave and LoopEnd | Fine for headless automated path; do NOT add a gate in the automated path — add only for interactive review runs |
| 5 | Global references only — ref image loaded outside the recursive body | 911 → 110 is a fixed external link; all 14 clips share one ref | Per-clip storyboard sheets require a `clip_index`-driven selector node between 911 and 110; not possible in-graph today |
