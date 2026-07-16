# LTX Director — Headless API Automation Research

**Date:** 2026-07-16  
**Companion doc:** [ltx-director-usage-and-prompting-guide.md](./ltx-director-usage-and-prompting-guide.md) (how to use Director + prompting best practices)  
**Source clone:** `Research/WhatDreamsCost-ComfyUI/` ([WhatDreamsCost/WhatDreamsCost-ComfyUI](https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI))  
**Canonical workflow:** `workflows/comfyui/LTX_Director_2_Workflow_Hotfix.json`  
**Setup script:** `workflows/setup/ltx-23-director-hotfix.sh`  
**Goal:** Reverse-engineer how to drive LTX Director from `/prompt` for a **side-by-side director_v2** path (I2V + true end-frame FLF + text-before-end-frame) **without** touching the existing story-maker `ltx-i2v` / `ltx-flf2v` templates.

---

## 1. Verdict

LTX Director is **API-automatable**. The UI timeline is a convenience editor that serializes into ordinary ComfyUI widget strings. Headless clients can:

1. `POST /upload/image` (subfolder `whatdreamscost` recommended — matches the UI)
2. Build `timeline_data` JSON + derived `local_prompts` / `segment_lengths` / `guide_strength`
3. Patch those into the Hotfix workflow API graph and `POST /prompt`

**Do not** put Comfy `/view?…` URLs in `imageB64` — Python treats them as empty and inserts a black 512×512 guide.

---

## 2. Node graph (what matters for AD)

| Node | Role |
|------|------|
| `LTXDirector` | Timeline → prompt-relay conditioning + empty video/audio latents + `GUIDE_DATA` / `MOTION_GUIDE_DATA` |
| `LTXDirectorGuide` (×2, stage 1 & 2) | Encodes guide images via `LTXVAddGuide.append_keyframe`; optional IC-LoRA motion |
| `LTXDirectorCropGuides` (×2) | Crops guide token padding after upsample stage |
| Rest of Hotfix | Distilled UNET, DualCLIP (gemma + projection), AV concat, 2-stage sampler + spatial upscaler |

Registered in `__init__.py` as `LTXDirector`, `LTXDirectorGuide`, `LTXDirectorCropGuides` (+ older sequencer/keyframer helpers we can ignore for v2).

Hotfix model stack (already documented in `skills/workflow-researcher/references/ltx-23-director.md`):

- `ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors`
- `gemma_3_12B_it_fp4_mixed` + `ltx-2.3_text_projection_bf16`
- Video + audio VAEs + spatial upscaler x2

This is a **different checkpoint path** than current story-maker I2V/FLF templates (dev ckpt + distilled LoRA + OmniNFT). Keep them isolated.

---

## 3. How the UI becomes API inputs

`js/ltx_director.js` → `commitChanges()` writes four hidden widgets every edit:

| Widget | Format | Built from |
|--------|--------|------------|
| `timeline_data` | JSON string | Full editor state (`toSave`) |
| `local_prompts` | `"prompt A \| prompt B \| …"` | Contiguous text spans over `[start_frame, start_frame+duration_frames)` |
| `segment_lengths` | `"48,72,…"` | Pixel-space frame lengths for those spans (gaps absorbed into neighbors) |
| `guide_strength` | `"0.70,0.85"` | Comma list for **non-text** image/video segments in range (order = sorted by `start`) |

Also set explicitly on the node:

- `start_frame`, `end_frame`, `duration_frames` (and second mirrors)
- `frame_rate` (default 24)
- `custom_width` / `custom_height` / `resize_method` / `divisible_by`
- `use_custom_audio`, `use_custom_motion`, `inpaint_audio`, `override_audio`
- Optional linked `global_prompt` input

For headless runs, **you must synthesize the same four strings** the UI would — Python does **not** recompute `local_prompts` / `segment_lengths` / `guide_strength` from `timeline_data` alone (except `global_prompt` fallback from JSON when the input is empty).

