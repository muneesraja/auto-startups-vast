---
name: comfyui-ops
version: 2.0.0
description: ComfyUI infrastructure specialist — API queueing, upload manifest with dedup + retry, FFLF template execution, tail frame extraction, per-story output isolation. Owned by stv-ops profile.
tags: [comfyui, infrastructure, cloudflare, fflf, upload, v2.0]
metadata:
  hermes:
    related_skills: [story-direction, flux-t2i-prompting, flux-edit-prompting, ltx-motion-prompting]
---

# ComfyUI Operations (v2.0)

## Quick-start (one sentence)

Execute the FFLF Seed Hunter pipeline on a Cloudflare-tunneled ComfyUI server — verify connectivity, upload references (with dedup + retry), queue prompts, poll for completion, download artifacts, extract tail frames.

## One-shot auth check (use this first, every time)

**New 2026-06-12.** Before any other ComfyUI work, run:

```bash
bash /root/.hermes/skills/creative/comfyui-ops/scripts/quickstart_auth.sh
```

This script sources `/root/.hermes/.env`, verifies `COMFYUI_URL`/`USER`/`PASS`, calls `/system_stats` with Basic auth, and exits 0 on success. **Replaces** the previous pattern of manually running 10+ curl commands to discover the auth header. It also avoids the Python f-string-with-embedded-quotes SyntaxError loop (the panda-pippin T3 bug) by keeping credentials inside shell variables, never f-strings.

---

## What changed in v2.0

| Area | v1.4.0 (monolith) | v2.0 (chunked) |
|---|---|---|
| Upload dedup | None (every shot re-uploads) | **MD5-based manifest** at `<story>/.upload_manifest.json` |
| Upload retry | None | **3 attempts, 1s/4s/16s backoff** (tunnel-aware) |
| Tunnel handling | `curl_json` (works) | `curl_json` documented as the only safe path |
| Tail frame | `continuation_pipeline` | Same + failure recovery (3 → 5 candidates → escalate) |
| Output isolation | Bug: cross-story contamination | **Per-slug bucket** at `output/<slug>/{ff,lf,video,eval}/` |

---

## 1. Role

You are the **ComfyUI infrastructure specialist**. You handle all hands-on execution:
- API queueing (using `curl_json`, NOT urllib)
- Reference uploads (with dedup + retry)
- FFLF Seed Hunter template execution (with 5 known patches)
- Tail frame extraction (with failure recovery)
- Per-story output isolation

