---
name: workflow-researcher
description: Parse ComfyUI workflow JSONs, extract all required models (UNET, CLIP, VAE, LoRA, checkpoints) and custom node packs, research download URLs via HuggingFace CLI (never download!), and generate self-contained provisioning-ready bash scripts for $REPO_ROOT/workflows/setup/. Scripts must be platform-aware (Vast.ai + RunPod) and end with a ComfyUI restart.
---

# Workflow Researcher — ComfyUI Model & Node Discovery → Script Generator

> Given a ComfyUI `workflow.json`, extract every model + every custom node pack it needs, find the exact HuggingFace download URLs, and generate a `$REPO_ROOT/workflows/setup/*.sh` script — **without ever downloading any model files.**
>
> ⚠️ **CRITICAL SAFETY RULE:** Models are multi-GB files (8-40GB each). **NEVER run `hf download` without `--dry-run`.** NEVER download model files to the local system. This skill is purely for research and URL extraction.
>
> ⚠️ **Output is a self-contained "make this workflow work" script.** It must install all required custom node packs, install their pip deps into ComfyUI's own Python, download every model, and **restart ComfyUI at the end** so the new nodes register. Provisioning pipelines (Vast.ai, RunPod) call this script and expect a fully-ready ComfyUI on exit. See §3.5 for the policy.

## Prerequisites

- **`hf` CLI** (HuggingFace Hub CLI) must be installed: `pip install huggingface-hub[cli]`
  - Verify: `hf version` (tested with v1.4.1+)
- **`jq`** for JSON parsing (optional but recommended)
- Read the **vast-ai SKILL.md** before generating any script — the output runs on Vast.ai by default

## Quick Map

| Section | What it does |
|---|---|
| **§0 Naming conventions** | Filename + `workflow:` ID rules. Resolve contradictions upfront. |
| **§1 Model + node extraction** | Walk JSON (flat AND subgraphs), identify loaders + custom node packs. |
| **§2 HuggingFace URL research** | Find the right repo, verify URLs, handle the LTX / gemma gotchas. |
| **§3 Script generation** | The canonical template. Platform-aware, restart at end, idempotent helpers. |
| **§4 Validation** | Completeness, URL, filename, pattern checks. |
| **§5 Commit & push** | Get the script onto `main` so the provisioning pipeline can fetch it. |
| **§6 Reference walkthroughs** | `references/ltx-23-director.md` and `references/ltx-23-fflf-seed-hunter.md` — full worked examples. |

---

## §0. Workflow File Naming & Storage Conventions

Resolve these **before** writing any code — they determine file paths and frontmatter IDs.

### 0.1 Three identifiers per workflow

| Field | Source | Example |
|---|---|---|
| **Workflow JSON filename** | User's original file name — preserve exactly | `ltx23FFLFSeedHunter_v10.json` |
| **Script filename** | Canonical kebab-case derived from model family + version + variant | `ltx-23-fflf-seed-hunter.sh` |
| **Internal `workflow:` ID** | Stable machine-readable tag in the script's YAML frontmatter | `ltx23_FFLFSeedHunter_v10` |

### 0.2 Canonical naming convention

```
<model-family>-<version>-<variant>.json   ← ComfyUI workflow
<model-family>-<version>-<variant>.sh     ← download script
```

| Rule | Detail | Example |
|------|--------|---------|
| All lowercase, hyphen-separated | No underscores, no dots, no spaces | `ltx-23-i2v-keyframe` |
| Model family first | Short canonical name | `ltx`, `wan`, `qwen`, `flux` |
| Version next | No dots, no `v` prefix | `23` for 2.3, `22` for 2.2 |
| Variant/mode last | Describes the workflow type | `i2v`, `t2v`, `keyframe`, `prompt-relay`, `image-edit` |
| JSON and script share the same base | Always | `ltx-23-fflf-seed-hunter.json` ↔ `ltx-23-fflf-seed-hunter.sh` |
| Shared helper scripts prefixed with `_` | Not a workflow entry point | `_hf_download.sh` |

**Current canonical names in the repo** (always check for the most recent):

| Script | JSON | Description |
|--------|------|-------------|
| `ltx-23-i2v-distilled.sh` | `ltx-23-i2v-distilled.json` | LTX 2.3 distilled FP8 I2V |
| `ltx-23-i2v-keyframe.sh` | `ltx-23-i2v-keyframe.json` | LTX 2.3 first/last-frame keyframing |
| `ltx-23-prompt-relay.sh` | `ltx-23-prompt-relay.json` | LTX 2.3 PromptRelay multi-segment |
| `ltx-23-fflf-seed-hunter.sh` | `ltx23FFLFSeedHunter_v10.json` | LTX 2.3 FFLF Seed Hunter (FFLF = First/Last Frame) |
| `ltx-23-director-subgraphs.sh` | `ltx-23-director-subgraphs.json` | LTX 2.3 Director 2-stage subgraphs |
| `qwen-image-edit.sh` | `qwen-image-edit.json` | Qwen image editing |
| `qwen-image-edit-2511-4steps.sh` | `qwen-image-edit-2511-4steps.json` | Qwen image edit 25.11, 4-step Lightning |
| `wan-22-i2v-keyframe.sh` | *(no JSON yet)* | Wan 2.2 multi-keyframe I2V |

