---
name: ltx23-video-gen
description: Generate videos using LTX 2.3 (text-to-video) on a RunPod ComfyUI pod via REST API. Covers workflow submission, monitoring, output retrieval, and audio merging.
tags: [video, ltx, comfyui, runpod, text-to-video]
---

# LTX 2.3 Video Generation via ComfyUI REST API

Generate short videos from text prompts using the LTX 2.3 model on a RunPod pod running ComfyUI with the `prompt_relay_ltx23_test_02` workflow.

## Prerequisites

- A running RunPod pod with ComfyUI + LTX 2.3 models installed (use `runpod-ai` skill to provision)
- ComfyUI listening on port 8188
- SSH access to the pod

### Quick Setup (if pod isn't running)

```bash
# Provision a pod with LTX 2.3 workflow pre-installed
python3 ~/.hermes/skills/runpod-ai/scripts/runpod-provision.py \
  --gpu 3090 --workflow prompt_relay_ltx23_test_02 --label mandi-ltx23

# Get SSH info
runpodctl ssh info <pod-id>
```

## Architecture

```
User Prompt → ComfyUI API (/prompt) → LTX 2.3 generates video → Output dir on Pod → SCP to local → ffmpeg merge → Share
```

**Key files on pod:**
- Workflow JSON: `/workspace/runpod-slim/ComfyUI/user/default/workflows/prompt_relay_ltx23_test_02.json`
- Output dir: `/workspace/runpod-slim/ComfyUI/output/`
- ComfyUI API: `http://localhost:8188` (local) or `https://<pod-id>-8188.runpod.app` (public)

## Step 1: Load the Workflow JSON

Fetch the workflow from the pod to build the API payload:

```bash
ssh <SSH_ARGS> "cat /workspace/runpod-slim/ComfyUI/user/default/workflows/prompt_relay_ltx23_test_02.json" > /tmp/ltx23_workflow.json
```

The workflow uses `PromptRelayEncodeTimeline` for multi-segment video generation. Key nodes to modify:
- **Node 607** (`PromptRelayEncodeTimeline`): Contains `global_prompt` and `local_prompts` — set these to your story
- **Node 266** (`LTXVSampler`): Controls `steps` (quality) and `seed` (variation)

## Step 2: Build the API Payload

Convert the workflow JSON to API format. The workflow stores nodes in `extra.prompt` (or as a flat object with class_type per node). Use a Python script to transform it:

```python
import json

with open("/tmp/ltx23_workflow.json") as f:
    workflow = json.load(f)

# Extract from extra.prompt if present, else use nodes array
if "extra" in workflow and "prompt" in workflow["extra"]:
    api_payload = {"prompt": workflow["extra"]["prompt"]}
else:
    # Convert nodes[] to {node_id: {class_type, inputs}} format
    api_payload = {"prompt": {}}
    for node in workflow.get("nodes", []):
        node_id = str(node["id"])
        api_payload["prompt"][node_id] = {
            "class_type": node["type"],
            "inputs": node.get("inputs", {})
        }

# Inject your story prompt into node 607 (PromptRelayEncodeTimeline)
prompt_node = api_payload["prompt"].get("607", {})
inputs = prompt_node.get("inputs", {})
inputs["global_prompt"] = "YOUR VIDEO PROMPT HERE"
inputs["local_prompts"] = [
    "Scene 1: The rabbit and tortoise agree to race",
    "Scene 2: The rabbit sprints ahead, tortoise plods steadily",
    "Scene 3: The rabbit naps under a tree",
    "Scene 4: The tortoise crosses the finish line, wins!"
]
prompt_node["inputs"] = inputs
api_payload["prompt"]["607"] = prompt_node

# Set seed for reproducibility (optional)
sampler = api_payload["prompt"].get("266", {})
if sampler:
    sampler["inputs"]["seed"] = 42  # Change for different variations
    api_payload["prompt"]["266"] = sampler

with open("/tmp/ltx23_payload.json", "w") as f:
    json.dump(api_payload, f)
```

### Important: Frontend-Only Nodes

The workflow contains `SetNode`/`GetNode`/`PrimitiveNode` nodes which are **frontend-only** (no `class_type`). These must be stripped before API submission. The `extra.prompt` section usually has the correct API-ready format.

## Step 3: Submit the Job

