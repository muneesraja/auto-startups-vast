# Continuity Ledger Schema Reference

Field-by-field specification of the continuity ledger `state.json`. The ledger is the single source of truth across the clip chain. Load this when reading or writing ledger state.

---

## Top-Level Fields

| Field | Type | Description |
|---|---|---|
| `run_name` | string | Human-readable run identifier. |
| `generation_fingerprint` | string | Hash of the input brief + config; detects stale runs. |
| `fps` | number | Output frames per second (e.g. 30). |
| `context_length` | number | Max clips the model plans against. |
| `arc[]` | array | 5-stage DOME arc mapped to clips. |
| `cast[]` | array | Character bible locks. |
| `items[]` | array | SCORE object-state tracking. |
| `places[]` | array | Location definitions. |
| `clips[]` | array | Per-clip generation + render state. |
| `conflicts[]` | array | Detected temporal contradictions. |

---

## `arc[]` — DOME Arc

| Field | Type | Description |
|---|---|---|
| `clip` | int | Clip index this stage maps to. |
| `stage` | string | One of the 5 DOME stages. |
| `tension` | number | 0–1 tension level at this stage. |
| `beat` | string | Narrative beat label. |

---

## `cast[]` — Character Bible

| Field | Type | Description |
|---|---|---|
| `id` | string | Stable character ID (`char_01`). |
| `label` | string | Human-readable name. |
| `appearance_lock` | string | Frozen physical description — the bible lock. |
| `wardrobe` | string | Outfit description per arc/clip. |
| `refs[]` | array | `asset_id@version` references (identity plate, previous sheets). |

---

## `items[]` — SCORE State

| Field | Type | Description |
|---|---|---|
| `id` | string | Stable item ID. |
| `name` | string | Human-readable name. |
| `state` | string | `active` \| `lost` \| `destroyed`. |
| `held_by` | string \| null | `cast.id` or null. |
| `since_clip` | int | Clip index where the current state began. |

---

## `places[]` — Locations

| Field | Type | Description |
|---|---|---|
| `id` | string | Stable place ID. |
| `name` | string | Human-readable name. |
| `light` | string | Lighting description. |
| `props[]` | array | Props present at this location. |

---

## `clips[]` — Per-Clip State

| Field | Type | Description |
|---|---|---|
| `index` | int | Zero-based clip index. |
| `id` | string | Stable clip ID. |
| `seed` | string \| null | Generation seed (null for gpt-image sheets). |
| `raw_frames` | int | Raw frame count from the render. |
| `delivered_frames` | int | Frames after trim / hinge alignment. |
| `steps` | int | Generation steps used. |
| `audio` | object | See `clips[].audio` below. |
| `shots[]` | array | Micro-shot list. See below. |
| `hinge_out` | object | Cross-clip continuity beat (end of this clip). |
| `hinge_in` | object | Cross-clip continuity beat (start of this clip). |
| `quads[]` | array | DOME temporal-KG quadruples. |
| `sheet` | string | Path to the storyboard sheet image. |
| `sheet_prompt` | string | Prompt used to generate the sheet. |
| `prompt_file` | string | Path to the H3 video prompt file. |
| `prompt_hash` | string | Hash of `prompt_file` — detects stale renders. |
| `render` | object | See `clips[].render` below. |

### `clips[].audio`

| Field | Type | Description |
|---|---|---|
| `start_s` | number | Audio start time in the song window (seconds). |
| `duration_s` | number | Audio window duration. |
| `lines[]` | array | Dialogue/vocal lines. |

`lines[]` item:

| Field | Type | Description |
|---|---|---|
| `t` | number | Timestamp within the clip (seconds). |
| `speaker` | string | `cast.id` or narrator label. |
| `lang` | string | Language tag. |
| `text` | string | Verbatim line text. |

### `clips[].shots[]`

| Field | Type | Description |
|---|---|---|
| `n` | int | Shot number within the clip (1-based). |
| `t` | `[start, end]` | Timestamp range in seconds. |
| `framing` | string | Framing token (ECU, CU, MCU, medium, wide, EWS, OTS, POV). |
| `angle` | string | Angle token (eye-level, high, low, dutch, bird's-eye, worm's-eye). |
| `action` | string | One dominant action description. |
| `sound` | string | Sound cue (SFX, vocal hit, or beat). |
| `cast[]` | array | Character IDs present in this shot. |
| `on_beat` | bool | True if cut snaps to a beat onset. |
| `panel` | int \| null | Panel number on the storyboard sheet (null = video-only). |

### `clips[].hinge_out` / `hinge_in`

Cross-clip continuity beat — the last micro-shot of clip N and first of clip N+1 are the same shot split across the boundary.

