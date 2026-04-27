---
name: workflow-researcher
description: Parse ComfyUI workflow JSONs, extract all required models (UNET, CLIP, VAE, LoRA, checkpoints), research download URLs via HuggingFace CLI (never download!), and generate provisioning-ready bash scripts for $REPO_ROOT/scripts/workflows/.
---

# Workflow Researcher — ComfyUI Model Discovery & Script Generator

> Given a ComfyUI `workflow.json`, extract every model it needs, find the exact HuggingFace download URLs, and generate a `$REPO_ROOT/scripts/workflows/*.sh` download script — **without ever downloading any model files.**
>
> ⚠️ **CRITICAL SAFETY RULE:** Models are multi-GB files (8-40GB each). **NEVER run `hf download` without `--dry-run`.** NEVER download model files to the local system. This skill is purely for research and URL extraction.

## Prerequisites

- **`hf` CLI** (HuggingFace Hub CLI) must be installed: `pip install huggingface-hub[cli]`
  - Verify: `hf version` (tested with v1.4.1+)
- **`jq`** for JSON parsing (optional but recommended)
- Read the **vast-ai SKILL.md** before generating any script — scripts must be compatible with the provisioning pipeline

---

## Phase 1: Extract Models from Workflow JSON

> ⚠️ **ComfyUI workflows have TWO parallel node representations.** The `nodes[]` array uses `type` as the class field and stores widget values in `widgets_values`. The `extra.prompt` object uses `class_type` and `inputs`. **Always check BOTH** — `extra.prompt` may contain models not visible in the interactive nodes (e.g., vocoder checkpoints). The two representations can also describe completely different rendering paths.
>
> **Also check the `mode` field** — nodes with `"mode": 4` are collapsed/disabled in the UI. **Exclude them from the model manifest** unless explicitly told to include alternate paths.

### 1.1 Identify Loader Nodes

Scan every node in the workflow JSON. Each node has a `class_type` and `inputs` object. The following loader types contain model references:

| `class_type` | Input Field | Model Type | ComfyUI Models Subdirectory |
|---|---|---|---|
| `UNETLoader` | `unet_name` | Diffusion Model | `diffusion_models/` or `unet/` |
| `CLIPLoader` | `clip_name` | Text Encoder / CLIP | `text_encoders/` or `clip/` |
| `VAELoader` | `vae_name` | VAE | `vae/` |
| `LoraLoader` | `lora_name` | LoRA | `loras/` |
| `LoraLoaderModelOnly` | `lora_name` | LoRA | `loras/` |
| `CheckpointLoader` | `ckpt_name` | Checkpoint (all-in-one) | `checkpoints/` |
| `CheckpointLoaderSimple` | `ckpt_name` | Checkpoint (all-in-one) | `checkpoints/` |
| `DiffusionModelLoader` | `unet_name` | Diffusion Model | `diffusion_models/` |
| `DualCLIPLoader` | `clip_name1`, `clip_name2` | Text Encoders | `text_encoders/` |
| `TripleCLIPLoader` | `clip_name1`, `clip_name2`, `clip_name3` | Text Encoders | `text_encoders/` |
| `ControlNetLoader` | `control_net_name` | ControlNet | `controlnet/` |
| `StyleModelLoader` | `style_model_name` | Style/IP-Adapter | `style_models/` |
| `CLIPVisionLoader` | `clip_name` | CLIP Vision | `clip_vision/` |
| `UpscaleModelLoader` | `model_name` | Upscale Model | `upscale_models/` |
| `ImageOnlyCheckpointLoader` | `ckpt_name` | SVD/Image Checkpoint | `checkpoints/` |
| `UnetLoaderGGUF` | `unet_name` | Diffusion Model (GGUF) | `unet/` |
| `DualCLIPLoaderGGUF` | `clip_name1`, `clip_name2` | Text Encoders (GGUF) | `text_encoders/` |
| `VAELoaderKJ` | `vae_name` | VAE | `vae/` |
| `LTXVAudioVAELoader` | `ckpt_name` | Audio VAE / Vocoder | `vae/` or `checkpoints/` |
| `LTXVGemmaCLIPModelLoader` | `gemma_path`, `ltxv_path` | Gemma CLIP + Vocoder | `text_encoders/` |

