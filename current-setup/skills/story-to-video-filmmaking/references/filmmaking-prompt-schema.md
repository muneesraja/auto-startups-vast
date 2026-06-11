# Filmmaking Prompt JSON Schema

The `filmmaking_prompt.json` file is the **central instruction sheet** for the `story-to-video-filmmaking` pipeline. It is composed by the agent in Phase 1.5 and is the most important document the pipeline consumes — every image gen call, every video gen call, every continuation chain, and every storytelling decision flows from it.

Unlike the legacy `prompt.json` (static scene stills) or `motion_prompt.json` (single-frame I2V), this schema coordinates:
- **Dual-keyframe generation** (First Frame + Last Frame per shot)
- **Reference-chained LF generation** (using FF or previous tail as structural anchor)
- **Recursive orchestration** (image gen → video gen → tail extract → next shot, per chain)
- **Continuation-aware shot chaining** across scenes

---

## JSON Schema Structure

```json
{
  "version": "1.1",
  "model": "ltx-2.3-fflf-seed-hunter",
  "workflow_template": "ltx-23-fflf-seed-hunter",
  "global": {
    "image_workflow_template": "flux-2-dev-turbo",
    "resolution_preset": "1080p",
    "custom_width": null,
    "custom_height": null,
    "fps": 25,
    "segment_duration": 5,
    "overlap_seconds": 1.0,
    "input_ref_strength": 0.8,
    "end_ref_strength": 0.8,
    "seed_base": 42,
    "auto_select_motion": true,
    "continuation_mode": "auto_chain",
    "style": "Cinematic 3D Pixar-style, soft volumetric lighting"
  },
  "shots": [
    {
      "scene": 1,
      "shot": 1,
      "shot_type": "chain_start",
      "first_frame_prompt": "establishing shot of a fantasy village at dawn, warm golden light, a girl stands at the edge of the frame looking outward",
      "last_frame_prompt": "same village, camera has pushed closer, the girl turned to face the camera with a confused expression",
      "first_frame_image": "film_001_shot001_ff.png",
      "last_frame_image": "film_001_shot001_lf.png",
      "motion_prompt": "A continuous fluid shot — camera slowly pushes in toward the girl as she turns her head to face us and tilts it curiously",
      "filename_prefix": "film_001_shot001",
      "continues_from": null,
      "break_continuity": false,
      "characters_present": ["girl"],
      "references": ["girl_reference_sheet.png"],
      "lf_references": ["girl_reference_sheet.png"],
      "lf_reference_note": "LF introduces no new characters. FF image will be prepended at runtime as the primary structural anchor. Only girl sheet kept for character fidelity check.",
      "overrides": {
        "input_ref_strength": 0.7,
        "end_ref_strength": 0.8,
        "segment_duration": 5
      }
    }
  ]
}
```

---

## Field Reference

### Global Parameters

| Field | Type | Default | Description |
|---|---|---|---|
| `version` | string | `"1.1"` | Schema version |
| `model` | string | — | Target model. Always `"ltx-2.3-fflf-seed-hunter"` |
| `workflow_template` | string | — | ComfyUI API template name. Always `"ltx-23-fflf-seed-hunter"` |
| `global.image_workflow_template` | string | `"flux-2-dev-turbo"` | Template for Phase 2 image generation |
| `global.resolution_preset` | string | `"1080p"` | `"1080p"` (1920×1088) or `"720p"` (1280×704) |
| `global.fps` | int | `25` | Frame rate |
| `global.segment_duration` | int | `5` | Duration per segment in seconds |
| `global.overlap_seconds` | float | `1.0` | Context buffer duration for continuation stitching |
| `global.input_ref_strength` | float | `0.8` | FF keyframe guide strength (0.5–0.9 Goldilocks zone) |
| `global.end_ref_strength` | float | `0.8` | LF keyframe guide strength |
| `global.seed_base` | int | `42` | Base seed |
| `global.auto_select_motion` | bool | `true` | Auto-pick best Stage 1 preview via Gemini evaluator |
| `global.continuation_mode` | string | `"auto_chain"` | `"auto_chain"` or `"independent"` |
| `global.style` | string | — | Global cinematic style descriptor |