```bash
# Local (via SSH tunnel or direct)
curl -s -X POST http://localhost:8188/prompt \
  -H "Content-Type: application/json" \
  -d @/tmp/ltx23_payload.json

# Public (via RunPod proxy)
curl -s -X POST https://<pod-id>-8188.runpod.app/prompt \
  -H "Content-Type: application/json" \
  -d @/tmp/ltx23_payload.json
```

Response: `{"prompt_id": "<uuid>", "number": <queue_position>, ...}`

**Save the `prompt_id`** — you'll need it to check progress.

## Step 4: Monitor Progress

```bash
# Check queue status
curl -s http://localhost:8188/queue | jq .

# Check if your prompt_id is done (look in /history/<prompt_id>)
curl -s http://localhost:8188/history/<prompt_id> | jq .

# Watch the ComfyUI log for progress
ssh <SSH_ARGS> "tail -f /tmp/comfyui.log 2>/dev/null || journalctl -u comfyui -f"
```

Progress indicators in logs:
- `Using prompt relay mode` — prompt relay pipeline started
- `Processing segment 1/4` — video segments being generated
- `Encoded timeline` — prompt relay encoding complete
- `PromptRelayEncodeTimeline completed` — all segments done

**Typical generation time:** 5-15 minutes for a 20-second video (4 segments × ~50 frames each).

## Step 5: Download Output Files

Once complete, the output contains **two files**:
- `<filename>.mp4` — video only (no audio)
- `<filename>-audio.mp4` — audio only (LTX audio track)

```bash
# List output files
ssh <SSH_ARGS> "ls -lh /workspace/runpod-slim/ComfyUI/output/ltx23_*.mp4"

# Download both tracks
scp <SCP_ARGS> root@<pod-ip>:<port>:/workspace/runpod-slim/ComfyUI/output/<filename>.mp4 /tmp/video.mp4
scp <SCP_ARGS> root@<pod-ip>:<port>:/workspace/runpod-slim/ComfyUI/output/<filename>-audio.mp4 /tmp/audio.mp4
```

## Step 6: Merge Video + Audio

LTX 2.3 generates separate video and audio tracks. Merge them with ffmpeg:

```bash
ffmpeg -i /tmp/video.mp4 -i /tmp/audio.mp4 \
  -c:v copy -c:a aac -strict experimental \
  /tmp/final_video.mp4 -y
```

- `-c:v copy` — no re-encoding of video (fast, lossless)
- `-c:a aac` — encode audio to AAC (widely compatible)
- Output: video + audio in a single MP4

## Step 7: Share the Video

```bash
# Upload to tmpfiles.org (temporary, ~24h expiry)
curl -F "file=@/tmp/final_video.mp4" https://tmpfiles.org/api/v1/upload

# Response: {"status":"success","data":{"url":"http://tmpfiles.org/<id>/final_video.mp4"}}
# Direct download URL: https://tmpfiles.org/dl/<id>/final_video.mp4
```

## Quick Reference: Full Pipeline Script

