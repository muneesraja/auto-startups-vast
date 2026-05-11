---
name: runpod-ai
description: Provision, monitor, and manage RunPod Community Cloud RTX 3090 pods with runpodctl. Includes a budget-conscious provisioning script, lifecycle commands, and troubleshooting notes for daily rent-and-destroy workflows.
---

# RunPod - Community Cloud GPU Pod Provisioning

## Provisioning - USE THE SCRIPT

When a user asks to "prepare a RunPod server", "rent a RunPod 3090", "set up a Community Cloud pod", or similar, run the script first. Use manual commands only if the script fails.

```bash
python3 ~/.hermes/skills/runpod-ai/scripts/runpod-provision.py \
  --gpu 3090 \
  --label <name> \
  [--workflow <script_name_or_alias>] \
  [--auto] [--dry-run] [--max-price 0.25] [--no-monitor] \
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

1. Verifies the GPU exists and is available on Community Cloud.
2. Lists Community Cloud datacenter candidates for RTX 3090.
3. Shows estimated hourly cost before provisioning.
4. Creates a pod with `--cloud-type COMMUNITY --public-ip`.
5. Sets env vars for `HF_TOKEN`, bootstrap URL, Discord webhook if present, and workflow URL.
6. Opens ports `8188/http,22/tcp,8080/http` and allocates a 50GB container disk.
7. Retries up to three datacenter candidates if provisioning fails.
8. Monitors until the pod reaches `RUNNING`, then reports SSH and web URLs.

Workflow aliases:

- `wan22`, `wan`, `wan 2.2`, `wanvideo` -> `wan22-download.sh`
- `prompt_relay_ltx23_test_02`, `ltx23-prompt-relay` -> `prompt_relay_ltx23_test_02.sh`
- `qwen`, `qwen-image` -> `qwen-image-download.sh`
- `kijai-ltx2.3`, `ltx2.3-img2video`, `ltx2-keyframing`, etc.

Default image:

```text
runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04
```

## GPU Profile

RTX 3090 Community Cloud:

- GPU ID: `NVIDIA GeForce RTX 3090`
- VRAM: 24GB
- Cloud type: `COMMUNITY`
- Public IP: required
- Estimated price target: about `$0.22/hr`; use `--max-price` to enforce a local cap.
- Default safety timers: set with `--stop-after` and `--terminate-after` when supported by the installed `runpodctl`.
- Default ports: `8188/http,22/tcp,8080/http`
- Default container disk: `50GB`
- Default persistent volume: `0GB`

Community Cloud availability is limited. If no RTX 3090 candidates appear, check later or consider a different GPU.

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
  --image runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04 \
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

## Available References

| File | When to use |
|------|-------------|
| `references/community-cloud-notes.md` | Community Cloud limitations, price expectations, and operational notes |