---

### Shot Parameters

| Field | Type | Required? | Description |
|---|---|---|---|
| `scene` | int | ✅ | Scene index |
| `shot` | int | ✅ | Shot index within scene |
| `shot_type` | string | ✅ | See Shot Types below |
| `first_frame_prompt` | string\|null | chain_start/independent only | Detailed Flux prompt for the opening composition |
| `last_frame_prompt` | string | ✅ | Detailed Flux prompt for the closing composition |
| `first_frame_image` | string\|null | chain_start/independent only | Filename for FF still (e.g. `film_001_shot001_ff.png`) |
| `last_frame_image` | string | ✅ | Filename for LF still (e.g. `film_001_shot001_lf.png`) |
| `motion_prompt` | string | ✅ | Brief (20–60 word) motion description for the LTX video model |
| `filename_prefix` | string | ✅ | Base name for all outputs. Format: `film_{scene_3d}_shot{shot_3d}` |
| `continues_from` | string\|null | — | Prefix of preceding shot if continuation chaining |
| `break_continuity` | bool | — | Forces `independent` even within a scene |
| `characters_present` | array | — | Names of characters visible in this shot |
| `references` | array | — | Character sheet filenames for **FF generation** |
| `lf_references` | array | ✅ | Character sheet filenames for **LF generation** (see below) |
| `lf_reference_note` | string | — | Agent reasoning note explaining the `lf_references` choice |
| `overrides` | object | — | Shot-level overrides to global params |

---

### Shot Types

| `shot_type` | FF Source | LF Source | Use Case |
|---|---|---|---|
| `chain_start` | Generated from `first_frame_prompt` + `references` | Generated from `last_frame_prompt` + `lf_references` + FF image (prepended at runtime) | First shot of a scene or after a visual break |
| `continuation` | **Extracted from preceding video's tail frame** (Phase 3 output) | Generated from `last_frame_prompt` + `lf_references` + tail frame (prepended at runtime) | Seamless extension of a scene chain |
| `independent` | Generated from `first_frame_prompt` + `references` | Generated from `last_frame_prompt` + `lf_references` + FF image (prepended at runtime) | Self-contained shot with no visual continuity to neighbors |
| `bridge` | **Extracted from preceding video's tail frame** | Generated from `last_frame_prompt` + `lf_references` + tail frame (prepended at runtime) | Connects two scene chains; LF lands in the new scene's visual world |

---

## `lf_references` — Agent Reasoning Rules

This is the most important field for storytelling quality. The agent **must reason per-shot** and never blindly copy `references` into `lf_references`.