```bash
#!/bin/bash
# ltx23-generate.sh — One-shot video generation
# Usage: ./ltx23-generate.sh "Your video prompt here" [pod_ip] [ssh_port]

PROMPT="${1:-A rabbit and tortoise racing in a magical forest}"
POD_IP="${2:-174.94.157.109}"
SSH_PORT="${3:-47388}"
SSH_KEY="/root/.runpod/ssh/RunPod-Key-Go"
SSH_ARGS="-i $SSH_KEY -o StrictHostKeyChecking=no -p $SSH_PORT root@$POD_IP"

echo "🎬 Generating video: $PROMPT"

# 1. Fetch workflow
ssh $SSH_ARGS "cat /workspace/runpod-slim/ComfyUI/user/default/workflows/prompt_relay_ltx23_test_02.json" > /tmp/ltx23_wf.json

# 2. Build payload (Python)
python3 -c "
import json, sys
with open('/tmp/ltx23_wf.json') as f:
    wf = json.load(f)
payload = wf.get('extra', {}).get('prompt', wf.get('nodes', []))
# Set prompt in node 607
if '607' in payload:
    payload['607']['inputs']['global_prompt'] = '''$PROMPT'''
with open('/tmp/ltx23_payload.json', 'w') as f:
    json.dump({'prompt': payload}, f)
print('Payload built')
"

# 3. Submit
RESPONSE=$(ssh $SSH_ARGS "curl -s -X POST http://localhost:8188/prompt -H 'Content-Type: application/json' -d @/tmp/ltx23_payload.json 2>/dev/null || cat /tmp/ltx23_payload.json | curl -s -X POST http://localhost:8188/prompt -H 'Content-Type: application/json' -d @-")
PROMPT_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('prompt_id',''))")
echo "📝 Prompt ID: $PROMPT_ID"

# 4. Wait for completion
echo "⏳ Waiting for generation..."
while true; do
  sleep 30
  STATUS=$(ssh $SSH_ARGS "curl -s http://localhost:8188/history/$PROMPT_ID 2>/dev/null")
  if echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('$PROMPT_ID') else 1)" 2>/dev/null; then
    echo "✅ Generation complete!"
    break
  fi
  echo "  Still generating... (checked at $(date +%H:%M:%S))"
done

# 5. Download
LATEST=$(ssh $SSH_ARGS "ls -t /workspace/runpod-slim/ComfyUI/output/ltx23_*.mp4 2>/dev/null | head -1")
BASENAME=$(basename "$LATEST" .mp4)
scp $SSH_ARGS root@$POD_IP:$SSH_PORT:$(dirname $LATEST)/${BASENAME}.mp4 /tmp/video.mp4
scp $SSH_ARGS root@$POD_IP:$SSH_PORT:$(dirname $LATEST)/${BASENAME}-audio.mp4 /tmp/audio.mp4

# 6. Merge
ffmpeg -i /tmp/video.mp4 -i /tmp/audio.mp4 -c:v copy -c:a aac -strict experimental /tmp/final_video.mp4 -y 2>/dev/null

# 7. Share
SHARE_URL=$(curl -s -F "file=@/tmp/final_video.mp4" https://tmpfiles.org/api/v1/upload | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['url'].replace('tmpfiles.org/','tmpfiles.org/dl/'))")
echo "🔗 Download: $SHARE_URL"
```

## Pitfalls

1. **Frontend-only nodes**: `SetNode`, `GetNode`, `PrimitiveNode` have no `class_type` — the API rejects them. Always use `extra.prompt` from the workflow JSON, not the `nodes[]` array.
2. **Pod restarts kill ComfyUI**: After a pod restart, ComfyUI doesn't auto-start. Run `cd /workspace/runpod-slim/ComfyUI && source .venv-cu128/bin/activate && python main.py --listen 0.0.0.0 --port 8188 >> /tmp/comfyui.log 2>&1 &` before submitting.
3. **Cloudflare Tunnel instability**: If using cloudflared for public access, it may exit (code 255) when the SSH session closes. Restart with `/tmp/cloudflared_bin tunnel --url http://localhost:8188 &`.
4. **Two output files**: LTX 2.3 generates video and audio separately. You MUST merge them with ffmpeg or the video will have no sound.
5. **Large files**: Generated videos are ~10-15MB. Use `scp` for reliable transfer; HTTP uploads to free services may fail.
6. **Generation time**: 5-15 minutes for a 20-second video. Don't poll too frequently — check every 30 seconds.

### SamplerCustom BrokenPipeError (CRITICAL)

When a long-running ComfyUI job is running and you run `pkill` or any command that terminates the SSH pipe while ComfyUI is writing to stderr, ComfyUI-Manager's Logger will try to write to `original_stderr.flush()` and get a **BrokenPipeError**. This corrupts the sampler state.

**Symptoms**: `SamplerCustom` node fails with `BrokenPipeError`, job stops, output files incomplete.

**Prevention**: NEVER run `pkill` on the pod while a job is executing. If you need to restart ComfyUI:
1. First check `/queue` — if `queue_running` has items, WAIT for completion.
2. Only restart when the queue is empty.
3. After killing ComfyUI process, always redirect stdout/stderr to a log file when restarting.

**Correct restart command** (redirects output to file, prevents BrokenPipeError):
```bash
ssh $SSH_ARGS "cd /workspace/runpod-slim/ComfyUI && source .venv-cu128/bin/activate && nohup python main.py --listen 0.0.0.0 --port 8188 --disable-auto-launch --front-end-version 0.1.0 >> /tmp/comfyui.log 2>&1 &"
```

### ComfyUI Startup — Virtual Environment

ComfyUI runs inside a Python virtual environment at `/workspace/runpod-slim/ComfyUI/.venv-cu128/`. The bare `python` command does NOT exist outside this environment.

