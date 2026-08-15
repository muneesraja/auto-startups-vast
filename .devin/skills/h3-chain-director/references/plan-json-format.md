# H3 Chain Plan JSON Format

Specification for the `MiniMaxH3ChainPlan` JSON (node 1700 widget). The plan drives the entire seamless chain: shot timing, seeds, prompts, and compatibility constraints. Load this when authoring or editing a plan.

---

## Top-Level Fields

| Field | Required | Type | Description |
|---|---|---|---|
| `run_name` | yes | string | unique run directory under `output/h3_chains/` |
| `compatibility` | yes | object | whole-plan constraints; changing any field invalidates all clips |
| `defaults` | yes | object | fallback `duration_seconds` + `steps` for shots that omit them |
| `base_seed` | no | uint64 | deterministic seed source when a shot omits `seed` |
| `prompt_prefix` | no | string | prepended to every shot's `prompt`; use for shared subject/wardrobe/style/continuity blocks |
| `shots` | yes | array | ordered list of shot objects |

### `compatibility`

| Field | Example | Invalidates |
|---|---|---|
| `width` | 960 | all |
| `height` | 544 | all |
| `context_length` | 22 | all |
| `anchor_mode` | `head` | all |
| `encode_mode` | `video` | all |
| `crop` | `disabled` | all |
| `audio_mode` | `source_track` | all |
| `audio_context_length` | 0 | all |
| `generation_fingerprint` | string | all |
| `segment_crf` | 20 | all |

### `defaults`

| Field | Example | Note |
|---|---|---|
| `duration_seconds` | 15 | requested duration; rounds UP to next valid H3 frame count |
| `steps` | 5 | sampler steps fallback |

---

## The Frame Grid

H3 runs at **24 FPS**. Valid raw lengths are on the `17k+5` grid:

```
5, 22, 39, 56, 73, …  (rule: length % 17 == 5)
```

| `anchor_mode` | First clip delivered | Later clips delivered |
|---|---|---|
| `head` | raw | raw − `context_length` |

With `context_length=22`, a 362-frame clip delivers 340 new frames. Every non-final clip must deliver **≥ `context_length`** frames.

| Duration | Raw frames | Clip 1 delivers | Later clips deliver (ctx=22) |
|---|---|---|---|
| 5 s | 124 | 124 | 102 |
| 10 s | 243 | 243 | 221 |
| 15 s | 362 | 362 | 340 |

`duration_seconds` rounds UP to the next valid grid count. For frame-exact control, set `length` or `frames` directly.

---

## Shot Fields

| Field | Required | Type | Description |
|---|---|---|---|
| `id` | yes | string | unique scene name; used by checkpoints; changing it can change an auto seed |
| `prompt` | yes | string \| array | scene prompt; array entries joined with line breaks; empty string = blank line; `prompt_prefix` prepended automatically |
| `prompt_hash` | no | string | computed from `prompt`; do not set manually |
| `seed` | no | uint64 | fixed seed; omit for deterministic seed from `base_seed` |
| `steps` | no | int | sampler steps for this scene (1–10000) |
| `duration_seconds` | no | number | requested duration; rounds up to grid |
| `length` | no | int | exact raw frame count (must be on grid) |
| `frames` | no | int | alias of `length` |
| `audio` | no | object | per-shot audio override |

### Precedence

```
length  >  frames  >  duration_seconds
shot value  >  JSON defaults  >  H3 Chain Plan node defaults
```

---

## Audio Modes

| Mode | Use | Wiring | Requirement |
|---|---|---|---|
| `source_track` | music videos (default) | same `LoadAudio` → LoopStart, CurrentShot, Assemble | source audio ≥ total delivered duration; only silent audio auto-padded |
| `generated_audio` | H3 native audio | H3 generates audio; `audio_context_length` may carry audio context | set `audio_context_length` (e.g. 22) for audio continuity |

---

## Node Settings → Plan Field Map

| Node | Widget / Input | Plan field |
|---|---|---|
| MiniMaxH3ChainPlan (1700) | JSON widget | entire plan |
| MiniMaxH3ChainLoopStart (1701) | `start_clip` | resume index (1-based) |
| MiniMaxH3ChainLoopStart (1701) | `run_name` | overrides plan `run_name` if non-empty |
| MiniMaxH3ReferenceToVideo (110) | `width`, `height` | `compatibility.width/height` |
| MiniMaxH3ReferenceToVideo (110) | `length` | shot `length` (from CurrentShot) |
| MiniMaxH3LoopTrim (132) | `fps` | 24 (fixed) |
| MiniMaxH3ChainAssemble (1706) | `run_name`, `crf` | assembly output name + quality |

---

## Worked Example — 3-clip plan, 960×544, context=22

```json
{
  "run_name": "demo_three_clip",
  "compatibility": {
    "width": 960, "height": 544, "context_length": 22,
    "anchor_mode": "head", "encode_mode": "video", "crop": "disabled",
    "audio_mode": "source_track", "audio_context_length": 0,
    "generation_fingerprint": "demo-v1", "segment_crf": 20
  },
  "defaults": { "duration_seconds": 15, "steps": 5 },
  "base_seed": 0,
  "prompt_prefix": "Subject: a woman in a red coat. Wardrobe unchanged throughout.",
  "shots": [
    { "id": "intro",  "prompt": ["Opening tracking shot backstage."], "seed": 123 },
    { "id": "street", "prompt": ["Continue through the door into the street."], "duration_seconds": 10, "seed": 456 },
    { "id": "outro",  "prompt": ["Resolve on a calm wide composition."], "length": 124 }
  ]
}
```

| Shot | Raw | Delivered | Cumulative | Seconds |
|---|---|---|---|---|
| intro | 362 | 362 | 362 | 15.08 |
| street | 243 | 221 | 583 | 24.29 |
| outro | 124 | 102 | 685 | 28.54 |

Delivered total = `362 + 221 + 102 = 685` frames → `685 / 24 = 28.5s`.