### Core Principle
The LF image is generated using the FF image (or the previous shot's tail frame) **already prepended as the primary structural anchor** by the pipeline at runtime. The `lf_references` field controls what additional references are included.

> ⚠️ **Production Learning (2026-06-11):** The structural anchor alone is **NOT sufficient** to preserve character identity. Flux's ReferenceLatent chain drifts character features across iterations — chibi proportions get diluted, new features get invented (leaf hats, changed stripes). Always include character sheets for the emotional focus character(s) of the LF.

### Decision Logic (Updated)

```
WHEN generating lf_references for a shot:

1. START with empty lf_references = []

2. CHECK: Is a character the emotional FOCUS of the LF?
   YES → ADD that character's reference sheet to lf_references
         (even if they're already visible in the structural anchor —
          the anchor alone is NOT enough to lock character appearance)
   NO  → Leave it empty

3. CHECK: Does the LF introduce a character NOT visible in the FF / preceding tail frame?
   YES → ADD that character's reference sheet to lf_references

4. CHECK: Is this a scene transition (bridge/independent with new location)?
   YES and the new environment needs a style anchor →
     consider adding an environment/style reference if available
   TYPICALLY → the text prompt alone handles environment; only add if truly novel

5. HARD LIMIT: lf_references must contain at most 3 items
   (the structural anchor image is prepended by the pipeline, consuming the 1st slot of 4)

6. ALWAYS write lf_reference_note explaining the reasoning for auditability
   The note MUST reference the story moment, not just the technical choice.
```

### Examples

```json
// Shot 1 — chain_start, hero is the emotional focus
"references": ["hero_sheet.png"],
"lf_references": ["hero_sheet.png"],
"lf_reference_note": "Hero is the sole emotional focus. Sheet included to prevent identity drift across Flux iteration — the structural anchor alone is not enough to lock character proportions."

// Shot 2 — continuation, same characters, hero still focus
"references": [],
"lf_references": ["hero_sheet.png"],
"lf_reference_note": "Continuation shot. Hero is still the emotional focus (reacting to environment). Sheet included to prevent identity drift from tail frame anchor."

// Shot 3 — villain enters the LF for the first time, hero also present
"references": ["hero_sheet.png"],
"lf_references": ["hero_sheet.png", "villain_sheet.png"],
"lf_reference_note": "Villain enters frame in the LF for the first time. Hero is still the emotional focus (reacting to villain). Both sheets needed: villain for new-character conditioning, hero to prevent identity dilution by the new ref."

// Shot 4 — continuation, both characters established, action scene
"references": [],
"lf_references": [],
"lf_reference_note": "Continuation shot. Both characters already established in the structural anchor (Shot 3 tail frame). Fast action scene — no identity-critical close-ups. lf_references stays empty."

// Bridge shot — transitioning from forest to palace
"references": [],
"lf_references": ["queen_sheet.png"],
"lf_reference_note": "Bridge shot: tail frame anchors the forest exit; LF opens in the palace with the Queen appearing for the first time. Queen sheet added to condition her appearance correctly."
```

---

## Storytelling Alignment Rules

The agent must maintain storytelling coherence when composing `filmmaking_prompt.json`. These rules apply across the whole film, not just individual shots:

1. **Every shot must advance the story** — the FF→LF motion prompt should describe a narrative beat, not just camera movement for its own sake.

2. **Character continuity across shots** — characters must look the same from shot to shot. The recursive pipeline (tail frame → next FF) handles visual continuity for continuation shots automatically. For `chain_start` and `independent` shots that follow a scene gap, use the same character reference sheets to maintain appearance. Always include focus character sheets in `lf_references` to prevent identity drift.

3. **Environment continuity within a chain** — shots in the same scene chain should share environment details. Let the structural anchor (FF/tail) carry the environment; don't re-describe it in the motion prompt.

4. **Emotional arc** — the sequence of `motion_prompt` values across shots should mirror the emotional beats of the story. Match `segment_duration` to spatial displacement: 2-3s for expression-only changes, 4-5s for subtle shifts, 5-7s for clear trajectories, 7-8s for full traversals. Do NOT default to 5-6s for every shot.

5. **Scene transition planning** — when moving between scenes (via `independent` or `bridge` shots), the LF of the last shot of Scene A and the FF of the first shot of Scene B should not attempt an impossible visual jump. Plan the `last_frame_prompt` of the bridge/final shot to "open the door" visually to Scene B (e.g., character walks through a doorway, camera pans to reveal the new setting). For radical visual jumps, use `break_continuity: true` + `independent`.

6. **`lf_reference_note` is mandatory reasoning** — it must contain a sentence explaining why the references were chosen, referencing the story moment. This keeps the pipeline auditable and prevents future hallucination drift.

7. **Manifest coverage** — `filmmaking_prompt.json` must contain entries for ALL scenes and shots in `story_manifest.json`. If partial composition is unavoidable, add a `coverage` field documenting what's missing and why.

8. **Continuation shot `first_frame_image` must be `null`** — for `continuation` and `bridge` shots, do not set `first_frame_image` to a fabricated filename. The pipeline uses the tail frame from the preceding shot automatically.