> ⚠️ **The JSON filename is preserved as-is from the user** — even if it doesn't match kebab-case (e.g. `ltx23FFLFSeedHunter_v10.json`). Only the **script** uses canonical kebab-case.

### 0.3 `workflow:` frontmatter ID

Derive the frontmatter `workflow:` field from the JSON filename (NOT the script name). This is the stable machine tag the provisioning pipeline uses.

```bash
# ---
# name: LTX 2.3 FFLF Seed Hunter
# workflow: ltx23_FFLFSeedHunter_v10   ← matches the JSON filename
# aliases: [ltx fflf, ltx 2.3 fflf, ltx23 fflf, ...]
# description: ...
# size: ~44.5GB
# min_vram: 24GB
# nodes: [ComfyUI-KJNodes, ComfyUI-LTXVideo, rgthree-comfy, ComfyUI-VideoHelperSuite, ComfyUI-Impact-Pack, cg-use-everywhere, ComfyUI-Easy-Use, ComfyUI-mxToolkit]
# node_patches: [ComfyUI-LTXVideo/kornia-pad (kornia 0.8.x compat, idempotent)]
# ---
```

The `nodes:` field is a hint for the agent generating the script — it lists all custom node packs the install section must cover. The `node_patches:` field is optional and lists any source patches the script applies (e.g. kornia compat).

### 0.4 Storage locations

| What | Where |
|---|---|
| Workflow JSONs (input) | `$REPO_ROOT/workflows/comfyui/*.json` |
| Download scripts (output) | `$REPO_ROOT/workflows/setup/<kebab-case>.sh` |
| Shared helper | `$REPO_ROOT/workflows/setup/_hf_download.sh` |
| This skill | `$REPO_ROOT/skills/workflow-researcher/SKILL.md` |
| Worked examples | `$REPO_ROOT/skills/workflow-researcher/references/` |
| Provisioning skill | `$REPO_ROOT/skills/vast-ai/SKILL.md` |

**Preserve the original JSON filename** — do not rename, slugify, or otherwise modify the name the user gave it. The internal `id` field inside the JSON (often a UUID) stays as-is.

---

## §1. Extract Models & Custom Nodes from Workflow JSON

> ⚠️ **ComfyUI workflows have THREE possible node representations:**
> 1. **Flat** — `nodes[]` array, each with `type` = class name.
> 2. **`extra.prompt`** — Alternate path inside `extra.prompt` keyed by node_id. May describe a different rendering branch.
> 3. **Subgraphs** — Top-level `nodes[]` may contain only UUID-typed "container" nodes; the real loaders live inside `definitions.subgraphs[].nodes[]`.
>
> **Always check all three.** For subgraphs, recurse. The two FFLF and Director reference walkthroughs in `references/` show what each format looks like in practice.

### 1.1 Detect the format

Run these three checks **first** — they'll save you a lot of time:

1. **Count top-level `nodes[]`.** If `<10` and any `type` is a UUID (e.g. `"739520a4-718f-490f-87d1-34ffbca98e3f"`), the workflow uses **subgraphs**.
2. **Check `extra.prompt`.** If present and non-empty, it may describe a different rendering branch. Compare its `class_type` values against `nodes[]` — if they overlap, treat as same graph; if they diverge, ask the user which branch to model.
3. **Grep every `properties.cnr_id`.** The distinct values map 1:1 to GitHub repos for the custom nodes (`comfyui-kjnodes` → `kijai/ComfyUI-KJNodes`, `whatdreamscost-comfyui` → `WhatDreamsCost/WhatDreamsCost-ComfyUI`, etc.). Don't rely on `class_type` alone — many packs use human-readable class names that look core-native.

### 1.2 Walk the JSON (works for flat, subgraphs, and `extra.prompt`)

```python
# Recursive walk — finds loaders anywhere in the tree
def walk(obj, results):
    if isinstance(obj, dict):
        if obj.get("type") in LOADER_TYPES and isinstance(obj.get("inputs"), list):
            results.append(obj)
        for v in obj.values():
            walk(v, results)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, results)
walk(data, loaders)  # finds loaders anywhere in the tree
```

For subgraph workflows, the walk hits loaders inside `definitions.subgraphs[*].nodes[]` automatically. For `extra.prompt`, the walk finds loaders there too. **One walk covers all three representations.**

### 1.3 Loader node table

Scan every node. Each node has a `class_type` (or `type`) and `inputs` object. Loaders contain model references:

| `class_type` | Input Field | Model Type | ComfyUI Subdirectory |
|---|---|---|---|
| `UNETLoader` | `unet_name` | Diffusion Model | `diffusion_models/` |
| `CLIPLoader` | `clip_name` | Text Encoder / CLIP | `text_encoders/` |
| `VAELoader` | `vae_name` | VAE | `vae/` |
| `LoraLoader` | `lora_name` | LoRA | `loras/` |
| `LoraLoaderModelOnly` | `lora_name` | LoRA | `loras/` |
| `CheckpointLoader` | `ckpt_name` | Checkpoint (all-in-one) | `checkpoints/` |
| `CheckpointLoaderSimple` | `ckpt_name` | Checkpoint (all-in-one) | `checkpoints/` |
| `DiffusionModelLoader` | `unet_name` | Diffusion Model | `diffusion_models/` |
| `DualCLIPLoader` | `clip_name1`, `clip_name2` | Text Encoders | `text_encoders/` |
| `TripleCLIPLoader` | `clip_name1/2/3` | Text Encoders | `text_encoders/` |
| `ControlNetLoader` | `control_net_name` | ControlNet | `controlnet/` |
| `StyleModelLoader` | `style_model_name` | Style/IP-Adapter | `style_models/` |
| `CLIPVisionLoader` | `clip_name` | CLIP Vision | `clip_vision/` |
| `UpscaleModelLoader` | `model_name` | Upscale Model | `upscale_models/` |
| `ImageOnlyCheckpointLoader` | `ckpt_name` | SVD/Image Checkpoint | `checkpoints/` |
| `UnetLoaderGGUF` | `unet_name` | Diffusion Model (GGUF) | `unet/` |
| `DualCLIPLoaderGGUF` | `clip_name1/2` | Text Encoders (GGUF) | `text_encoders/` |
| `VAELoaderKJ` | `vae_name` | VAE (KJNodes variant) | `vae/` |
| `LatentUpscaleModelLoader` | `model_name` | Latent Upscaler | `latent_upscale_models/` |
| `LTXVAudioVAELoader` | `ckpt_name` | Audio VAE / Vocoder | `vae/` |
| `LTXVGemmaCLIPModelLoader` | `gemma_path`, `ltxv_path` | Gemma CLIP + Vocoder | `text_encoders/` |
| `Power Lora Loader (rgthree)` | **nested dict in `widgets_values`** (see §1.5) | LoRA | `loras/` |

### 1.4 Extract the filename — `widgets_values[0]` is the model name

> ⚠️ **Most ComfyUI loaders store filenames in `widgets_values`, NOT `inputs`.** When `inputs` is empty or contains only link references (`[[node_id, output_idx]]`), the model filename is in `widgets_values[0]`. This applies to: `VAELoaderKJ`, `DualCLIPLoader`, `UNETLoader`, `LoraLoaderModelOnly`, `LTXVAudioVAELoader`, and most KJNodes loaders.

```python
wv = node.get("widgets_values", [])
if isinstance(wv, list) and len(wv) > 0:
    model_filename = wv[0]  # model name is always first
```

For `DualCLIPLoader`, the second text encoder is in `widgets_values[1]` (not in `inputs`).

**Deduplicate** — many workflows reuse the same model across multiple nodes (e.g. a shared VAE used by 10 scenes).

### 1.5 Power Lora Loader (rgthree) widget format — exception

`Power Lora Loader (rgthree)` stores its LoRAs inside a **list of dicts** in `widgets_values`, NOT a flat list of filenames:

```json
{
  "widgets_values": [
    {},
    {"type": "PowerLoraLoaderHeaderWidget"},
    {"on": true, "lora": "LTX2\\LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors", "strength": 2.0, "strengthTwo": null},
    {},
    ""
  ]
}
```

Extraction:

```python
for wv in node.get("widgets_values", []):
    if isinstance(wv, dict) and wv.get("on") and wv.get("lora"):
        lora_path = wv["lora"].split("\\")[-1]  # strip secondary-dir prefix
        # lora_path is now the bare filename, ready for HF lookup
```

The `\<dirname>` prefix is a "secondary directory" ComfyUI display quirk — it's NOT a real subdirectory. The actual HF file has no prefix. The `hf_download` helper saves the file as the bare basename under the target subdir, which is what the workflow widget expects.

### 1.6 Disabled nodes — exclude by default

Nodes with `"mode": 4` are collapsed/disabled in the UI. **Exclude them from the model manifest** unless explicitly told to include alternate paths.

### 1.7 Custom node pack detection — don't rely on `class_type` alone

> ⚠️ **Custom node detection by `class_type` is unreliable.** A `*KJ` suffix suggests KJNodes, but many other packs (rgthree, mxToolkit, WhatDreamsCost) use human-readable class names that look core-native. The `properties.cnr_id` field on every node is the authoritative source.

| Pack | `cnr_id` value | Signature class_types (fallback) |
|---|---|---|
| `kijai/ComfyUI-KJNodes` | `comfyui-kjnodes` | `*KJ`, `LTX2SamplingPreviewOverride`, `PatchSageAttentionKJ` |
| `Lightricks/ComfyUI-LTXVideo` | `comfyui-ltxvideo` (or no `cnr_id` for core LTX nodes) | `LTXV*` (AddGuide, Conditioning, ConcatAVLatent, etc.) |
| `WhatDreamsCost/WhatDreamsCost-ComfyUI` | `whatdreamscost-comfyui` | `LTXDirector`, `LTXDirectorGuide`, `LTXSequencer`, `LTXKeyframer` |
| `rgthree/rgthree-comfy` | `rgthree-comfy` | `Any Switch (rgthree)`, `Fast Groups Bypasser (rgthree)`, `Power Lora Loader (rgthree)` |
| `chrisgoringe/cg-use-everywhere` | `cg-use-everywhere` | `Anything Everywhere` |
| `yolain/ComfyUI-Easy-Use` | `comfyui-easy-use` | `easy seed`, `easy showLoaderSettingsNames` |
| `Smirnov75/ComfyUI-mxToolkit` | `comfyui-mxtoolkit` | `mxSlider`, `mxSeed`, `mxReroute` |
| `Kosinkadink/ComfyUI-VideoHelperSuite` | `comfyui-videohelpersuite` | `VHS_*` |
| `ltdrdata/ComfyUI-Impact-Pack` | `comfyui-impact-pack` | `ImpactSwitch`, `SAMLoader`, `UltralyticsDetectorProvider` |