| Field | Type | Description |
|---|---|---|
| `shot_ref` | string | Reference to the shared shot. |
| `beat` | string | Held/simple-motion beat description. |
| `cut_after` | bool | Cut immediately after the hinge resolves. |

### `clips[].quads[]`

DOME temporal-KG quadruples `[subject, action, object, index]` — subject (`cast.id`/`items.id`), action verb, object (`cast.id`/`items.id`/null), shot index.

### `clips[].render`

| Field | Type | Description |
|---|---|---|
| `status` | string | `pending` \| `rendering` \| `done` \| `failed`. |
| `attempts` | int | Render attempt count. |
| `scores` | object | Quality scores from the vision gate. |
| `observed` | object | See below. |

`render.observed` — `last_frame` (string, path to extracted last frame), `cuts_detected` (array, detected cut timestamps), `drift[]` (array, identity/continuity drift observations).

---

## Observed-vs-Planned Rule

`render.observed` is written by S11 **from the rendered file**, never from the plan. The next clip's `hinge_in` and storyboard sheet are authored against **observed state**, never planned state. This is the single hardest rule in the ledger — planning against expected output produces drift cascades.

---

## `conflicts[]`

| Field | Type | Description |
|---|---|---|
| `clip` | int | Clip where the conflict was detected. |
| `type` | string | `identity` \| `wardrobe` \| `item_state` \| `spatial` \| `temporal`. |
| `detail` | string | Human-readable contradiction description. |

---

## Full JSON Example (2 Clips, abbreviated)

```json
{
  "run_name": "bamboo-epi-1", "generation_fingerprint": "a1b2c3", "fps": 30, "context_length": 4,
  "arc": [
    {"clip": 0, "stage": "Discovery", "tension": 0.2, "beat": "toddler finds egg"},
    {"clip": 1, "stage": "Open", "tension": 0.5, "beat": "egg hatches, dino emerges"}
  ],
  "cast": [{"id": "char_01", "label": "Toddler", "appearance_lock": "brown eyes, blue/yellow socks", "wardrobe": "pajamas", "refs": ["identity_plate@1"]}],
  "items": [{"id": "item_01", "name": "glowing egg", "state": "destroyed", "held_by": null, "since_clip": 1}],
  "places": [{"id": "place_01", "name": "dusty basement", "light": "single golden shaft", "props": ["cardboard boxes", "canvas sheet"]}],
  "clips": [
    {"index": 0, "id": "clip_01", "seed": null, "raw_frames": 425, "delivered_frames": 425, "steps": 50,
     "audio": {"start_s": 0.0, "duration_s": 14.17, "lines": [{"t": 10.5, "speaker": "char_02", "lang": "en", "text": "Mama!"}]},
     "shots": [
       {"n": 1, "t": [0.0, 1.5], "framing": "ECU", "angle": "eye-level", "action": "toddler's eyes peer into dark basement", "sound": "heavy breathing", "cast": ["char_01"], "on_beat": true, "panel": 1},
       {"n": 2, "t": [1.5, 3.0], "framing": "medium", "angle": "low", "action": "feet padding through dust", "sound": "padding footsteps", "cast": ["char_01"], "on_beat": true, "panel": 2}
     ],
     "hinge_out": {"shot_ref": "shot_7", "beat": "toddler reacts to dino squeak", "cut_after": true}, "hinge_in": null,
     "quads": [["char_01", "peers", null, 1], ["char_01", "walks", null, 2]],
     "sheet": "sheets/clip_01.png", "sheet_prompt": "...", "prompt_file": "video_prompts/clip_01.txt", "prompt_hash": "d4e5f6",
     "render": {"status": "done", "attempts": 1, "scores": {"identity": 0.9}, "observed": {"last_frame": "frames/clip_01_last.png", "cuts_detected": [1.5, 3.0], "drift": []}}},
    {"index": 1, "id": "clip_02", "seed": null, "raw_frames": 425, "delivered_frames": 420, "steps": 50,
     "audio": {"start_s": 14.17, "duration_s": 14.17, "lines": []},
     "shots": [{"n": 1, "t": [0.0, 2.0], "framing": "CU", "angle": "eye-level", "action": "toddler's shocked face held from previous clip", "sound": "toddler shriek tail", "cast": ["char_01"], "on_beat": true, "panel": 1}],
     "hinge_out": null, "hinge_in": {"shot_ref": "shot_7", "beat": "toddler reacts to dino squeak", "cut_after": true},
     "quads": [["char_01", "reacts", "char_02", 1]],
     "sheet": "sheets/clip_02.png", "sheet_prompt": "...", "prompt_file": "video_prompts/clip_02.txt", "prompt_hash": "g7h8i9",
     "render": {"status": "pending", "attempts": 0, "scores": {}, "observed": {"last_frame": null, "cuts_detected": [], "drift": []}}}
  ],
  "conflicts": []
}
```
