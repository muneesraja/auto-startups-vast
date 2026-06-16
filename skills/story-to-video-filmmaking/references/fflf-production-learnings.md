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

**Bug 5b (2026-06-11, elephant run) — Stage 1 previews also download as 0 bytes:**

`comfyui_api.py::download_output` hardcoded `type=output` in the ComfyUI `/view` URL.
Stage 1 preview clips live at `type=temp` (ComfyUI's temp folder), so the request
returned 404 and the script silently saved a 0-byte file to `motion_eval/`. ffmpeg
then failed to extract any frames → the auto-evaluator couldn't score the previews
and fell back to default seed index `[0]`.

**Fix applied:** Added `file_type` parameter to `download_output` (default `"output"`)
and updated `queue_and_download_previews` to pass `file_type=item.get("type", "temp")`.
Now previews download as real 170KB+ mp4s and the auto-evaluator can extract frames.

⚠️ **Heads up for in-flight runs:** Python modules load at process start. If a
long-running orchestrator is already mid-run, the patch won't apply to shots that
have *already* loaded `fflf_executor` into memory. The current shot's auto-eval
will fall back to default seed index. New runs (and any re-runs) get the fix.

**Verification commands:**
```bash
# Should return ~170KB+ (not 0 bytes):
curl -sSL -u "$AUTH" \
  "$COMFY_URL/view?filename=LTX-2_00010.mp4&subfolder=&type=temp" \
  -o /tmp/test.mp4 -w "%{size_download}\n"

# Then verify it plays:
ffprobe -v error -show_streams /tmp/test.mp4 2>&1 | grep "codec_name\|nb_frames"
```

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

**Script fix applied (2026-06-11, tiny-bee run):** Patched
`scripts/fflf_executor.py::queue_and_wait_video` to filter out temp-directory
outputs. Now skips items where `type=="temp"` or `subfolder=="temp"`, and
downloads the real final from node 5033 (subfolder=`video`, type=`output`).
No more 0-byte false positives.

```python
# In queue_and_wait_video, before each download:
if item.get("type") == "temp" or item.get("subfolder", "") == "temp":
    continue
```

---

## Character Drift Across Iterations — `lf_references` Lesson (2026-06-11)

**Symptom:** Shot 1 chain_start produced:
- FF (with `barnaby_reference_sheet.png` as ref): correct chibi Barnaby ✓
- LF (with FF as the only "anchor", `lf_references=[]`): drifted to a
  classic cartoon bee with **brown-yellow stripes**, a **green leaf hat**,
  and **diminished chibi head proportions**. NOT the chibi Barnaby anymore.

**Root cause:** Flux's ReferenceLatent chain *drifts across iterations* when
the structural anchor is the only identity source. The FF image carries
Barnaby's identity, but by the LF step, Flux's interpretation of "baby bee"
loosens — the model reverts to its training bias (generic cartoon bee) and
adds/removes details that weren't in the original ref sheet.

**Rule:** For every shot where the character is the **emotional focus** of
the LF, include their character sheet in `lf_references` *alongside* the
structural anchor. The schema's default heuristic of "anchor carries identity,
skip the ref" is wrong for character-driven shots.

```json
// Bad — Barnaby drifts to a leaf-hat bee by the LF step
"references": ["barnaby_reference_sheet.png"],
"lf_references": []

// Good — chibi Barnaby locked in across the iteration
"references": ["barnaby_reference_sheet.png"],
"lf_references": ["barnaby_reference_sheet.png"]
```

**Continuation shots — new character joins:** When a new character appears
in the LF (e.g. Spider enters the frame for the first time) AND the existing
character is still the focus (e.g. Barnaby reacting to the Spider), include
**both** character sheets in `lf_references`. The new character needs their
sheet (the tail-frame anchor doesn't carry them yet), and the existing
character needs their sheet to prevent dilution by the new ref.

```json
// Spider joins, Barnaby reacts — both refs needed
"lf_references": ["barnaby_reference_sheet.png", "spider_reference_sheet.png"]
```

**3-slot budget:** `lf_references` has a hard max of 3 items. For 3-character
scenes (future, e.g. Mama Bee + Barnaby + Spider all in one shot), you may
hit this limit. The structural anchor still gets the 1st slot, so
2-character scenes (like Spider + Barnaby) leave room for 1 more ref. Plan
shot compositions around the 3-ref budget.

**How to detect this drift:** When reviewing generated stills, compare the
LF to the ref sheet — if the character has *any* new feature not in the
sheet (a hat, different stripes, different eyes, changed proportions), the
anchor is not strong enough. Add the sheet to `lf_references` and re-run.

---

## Resolution Mismatch Causes FFLF Camera Drift (2026-06-11, tiny-bee)

**Symptom:** Shot 1 FF and LF are near-identical compositions (same camera,
same character position, only expression changes). Yet the FFLF video pans
dramatically upward, losing the character by mid-clip.

**Root cause — 3 compounding factors:**

1. **Resolution mismatch → crop destroys alignment.**
   Flux generates stills at 1344×768 (1.75:1). The FFLF template runs at
   720p = 1280×640 (2.00:1). The template's `ImageResizeKJv2` uses
   `keep_proportion: "crop"` + `crop_position: "center"`, cutting ~64px
   from top and bottom. Because FF and LF have slightly different vertical
   element distributions (character shifts down by a few px in LF), the
   center-crop produces different vertical slices. LTX interprets this as
   camera motion and amplifies it.

2. **Motion prompt conflicts with keyframes.**
   The prompt said "camera tilts down slightly" + "golden light shifts" — the
   model couldn't reconcile downward motion with near-static keyframes AND
   an upward light-shift cue, so it defaulted to panning toward the brightest
   element.

3. **Keyframes too similar for 6 seconds.**
   Expression-only change (eyes open → eyes closed) gives LTX no spatial
   displacement signal for 150 frames. The model invented dramatic motion.

**Resolution matching rule:** Generate stills at the **same resolution** as
the video pipeline target. For `720p` → 1280×704. For `1080p` → 1920×1088.

---

## Duration-to-Displacement Heuristic (2026-06-11, tiny-bee)

Match `segment_duration` to the amount of spatial change between FF and LF.
Too much duration for too little spatial change = the model invents camera
motion to fill the temporal gap.

| FF → LF Delta | segment_duration | Notes |
|---|---|---|
| Expression only (same pose/camera) | 2–3s | Use micro-motion in prompt ("slight head tilt") |
| Subtle spatial shift (slight push, head turn) | 4–5s | |
| Clear trajectory (character moves, camera tracks) | 5–7s | Author's standard range |
| Full traversal (wide → close-up, crosses frame) | 7–8s | Author's max demonstrated |

---

## Adaptive Tail Frame Extraction (2026-06-11, implemented)

The old `extract_continuation_frame()` extracted a single frame at
`N - overlap_seconds × fps` from the end. This was arbitrary and often
caught the video mid-drift (e.g., camera already panned to the ceiling).

**New behavior:** Extract 3 candidates (last frame, last-0.5s, last-1.0s),
compute SSIM against the target LF, and pick the best match. If the best
SSIM is below `quality_threshold` (0.3), emit a quality gate warning —
the video likely drifted far from the intended composition, and the next
shot's FF should be regenerated from scratch rather than using the
degraded tail.

---

## V2 Motion Evaluator Prompt (2026-06-11, elephant story)

The V1 motion eval prompt (4-axis independent scoring, 5 frames/video, no FF/LF anchors)
produced inconsistent winners across re-runs of the same inputs. On shot 1.2 of the
elephant story (3 previews of a foot-slip close-up), V1 selected Preview 0 (score 5.0)
when hand-scored the correct answer was Preview 1 (score 9).

**V2 prompt design fixes (now default in `motion_evaluator.py`):**

1. **FF + LF as actual image attachments** (not just text descriptions) — the model
   can directly compare each preview's frame 3 to the actual LF still, eliminating
   the "model has to remember what the target looks like" failure mode.
2. **3 frames per video at 10% / 50% / 90%** (vs V1's 5 at 0/25/50/75/100) —
   0% and 100% are always nearly identical to FF and LF, so they add noise without
   adding signal. The 90% frame is the only one that correlates with LF-arrival.
3. **Forced a/b/c ranked comparison** (vs V1's independent 0-10 scoring) — kills
   the "all three look great, give them all 9" failure mode where the model
   produces nearly identical scores for all candidates.
4. **LF-arrival weighted at 35%** with explicit "chain-cleanliness > prettiness"
   tie-breaker. The only thing that matters for the next shot in the chain is
   whether this shot's tail frame matches the LF.
5. **Mandatory "cite ONE specific visual observation"** per video — kills hand-waving
   "this looks smoother" claims without pointing to actual pixels.
6. **`temperature=0.2`** in API call — v1 had no temp control, model produced
   different winners across runs of the same inputs. v2 is much more stable.

**Calibration (shot 1.2, elephant story):**

| Prompt version | Winner | Score | Runner-up | Agree with hand-score? |
|---|---|---|---|---|
| V1 (legacy) | A (14) | 5.0 | B (15) = 6.8 | ❌ wrong winner |
| V2 (initial test) | B (15) | 8.95 | A (14) = 5.05 | ✅ correct winner |
| V2 (rerun via `evaluate_motion_previews`) | A (14) | 8.65 | B (15) = 3.30 | ❌ flipped |
| Hand-score (user) | B (15) | 9 | A (14) = 7 | — |

**Honest assessment:** V2 agrees with hand-score in 1 of 2 automated re-runs. The
infrastructure is in place (anchors, ranked comparison, lower temp) but model
variance at temp=0.2 is still non-zero. The `lead_over_runnerup` confidence signal
that's now logged tells you when the selection is uncertain (lead < 1.0 = LOW).

**Still recommended (production):** Run V2, use the winner, but check the
`lead_over_runnerup` field. If lead < 1.0, consider re-rendering the runner-up
and picking manually (or boosting temp down to 0.1 next time). If lead > 2.0,
trust the selection.

### Short-shot heuristic — skip eval for ≤3s shots (2026-06-11, elephant)

For shots with `segment_duration <= 3s` (expression-only / micro-motion), seed
selection matters very little — there's basically only one valid motion path
the model can take. The auto-eval cost (~5 cents + ~30s) isn't worth it for
these.

**Implementation (in `fflf_executor.py`):** If `overrides.segment_duration <= 3`
and `overrides.force_seed_hunt != true`, skip Stage 1 previews and the eval
entirely, jump straight to Stage 2+3 with `_selected_gen_index=1` (seed 0).

**Override per-shot:** if you want to force the eval for a specific short shot,
add `"force_seed_hunt": true` to that shot's `overrides` in `filmmaking_prompt.json`.

**Expected impact on a 14-shot film:** ~3-4 short shots (2-3s) skip the eval,
saving ~20-30 seconds and 15-20 cents per film. Quality impact: negligible for
those shots (seed 0 is essentially always right for expression-only).

### Cost summary per shot (RTX 3090, 720p)

| Stage | Time | Cost (USD) |
|---|---|---|
| Image gen (Flux 2 Dev Turbo, FF or LF with 1 ref) | ~30-40s | ~$0.01 |
| Stage 1 previews (3× parallel, low-res) | ~30-60s | ~$0.02 |
| V2 eval (OpenRouter gemini-3.1-flash-lite, 9 frames + 2 anchors) | ~2-5s | ~$0.0035 |
| Stage 2+3 (upscale + final render, 720p) | ~30-60s | ~$0.02 |
| **Total per shot (full pipeline, auto mode)** | **~90-180s** | **~$0.05** |
| **Short shot (≤3s, heuristic skip)** | **~60-100s** | **~$0.03** |

---

## LF Edit-Mode Prompting (2026-06-11, elephant story)

### Problem

The elephant story (14 shots, 4 scenes) ran end-to-end in 78.6 minutes on RTX 3090 and produced 14 valid mp4 files. Quality audit on the FF↔LF keyframes revealed that **10 of 14 shots (71%) had FF↔LF problems that the video model couldn't recover from**:

| Verdict | SSIM band | Count | Elephant shots |
|---|---|---|---|
| ❌ FROZEN (FF≈LF, near-identical) | > 0.92 | 2 | `film_002_shot001`, `film_003_shot001` |
| ⚠️ SUBTLE (small change, expression-only) | 0.80–0.92 | 2 | `film_001_shot001`, `film_004_shot001` |
| ✓ STRONG (big change, will animate well) | 0.40–0.60 | 2 | `film_003_shot002`, `film_004_shot002` |
| ⚠️ RADICAL (too different, model invents transitions) | < 0.40 | 8 | All other shots |

A 71% failure rate on a 14-shot run is unacceptable. The story rendered, the film assembled, but the videos do not interpolate meaningfully between the keyframes the way FFLF Seed Hunter is supposed to work.

### Root cause

The `last_frame_prompt` field in `filmmaking_prompt.json` was being authored as a **T2I composition description** ("Wide shot. Elly is now on the riverbank. The dam is visible behind her...") — exactly the wrong shape for a workflow that calls Flux 2 Dev Turbo with the **FF image already in the `references[]` list**. Flux received the FF as an image attachment, but the prompt told it to "generate this scene" rather than "edit image 1, keep X, change Y". Flux dutifully produced a beautiful still that satisfied the text — and that still happened to share the same semantic concept ("elephant + water + dam") as the FF, so it looked visually similar despite having no enforced structural relationship.

The LTX prompting guides (Single-Reference Editing, Multi-Reference Editing, Image Editing Overview) all say the same thing:
> *"Be specific about what changes and explicit about what should stay the same. The more precise your instruction, the better the result."*

This rule was being silently violated by the LF prompt format.

### The fix: edit-instruction LF pattern

The LF prompt must be structured as a **delta from the FF**, not a fresh scene. The full template, vocabulary, and calibration example are in [phases/phase-1-prompt-composition.md § "The Edit-Instruction LF Pattern"](phases/phase-1-prompt-composition.md#the-edit-instruction-lf-pattern-2026-06-11-elephant-story). The short version:

```
Edit image 1 (the previous frame). [1-2 sentence story context]

KEEP UNCHANGED: [explicit preserve list — character, environment, lighting, style]

CHANGE:
- [primary pose/motion delta]
- [secondary expression/detail delta]
- [tertiary ambient motion, e.g. water drips, dust]

Camera: [same as FF / slight change]

Mood: [single word: tense / relieved / heroic / intimate]
```

**Rule of thumb:** if the LF prompt could be rewritten as an FF prompt (a complete scene description), it's wrong. An LF prompt must be a delta.

### Calibration: elephant shot 3.2 before/after

Shot 3.2 ("The wade-out") is a representative failure. The original LF prompt was 70 words of T2I composition. The rewrite is 200 words of I2I edit instructions. Per the audit I ran after the pipeline finished, the original LF produced a still with 0.45 SSIM to the FF (radical — model invented a transition). The expected SSIM band for a properly-edited LF is 0.65–0.85.

The full before/after prompt text is in phase-1-prompt-composition.md. The diff:

| | Before (T2I) | After (I2I edit) |
|---|---|---|
| Opening | "Wide shot. Elly's round body is now on the shallow pebbly riverbank..." | "Edit image 1 (the previous frame). Elly has just been saved from a waterfall by hitting a wooden dam..." |
| Character | Re-described (gray skin, brown eyes, etc.) | KEEP UNCHANGED: (reference sheet + FF are already attached) |
| Pose | "stepped out of the deep water" | "stepping forward onto a pebbly riverbank, one foot still in the water, one foot on the pebbles" |
| Expression | "breathing a huge visible sigh of relief, body deflating" | "eyes open, looking down at her feet, mouth in a small shaky relieved exhale" |
| Camera | Implied wide shot | "same medium shot angle, slightly wider framing (pulled back ~10%)" |
| Expected FF↔LF SSIM | 0.45 (radical — actual) | 0.70–0.80 (healthy — expected) |

### Expected impact on the next run

If all 14 LF prompts in the next story are rewritten in I2I edit-mode before Phase 2:

| Metric | Elephant (T2I LF) | Expected next run (I2I edit LF) |
|---|---|---|
| Frozen (SSIM > 0.92) | 2 / 14 (14%) | 0 / 14 (0%) — edit-mode forces visible change |
| Subtle (0.80–0.92) | 2 / 14 (14%) | 2-3 / 14 (14-21%) — expression-only beats accepted, flagged for short-shot heuristic |
| Healthy (0.60–0.80) | 0 / 14 (0%) | 9-10 / 14 (64-71%) — clearly-edited shots |
| Radical (SSIM < 0.40) | 8 / 14 (57%) | 1-2 / 14 (7-14%) — only genuine scene changes, flagged for review |
| Per-shot video quality | Hit or miss | Predictable motion, model has signal to interpolate |

The elephant film is a learning artifact. The next story (using I2I edit-mode LF prompts from the start) should produce a watchable film on the first render. See the next two sections ("Per-Image Quality Gate" and "Pre-Flight FF↔LF Audit") for the safety nets that catch failures earlier and cheaper than the post-render audit I did here.

---

## Per-Image Quality Gate (2026-06-11, added in v1.4.0)

An optional per-image evaluation step that runs after each still is generated. Uses Gemini 3.1 Flash Lite via OpenRouter (or Gemini direct) to score the image against its target character reference sheet, with a hard pass/fail threshold and a single regeneration retry on failure.

**When to enable:** if you observe character drift across iterations (Flux diluting chibi proportions, adding leaf hats, getting the eye color wrong, etc.). Tiny-bee documented this drift; the elephant story did not see it because the character sheets were strong, but it's the next failure mode once the edit-instruction LF pattern is in use.

**Configuration** (`filmmaking_prompt.json` `global`):
```json
{
  "quality_gate": {
    "enabled": false,
    "min_score": 7.0,
    "max_retries": 1
  }
}
```

**CLI flag:** `--quality-gate` enables the gate for a run. Disabled by default.

**What the model scores:** `character_likeness` (does the image match the reference sheet's character?), `style_match` (does it match the visual style — 3D Pixar, chibi, etc.?), `expression_neutrality` (for reference sheets that need to be neutral).

**On failure:** the gate appends the model's `rejection_reason` to the next prompt and regenerates the image, up to `max_retries` times. The retry is bounded to avoid loops.

**Cost:** ~$0.0005 per image (1 candidate + 1 reference). For a 14-shot film with FF+LF = 28 evaluations = ~$0.014 total. Negligible.

**Why gemini-3.1-flash-lite:** the V2 motion eval already uses it via OpenRouter and we have the cost / latency profile validated. Same model, same provider — just a different prompt and different images.

**Detailed implementation:** see [scripts/gemini_eval.py § evaluate_image_against_reference](scripts/gemini_eval.py) and [scripts/generate_frames.py § quality_gate_image](scripts/generate_frames.py).

---

## Pre-Flight FF↔LF Audit (2026-06-11, added in v1.4.0)

A standalone text-based audit that runs **before Phase 2** and checks every shot's FF and LF prompts for the failure modes the elephant run exposed. Emits warnings for frozen, subtle, and radical risk before any image is generated.

**Why this matters:** the elephant post-render audit took 30 seconds to run on already-rendered stills and 14 rendered videos. The pre-flight audit takes 2 seconds on the `filmmaking_prompt.json` text alone, before any GPU time is spent. Catches the same problems for 0.5% of the cost.

**Usage:**
```bash
# Standalone
python3 scripts/prompt_audit.py /path/to/filmmaking_prompt.json

# Or via the orchestrator (advisory, does not block by default)
python3 scripts/filmmaking_orchestrator.py --prompts filmmaking_prompt.json --preflight-audit
```

**Output:** `feedback/ff_lf_audit_preflight.md` with a per-shot risk table and re-authoring suggestions.

**Heuristics used:**
- **Frozen risk** (LF ≈ FF, SSIM expected > 0.92): text similarity (SequenceMatcher) > 0.85 + absence of any spatial-delta keywords ("stepping", "releasing", "turning", "leaning", "looking", "mouth", "pushing in", "pulling back") in the LF prompt
- **Subtle risk** (expression-only change): presence of "expression", "eyes", "mouth", "sigh", "grip firming" without any spatial-delta keywords
- **Radical risk** (LF implies a different scene): presence of "different location", "new place", "meanwhile", "later", "elsewhere" OR absence of shared character nouns between FF and LF OR `break_continuity: true` not set

**Not perfect.** The audit is text-only and can't see the actual images, so it's a first-pass filter, not a final judgment. False positives are expected and easy to dismiss. False negatives (truly radical LFs that the audit misses) will be caught by the post-render audit at the end.

**Detailed implementation:** see [scripts/prompt_audit.py](scripts/prompt_audit.py).