`MarkdownNote` / FAQ nodes often include "Where do I download these models??" sections from the workflow author — read these for source-repo hints and one-off variants that aren't obvious from filenames alone.

### 1.8 Output — model manifest + node manifest

Present as a table:

```
Model Filename                                              | Type           | Loader Node
------------------------------------------------------------|----------------|-------------------
qwen_image_edit_2509_fp8_e4m3fn.safetensors                 | Diffusion      | UNETLoader
qwen_2.5_vl_7b_fp8_scaled.safetensors                      | Text Encoder   | CLIPLoader
qwen_image_vae.safetensors                                  | VAE            | VAELoader
Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors| LoRA           | LoraLoaderModelOnly

Custom node packs required: 3
  - kijai/ComfyUI-KJNodes
  - Lightricks/ComfyUI-LTXVideo
  - rgthree/rgthree-comfy
```

---

## §2. Research HuggingFace URLs

### 2.1 Safety rules

1. **NEVER** run `hf download` without `--dry-run`
2. **NEVER** use `--local-dir` or `--cache-dir` — those actually download
3. Always verify URLs resolve before adding to the script (`curl -sI` HEAD request)
4. Prefer `Comfy-Org/*` repos when available — pre-split, ComfyUI-ready

### 2.2 Search for model repos

For each filename, find the repo that hosts it:

```bash
hf models ls --search "<model keywords>" --limit 10
```

**Search strategy:**
- Strip file extension (`.safetensors`, `.ckpt`, `.bin`)
- Strip quantization suffixes (`_fp8`, `_fp8_e4m3fn`, `_bf16`, `_fp4_mixed`)
- Use the core model name as search terms

**Priority order:**
1. `Comfy-Org/*` repos (pre-split, most reliable)
2. Official model author repos (`Qwen/*`, `Lightricks/*`, `Kijai/*`)
3. Community repos (`Kijai/*`, `GitMylo/*`)

> ⚠️ **`hf models ls --search` searches repo IDs/names, not filenames inside repos.** If a search returns nothing useful, skip the search and go directly to the most likely repo + `hf download <repo> --dry-run` to see the file listing.

### 2.3 Inspect a repo (without downloading)

```bash
# Quick info
hf models info <org>/<repo>

# List ALL files in a repo with sizes — USE THIS to explore what a repo contains
hf download <org>/<repo> --dry-run

# Filter dry-run to a specific file
hf download <org>/<repo> --dry-run | grep "filename_you_want"

# Siblings (file listing only)
hf models info <org>/<repo> --expand siblings
```

### 2.4 Construct the exact URL

**Manual URL pattern (preferred):**

```
https://huggingface.co/{org}/{repo}/resolve/main/{filepath}
```

Where `{filepath}` is the `rfilename` from siblings or the path shown in dry-run. Example: `split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors`.

**Debug mode (use with `--dry-run` for safety):**

```bash
HF_DEBUG=1 hf download <org>/<repo> <filepath> --dry-run 2>&1 | grep "https://"
```

### 2.5 Verify each URL (no download)

```bash
curl -sI -o /dev/null -w '%{http_code}' "https://huggingface.co/<org>/<repo>/resolve/main/<filepath>"
```

- `200` or `302` = ✅ valid
- `404` = ❌ wrong path/repo
- `401` = 🔒 gated model (needs auth token)

### 2.6 LTX / gemma gotchas (high-frequency)

These are the most common traps. Read once, avoid 30 minutes of debugging.

**`Comfy-Org/ltx-2.3` vs `Comfy-Org/ltx-2`:**
- `Comfy-Org/ltx-2.3` does NOT contain gemma text encoders.
- They are in **`Comfy-Org/ltx-2`** (the v2 repo).
- In `Comfy-Org/ltx-2`, gemma files live under **`split_files/text_encoders/`** prefix (e.g. `split_files/text_encoders/gemma_3_12B_it.safetensors`).

**`Kijai/LTX2.3_comfy` vs `Lightricks/LTX-2.3`:**
- `Kijai/LTX2.3_comfy` has VAEs, diffusion models, text projections, and some LoRAs — all with ComfyUI-friendly paths (`vae/`, `diffusion_models/`).
- LoRA variants differ. Kijai has dynamic fro9 rank variants; the official `Lightricks/LTX-2.3` has different LoRAs (e.g. `ltx-2.3-22b-distilled-lora-384-1.1.safetensors`). If a LoRA isn't in Kijai's repo, search `Lightricks/LTX-2.3` directly.
- `Kijai/LTX2.3_comfy` does NOT have gemma text encoders — those come from `Comfy-Org/ltx-2` or community quantizations.

