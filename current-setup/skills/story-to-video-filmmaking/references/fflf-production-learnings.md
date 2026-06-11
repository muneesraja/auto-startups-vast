# FFLF Production Run Learnings (2026-06-11)

Battle-tested learnings from the `cherry-late-for-party` 15-second FFLF production run on
a Vast.ai ComfyUI instance (Flux 2 Dev Turbo + LTX 2.3 FFLF Seed Hunter).

## Critical Template Bugs in `ltx-23-fflf-seed-hunter.json`

The shipped FFLF Seed Hunter template has **5 wiring issues** that cause ComfyUI to reject the prompt
with `prompt_outputs_failed_validation`. All of these were fixed in-place. If you're running on a
freshly-deployed instance that has the original template, hit these errors first.

### Bug 1: Bare model filenames instead of folder-prefixed paths

`VAELoader`, `UNETLoader`, `DualCLIPLoader`, and `CLIPLoader` in modern ComfyUI expect
folder-prefixed paths (e.g. `vae/foo.safetensors`, `diffusion_models/bar.safetensors`).
The template uses bare filenames.

**Fixes applied** (in node IDs that vary per template version):

| Field | Before (broken) | After (fixed) |
|---|---|---|
| `VAELoader.vae_name` (node 5149) | `taeltx2_3.safetensors` | `vae/taeltx2_3.safetensors` |
| `VAELoader.vae_name` (node 5025:5029) | `LTX23_video_vae_bf16.safetensors` | `vae/LTX23_video_vae_bf16.safetensors` |
| `UNETLoader.unet_name` (node 5025:5028) | `ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors` | `diffusion_models/ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors` |
| `DualCLIPLoader.clip_name2` (node 5025:5032) | `ltx-2.3_text_projection_bf16.safetensors` | `text_encoders/ltx-2.3_text_projection_bf16.safetensors` |

`DualCLIPLoader.clip_name1` (`gemma_3_12B_it_fp8_e4m3fn.safetensors`) is fine — gemma sits
at the root and doesn't need a folder prefix on this instance.

**How to discover the right paths on a new instance:**
```bash
curl -sS -u "USER:PASS" "$COMFY_URL/object_info" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for cls in ['UNETLoader', 'VAELoader', 'CLIPLoader', 'DualCLIPLoader', 'LatentUpscaleModelLoader']:
    if cls in data:
        for k, v in data[cls]['input']['required'].items():
            if isinstance(v, list) and v and isinstance(v[0], list):
                print(f'{cls}::{k}: {v[0]}')
"
```

### Bug 2: `LTXVEmptyLatentAudio` has no `audio_vae` input wired

Node 5050 (`LTXVEmptyLatentAudio`) requires an `audio_vae` VAE connection. The template
omits it entirely. Without it, the prompt fails validation with:
```
Node 5050: audio_vae
```

**Fix:** Add a separate audio VAE loader and wire it. The audio VAE is
`vae/LTX23_audio_vae_bf16.safetensors` (NOT the regular `taeltx2_3` VAE which is for video).

```json
"9999:audio_vae_loader": {
  "inputs": {
    "vae_name": "vae/LTX23_audio_vae_bf16.safetensors"
  },
  "class_type": "VAELoader",
  "_meta": {"title": "Load VAE (audio VAE for FFLF)"}
}
```

And in node 5050's `inputs`:
```json
"audio_vae": ["9999:audio_vae_loader", 0]
```

### Bug 3: `CFGGuider` (5002:4828) is missing the `model` input

The `CFGGuider` node requires `model` (a MODEL type connection). The template defines it
with only `cfg`, `positive`, and `negative` inputs. Validation fails with:
```
Node 5002:4828: model
```

**Fix:** Wire the model to the output of `PathchSageAttentionKJ` (node `5025:5153`):
```json
"5002:4828": {
  "inputs": {
    "cfg": 1,
    "model": ["5025:5153", 0],
    "positive": ["5013:5074", 0],
    "negative": ["5013:5074", 1]
  },
  ...
}
```

**NOTE:** Other CFGGuider nodes in the same template (e.g. `5190:5182`, `5206:5202`) are
also missing the `model` input. They appear to work during seed-hunt Stage 1 but will fail
during Stage 2/3. Patch all of them with the same fix.

### Bug 4: `ImpactSwitch.select` is 0-indexed in code but 1-indexed in the node

