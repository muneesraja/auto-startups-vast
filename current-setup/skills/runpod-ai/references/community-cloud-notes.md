---
name: community-cloud-notes
description: Operational notes for RunPod Community Cloud RTX 3090 provisioning.
---

# RunPod Community Cloud Notes

## Scope

This skill targets short-lived RTX 3090 Community Cloud pods created with `runpodctl`.

The intended workflow is daily rent-and-destroy:

1. Provision the cheapest available Community Cloud 3090 candidate.
2. Run ComfyUI or workflow bootstrap tasks.
3. Stop or delete the pod when finished.

## Pricing

RTX 3090 Community Cloud is usually the budget option compared with Secure Cloud. The expected target price is about `$0.22/hr`, but exact prices and availability can change. Treat the script's price as a local estimate unless the installed `runpodctl` version returns price fields in `gpu list`, `datacenter list`, or pod details.

Use:

```bash
python3 ~/.hermes/skills/runpod-ai/scripts/runpod-provision.py --gpu 3090 --label test --dry-run
```

Use `--max-price` to prevent provisioning if the local estimated GPU profile exceeds the cap:

```bash
python3 ~/.hermes/skills/runpod-ai/scripts/runpod-provision.py --gpu 3090 --label test --auto --max-price 0.25
```

## Limitations

- Community Cloud requires `--cloud-type COMMUNITY --public-ip`.
- Availability is limited and stock changes quickly.
- Community hosts may have less predictable uptime than Secure Cloud.
- Host isolation and operational guarantees are weaker than Secure Cloud.
- RunPod has historically limited new Community Cloud host onboarding, so capacity can be thin.
- Datacenter availability from `runpodctl datacenter list` is a candidate signal, not a guaranteed reservation.
- SSH and HTTP endpoints can lag after the pod status changes to `RUNNING`.

## Recommended Defaults

- GPU: `NVIDIA GeForce RTX 3090`
- GPU count: `1`
- Image: `runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04`
- Ports: `8188/http,22/tcp,8080/http`
- Container disk: `50GB`
- Persistent volume: `0GB`
- Cloud type: `COMMUNITY`
- Public IP: enabled

## Cost Control

Always set a lifecycle timer when the installed CLI supports it:

```bash
--stop-after 4h --terminate-after 8h
```

If `runpodctl pod create --help` does not list those flags, the provisioning script will warn and omit them rather than failing before pod creation.

Delete disposable pods after use:

```bash
runpodctl pod delete <pod-id>
```

Check account state:

```bash
runpodctl user -o json
runpodctl pod list --all -o json
```

## Workflow Bootstrap Notes

The script passes these environment variables to the pod:

- `HF_TOKEN`
- `PROVISIONING_SCRIPT`
- `WORKFLOW_SCRIPT`
- `DISCORD_WEBHOOK_URL` if configured
- `COMFYUI_ARGS`
- `DATA_DIRECTORY`

The default RunPod PyTorch image may not automatically execute `PROVISIONING_SCRIPT`. If bootstrap does not start, SSH into the pod and run the bootstrap script manually, or create a RunPod template whose container start command consumes those env vars.