### Widget order in Hotfix UI export (`widgets_values`)

Approximate order on node `131` (verify when converting UI→API):

0–5: `start_second`, `end_second`, `duration_seconds`, `start_frame`, `end_frame`, `duration_frames`  
6: `timeline_data`  
7–8: `local_prompts`, `segment_lengths`  
9: `epsilon`  
10: `guide_strength`  
11–13: `use_custom_audio`, `use_custom_motion`, `inpaint_audio` (booleans; exact index may shift by Comfy version)  
14–15: `frame_rate`, `display_mode`  
16–20: `custom_width`, `custom_height`, `resize_method`, `divisible_by`, `img_compression`  
(+ `override_audio`)

Prefer API-format graphs keyed by input name, not fragile index lists.

---

## 4. `timeline_data` schema

Top-level object (defaults from `parseInitial` / empty Hotfix):

```json
{
  "mainTrackEnabled": true,
  "audioTrackEnabled": false,
  "motionTrackEnabled": false,
  "propHeight": 90,
  "globalPropHeight": 60,
  "showFilenames": true,
  "overrideAudio": false,
  "inpaint_audio": true,
  "global_prompt": "…",
  "retake_global_prompt": "",
  "retakeMode": false,
  "retakeStart": 24,
  "retakeLength": 48,
  "retakePrompt": "",
  "retakeStrength": 1.0,
  "retakeVideo": null,
  "normalStartFrame": 0,
  "normalDurationFrames": 121,
  "segments": [],
  "motionSegments": [],
  "audioSegments": []
}
```

### Main-track segment (`segments[]`)

| Field | Notes |
|-------|--------|
| `id` | Stable string |
| `type` | `"image"` \| `"video"` \| `"text"` |
| `start` | Frame index on timeline (absolute) |
| `length` | Duration in frames (visual block width) |
| `prompt` | Local prompt text (used for prompt-relay; image blocks may also carry prompts) |
| `imageFile` | Path relative to Comfy `input/` e.g. `whatdreamscost/panel.png` — **preferred for API** |
| `imageB64` | Real `data:image/…;base64,…` **or omit**. `/view?…` → black dummy |
| `guideStrength` | Per-image lock strength (also mirrored into widget) |
| `isEndFrame` | `true` → insert guide at **end** of block (`start+length-1`), else at `start` |
| `trimStart` | Video-only |

**Text segments** (`type: "text"`): no image; contribute only to `local_prompts` / `segment_lengths`. They are **excluded** from `guide_strength`.

### Motion / audio tracks

`motionSegments[]` with `videoFile` → IC-LoRA guidance (`MOTION_GUIDE_DATA`). Not needed for AD I2V/FLF spike.  
`audioSegments[]` — skip for v1 spike (`use_custom_audio=false`).

### Retake mode

Out of scope for AD spike. Requires `retakeMode` + uploaded base video; `LTXDirectorGuide` temporal-masks a region.

---

## 5. Python execute path (image guides)

`ltx_director.py` `LTXDirector.execute`:

1. Parse `timeline_data`
2. Collect image/video segs overlapping `[start_frame, start_frame+duration_frames)` that have `imageFile` or `imageB64`
3. Load via `_load_image_tensor` / `_load_video_tensor`
4. Resize to `custom_width`×`custom_height` (or snap source) with `divisible_by` (32)
5. Build `guide_data`:
   - `images[]`, `insert_frames[]`, `strengths[]`
   - `insert_frame = start - start_frame` **or** `start+length-1 - start_frame` if `isEndFrame`
   - strength from `guide_strength` widget by index (default 1.0)
6. Auto empty latent with LTX `8n+1` length: `ceil((duration_frames-1)/8)*8+1`
7. Prompt-relay encode from `global_prompt` + `local_prompts` + `segment_lengths`
8. Emit `guide_data` (+ raw `timeline_data` for retake) and optional motion guides

`LTXDirectorGuide` then calls Lightricks `LTXVAddGuide.append_keyframe` per image (skips strength ≤ 0).