### 1.2 Extract Unique Model Filenames

For each matching node, extract the model filename from the relevant input field. **Deduplicate** — many workflows reuse the same model across multiple nodes (e.g., a shared VAE used by 10 scenes).

### 1.3 Output a Model Manifest

Present the extracted models as a clear table:

```
Model Filename                                              | Type           | Loader Node
------------------------------------------------------------|----------------|-------------------
qwen_image_edit_2509_fp8_e4m3fn.safetensors                 | Diffusion      | UNETLoader
qwen_2.5_vl_7b_fp8_scaled.safetensors                      | Text Encoder   | CLIPLoader
qwen_image_vae.safetensors                                  | VAE            | VAELoader
Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors| LoRA           | LoraLoaderModelOnly
```

### 1.4 Detect Custom Nodes (Optional)

Some workflows use non-standard `class_type` values that require custom ComfyUI nodes. Common patterns:
- `FluxKontextImageScale` → may need a Flux-related custom node
- `TextEncodeQwenImageEditPlus` → Qwen-specific node
- `CFGNorm`, `ModelSamplingAuraFlow` → specialized sampling nodes

If custom nodes are detected, note them in the output but **do not block** — model download scripts don't need to install nodes (that's a separate concern, though some scripts like `ltx2-keyframing.sh` do include node installation).

---

## Phase 2: Research HuggingFace URLs

### ⚠️ Safety Rules

1. **NEVER** run `hf download` without `--dry-run`
2. **NEVER** use `--local-dir` or `--cache-dir` — those actually download
3. Always verify URLs resolve before adding to the script
4. Prefer `Comfy-Org` repos when available — they contain pre-split, ComfyUI-ready model files

### 2.1 Search for Model Repos

For each model filename, search HuggingFace to find the repository that hosts it:

```bash
hf models ls --search "<model keywords>" --limit 10
```

**Search strategy by model name:**
- Strip file extension (`.safetensors`, `.ckpt`, `.bin`)
- Strip quantization suffixes (`_fp8`, `_fp8_e4m3fn`, `_bf16`, `_fp4_mixed`)
- Use the core model name as search terms
- Also try the creator/org name if it's embedded in the filename

**Example:** For `qwen_image_edit_2509_fp8_e4m3fn.safetensors`:
```bash
hf models ls --search "qwen image edit" --limit 10
hf models ls --search "qwen image edit comfyui" --limit 5
```

**Prioritize repos in this order:**
1. `Comfy-Org/*` repos (pre-split for ComfyUI, most reliable)
2. Official model author repos (e.g., `Qwen/*`, `Lightricks/*`)
3. Community repos (e.g., `Kijai/*` — good for optimized variants)

### 2.2 Get Model Info & List Files

Once you find a candidate repo, get its details:

```bash
# Quick info
hf models info <org>/<repo>

# List all files (siblings = file listing)
hf models info <org>/<repo> --expand siblings
```

### 2.3 Dry-Run to See Files + Sizes

**This is the safest way to see all files and their sizes without downloading:**

```bash
hf download <org>/<repo> --dry-run
```

Example output:
```
[dry-run] Will download 16 files (out of 16) totalling 247.2G.
File                                                                     Bytes to download
------------------------------------------------------------------------ -----------------
split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors 20.4G
split_files/loras/Qwen-Image-Edit-2509-Anything2RealAlpha.safetensors    609.6M
...
```

**To check a specific file:**
```bash
hf download <org>/<repo> <path/to/file> --dry-run
```

### 2.5 Comfy-Org LTX Repo Naming Gotcha