**`Lightricks/LTX-2.3-fp8` is a SEPARATE repo from `Lightricks/LTX-2.3`:**
- The LTX 2.3 FP8 transformer files (`ltx-2.3-22b-dev-fp8.safetensors`, `ltx-2.3-22b-distilled-fp8.safetensors`) live at `https://huggingface.co/Lightricks/LTX-2.3-fp8/...` — NOT in `Lightricks/LTX-2.3`.
- The latter only has full bf16 checkpoints and Lightricks-named LoRAs.
- When a widget references `ltx-2.3-22b-dev-fp8.safetensors` (no `transformer_only` suffix), it's expected to land in `checkpoints/` for use with `CheckpointLoaderSimple` — download from `Lightricks/LTX-2.3-fp8`.

**`gemma_3_12B_it_fp8_e4m3fn.safetensors` is a COMMUNITY quantization, not in `Comfy-Org/ltx-2`:**
- `Comfy-Org/ltx-2` only ships `gemma_3_12B_it.safetensors` (24.4G bf16), `gemma_3_12B_it_fp8_scaled.safetensors` (13.2G fp8 scaled), `gemma_3_12B_it_fp4_mixed.safetensors` (9.4G fp4 mixed).
- The `fp8_e4m3fn` variant is a community build at `GitMylo/LTX-2-comfy_gemma_fp8_e4m3fn` — file lives at the repo root (no `split_files/` prefix), ~13.2GB. Public, ungated.
- This is the variant the LTX 2.3 FFLF Seed Hunter, LTX-2 text2vid, and most post-2026 LTX workflows use.

---

## §3. Generate the Workflow Script

> ⚠️ **Output policy (Munees, 2026-06-08):** The download script is the **single self-contained entry point** that makes a ComfyUI instance ready to run the workflow. It must:
> 1. Detect the platform (Vast.ai vs RunPod) for `BASE_DIR`
> 2. Detect the ComfyUI Python interpreter (`/venv/main/bin/python3` on Vast, `venv/bin/python3` on RunPod, system as fallback)
> 3. Install all required custom node packs (via `comfy-cli` with `git clone` fallback)
> 4. Install pip deps for each pack **into ComfyUI's own Python** (not system Python)
> 5. Apply any known patches (e.g. kornia-0.8.x compat for ComfyUI-LTXVideo) — idempotent
> 6. Download all models sequentially via `hf_download`
> 7. **Restart ComfyUI at the end** via `supervisorctl` (Vast) with manual fallback (RunPod)
>
> The older guidance ("scripts only download models, the bootstrap installs nodes") is **deprecated**. Don't generate model-only scripts anymore.

### 3.1 Canonical script template

