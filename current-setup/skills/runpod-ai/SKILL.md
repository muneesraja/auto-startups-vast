---
name: runpod-ai
description: Provision, monitor, and manage RunPod Community Cloud RTX 3090 pods with runpodctl. Includes a budget-conscious provisioning script, lifecycle commands, remote workflow execution on existing pods, and troubleshooting notes for daily rent-and-destroy workflows.
---

# RunPod - Community Cloud GPU Pod Provisioning

## Repo Awareness

All workflow scripts live in the **`muneesraja/auto-startups-vast`** GitHub repo under `scripts/workflows/`. The provisioning script and this skill resolve friendly aliases to raw GitHub URLs. Workflow scripts are platform-aware — they detect RunPod vs Vast.ai and set `BASE_DIR` accordingly:

- **RunPod:** `/workspace/runpod-slim/ComfyUI/models`
- **Vast.ai:** `/workspace/ComfyUI/models`

The `~/.hermes/skills/runpod-ai` directory is a symlink to the repo at `~/repos/auto-startups-vast/current-setup/skills/runpod-ai`. Changes made via the Hermes skill path are reflected in the repo and vice versa.

## Provisioning - USE THE SCRIPT

When a user asks to "prepare a RunPod server", "rent a RunPod 3090", "set up a Community Cloud pod", or similar, run the script first. Use manual commands only if the script fails.

```bash
python3 ~/.hermes/skills/runpod-ai/scripts/runpod-provision.py \
  --gpu 3090 \
  --label <name> \
  [--workflow <script_name_or_alias>] \
  [--auto] [--dry-run] [--max-price 0.25] [--no-monitor] [--no-bootstrap] \
  [--stop-after 4h] [--terminate-after 8h]
```

Examples:

```bash
# Bare RunPod PyTorch pod
python3 ~/.hermes/skills/runpod-ai/scripts/runpod-provision.py --gpu 3090 --label mandi

# With workflow bootstrap env
python3 ~/.hermes/skills/runpod-ai/scripts/runpod-provision.py --gpu 3090 --workflow prompt_relay_ltx23_test_02 --label mandi

# Non-interactive cheapest Community Cloud candidate
python3 ~/.hermes/skills/runpod-ai/scripts/runpod-provision.py --gpu 3090 --workflow wan22 --label balaji --auto

# Preview availability and cost without provisioning
python3 ~/.hermes/skills/runpod-ai/scripts/runpod-provision.py --gpu 3090 --workflow qwen --label test --dry-run
```

What the script does:

1. **Validates** HF token format before provisioning (catches corrupted tokens early).
2. **Verifies** the GPU exists and is available on Community Cloud.
3. **Lists** Community Cloud datacenter candidates for RTX 3090.
4. **Shows** estimated hourly cost before provisioning.
5. **Creates** a pod with `--template-id cw3nka7d08` (ComfyUI pre-installed).
6. **Sets env vars** for `HF_TOKEN`, `WORKFLOW_SCRIPT`, `DISCORD_WEBHOOK_URL`.
7. **Opens ports** `8188/http,22/tcp,8080/http` and allocates 100GB container disk.
8. **Retries** up to three datacenter candidates if provisioning fails.
9. **Monitors** until the pod reaches `RUNNING`.
10. **Bootstraps via SSH** (unless `--no-bootstrap`):
    - Uploads env vars to `/root/.ssh/environment`
    - Uploads `hf_download.sh` helper script
    - Installs `hf` CLI and authenticates with HF token
    - Downloads workflow script from GitHub
    - Launches workflow in tmux session `workflow`

Default template:

```text
runpod/comfyui:latest (template ID: cw3nka7d08)
```

The provisioning script uses the RunPod ComfyUI template which comes with ComfyUI pre-installed. Workflow scripts auto-detect the platform and use the correct base directory:
- RunPod: `/workspace/runpod-slim/ComfyUI/models`
- Vast.ai: `/workspace/ComfyUI/models`

---

## Running Workflows on Existing Pods

When the user says "run this script on the instance" or "run flux-2-klein on pod jgcsq9hytybk5i", use the SSH execution method below. This works for **any** pod that's already running — no re-provisioning needed.

### Workflow Alias Registry

All workflow scripts come from `https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/workflows/`. Use the alias to resolve the filename:

| Alias(es) | Script File | Size | Min VRAM |
|---|---|---|---|
| `wan22`, `wan`, `wan 2.2`, `wanvideo` | `wan-22-i2v-keyframe.sh` | ~25GB | 24GB |
| `ltx-23-prompt-relay`, `ltx23-pr` | `ltx-23-prompt-relay.sh` | ~61.4GB | 24GB |
| `ltx-23-i2v-keyframe`, `ltx-keyframe` | `ltx-23-i2v-keyframe.sh` | ~60GB | 24GB |
| `ltx-23-i2v-distilled`, `ltx-distilled` | `ltx-23-i2v-distilled.sh` | ~35GB | 24GB |
| `ltx-23-i2v-official`, `ltx-official` | `ltx-23-i2v-official.sh` | ~47GB | 24GB |
| `qwen`, `qwen-image`, `qwen-image-edit` | `qwen-image-edit.sh` | varies | 24GB |
| `qwen-2511`, `qwen-image-edit-2511-4steps` | `qwen-image-edit-2511-4steps.sh` | ~31.4GB | 24GB |
| `hidream-o1`, `hidream-o1-dev-i2i`, `hidream` | `hidream-o1-dev-i2i.sh` | ~18.5GB | 24GB |
| `flux-2-klein`, `flux-klein`, `flux2-klein` | `flux-2-klein-image-edit.sh` | ~18.4GB | 24GB |
| `flux-2-dev-turbo`, `flux2-dev-turbo`, `flux-dev-turbo`, `flux2-turbo` | `flux-2-dev-turbo.sh` | ~51GB | 24GB |

**Note:** `flux-2-dev-turbo.sh` has enhanced automation:
- **Phase 0:** Auto-updates ComfyUI to latest version (git checkout + pip install)
- **Phase 3:** Auto-restarts ComfyUI after installing new custom nodes
- Smart Python detection from running process
- Health check wait loop after restart

You can also pass the exact filename (with or without `.sh`).

### Step-by-Step: Run a Workflow on an Existing Pod

**1. Get SSH connection info**

```bash
runpodctl ssh info <POD_ID>
```

This outputs JSON with `ip` and `port` fields. The SSH key is at `/root/.runpod/ssh/RunPod-Key-Go`.

**2. Upload the HF download helper**

```bash
SSH_KEY="/root/.runpod/ssh/RunPod-Key-Go"
curl -sSL "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/workflows/_hf_download.sh" | \
  ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p <PORT> root@<IP> "cat > /workspace/_hf_download.sh && chmod +x /workspace/_hf_download.sh"
```

**3. Download the workflow script onto the pod**

```bash
WF_URL="https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/workflows/<SCRIPT_FILE>"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p <PORT> root@<IP> \
  "curl -sSL '$WF_URL' -o /workspace/workflow-setup.sh && chmod +x /workspace/workflow-setup.sh"
```

**4. Run the workflow in tmux**

```bash
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -p <PORT> root@<IP> \
  "tmux kill-session -t workflow 2>/dev/null || true; \
   tmux new-session -d -s workflow 'export HF_TOKEN=\"<HF_TOKEN>\" && export HF_HUB_ENABLE_HF_TRANSFER=1 && bash /workspace/workflow-setup.sh 2>&1 | tee /workspace/workflow.log'"
```

**5. Monitor progress**

```bash
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -p <PORT> root@<IP> \
  "tail -20 /workspace/workflow.log"
```

Or check if the tmux session is still running:

```bash
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -p <PORT> root@<IP> \
  "tmux list-sessions 2>/dev/null && echo '--- Running ---' || echo '--- No sessions ---'"
```

**6. Quick one-liner (all steps combined)**

For convenience, here's a template that does steps 2-4 in one go:

```bash
POD_ID="<POD_ID>"
SSH_KEY="/root/.runpod/ssh/RunPod-Key-Go"
WORKFLOW="<alias_or_filename>"
HF_TOKEN="<HF_TOKEN>"

# Resolve alias to filename
case "$WORKFLOW" in
  wan22|wan|wan2.2|wanvideo) WF_FILE="wan-22-i2v-keyframe.sh" ;;
  ltx-23-prompt-relay|ltx23-pr) WF_FILE="ltx-23-prompt-relay.sh" ;;
  ltx-23-i2v-keyframe|ltx-keyframe) WF_FILE="ltx-23-i2v-keyframe.sh" ;;
  ltx-23-i2v-distilled|ltx-distilled) WF_FILE="ltx-23-i2v-distilled.sh" ;;
  ltx-23-i2v-official|ltx-official) WF_FILE="ltx-23-i2v-official.sh" ;;
  qwen|qwen-image|qwen-image-edit) WF_FILE="qwen-image-edit.sh" ;;
  qwen-2511|qwen-image-edit-2511-4steps) WF_FILE="qwen-image-edit-2511-4steps.sh" ;;
  hidream-o1|hidream-o1-dev-i2i|hidream) WF_FILE="hidream-o1-dev-i2i.sh" ;;
  flux-2-klein|flux-klein|flux2-klein) WF_FILE="flux-2-klein-image-edit.sh" ;;
  *) WF_FILE="${WORKFLOW%.sh}.sh" ;;
esac

WF_URL="https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/workflows/$WF_FILE"

# Get SSH info
SSH_INFO=$(runpodctl ssh info "$POD_ID" -o json)
IP=$(echo "$SSH_INFO" | jq -r '.ip // .host')
PORT=$(echo "$SSH_INFO" | jq -r '.port')

echo "📋 Pod: $POD_ID | IP: $IP | Port: $PORT | Workflow: $WF_FILE"

# Upload HF helper + download workflow + run in tmux
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p "$PORT" "root@$IP" "
  mkdir -p /root/config
  echo '{\"huggingface_token\": \"$HF_TOKEN\"}' > /root/config/token.json
  curl -sSL 'https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/workflows/_hf_download.sh' -o /workspace/_hf_download.sh
  chmod +x /workspace/_hf_download.sh
  curl -sSL '$WF_URL' -o /workspace/workflow-setup.sh
  chmod +x /workspace/workflow-setup.sh
  tmux kill-session -t workflow 2>/dev/null || true
  tmux new-session -d -s workflow 'export HF_TOKEN=\"$HF_TOKEN\" && export HF_HUB_ENABLE_HF_TRANSFER=1 && export BASE_DIR=/workspace/runpod-slim/ComfyUI/models && bash /workspace/workflow-setup.sh 2>&1 | tee /workspace/workflow.log'
  echo '✅ Workflow launched in tmux session: workflow'
  echo '📊 Monitor with: ssh -i $SSH_KEY -p $PORT root@$IP \"tail -20 /workspace/workflow.log\"'
"
```

### HF Token

The HF token is stored at `/root/config/token.json`:

```json
{
  "huggingface_token": "hf_...",
  "runpod_api_key": "rpa_...",
  "discord_webhook_url": "https://discord.com/api/webhooks/..."
}
```

It's also available as `HF_TOKEN` in `/root/.hermes/skills/runpod-ai/.env` (if symlinks are set up) and `/root/.hermes/skills/vast-ai/.env`.

### Troubleshooting Remote Workflow Execution

| Problem | Solution |
|---|---|
| `runpodctl ssh info` returns empty | Wait 30-60s after pod RUNNING; SSH can lag |
| `Permission denied (publickey)` | Verify the SSH key path: `ls -la /root/.runpod/ssh/RunPod-Key-Go` |
| `curl: command not found` on pod | Pod may still be bootstrapping; wait and retry |
| Workflow script fails with `hf_download: not found` | The `_hf_download.sh` helper wasn't uploaded properly — re-upload it |
| Downloads are slow (<10 MB/s) | Check `HF_TOKEN` is set — anonymous downloads are rate-limited |
| Models go to wrong directory | Verify `BASE_DIR` — RunPod uses `/workspace/runpod-slim/ComfyUI/models` |
| tmux session not found | The workflow finished (or crashed). Check `/workspace/workflow.log` for errors |

---

## GPU Requirements & Fallback Hierarchy

**Minimum spec for LTX 2.3 and video generation workflows:**
- VRAM: ≥20GB (RTX 3090 24GB is the baseline)
- Generation speed must match or exceed RTX 3090

**GPU Fallback Priority** (Community Cloud, ordered by price/performance):

| Priority | GPU ID | VRAM | Est. $/hr | Notes |
|----------|--------|------|-----------|-------|
| 1 | `NVIDIA GeForce RTX 3090` | 24GB | ~$0.22 | ✅ Primary — best price/performance |
| 2 | `NVIDIA GeForce RTX 3090 Ti` | 24GB | ~$0.25 | ✅ Acceptable fallback |
| 3 | `NVIDIA RTX A5000` | 24GB | ~$0.35 | ✅ Last resort on Community Cloud |

**GPUs to NEVER use for video workloads:**
- ❌ Tesla V100 16GB — only 16GB VRAM, too slow for LTX 2.3
- ❌ RTX A4000 — only 16GB VRAM
- ❌ RTX 3080/3080 Ti — 10-12GB VRAM
- ❌ RTX 4070 Ti — 12GB VRAM

**Cost ceiling: $0.25/hr max** on Community Cloud. Never fall back to Secure Cloud (2x+ price) without explicit user approval. If no Community Cloud GPU meeting the spec is available, **stop and ask the user** — do not auto-provision Secure Cloud or under-spec'd GPUs.

## Primary GPU Profile

RTX 3090 Community Cloud:

- GPU ID: `NVIDIA GeForce RTX 3090`
- VRAM: 24GB
- Cloud type: `COMMUNITY`
- Public IP: required
- Estimated price target: about `$0.22/hr`; use `--max-price` to enforce a local cap.
- Default safety timers: set with `--stop-after` and `--terminate-after` when supported by the installed `runpodctl`.
- Default ports: `8188/http,22/tcp,8080/http`
- Default container disk: `100GB`
- Default persistent volume: `0GB`

Community Cloud availability fluctuates. If no RTX 3090 is available, try fallback GPUs in priority order above. If none meet the ≥20GB VRAM / ≤$0.25/hr requirement, **wait and retry later** — do NOT fall back to Secure Cloud without user approval.

## Pod Lifecycle Commands

List pods:

```bash
runpodctl pod list
runpodctl pod list --all
```

Inspect a pod:

```bash
runpodctl pod get <pod-id> -o json
runpodctl pod get <pod-id> --include-machine -o json
runpodctl ssh info <pod-id>
```

Start, stop, restart, and delete:

```bash
runpodctl pod start <pod-id>
runpodctl pod stop <pod-id>
runpodctl pod restart <pod-id>
runpodctl pod delete <pod-id>
```

Discovery:

```bash
runpodctl gpu list -o json
runpodctl datacenter list -o json
runpodctl user -o json
```

Access URLs:

```text
ComfyUI: https://<pod-id>-8188.runpod.app
Jupyter: https://<pod-id>-8080.runpod.app
SSH:     runpodctl ssh info <pod-id>
```

If the `runpod.app` URL format fails, check `runpodctl pod get <pod-id> -o json` for the current endpoint fields.

## Manual Fallback

Use this only if the provisioning script is unavailable or broken.

1. Confirm availability:

```bash
runpodctl gpu list -o json
runpodctl datacenter list -o json
```

2. Create the pod:

```bash
runpodctl pod create \
  --name "<label>" \
  --template-id cw3nka7d08 \
  --gpu-id "NVIDIA GeForce RTX 3090" \
  --gpu-count 1 \
  --cloud-type COMMUNITY \
  --public-ip \
  --container-disk-in-gb 50 \
  --volume-in-gb 0 \
  --ports "8188/http,22/tcp,8080/http" \
  --env '{"HF_TOKEN":"<token>","PROVISIONING_SCRIPT":"https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/comfyui-bootstrap.sh","WORKFLOW_SCRIPT":"<workflow-url>"}'
```

Add `--data-center-ids <dc-id>` if targeting a specific datacenter. Add `--stop-after 4h` and `--terminate-after 8h` if your installed `runpodctl pod create --help` lists those flags.

3. Monitor:

```bash
runpodctl pod get <pod-id> -o json
runpodctl ssh info <pod-id>
```

4. Destroy when finished:

```bash
runpodctl pod delete <pod-id>
```

## Troubleshooting

No 3090 candidates:

```bash
runpodctl gpu list -o json
runpodctl datacenter list -o json
```

Community Cloud stock changes quickly. Wait and retry, or choose another GPU explicitly if acceptable.

Create fails with availability errors:

- Retry without `--data-center-ids` or use the script retry loop.
- Confirm the GPU ID is exactly `NVIDIA GeForce RTX 3090`.
- Confirm `--cloud-type COMMUNITY --public-ip` are present.

SSH missing or not ready:

```bash
runpodctl pod get <pod-id> -o json
runpodctl ssh info <pod-id>
```

Wait 30-90 seconds after the pod enters `RUNNING`; SSH can lag behind pod status.

Web URL does not open:

- Check the pod is `RUNNING`.
- Confirm the service inside the container is listening on the exposed port.
- Inspect `runpodctl pod get <pod-id> -o json` for endpoint or port fields.

Cost control:

- Prefer `--terminate-after` for disposable daily pods.
- Stop or delete pods immediately after use.
- Use `runpodctl user -o json` to check balance and current spend.

## Credentials

The provisioning script reads credentials from `/root/config/token.json`:

```json
{
  "huggingface_token": "hf_...",
  "runpod_api_key": "rpa_...",
  "discord_webhook_url": "https://discord.com/api/webhooks/..."
}
```

- `huggingface_token` — Required for authenticated HF downloads (faster, no rate limits)
- `runpod_api_key` — Required for RunPod API access
- `discord_webhook_url` — Optional; used for pod-ready notifications

Environment variables (`HF_TOKEN`, `RUNPOD_API_KEY`, `DISCORD_WEBHOOK_URL`) take precedence over config file values.

## Available References

| File | When to use |
|------|-------------|
| `references/community-cloud-notes.md` | Community Cloud limitations, price expectations, and operational notes |