```bash
# WRONG — will fail with "command not found"
ssh $SSH_ARGS "python main.py ..."

# CORRECT — activate venv first
ssh $SSH_ARGS "cd /workspace/runpod-slim/ComfyUI && source .venv-cu128/bin/activate && python main.py ..."
```

### Checking Job Status Correctly

The `/history/<prompt_id>` endpoint returns inconsistent structures. Use `/queue` instead:

```bash
# Check if job is still running
ssh $SSH_ARGS "curl -s http://localhost:8188/queue" | python3 -c "import sys,json; d=json.load(sys.stdin); print('Running:', len(d.get('queue_running',[])), 'Pending:', len(d.get('queue_pending',[])))"

# When Running=0 and Pending=0, job is done — then check /history
ssh $SSH_ARGS "curl -s http://localhost:8188/history/<prompt_id>"
```

The `/queue` endpoint returns the prompt_id inside the running array — use it to confirm your job is the one running.

### Reference Image for Image-to-Video

When using `LTXVImgToVideoInplaceKJ`:
1. Upload reference image to pod: `scp <SCP_ARGS> /local/image.png root@<pod-ip>:/workspace/runpod-slim/ComfyUI/input/`
2. In the API payload, `LoadImage` node (node 584) must have `"image": "<filename>"` (just the filename, no path)
3. Reference image should be in `/workspace/runpod-slim/ComfyUI/input/` on the pod

### ComfyUI Version and Ports

- ComfyUI version: `v0.18.2` (from template `cw3nka7d08`)
- Listens on: `0.0.0.0:8188` (not `127.0.0.1`)
- JupyterLab also runs on port 8888 (auto-started)
- Log file: `/tmp/comfyui.log` (when started with redirection)

### Pod SSH Behavior

- SSH can lag behind pod status — wait 30-90s after pod shows RUNNING before connecting
- SSH exit code 0 = connection successful (even if remote command has issues)
- ComfyUI process may survive SSH disconnect (backgrounded with nohup)
- Always verify with `/system_stats` after connecting

### Output Files Naming

The `VHS_VideoCombine` node's `filename_prefix` parameter determines the output filenames:
- Prefix `brave_farmer_60s` → outputs: `brave_farmer_60s.mp4`, `brave_farmer_60s-audio.mp4`
- Two separate files must be merged with ffmpeg

## Recent Learnings (May 11, 2026)

### Pod SSH Connection Details
- IP: `174.94.157.109`
- SSH port: `47388`
- Key: `/root/.runpod/ssh/RunPod-Key-Go`
- ComfyUI URL: `http://174.94.157.109:8188` (direct, no tunnel needed)
- Output path: `/workspace/runpod-slim/ComfyUI/output/`
- Workflow: `prompt_relay_ltx23_test_02.json`

### Workflow JSON Format Discovery
- The workflow JSON has a flat `nodes[]` array AND an `extra.prompt` dict
- `extra.prompt` is the API-ready format with node IDs as keys
- `nodes[]` array uses frontend-only format (has `PrimitiveNode` etc.)
- **Use `extra.prompt`** for API submission — `nodes[]` will cause `missing_node_type` errors

### Missing Node Type Fix
When the API returns `missing_node_type` for nodes like `LTXVGemmaCLIPModelLoader`:
- This means the `nodes[]` format was used instead of `extra.prompt`
- Always extract from `extra.prompt` dict for valid API submission
- The `nodes[]` array is frontend-display only, not API-compatible

### Job Completion Detection
- Log shows `Prompt executed in HH:MM:SS` when job finishes
- Latest output files are `ltx23_00011.mp4` and `ltx23_00011-audio.mp4` (10.5MB each, 19.5s duration)
- `ltx23_00011.png` is a thumbnail/preview frame

### Brave Farmer Video (ltx23_00011)
- Generated on: May 11, 2026 at 15:31
- Duration: ~19.5 seconds
- Video: 10.5MB | Audio: 10.8MB | Merged: 11MB
- Prompt: "A brave farmer..." (full prompt in previous session)
- Merged output: https://tmpfiles.org/dl/37596715/brave_farmer_final.mp4

### Video + Audio Merge Command
```bash
ffmpeg -i video.mp4 -i audio.mp4 \
  -c:v copy -c:a aac -strict experimental \
  /tmp/final_video.mp4 -y
```