```bash
#!/bin/bash
# ---
# name: <Human-Readable Workflow Name>
# workflow: <matches JSON filename>
# aliases: [<alias1>, <alias2>, <alias3>]
# description: <One-line description of what models this downloads and which nodes it installs>
# size: ~<estimated total download size>GB
# min_vram: <minimum VRAM required>GB
# nodes: [<pack1>, <pack2>, ...]                ← custom node packs the install section covers
# node_patches: [<pack>/<patch-name> <desc>]    ← optional, source patches applied
# ---
set -e

# ─── Platform-aware base directory detection (Vast.ai vs RunPod) ───
if [ -d "/workspace/runpod-slim/ComfyUI" ]; then
  BASE_DIR="/workspace/runpod-slim/ComfyUI/models"
  COMFYUI_DIR="/workspace/runpod-slim/ComfyUI"
  echo "  Platform: RunPod (base: $BASE_DIR)"
elif [ -d "/workspace/ComfyUI" ]; then
  BASE_DIR="/workspace/ComfyUI/models"
  COMFYUI_DIR="/workspace/ComfyUI"
  echo "  Platform: Vast.ai (base: $BASE_DIR)"
else
  BASE_DIR="/workspace/ComfyUI/models"
  COMFYUI_DIR="/workspace/ComfyUI"
  echo "  ⚠️  No ComfyUI dir found, defaulting to $BASE_DIR"
fi

CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"

echo "==> Setting up ComfyUI nodes..."
cd "$COMFYUI_DIR"

# ─── ComfyUI Python detection ───
COMFY_PYTHON=""
COMFY_PIP=""
if [ -f /venv/main/bin/python3 ]; then
    COMFY_PYTHON="/venv/main/bin/python3"
    COMFY_PIP="/venv/main/bin/pip"
elif [ -f venv/bin/activate ]; then
    source venv/bin/activate
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$(which pip)"
elif [ -f .venv-cu128/bin/activate ]; then
    source .venv-cu128/bin/activate
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$(which pip)"
else
    COMFY_PYTHON="$(which python3)"
    COMFY_PIP="$(which pip)"
fi
echo "  Using ComfyUI Python: $COMFY_PYTHON"

# ─── Custom node install (comfy-cli first, manual fallback) ───
# List every pack the workflow requires here, derived from §1.7.
if command -v comfy &> /dev/null; then
    echo "  Using comfy-cli to install nodes..."
    comfy node install https://github.com/<org>/<pack1>
    comfy node install https://github.com/<org>/<pack2>
    # ... one per pack
else
    echo "  comfy-cli not found, cloning node repositories manually..."
    mkdir -p "$CUSTOM_NODES_DIR"
    cd "$CUSTOM_NODES_DIR"
    [ -d <pack1-dir> ]    || git clone https://github.com/<org>/<pack1>     || true
    [ -d <pack2-dir> ]    || git clone https://github.com/<org>/<pack2>     || true
    # ... one per pack
    cd "$COMFYUI_DIR"
fi

# ─── Known-patch block (idempotent, document every patch) ───
# Example: kornia 0.8.x dropped the `pad` re-export required by ComfyUI-LTXVideo.
# See: https://github.com/Lightricks/ComfyUI-LTXVideo/issues/505
# This block must be idempotent — re-running on an already-patched file is a no-op.
PATCH_FILE="$CUSTOM_NODES_DIR/<pack>/<file.py>"
if [ -f "$PATCH_FILE" ] && grep -q "<marker-for-original-import>" "$PATCH_FILE"; then
    if grep -q "<marker-for-patched-state>" "$PATCH_FILE"; then
        echo "  <pack> patch already applied"
    else
        echo "  Patching <pack> <file.py>..."
        sed -i 's|<original>|<patched>|' "$PATCH_FILE"
    fi
fi

# ─── Pip deps for each pack into ComfyUI's Python ───
echo "==> Installing node dependencies..."
for repo in <pack1-dir> <pack2-dir> ...; do
    REQ="$CUSTOM_NODES_DIR/$repo/requirements.txt"
    if [ -f "$REQ" ]; then
        echo "  Installing $repo deps..."
        $COMFY_PIP install -q -r "$REQ" 2>&1 | tail -3 || true
    fi
done

# ─── Model directory creation ───
echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/{<subdir1>,<subdir2>,...}   # only dirs that are actually used

# ─── Load shared HF download helper (auto-fetch if missing) ───
# All workflow scripts self-fetch _hf_download.sh from GitHub if not present locally.
# The Vast.ai ComfyUI image does not bundle it.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_HF_HELPER=""
for f in "$SCRIPT_DIR/_hf_download.sh" "/workspace/_hf_download.sh" "/tmp/_hf_download.sh"; do
  [ -f "$f" ] && _HF_HELPER="$f" && break
done
if [ -z "$_HF_HELPER" ]; then
  echo "  Fetching _hf_download.sh from GitHub..."
  GITHUB_BASE="https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/workflows/setup"
  _HF_HELPER="/tmp/_hf_download.sh"
  if ! curl -sSL --fail "$GITHUB_BASE/_hf_download.sh" -o "$_HF_HELPER" 2>/dev/null; then
    curl -sSL --fail "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/workflows/setup/_hf_download.sh" -o "$_HF_HELPER" \
      || { echo "❌ FATAL: could not download _hf_download.sh"; exit 1; }
  fi
  chmod +x "$_HF_HELPER"
fi
source "$_HF_HELPER"
unset _HF_HELPER

# ─── Downloads ───
echo "==> Starting downloads..."

# <Model Type Comment>
echo "[1/N] <Model Name>..."
hf_download "<org>/<repo>" "<filepath>" "$BASE_DIR/<subdir>"

# ... one per model ...

echo "==> All downloads completed!"

# ─── Restart ComfyUI so new nodes + models are picked up ───
echo "==> Restarting ComfyUI..."
if command -v supervisorctl &> /dev/null; then
    supervisorctl restart comfyui 2>/dev/null \
        && echo "✅ ComfyUI restarted via supervisorctl" \
        || echo "⚠️  supervisorctl failed — restart ComfyUI manually"
elif [ -f /etc/supervisor/supervisord.conf ]; then
    supervisord -c /etc/supervisor/supervisord.conf 2>/dev/null \
        && echo "✅ ComfyUI supervisor started" \
        || echo "⚠️  supervisord failed — restart ComfyUI manually"
else
    echo "⚠️  No supervisor found — restart ComfyUI manually"
    echo "    Run: cd $COMFYUI_DIR && $COMFY_PYTHON main.py --listen 0.0.0.0 --port 8188 &"
fi

echo "==> Done!"
echo "👉 ComfyUI should now be loading the new nodes and models."
```

### 3.2 Template rules