The `Comfy-Org/ltx-2.3` repo **does not contain gemma text encoders**. The gemma fp4/fp8 text encoders for LTX video are in **`Comfy-Org/ltx-2`** (the v2 repo), not v2.3. If a dry-run returns no matching files for gemma, try `Comfy-Org/ltx-2` instead. Always verify with `curl -sI` HEAD request — 302 = valid redirect, 404 = wrong repo.

### 2.6 Extract the Exact Download URL

**Method 1 — Manual URL pattern (preferred, no debug needed):**

HuggingFace uses a deterministic URL pattern:
```
https://huggingface.co/{org}/{repo}/resolve/main/{filepath}
```

Where `{filepath}` is the `rfilename` from siblings or the path shown in dry-run.

**Examples:**
```
https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors
https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Lightning/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors
```

**Method 2 — Debug mode (shows full URL in output, use for verification):**
```bash
HF_DEBUG=1 hf download <org>/<repo> <filepath> --dry-run 2>&1 | grep "https://"
```

### 2.7 Verify Each URL

Before adding a URL to the script, verify it resolves (HEAD request, no download):

```bash
curl -sI -o /dev/null -w '%{http_code}' "https://huggingface.co/<org>/<repo>/resolve/main/<filepath>"
```

- `200` or `302` = ✅ valid
- `404` = ❌ wrong path/repo
- `401` = 🔒 gated model (needs auth token)

---

## Phase 3: Generate the Workflow Script

### 3.1 Script Template

Every script in `$REPO_ROOT/scripts/workflows/` MUST follow this exact pattern:

```bash
#!/bin/bash
# ---
# name: <Human-Readable Workflow Name>
# aliases: [<alias1>, <alias2>, <alias3>]
# description: <One-line description of what models this downloads>
# size: ~<estimated total download size>GB
# min_vram: <minimum VRAM required>GB
# ---
set -e

BASE_DIR="/workspace/ComfyUI/models"

echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/{<comma-separated subdirectories needed>}

echo "==> Checking aria2..."
if ! command -v aria2c &> /dev/null; then
    echo "aria2 not found, installing..."
    sudo apt update && sudo apt install -y aria2
else
    echo "aria2 already installed"
fi

echo "==> Starting downloads..."

# <Model Type Comment>
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/<subdirectory>" -o "<output_filename>" "<HuggingFace_URL>" &

# ... more downloads ...

wait
echo "==> All downloads completed!"

echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
```

### 3.2 Template Rules

1. **Frontmatter is REQUIRED** — The provisioning system uses it for discovery via GitHub API
2. **`aliases`** — Include the workflow name in various formats (lowercase, hyphenated, abbreviated)
3. **`size`** — Sum all model file sizes from the dry-run output. Use `~` prefix for approximation
4. **`min_vram`** — Usually `24GB` for most modern workflows (RTX 3090/4090)
5. **`set -e`** — Script MUST exit on error
6. **`BASE_DIR`** — Always `/workspace/ComfyUI/models`
7. **`mkdir -p`** — Create all needed subdirectories in one command. Only include directories that are actually used
8. **aria2 check** — Always include the apt-get install fallback
9. **Downloads** — Use `aria2c -x 16 -s 16 -k 1M` for maximum download speed
   - `-d` for output directory
   - `-o` for output filename (the filename ComfyUI expects, from the workflow JSON)
   - URL in quotes
   - `&` at the end for parallel downloads
10. **`wait`** — Always wait for all background downloads to finish
11. **Comments** — Add a comment above each download line indicating the model type

### 3.3 Directory Mapping

Map the model type to the correct ComfyUI subdirectory:

| Model Type | Directory |
|---|---|
| Checkpoint | `checkpoints/` |
| Diffusion Model / UNET | `diffusion_models/` or `unet/` (check existing scripts) |
| VAE | `vae/` |
| Text Encoder / CLIP | `text_encoders/` |
| LoRA | `loras/` |
| ControlNet | `controlnet/` |
| Upscale Model | `upscale_models/` or `latent_upscale_models/` |
| Style Model | `style_models/` |
| CLIP Vision | `clip_vision/` |

