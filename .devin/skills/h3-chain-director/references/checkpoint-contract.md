# H3 Chain — Checkpoint / Resume Contract

Resume semantics for the `ComfyUI-MiniMaxH3-Contex-Loop` pack (custom node `ethanfel/ComfyUI-MiniMaxH3-Contex-Loop`, installed by `workflows/setup/minimax-h3-seamless-chain-global-refs.sh` line 65). Load this when reasoning about what is checkpoint-safe to change mid-run.

---

## Hash Construction

| Hash | Scope | Inputs |
|---|---|---|
| `plan_hash` | whole plan | `compatibility` block + all `shots` **minus prompt text** |
| `prompt_hash` | one shot | the shot's `prompt` (joined array or string) |
| `_history_contract(plan, through_index)` | prefix | `shots[:through_index]` only, fields `{id, prompt_hash, seed, steps, raw_frames, delivered_frames, generation_start_frame}` |

### Prefix Property

`_history_contract` hashes only `shots[:through_index]`. Therefore:

- Editing clip N's `prompt` / `seed` / `length` / `steps` does **NOT** invalidate clips `1…N-1`.
- Reference images appear in **no hash** ⇒ swapping ref images per scene is checkpoint-safe.
- Changing any `compatibility` field invalidates **every** clip (the whole-plan hash changes).

---

## What Invalidates What

| Change | Invalidates |
|---|---|
| A shot's `prompt` | that shot and all later shots (prefix grows from that point) |
| A shot's `seed` / `steps` / `length` / `frames` | that shot and all later shots |
| A shot's `id` | that shot's checkpoint identity (auto-seed may change) |
| `compatibility.width` / `height` | everything |
| `compatibility.context_length` | everything |
| `compatibility.anchor_mode` | everything |
| `compatibility.audio_mode` | everything |
| `compatibility.generation_fingerprint` | everything |
| `compatibility.segment_crf` | everything |
| Reference image swap | **nothing** (refs are outside all hashes) |
| Source audio swap (source_track) | assembly + any unfinished clip; finished clip checkpoints stand |

`generation_fingerprint` must be changed whenever model, VAE, LoRA, references, CFG, scheduler, or another generation dependency changes.

---

## scene_range

| Form | Meaning |
|---|---|
| `N` | run only clip N |
| `N:M` | run clips N through M (one contiguous range) |
| disjoint (e.g. `1:3,7:9`) | **rejected** |

Resume needs the predecessor checkpoint: to resume at clip N, clips `1…N-1` must already be saved under the same `run_name` + `plan_hash`.

---

## source_track Audio Requirement

`audio_mode: source_track` wires the same `LoadAudio` output to `LoopStart`, `CurrentShot`, and `Assemble`. The source audio duration must be **≥ total delivered video duration**. Only silent audio is auto-padded; a too-short real track fails assembly.

---

## Artifacts

`output/h3_chains/<run_name>/`

| Artifact | Per | Purpose |
|---|---|---|
| `<id>.mp4` | segment | rendered clip video |
| `<id>.prompt.txt` | segment | prompt text used for that clip |
| `<id>.json` | segment | checkpoint (prompt_hash, seed, steps, frame counts) |
| `<id>.safetensors` | segment | saved latent for context/continuation |
| `plan.json` | run | the plan as executed |
| `workflow.json` | run | graph snapshot |
| `api_prompt.json` | run | API-format submission |

---

## Architectural Consequence

The outer loop belongs in **Python, not in the graph**. Submit one scene at a time (`scene_range=k`). Between scenes you may freely:

- swap reference images,
- author or repair the next clip's prompt,
- reroll a seed,
- adjust `length` / `frames` for frame-exact timing,

—all without losing prior work, because the prefix checkpoint history is untouched. The graph's internal recursion is a convenience for unattended full-plan runs; the Python outer loop is the safe path for iterative authoring.
