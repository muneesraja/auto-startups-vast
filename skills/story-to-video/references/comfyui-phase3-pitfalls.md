# Story-to-Video ComfyUI / Phase 3 Pitfalls

> Runtime issues hit when running `generate_video.py` against hosted ComfyUI
> instances. Captured from the `ltx-23-director` (v2 schema) workflow on a
> RunPod proxy ComfyUI pod (June 2026). Most of these are independent of the
> `story-to-video` skill — they apply to anyone calling the LTXDirector
> node via API.

## Director Node Validation (Resolved)

### Symptom 1: `prompt_outputs_failed_validation` — model filename mismatch

```
Node 93:3: vae_name: 'LTX23_video_vae_bf16.safetensors' not in
  ['vae/LTX23_audio_vae_bf16.safetensors', 'vae/LTX23_video_vae_bf16.safetensors', ...]
```

**Root cause:** The shipped `ltx-23-director.json` template references bare
filenames (e.g. `LTX23_video_vae_bf16.safetensors`). Hosted ComfyUI pods
that use the standard `models/{vae,loras,text_encoders}/` subfolder layout
require subfolder prefixes (`vae/LTX23_video_vae_bf16.safetensors`).

**Fix:** In the template, add the subfolder prefix to the 5 model-loader
inputs (Node 93:80, 93:78, 93:4, 93:3, 93:84). The checkpoint (93:77) and
spatial upscaler (95:57) loaders are already correct in the flat layout.

```text
Node 93:80  lora_name   -> loras/ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors
Node 93:78  vae_name    -> vae/taeltx2_3.safetensors
Node 93:4   vae_name    -> vae/LTX23_audio_vae_bf16.safetensors
Node 93:3   vae_name    -> vae/LTX23_video_vae_bf16.safetensors
Node 93:84  clip_name1  -> split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors
Node 93:84  clip_name2  -> text_encoders/ltx-2.3_text_projection_bf16.safetensors
```

### Symptom 2: `Node 46 (LTXDirector): There is a segment on the timeline missing a prompt!`

**Root cause:** The Director node reads `local_prompts` / `segment_lengths` /
`guide_strength` (which the tooltips describe as "auto-populated from the
timeline editor"). When you submit via API (skipping the editor), those
fields stay empty strings and the node refuses to run.

**Fix:** In the template, change the empty strings to placeholder tokens
that the script can substitute:

```json
"local_prompts": "__LOCAL_PROMPTS__",
"segment_lengths": "__SEGMENT_LENGTHS__",
"guide_strength": "__GUIDE_STRENGTH__"
```

Then derive the values in the script from `timeline_data.segments` (see
`workflow_builder.py` `ltx_director` branch).

### Symptom 3: `could not convert string to float: '[12'`

**Root cause:** The node parses `segment_lengths` as a comma-separated
string (`"12,48,60"`), not a JSON list. If you pass `"[12, 48, 60]"` it
tries to parse the first numeric substring and fails.

**Fix:** Use comma-separated for `segment_lengths` and `guide_strength`.
Use comma-separated floats formatted to 3 decimals:
`"1.000,1.000,1.000"`.

### Symptom 4: `Number of segment_lengths (3) must match number of local prompts (1)`

**Root cause:** The node parses `local_prompts` by splitting on the pipe
character `|` (per the upstream ComfyUI-PromptRelay source code:
`nodes.py` → `_encode_relay()` does `local_prompts.split("|")`). Newline-
or JSON-list-separated prompts are treated as a single entry.

**Fix:** Use pipe-separated: `"first segment prompt | second segment prompt | third segment prompt"`.

### Non-overlapping frame schedule

The Director node schedules segments sequentially with non-overlapping
frame budgets, so the script's `build_director_timeline()` output (which
can emit a 0.5s keyframe + 0-2.5s text + 2.5-5.0s text) must be
**collapsed** into a single non-overlapping walk before the frame
lengths are computed. The `ltx_director` branch in
`workflow_builder.build_dynamic_workflow()` does this: it walks
timeline boundaries, assigns frame ranges so the totals sum to
`duration_frames`, and borrows the top-level prompt if any slice has
no text.