> **Note:** ComfyUI has evolved its directory naming. Some older workflows use `unet/` while newer ones use `diffusion_models/`. Some use `checkpoints/` as an alias for diffusion models. Check the existing `$REPO_ROOT/scripts/workflows/` scripts for precedent.

### 3.4 Filename Rules

The **output filename** (`-o` flag) MUST match exactly what the workflow JSON expects. This is the filename from the loader node's input field. Do NOT rename or modify it.

### 3.5 Custom Nodes (If Applicable)

If the workflow requires custom nodes (detected in Phase 1), add a section before downloads:

```bash
echo "==> Setting up ComfyUI nodes..."
cd /workspace/ComfyUI
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
fi
if command -v comfy &> /dev/null; then
    comfy node install <node_repo_url>
else
    echo "comfy-cli not found, cloning node repository manually..."
    cd custom_nodes
    git clone <node_repo_url> || true
    cd ..
fi
```

---

## Phase 4: Validation

Before finalizing the script, verify:

### 4.1 Completeness Check
- [ ] Every model from the Phase 1 manifest has a corresponding `aria2c` line
- [ ] No extra models were added that aren't in the workflow
- [ ] All directories referenced in `-d` flags are included in the `mkdir -p` line

### 4.2 URL Check
- [ ] Every URL follows the pattern `https://huggingface.co/{org}/{repo}/resolve/main/{filepath}`
- [ ] Every URL was verified with a HEAD request (200 or 302)
- [ ] No URLs point to gated models without noting auth requirements

### 4.3 Filename Check
- [ ] Every `-o` filename matches exactly what the workflow JSON expects
- [ ] No filename modifications, renaming, or path changes

### 4.4 Pattern Check
- [ ] Script has the correct frontmatter block
- [ ] Uses `set -e`
- [ ] Uses `BASE_DIR="/workspace/ComfyUI/models"`
- [ ] Has the aria2 check block
- [ ] All downloads use `aria2c -x 16 -s 16 -k 1M`
- [ ] All downloads end with `&` for parallel execution
- [ ] Has `wait` before the completion messages
- [ ] Ends with restart hint

### 4.5 Cross-Reference with Existing Scripts

Check if any models are already downloaded by other workflow scripts. Document shared models:
```bash
# Check for duplicate model filenames across existing scripts
grep -r "safetensors" "$REPO_ROOT/scripts/workflows/" | grep -o '\-o "[^"]*"'
```

---

## Phase 5: Commit & Push to Git

After the script is written to `scripts/workflows/` and passes all Phase 4 validation checks, commit and push it so the provisioning pipeline can access it via raw GitHub URL.

> The repository remote (`origin`) and SSH key for push access are already configured. No additional auth setup is needed.

### 5.1 Stage, Commit, and Push

```bash
git add scripts/workflows/<script-name>.sh
git commit -m "feat: add <workflow-name> workflow download script"
git push origin main
```

### 5.2 Commit Message Convention

Use this format:
- **New script:** `feat: add <workflow-name> workflow download script`
- **Update existing:** `fix: update <model-name> URL in <script-name>`
- **Multiple changes:** `feat: add <workflow-name> script and update <other-script>`

### 5.3 Verify the Raw URL

After pushing, the script is immediately available at:
```
https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/workflows/<script-name>.sh
```

This is the URL used in the `WORKFLOW_SCRIPT` env var during provisioning. Verify it resolves:
```bash
curl -sI -o /dev/null -w '%{http_code}' "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/workflows/<script-name>.sh"
```
- `200` = ✅ live and ready for provisioning

---

## Quick Reference: HF CLI Commands

### Repo Discovery (finding which repo hosts a model)
```bash
# Search repos by name/keywords — searches repo IDs, not file contents
hf models ls --search "<keywords>" --limit 10

# ⚠️ The command is `hf models ls` (NOT `hf models list`). The `list` subcommand does not exist.
```

