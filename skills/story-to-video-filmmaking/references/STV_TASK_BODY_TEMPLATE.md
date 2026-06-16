# STV Task Body Template

This is the **mandatory** task body structure for any STV (story-to-video) orchestrator task. Any STV worker LLM (T2 through T13) that receives a task body should see all four sections below. If your task body is missing any of them, **do not start work** — flag it back to the orchestrator.

> **Origin:** Built 2026-06-12 after the panda-pippin T3 run burned 185 turns. Root causes: (1) agent discovered auth via 15 curl variants, (2) agent rebuilt a Python helper from scratch instead of using the existing `comfyui_api.py`, (3) agent hit a Python f-string-with-embedded-quotes SyntaxError and looped 80+ turns debugging it, (4) agent had no file-based success gate and continued working after success.

---

## Section 1: SETUP (mandatory, run FIRST)

```bash
# Load ComfyUI credentials from the central .env.
# Do NOT pass tokens inline — that causes the f-string-with-quotes bug
# (e.g. f"Authorization: Bearer ...\"y = \"ok\"").
set -a
. /root/.hermes/.env
set +a

# Verify the three required vars loaded.
for v in COMFYUI_URL COMFYUI_USER COMFYUI_PASS; do
  test -n "${!v:-}" || { echo "❌ $v missing from /root/.hermes/.env"; exit 1; }
done

# One-shot auth + connectivity check. Exits 0 on success.
bash /root/.hermes/skills/creative/comfyui-ops/scripts/quickstart_auth.sh || {
  echo "❌ Auth failed. Do NOT proceed — stop and report the error."
  exit 1
}
```

**STOP HERE if `quickstart_auth.sh` fails.** Do not debug curl by hand. The script already handles Cloudflare, Basic auth, and the trailing-slash 301 trap.

---

## Section 2: USE EXISTING HELPERS (do NOT rebuild)

The filmmaking skill ships battle-tested helpers. **Always import them — do not write your own.**

| What you need | Import from | Function |
|---|---|---|
| GET/POST to ComfyUI | `comfyui_api.py` | `curl_json(method, endpoint, url, auth=(user, pass), data=None)` |
| Poll a prompt until done | `comfyui_api.py` | `wait_for_prompt(prompt_id, url, auth=(user, pass))` |
| Download a still or video | `comfyui_api.py` | `download_output(filename, local_path, url, subfolder="", auth=(user, pass), is_video=False, file_type="output")` |
| Upload a reference image | `comfyui_api.py` | `upload_image(local_path, url, auth=(user, pass), subfolder="")` |
| Substitute __PROMPT__ / __SEED__ placeholders | `workflow_builder.py` | `WorkflowBuilder(workflow_json).with_prompt(p).with_seed(s).build()` |
| Apply FFLF template patches (5 known bugs) | `fflf_executor.py` | `apply_fflf_patches(workflow_path)` |
| Run the full pipeline (frames→videos) | `filmmaking_orchestrator.py` | `python3 filmmaking_orchestrator.py --prompts ... --url ... --auth user:pass --skip-existing` |
| Dedup + retry uploads | `upload_manifest.py` (in comfyui-ops) | `UploadManifest(<story>/.upload_manifest.json)` |

**Rule:** If you find yourself writing a `curl` command, stop and check if `curl_json()` already does it. If you find yourself writing a `requests.get`, stop. The whole point of this template is to keep you from writing the same code 100 times in different ways.

**Auth pattern (use exactly this, no f-string substitutions):**
```python
import sys
sys.path.insert(0, "/root/.hermes/skills/creative/story-to-video-filmmaking/scripts")
from comfyui_api import curl_json, wait_for_prompt, download_output, upload_image

AUTH = (os.environ["COMFYUI_USER"], os.environ["COMFYUI_PASS"])
URL = os.environ["COMFYUI_URL"]

# GET /object_info
info = curl_json("GET", "/object_info", URL, auth=AUTH)
# POST /prompt
resp = curl_json("POST", "/prompt", URL, auth=AUTH, data={"prompt": workflow})
# Poll
outputs = wait_for_prompt(resp["prompt_id"], URL, auth=AUTH)
# Download
ok = download_output("ComfyUI_00001_.png", "/tmp/out.png", URL, auth=AUTH)
```

---

## Section 3: SUCCESS CRITERIA (file-based, objective)

Replace the placeholders with the actual paths for this task. **The agent's only job is to make these files exist with the right minimum size. Nothing more.**

| Output | Min size | Required? |
|---|---|---|
| `<STORY>/characters/<char>_reference_sheet.png` | 100 KB | Yes (T3 only) |
| `<STORY>/scenes/<scene>/ff.png` | 50 KB | Per shot (T5) |
| `<STORY>/scenes/<scene>/lf.png` | 50 KB | Per shot (T5) |
| `<STORY>/output/<slug>/video/<scene>_<shot>.mp4` | 200 KB | Per shot (T11) |

Use the `done_check.sh` helper for the actual gate:

```bash
bash /root/.hermes/skills/creative/story-to-video-filmmaking/scripts/done_check.sh \
  100 \
  <STORY>/characters/pippin_reference_sheet.png \
  <STORY>/characters/bamboo_reference_sheet.png
```

`done_check.sh` exits 0 (DONE) or 1 (NOT DONE). Use the exit code as the task's success signal.

---

## Section 4: STOP CONDITION (the most important section)

**If `done_check.sh` exits 0, post your completion report and STOP. Do not iterate. Do not "verify" the files by re-rendering. Do not add enhancements. The work is done.**

Anti-patterns to avoid:
- ❌ "Let me just re-render once more to be safe."
- ❌ "Let me check the quality of the generated images."
- ❌ "Let me fix the small typo in the helper script."
- ❌ "Let me make one more improvement to the workflow."

These are all loops. The success gate is the file check. Once it passes, exit.

**If `done_check.sh` exits 1:** you have a real failure. Diagnose it (one tool call), fix it (one write), re-run. Do not the same tool 5 times in a row — that's the loop guardrail firing. Try a different angle.

---

## Worked Example: T3 (Character Sheets)

```markdown
## Task: T3 — Generate Pippin and Bamboo character reference sheets

### Setup
[Section 1 above]

### Helpers
- Use `curl_json()` from `comfyui_api.py` to POST `/prompt` with the workflow.
- Use `wait_for_prompt()` to poll for completion.
- Use `download_output()` to fetch the rendered PNG.
- Do NOT build your own curl commands with auth headers inline.

### Success criteria
`done_check.sh 100` must exit 0 for both:
- `<STORY>/characters/pippin_reference_sheet.png`
- `<STORY>/characters/bamboo_reference_sheet.png`

### Stop
When `done_check.sh` exits 0, post "T3 done" and exit. No further work.
```

That's a complete T3 body. ~150 tokens. Worker follows it linearly, exits in ~15-25 turns.