1. **YAML frontmatter is REQUIRED** — `name`, `workflow:`, `aliases:`, `description:`, `size:`, `min_vram:`, `nodes:`, optional `node_patches:`.
2. **`workflow:`** — matches the JSON filename, used as the stable machine ID.
3. **`aliases:`** — kebab-case + space-separated variants (lowercase, hyphenated, abbreviated).
4. **`size:`** — sum all model file sizes from dry-run, use `~` prefix.
5. **`min_vram:`** — usually `24GB` for modern video workflows (RTX 3090/4090).
6. **`nodes:`** — complete list of custom node packs the install section will clone. **No partial installs** — if the workflow uses nodes from 8 packs, list all 8.
7. **`set -e`** — fail fast.
8. **Platform-aware `BASE_DIR` block** — mandatory, see template.
9. **ComfyUI Python detection** — `/venv/main/bin/python3` (Vast) > `venv/bin/python3` (RunPod slimmer) > `.venv-cu128/bin/activate` (RunPod CUDA 12.8) > system.
10. **`mkdir -p`** — only include subdirs actually used.
11. **HF download helper** — sources `_hf_download.sh` (underscore prefix). Self-fetches from GitHub if not present locally.
12. **Downloads** — `hf_download "<org>/<repo>" "<filepath>" "$BASE_DIR/<subdir>"`. Sequential (hf_transfer is fast enough). Progress echoes `[N/Total]`.
13. **Custom node install** — `comfy node install` first, manual `git clone` fallback to `custom_nodes/`. List **every** pack the workflow needs (see §1.7).
14. **Pip deps** — install per-pack `requirements.txt` into **ComfyUI's Python** (`$COMFY_PIP`), not system Python.
15. **Patch block** — idempotent. Document every patch with a comment + a marker grep so re-runs are no-ops. Reference the upstream issue.
16. **ComfyUI restart** — `supervisorctl restart comfyui` (Vast) with manual fallback. **Mandatory** — without it, new nodes don't register until the next reboot.

### 3.3 Directory mapping

| Model Type | Directory |
|---|---|
| Checkpoint | `checkpoints/` |
| Diffusion Model / UNET | `diffusion_models/` (or `unet/` for older workflows) |
| VAE | `vae/` |
| Text Encoder / CLIP | `text_encoders/` |
| LoRA | `loras/` |
| ControlNet | `controlnet/` |
| Upscale Model | `upscale_models/` (or `latent_upscale_models/` for latent upscalers) |
| Style Model | `style_models/` |
| CLIP Vision | `clip_vision/` |

> ComfyUI directory naming has evolved. Some older workflows use `unet/` while newer ones use `diffusion_models/`. Some use `checkpoints/` as an alias for diffusion models. **Check the existing scripts in `$REPO_ROOT/workflows/setup/` for precedent** when unsure.

### 3.4 Filename rules

The **output filename** must match exactly what the workflow JSON's loader node expects. The filename comes from the loader node's input field (or `widgets_values[0]`). Do NOT rename, lowercase, or modify it.

---

## §4. Validation

Before finalizing the script:

### 4.1 Completeness
- [ ] Every model from §1.8 manifest has a corresponding `hf_download` line
- [ ] No extra models added that aren't in the workflow
- [ ] All directories referenced are included in the `mkdir -p` line
- [ ] Every custom node pack from §1.8 is listed in the `nodes:` frontmatter AND cloned in the install section

### 4.2 URL check
- [ ] Every URL follows `https://huggingface.co/{org}/{repo}/resolve/main/{filepath}`
- [ ] Every URL was verified with `curl -sI` (200 or 302)
- [ ] No URLs point to gated models without noting auth requirements

### 4.3 Filename check
- [ ] Every filename matches exactly what the workflow JSON expects
- [ ] No filename modifications or path renames
- [ ] For `DualCLIPLoader`, `widgets_values[0]` = clip_name1, `widgets_values[1]` = clip_name2
- [ ] For `Power Lora Loader (rgthree)`, secondary-dir `\<dirname>` prefix is stripped before HF lookup

### 4.4 Pattern check
- [ ] YAML frontmatter has all required fields
- [ ] `set -e` present
- [ ] Platform-aware `BASE_DIR` block present
- [ ] ComfyUI Python detection block present
- [ ] Custom node install covers **all** packs in `nodes:`
- [ ] `_hf_download.sh` sourced (underscore prefix)
- [ ] All downloads use `hf_download "<org>/<repo>" "<filepath>" "$BASE_DIR/<subdir>"`
- [ ] Progress echoes `[N/Total]` present
- [ ] ComfyUI restart at end (`supervisorctl` with fallback)

### 4.5 Cross-reference with existing scripts

```bash
# Check for duplicate model filenames across existing scripts
grep -r "hf_download" "$REPO_ROOT/workflows/setup/" | grep -o '"[^"]*\.safetensors\|"[^"]*\.gguf"'
```

Document any shared models so the next script author knows they can skip the download.

### 4.6 Bash syntax check

```bash
bash -n "$REPO_ROOT/workflows/setup/<new-script>.sh"
```

### 4.7 Worktree-isolation check (subgraph workflows)

If the workflow uses subgraphs (§1.1 detection), **all** loaders must be inside the extracted manifest — not just the top-level `nodes[]`. Verify by counting: the union of all `type` values matching the loader table should equal the manifest size.

---

## §5. Commit & Push

After the script passes all §4 validation checks, commit and push to `main`. The provisioning pipeline fetches scripts from `raw.githubusercontent.com`.

### 5.1 Commit and push

```bash
cd $REPO_ROOT
git add workflows/setup/<new-script>.sh
git commit -m "feat: add <workflow-name> workflow download + node install script"
git push origin main
```