The workflow template has `"select": "__SELECTED_GEN_INDEX__"` which the FFLF builder
substitutes with the 0-based `selected_index` (0, 1, or 2). But `ImpactSwitch.select`
is **1-indexed** — `select=0` is rejected with:
```
Node 5173: select
```

**Fix in `scripts/fflf_executor.py`:** When setting `_selected_gen_index`, add 1:
```python
# In fast mode:
shot_for_builder["_selected_gen_index"] = 1  # Was 0

# In Stage 2+3 mode:
shot_for_builder["_selected_gen_index"] = selected_index + 1  # Was selected_index
```

This is a script-level fix — the template stays untouched, only the index is shifted.

### Bug 5: `fflf_executor.py` downloads the wrong (empty) file

The script's `queue_and_wait_video()` function looks for video outputs from ALL
output nodes (VHS_VideoCombine nodes 5178 and 5033 both write videos). It picks the
first one it finds, which is the **Stage 1 preview node (5178)** that writes to the
`temp/` directory with `save_output: false`. That file gets downloaded as 0 bytes.

The **real** final video is in node 5033, subfolder `video/`, filename
`{prefix}_00001.mp4`.

**Fix:** After the script reports success, manually download the actual file:
```bash
curl -sSL -u "$AUTH" \
  "$COMFY_URL/view?filename=${PREFIX}_00001.mp4&subfolder=video&type=output" \
  -o videos/${PREFIX}.mp4
```

OR: patch `queue_and_wait_video` to filter to nodes with `save_output: true` / output
type. (Future improvement; for now the manual curl works fine.)

## Timing & Resource Notes (Vast.ai RTX 3090, batched)

| Operation | Time | Notes |
|---|---|---|
| Character sheet (1 image, T2I, 1344×768) | ~25s | Flux 2 Dev Turbo, 8 steps |
| Scene still (1 image, I2I, 1344×768) | ~30-40s | Flux 2 Dev Turbo with 1 ref |
| LF keyframe (1 image, I2I, 1344×768) | ~30-40s | Same as scene still |
| FFLF shot `--fast` mode (5s @ 1280×640) | ~60-90s | Distilled model, single pass |
| FFLF shot full seed-hunt (3 previews + select + upscale + render) | ~5-8 min | Stage 1 previews are fast (~30s each) |
| ffmpeg concat of 3 clips | <1s | Lossless concat with `-c copy` |

For a 15s test (3 shots × 5s) the FFLF `--fast` path takes about **5 minutes total**
on a 3090. Full seed-hunt mode would take ~20-25 minutes.

## Story-to-Video vs Story-to-Video-Filmmaking — When to Use Which

- **`story-to-video`** (single-image T2I → I2V Director): Simpler, faster, but each shot
  is a separate video gen with NO temporal continuity between shots. Good for one-off
  illustrations or when each shot is a self-contained scene.

- **`story-to-video-filmmaking`** (FFLF Seed Hunter): Each shot has a starting frame (FF)
  AND an ending frame (LF), with seed-hunt across 3 previews + spatial upscale +
  Stage 3 final render. Continuation chains extract the tail frame from the previous
  video and feed it as the FF of the next shot → seamless cinematic motion.

**Use filmmaking** for any story where shots need to flow together (the user explicitly
asked for it: "as per story-to-video-filmmaking skill which uses filmmaking workflow
for video generation also FFLF based image and video generation").

## Phase 5: Stitching Video Clips

After FFLF Executor finishes, stitch the per-shot videos with ffmpeg's concat demuxer:

```bash
cat > /tmp/concat_list.txt <<EOF
file '/abs/path/to/videos/film_001_shot001.mp4'
file '/abs/path/to/videos/film_001_shot002.mp4'
file '/abs/path/to/videos/film_001_shot003.mp4'
EOF
ffmpeg -y -f concat -safe 0 -i /tmp/concat_list.txt -c copy final_15s.mp4
```

**Important:** Use absolute paths in the concat list. Relative paths fail with
`Impossible to open` because ffmpeg resolves them relative to the concat list location,
not the cwd.

`-c copy` is lossless and fast. If shots have different resolutions/framerates, re-encode
with `-c:v libx264 -crf 18` instead.

## Output File Naming

Per-shot videos land on ComfyUI at:
- `output/video/{prefix}_00001.mp4` ← **the real one**
- `temp/LTX-2_00001.mp4` ← the Stage 1 preview (0 bytes or small, NOT the final)

The executor's `queue_and_wait_video` mistakenly grabs the temp file. Always
verify file size > 1MB after download.