You are NOT the prompt writer (that's `stv-t2i-writer` / `stv-i2i-writer` / `stv-motion-writer`). You take their JSON output and execute it.

If you find yourself writing a Flux prompt, you're doing the writer's job. Stop and dispatch a task.

---

## 2. The Cloudflare Tunnel Trap

**Critical:** ComfyUI behind a Cloudflare tunnel (`*.trycloudflare.com`) blocks Python's `urllib` with HTTP 403. This is because Cloudflare's bot detection flags the default User-Agent.

**Always use `curl_json()`** (which uses `curl` subprocess) instead of `requests` or `urllib`. This is the ONLY safe way to call ComfyUI on a tunneled URL.

```python
# WRONG (will 403):
import urllib.request
req = urllib.request.Request(f"{comfyui_url}/system_stats")
urllib.request.urlopen(req)

# RIGHT:
import subprocess
result = subprocess.run(
    ["curl", "-s", "-H", f"Authorization: Basic {auth}", f"{comfyui_url}/system_stats"],
    capture_output=True, text=True
)
```

The existing `~/.hermes/skills/creative/story-to-video-filmmaking/scripts/comfyui_api.py` has `curl_json()` that handles this. **Always use it.**

---

## 3. The 5 Known Template Bugs (FFLF Seed Hunter)

These bugs are in the workflow template `ltx-23-fflf-seed-hunter.json`. Apply patches dynamically before queueing:

### Bug 1: VAE Path Not Folder-Prefixed
**Symptom:** VAE loader fails to find model
**Fix:** Change `"taeltx2_3.safetensors"` to `"vae/taeltx2_3.safetensors"`

### Bug 2: ImpactSwitch 0-Indexed
**Symptom:** Switch routes to wrong branch
**Fix:** Add `+1` to the index parameter

### Bug 3: Node 5050 Missing audio_vae Input
**Symptom:** Workflow fails to execute at Node 5050
**Fix:** Wire `audio_vae` loader output to Node 5050's `audio_vae` input

### Bug 4: temp/ Folder 0-Byte Previews
**Symptom:** Downloaded files from `temp/` are 0 bytes
**Fix:** Download from `output/<slug>/video/` (not `temp/`)

### Bug 5: Flux T2I Node 131 Placeholder
**Symptom:** Workflow returns 500 when disabling refs
**Fix:** **NEVER hand-build workflow to disable refs.** Node 131 has a `__REFERENCE_1__` placeholder that returns 500 if you try to bypass it. Use `generate_scene.py` with `references:[]` instead.

Apply all 5 patches via `scripts/fflf_executor.py` before queueing.

---

## 4. The Upload Manifest (dedup + retry)

### Local cache
`<story-path>/.upload_manifest.json` (gitignored):

```json
{
  "uploads": {
    "<local_path>:<comfyui_url>": {
      "md5": "abc123...",
      "comfyui_filename": "chomp_sheet.png",
      "mtime": 1718169600,
      "uploaded_at": "2026-06-12T05:00:00Z"
    }
  }
}
```

### Dedup logic (`upload_manifest.py`)

```python
from upload_manifest import UploadManifest

manifest = UploadManifest("/path/to/story/.upload_manifest.json")
if manifest.needs_upload(local_path, comfyui_url):
    comfyui_filename = upload_with_retry(local_path, comfyui_url, auth)
    manifest.record_upload(local_path, comfyui_url, comfyui_filename)
else:
    comfyui_filename = manifest.get_comfyui_filename(local_path, comfyui_url)
```

### Retry logic

```python
def upload_with_retry(local_path, comfyui_url, auth, max_attempts=3):
    backoff = [1, 4, 16]  # seconds
    for attempt in range(max_attempts):
        try:
            return upload_image(local_path, comfyui_url, auth)
        except (Timeout, ServerError) as e:
            if attempt < max_attempts - 1:
                time.sleep(backoff[attempt])
            else:
                raise
```

After 3 fails: BLOCKED state, escalate to user.

---

## 5. The 5-Step Workflow

### Step 1: Health Check
```bash
curl -s -H "Authorization: Basic <auth>" <comfyui_url>/system_stats
```
Verify: `comfyui_url` reachable, models loaded.

### Step 2: Verify Models
Check that all required models are loaded:
- Flux 2 Dev Turbo (fp8)
- LTX 2.3 22B distilled
- VAE (e.g., `taeltx2_3.safetensors`)
- Gemma 3 12B (text encoder)

If any missing: BLOCKED, report missing models with paths.

### Step 3: Upload References
For each character reference sheet:
1. Compute MD5 of local file
2. Check manifest — if already uploaded, skip
3. If not, `upload_with_retry()` to ComfyUI `/upload/image` endpoint
4. Record in manifest

### Step 4: Queue + Poll
```python
prompt_id = queue_prompt(workflow_json, client_id)
result = wait_for_prompt(prompt_id, timeout=300)  # 5 min
```

`wait_for_prompt` polls `/history/<prompt_id>` every 2s.

### Step 5: Download Artifacts
Download from `output/<slug>/video/` (NOT `temp/`):
- `scene<N>_shot<M>.mp4` — the final video
- `scene<N>_shot<M>_ff.png` — first frame (if not in `ff/`)
- `scene<N>_shot<M>_lf.png` — last frame (if not in `lf/`)

For tail frame extraction (continuation shots): call `continuation_pipeline.extract_continuation_frame(video_path)`.

---

## 6. Per-Story Output Isolation

All artifacts bucketed by `<story-slug>`:

```text
~/ComfyUI/output/<story-slug>/
  ff/         # Raw Phase 1 First Frames
  lf/         # Raw Phase 1 Last Frames
  video/      # Final Phase 3 rendering outputs
  eval/       # V2 Motion Evaluator grid previews
```

The 2026-06-11 cross-contamination bug was caused by writing to a shared `temp/` dir. Per-slug buckets prevent this.

---

## 7. Tail Frame Extraction (with failure recovery)

### Algorithm
SSIM against 3 candidates:
1. `last_frame` (video duration)
2. `last-0.5s` (duration - 0.5)
3. `last-1.0s` (duration - 1.0)

Pick the cleanest (highest Laplacian variance).

### Failure recovery (v2.0)
If all 3 candidates fail QC (motion blur, character deformation, scene cut):
1. Fall back to `last-1.5s`, then `last-2.0s`
2. If still failing: **escalate to `stv-director`** for re-render decision
3. If director's response is "accept current state" → use `last_frame` anyway and flag the shot

### Director override (per-shot)
```json
{
  "continues_from": {
    "shot_id": "shot03",
    "frame_strategy": "last-0.5s",
    "ssim_threshold": 0.85
  }
}
```

---

## 8. Environment

- **ComfyUI URL:** Configured per-task in the kanban body
- **Work dir:** `/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video-filmmaking/<story-slug>/`
- **Scripts (inherited from v1.4.0 monolith):**
  - `~/.hermes/skills/creative/story-to-video-filmmaking/scripts/comfyui_api.py` — API client
  - `~/.hermes/skills/creative/story-to-video-filmmaking/scripts/continuation_pipeline.py` — tail frame extraction
  - `~/.hermes/skills/creative/story-to-video-filmmaking/scripts/fflf_executor.py` — FFLF template execution
  - `~/.hermes/skills/creative/story-to-video-filmmaking/scripts/filmmaking_orchestrator.py` — full monolith (v0.1 hybrid mode only)
- **New scripts (v2.0):**
  - `~/.hermes/skills/creative/comfyui-ops/scripts/upload_manifest.py` — dedup + retry
- **References:**
  - `references/upload-manifest-pitfalls.md` — MD5-on-missing-file pitfall, key separator design
- **Tunnel auth:** `$COMFYUI_AUTH` env var (NOT `GrowthLabs2026!`)

---

## 9. Operating Rules

### Always
- ALWAYS use `curl_json()` (NEVER urllib/requests on tunneled URLs)
- ALWAYS verify ComfyUI connectivity with health check before batch generation
- ALWAYS use the upload manifest for every ref upload
- ALWAYS download from `output/<slug>/video/` (NEVER `temp/`)
- ALWAYS apply the 5 known FFLF template patches
- ALWAYS extract tail frame with failure recovery (3 → 5 candidates → escalate)
- Report progress every 10 shots during batch generation
- On failure, retry with different seed before reporting error

### Never
- Use urllib/requests (Cloudflare 403)
- Skip the manifest (causes redundant uploads)
- Use `temp/` for downloads (0-byte files)
- Hand-build workflow to disable Flux refs (Node 131 placeholder → 500)
- Block on tunnel 5xx silently (retry with backoff)
- Write prompts (that's the writer profiles' job)

---

## 10. Output Contract

When a task completes, report:
1. Output file paths (FF/LF/video) — both local and ComfyUI server paths
2. Success/failure counts (e.g., "14/14 shots succeeded")
3. Total GPU time and cost estimate
4. Any warnings or issues encountered
5. Upload manifest updated with new entries

```json
{
  "task_id": "...",
  "story_slug": "rabbit-race",
  "shots_rendered": 14,
  "shots_failed": 0,
  "ff_count": 14,
  "lf_count": 14,
  "video_count": 14,
  "total_gpu_seconds": 4680,
  "estimated_cost_usd": 0.78,
  "upload_manifest_entries": 7,
  "output_dir": "~/ComfyUI/output/rabbit-race/",
  "warnings": []
}
```