---

## 6. Mapping Assistant-Director clips → Director timeline

Existing AD schema (`DirectorClip` in `skills/story-maker/schemas/generation.py`):

- `workflow`: `i2v` | `flf2v`
- `duration_seconds`, `motion_prompt`
- `i2v_strength`, `last_frame_strength`, `cfg` (from `ltx_render_params.py`)

Assume `fps=24`. Snap duration: `duration_frames = 8*n+1` with `n = ceil((seconds*fps - 1)/8)`.

### 6.1 I2V (single start panel)

```
segments = [
  {
    "id": "start",
    "type": "image",
    "start": 0,
    "length": duration_frames,   # or 1s block; insert uses start=0
    "prompt": "",
    "imageFile": "whatdreamscost/<clip>_start.png",
    "guideStrength": <i2v_strength>,
    "isEndFrame": false
  },
  {
    "id": "motion",
    "type": "text",
    "start": 0,                  # or slightly after if you want split relay
    "length": duration_frames,
    "prompt": "<motion_prompt>"
  }
]
```

Derived widgets (minimal contiguous example — one text span covering full range):

- `local_prompts` = motion prompt (or `" | "`-joined if multiple text/image prompt blocks)
- `segment_lengths` = `"<duration_frames>"`
- `guide_strength` = `"0.70"` (one non-text image)
- `start_frame=0`, `duration_frames=<8n+1>`, `end_frame=duration_frames`
- `custom_width=1920`, `custom_height=1088`, `resize_method="crop"` or `"maintain aspect ratio"`
- `use_custom_motion=false`, `use_custom_audio=false`
- CFG on Hotfix `CFGGuider` nodes ← `clip.cfg`

**Simpler I2V:** one image segment + put motion text in `global_prompt` only, leave `local_prompts` empty / single empty local — prompt relay falls back to global. Prefer explicit text segment for parity with “text before end frame”.

### 6.2 FLF2V (first → last, true end frame)

```
segments = [
  {
    "id": "first",
    "type": "image",
    "start": 0,
    "length": 24,                 # 1s visual block; insert at frame 0
    "imageFile": "…_first.png",
    "guideStrength": <i2v_strength>,
    "isEndFrame": false,
    "prompt": ""
  },
  {
    "id": "middle_text",
    "type": "text",
    "start": 24,
    "length": duration_frames - 48,
    "prompt": "<motion_prompt>"
  },
  {
    "id": "last",
    "type": "image",
    "start": duration_frames - 24,
    "length": 24,
    "imageFile": "…_last.png",
    "guideStrength": <last_frame_strength>,  # max(0.85, i2v+0.05) from AD
    "isEndFrame": true,           # CRITICAL — insert at last frame of clip
    "prompt": ""
  }
]
```

`guide_strength` widget must list **only** the two images, in start order:  
`"0.70,0.85"`.

`local_prompts` / `segment_lengths` must cover contiguous ranges across all three blocks (gaps absorbed — match `commitChanges` logic).

### 6.3 Strength / CFG parity with current AD

| AD field | Director target |
|----------|-----------------|
| `i2v_strength` | First image `guideStrength` + widget entry |
| `last_frame_strength` | End-frame image `guideStrength` |
| `cfg` | Both stage `CFGGuider.cfg` (Hotfix defaults may differ from distilled I2V templates — validate empirically) |
| `motion_prompt` | Text segment + optional `global_prompt` (character/scene lock) |

---

## 7. Upload + `/prompt` injection recipe

```
POST {COMFYUI_URL}/upload/image
  multipart: image=<file>, subfolder=whatdreamscost
→ { "name": "foo.png", "subfolder": "whatdreamscost", ... }

imageFile = "whatdreamscost/foo.png"   # NOT /api/view URL
```

Reuse `skills/story-maker/tools/comfyui_tools.upload_image` (add subfolder arg if needed).

API node patch (conceptual):