### 5.2 Commit message convention

- **New script:** `feat: add <workflow-name> workflow download + node install script`
- **Update existing:** `fix: update <model-name> URL in <script-name>`
- **Multiple changes:** `feat: add <workflow-name> script and update <other-script>`

### 5.3 Verify the raw URL

```bash
curl -sI -o /dev/null -w '%{http_code}' \
  "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/workflows/setup/<script-name>.sh"
```

`200` = ✅ live and ready for provisioning. This is the URL the provisioning pipeline uses in the `WORKFLOW_SCRIPT` env var.

---

## §6. Reference Walkthroughs

End-to-end worked examples for the two most common workflow shapes. Read these before generating a new script — they'll save you the discovery work.

| Reference | Use when |
|---|---|
| [`references/ltx-23-director.md`](references/ltx-23-director.md) | Canonical pattern. LTX 2.3 with 3 custom node packs, subgraphs, `LoraLoaderModelOnly` with `\<dirname>` prefix, `cnr_id`-based pack detection. |
| [`references/ltx-23-fflf-seed-hunter.md`](references/ltx-23-fflf-seed-hunter.md) | **All loaders inside a subgraph**, **Power Lora Loader (rgthree)** nested-dict widget, **7-pack custom node install** (`rgthree` + `Impact` + `VHS` + `mxSlider` etc. in addition to KJNodes/LTXVideo), `GitMylo/LTX-2-comfy_gemma_fp8_e4m3fn` source. |

---

## §7. Quick Reference — HF CLI Commands

### Repo discovery
```bash
hf models ls --search "<keywords>" --limit 10
# ⚠️ The command is `hf models ls` (NOT `hf models list`). `list` does not exist.
```

### Repo inspection
```bash
hf models info <org>/<repo>
hf download <org>/<repo> --dry-run
hf download <org>/<repo> --dry-run | grep "filename_you_want"
hf models info <org>/<repo> --expand siblings
```

### File verification (no download)
```bash
# HEAD request — 200/302 = valid, 404 = wrong path, 401 = gated
curl -sI -o /dev/null -w '%{http_code}' "https://huggingface.co/<org>/<repo>/resolve/main/<filepath>"

# Dry-run for a specific file
hf download <org>/<repo> <filepath> --dry-run

# Debug mode (SAFE with --dry-run)
HF_DEBUG=1 hf download <org>/<repo> <filepath> --dry-run 2>&1 | grep "https://"
```

### URL pattern
```
https://huggingface.co/{org}/{repo}/resolve/main/{filepath}
```

---

## §8. Common Pitfalls — Cheat Sheet

| Pitfall | Resolution |
|---|---|
| `hf models ls --search` returns nothing | It searches repo IDs, not filenames. Try `hf download <likely-repo> --dry-run` directly. |
| `Comfy-Org/ltx-2.3` has no gemma | Try `Comfy-Org/ltx-2` (v2 repo) or `GitMylo/LTX-2-comfy_gemma_fp8_e4m3fn` (community fp8_e4m3fn). |
| `Lightricks/LTX-2.3-fp8` 404 | It's a SEPARATE repo from `Lightricks/LTX-2.3`. The latter only has bf16. |
| `LoraLoaderModelOnly` filename has `ltx2\` prefix | Secondary-dir display quirk. Strip the prefix before HF lookup. |
| `Power Lora Loader (rgthree)` uses dicts in `widgets_values` | See §1.5 — nested `{on, lora, strength}` schema. |
| `mode: 4` nodes still in the manifest | Exclude them — they're disabled in the UI. |
| Top-level `nodes[]` has <10 UUID-typed nodes | Workflow uses subgraphs. Recurse into `definitions.subgraphs[].nodes[]`. |
| `cnr_id` is the right pack detection signal | Many packs use human-readable class names that look core-native. Always grep `properties.cnr_id`. |
| Script installs nodes but ComfyUI doesn't see them | Missing restart. End the script with `supervisorctl restart comfyui`. |
| `hf_download: command not found` (EXIT=127) | The shared `_hf_download.sh` helper isn't present. The auto-fetch block in §3.1 fixes this — make sure it's in the script. |
| LTX-Video kornia import fails on Vast | Vast base image ships kornia 0.8.x, which dropped the `pad` re-export. Apply the kornia-pad patch in §3.1. |
| File lands in `$BASE_DIR/diffusion_models/diffusion_models/<file>` (double-nested) | The `hf_download` helper uses `hf_hub_download(local_dir=...)` which **preserves the filename's directory prefix**. If you pre-create `$BASE_DIR/diffusion_models/` AND pass `filename="diffusion_models/<file>.safetensors"`, the file lands in the doubled path. **Fix:** pass `local_dir="$BASE_DIR"` (not `$BASE_DIR/<subdir>`) and let the helper create the subdir from the filename prefix. See `ideogram-4-t2i.sh` for the corrected pattern. Discovered 2026-06-13 when Comfy-Org/Ideogram-4 files nested incorrectly on instance 40800182. |

---

## Base Path

All paths in this skill reference the repo root:

```
REPO_ROOT="/root/repos/auto-startups-vast"
```