## Output Path Surprise

The `generate_video.py` script defaults `output_dir` to
`{STORY_TO_VIDEO}/` (the parent of the story folder), so
`videos_dir = {STORY_TO_VIDEO}/videos/`. If you pass `--prompts` pointing
into a story subfolder (`pluffy-bun/motion.json`) without `--output-dir`,
the generated MP4s land in the **parent** `story-to-video/videos/`
directory, not in the story's own `videos/` subdir.

The script's `Save path:` log correctly prints the resolved path, but
the path is **not** the story folder — it's the parent. Use
`--output-dir /path/to/story-folder/` to keep outputs grouped with the
story assets, or `mv` the outputs into place after the run.

## Resolution: 16:9 base latent is required

The `LTXVLatentUpsampler` + `ltx-2.3-spatial-upscaler-x2-1.1.safetensors`
pipeline hardcodes the base latent to multiples of 32×18 (i.e. 16:9 at
multiples of 32px). Non-16:9 resolutions blow up the upscaler's tile
geometry: `RuntimeError: The size of tensor a (2560) must match the
size of tensor b (128) at non-singleton dimension 2`. The 2560
mismatch = the 2× concat overflowing the upscaler's hidden dim 128.

**Valid 16:9 resolutions (both dims divisible by 32):**

| Resolution | Notes |
|---|---|
| 768×432 | LTX native minimum |
| 1024×576 | Solid mid-tier, fits on smaller VRAM |
| 1536×864 | High quality, safe for hosted ComfyUI |
| 2048×1152 | High-end, requires ≥24GB VRAM |

**Invalid (NOT 16:9 or non-divisible-by-32) examples:**

- 1280×704 — 64:35.2 ratio (1.818:1) ❌ — looks 16:9-ish but isn't
- 1280×720 — 16:9 exact but 720 not divisible by 32 ❌
- 1920×1080 — 16:9 exact but 1080 not divisible by 32 ❌

**The script guards against this** as of v5.1.0: the `ltx_director`
branch in `workflow_builder.py` raises `ValueError` with a
"Aspect ratio {w}x{h} ({r}:1) is not 16:9" error and suggests a fix
when the configured width/height aren't a 16:9 pair divisible by 32.

**Note on the 1280×704 case (June 2026):** the first multi-keyframe
30s run used 1280×704 and DID produce a watchable video (the
spatial upscaler warned but didn't fully fail — the file at
`director_multichain_30s_1280x704_warned.mp4` in the pluffy-bun
project is from that run, and is in some ways more aesthetically
rich than the 1024×576 fixed-version). But the model was clearly
struggling with the off-tile geometry, and the warning will become
a hard crash in future Director versions. Stick to 16:9 from now on.

## Timeout: long Director chains need a bigger poll ceiling

The `wait_for_prompt` function in `comfyui_api.py` defaults to
`max_wait=600s` (10 min), which was right for 5-second single-keyframe
tests but wrong for 30-second multi-keyframe chains (which routinely
take 12-15 min on a hosted ComfyUI pod, per Kijai's published
benchmarks). The default was bumped to **2400s (40 min)** as of
v5.1.0.

`workflow_builder` logs `⚠️ Unknown override 'steps_pass1' — skipping`
when a per-shot override name isn't in the template's `_overrides_map`.
The Director template only wires `lora_strength`; `steps_pass1`,
`steps_pass2`, and `denoise_pass2` (mentioned in
`ltx-director-prompting-guide.md`) are not in the override map and are
silently dropped. The defaults that the template itself ships with
(`steps_pass1=8, steps_pass2=4, denoise_pass2=0.42`) are already
sensible, so this is a non-issue unless you specifically need to
tune them per shot.