```python
node = workflow["<LTXDirector_node_id>"]["inputs"]
node["timeline_data"] = json.dumps(timeline)
node["local_prompts"] = local_prompts
node["segment_lengths"] = segment_lengths
node["guide_strength"] = guide_strength
node["start_frame"] = 0
node["duration_frames"] = duration_frames
node["end_frame"] = duration_frames
node["frame_rate"] = 24
node["custom_width"] = 1920
node["custom_height"] = 1088
node["use_custom_motion"] = False
node["use_custom_audio"] = False
# global_prompt via linked input or widget if present
```

Convert Hotfix UI JSON → API once (Comfy “Save (API Format)” or existing researcher tooling), store under e.g. `skills/story-maker/assets/workflow-templates/ltx-director-hotfix-api.json` behind a **new** env flag — do not replace `ltx-i2v.json` / `ltx-flf2v.json`.

---

## 8. Pitfalls (must-know)

1. **`imageB64` with `/view?`** → black guide (`_load_image_tensor`). Prefer `imageFile` only after upload.
2. **Hidden widgets must be filled** — empty `local_prompts`/`segment_lengths` changes prompt-relay behavior.
3. **`isEndFrame`** is the only clean FLF end lock; placing an image at the end without the flag inserts at block **start**.
4. **`guide_strength` order** = sorted non-text segments in range, not all segments.
5. **Duration `8n+1`** — Director auto-snaps latent length; keep widget duration consistent to avoid off-by-one inserts.
6. **Model stack mismatch** with current AD templates — side-by-side only.
7. **Custom node must be installed** (`WhatDreamsCost-ComfyUI` + updated `ComfyUI-LTXVideo` + `ComfyUI-KJNodes`) or `/prompt` validation fails.
8. **IC-LoRA / retake / audio** — ignore until I2V/FLF spike is green.
9. Large `timeline_data` with embedded base64 will bloat prompts — use files.

---

## 9. Proposed `director_v2` spike (isolated)

**Do not modify** existing reel_v2 generate path until spike passes.

1. Install nodes on `COMFYUI_URL` via hotfix script / Manager (parallel — user doing this).
2. Export Hotfix to API JSON; confirm node IDs for Director + both Guides + CFGGuiders.
3. Helper module (new): `tools/ltx_director_timeline.py`
   - `build_i2v_timeline(...)`, `build_flf_timeline(...)`
   - mirrors `commitChanges` contiguous prompt/length logic
4. Smoke tests (manual or pytest with fixtures):
   - I2V 5s talking clip (strength 0.8)
   - FLF 6s with end-frame strength 0.85
   - Confirm guides appear in Comfy logs (`[LTXDirectorGuide] … image_guides: N`)
5. Gate behind `STORY_MAKER_VIDEO_BACKEND=director_v2` (or similar); default remains current templates.
6. Later: wire AD planner output → timeline builder → queue; keep OmniNFT/I2V templates as A/B control.

---

## 10. Key source anchors (clone)

| File | Why |
|------|-----|
| `ltx_director.py` | `_load_image_tensor`, `LTXDirector.execute`, guide insert / `isEndFrame` |
| `ltx_director_guide.py` | `LTXVAddGuide` keyframe path |
| `js/ltx_director.js` | `commitChanges`, `parseInitial`, upload → `imageFile`, end-frame toggle |
| `prompt_relay.py` | Token ranges / segment length distribution |
| `example_workflows/LTX_Director_2_Workflow_Hotfix.json` | Same as repo Hotfix |

---

## 11. Open questions for first live run

- Exact API input names / which CFGGuider stage(s) to set for distilled-1.1 CFG ≈ 1.0–1.5
- Whether Hotfix negative/zero conditioning needs AD negative prompts
- Best `resize_method` for 1920×1088 panels (`crop` vs `maintain aspect ratio`)
- Whether a single text segment spanning full duration is enough vs image-attached prompts

Once the custom node is live on the server, next step is a single I2V smoke `/prompt` with a known Naila panel.