### Repo Inspection (once you know the repo)
```bash
# Get repo metadata
hf models info <org>/<repo>

# List ALL files in a repo with sizes — USE THIS to explore what a repo contains
hf download <org>/<repo> --dry-run

# Filter the dry-run output to find a specific file
hf download <org>/<repo> --dry-run | grep "filename_you_want"

# List only specific files/directories in a repo (siblings = file listing)
hf models info <org>/<repo> --expand siblings
```

### File Verification (getting the exact URL and checking it resolves)
```bash
# Verify a URL resolves (HEAD request — no download)
# 200 = direct hit, 302 = valid redirect (HF redirects to CDN), 404 = wrong path/repo
curl -sI -o /dev/null -w '%{http_code}' "https://huggingface.co/<org>/<repo>/resolve/main/<filepath>"

# Dry-run for a specific file to see its size
hf download <org>/<repo> <filepath> --dry-run

# Debug mode — shows the full resolved URL (SAFE with --dry-run)
HF_DEBUG=1 hf download <org>/<repo> <filepath> --dry-run 2>&1 | grep "https://"
```

### URL Pattern (manual — no CLI needed)
```
https://huggingface.co/{org}/{repo}/resolve/main/{filepath}
```
Where `{filepath}` is the `rfilename` from siblings or the path shown in dry-run output.

### Common Pitfalls
- **`hf models ls --search`** searches **repo IDs/names**, not filenames inside repos. If you can't find a model by searching, use `hf download <repo> --dry-run` directly on the likely repo.
- **Comfy-Org LTX v2.3 vs v2:** `Comfy-Org/ltx-2.3` does NOT contain gemma text encoders. They are in **`Comfy-Org/ltx-2`** (the v2 repo). Always verify with `curl -sI`.
- **Disabled nodes:** Nodes with `"mode": 4` in the JSON are collapsed/disabled. Exclude them unless instructed otherwise.
- **extra.prompt section:** Some workflows store a completely different node graph in `extra.prompt`. This can describe alternate/active rendering paths with different models from the interactive `nodes[]` array. Always check both.

---

## Example: Full Walkthrough

Given `$REPO_ROOT/current-setup/comfyui-workflows/qwen_img_story_10scenes.json`:

### Step 1: Extract models
| Filename | Type | Loader |
|---|---|---|
| `qwen_image_edit_2509_fp8_e4m3fn.safetensors` | UNET | `UNETLoader` |
| `qwen_2.5_vl_7b_fp8_scaled.safetensors` | CLIP | `CLIPLoader` |
| `qwen_image_vae.safetensors` | VAE | `VAELoader` |
| `Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors` | LoRA | `LoraLoaderModelOnly` |

### Step 2: Research URLs
```bash
hf models ls --search "qwen image edit comfyui" --limit 5
# → Found: Comfy-Org/Qwen-Image-Edit_ComfyUI, Comfy-Org/Qwen-Image_ComfyUI

hf download Comfy-Org/Qwen-Image-Edit_ComfyUI --dry-run
# → split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors (20.4G)

hf download Comfy-Org/Qwen-Image_ComfyUI --dry-run
# → split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
# → split_files/vae/qwen_image_vae.safetensors

# LoRA is from a different repo:
hf models ls --search "qwen image lightning" --limit 5
# → lightx2v/Qwen-Image-Lightning
```

### Step 3: Result → `$REPO_ROOT/scripts/workflows/qwen-image-download.sh`
(See the existing script for the generated output)

---

## Base Path

All paths in this skill reference the repo root:
```
REPO_ROOT="/root/repos/auto-startups-vast"
```

## File Locations

| What | Where |
|---|---|
| Workflow JSONs (input) | `$REPO_ROOT/current-setup/comfyui-workflows/*.json` |
| Download scripts (output) | `$REPO_ROOT/scripts/workflows/*.sh` |
| This skill | `$REPO_ROOT/current-setup/skills/workflow-researcher/SKILL.md` |
| Provisioning skill | `$REPO_ROOT/current-setup/skills/vast-ai/SKILL.md` |
| Bootstrap script | `$REPO_ROOT/scripts/comfyui-bootstrap.sh` |
