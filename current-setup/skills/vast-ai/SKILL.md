---
name: vast-ai
description: Provision, monitor, and manage Vast.ai GPU servers autonomously. Uses a stable Docker image + bootstrap script approach (no fragile template hashes). Includes extended diagnostics, tmux background execution, and strict SSH-only remote execution.
---

# Vast.ai — GPU Server Provisioning

## ⚡ Provisioning — USE THE SCRIPT

When a user asks to "prepare a server", "rent a GPU", "set up a 3090/4090", or similar — **run the script. Do NOT follow manual steps.**

```bash
python3 ~/.hermes/skills/vast-ai/scripts/vastai-provision.py \
  --gpu <3090|4090> \
  --label <name> \
  [--workflow <script_name_or_alias>] \
  [--auto] [--dry-run] [--max-price 0.30] [--no-monitor] [--no-frp]
```

**Examples:**
```bash
# Bare ComfyUI (no workflow)
python3 ~/.hermes/skills/vast-ai/scripts/vastai-provision.py --gpu 3090 --label mandi

# With workflow
python3 ~/.hermes/skills/vast-ai/scripts/vastai-provision.py --gpu 3090 --workflow wan22 --label mandi

# Auto-select best offer (no confirmation prompt)
python3 ~/.hermes/skills/vast-ai/scripts/vastai-provision.py --gpu 4090 --workflow wan22 --label balaji --auto


# No FRP tunnel (use Cloudflare quick tunnels)
python3 ~/.hermes/skills/vast-ai/scripts/vastai-provision.py --gpu 3090 --label mandi --no-frp

# Preview only (don't provision)
python3 ~/.hermes/skills/vast-ai/scripts/vastai-provision.py --gpu 3090 --label mandi --dry-run
```

**What the script does (no manual intervention needed):**
1. Loads `.env` secrets (HF_TOKEN, DISCORD_WEBHOOK_URL, FRP_TOKEN)
2. Loads GPU profile (specs, filters, skip countries like China)
3. Searches Vast.ai, filters bad offers, ranks by total cost
4. Shows top 5 offers (or auto-selects with `--auto`)
5. Provisions instance with correct env vars
6. Monitors until running, runs health check, reports SSH/portal URLs
7. Sends Discord notifications (Server Ready + Models Ready)

**⚠️ CRITICAL RULES (DO NOT BREAK):**
- **ALWAYS use `--auto`** — offers go stale within seconds on the competitive market. Never pause to ask the user between search and provision.
- **NEVER manually SSH in to fix tunnels, portals, or nginx** — if provisioning fails, destroy the instance and re-run the script. The script has retry logic (tries up to 5 hosts).
- **NEVER run the script multiple times simultaneously** — if the first attempt fails, wait for it to fully exit before re-running.
- **If the script fails 3+ times**, report the error to the user instead of improvising manual fixes.

**Flags:**

| Flag | Description |
|------|-------------|
| `--gpu` | GPU type: `3090` or `4090` (required) |
| `--label` | Instance label, lowercase no spaces (required) |
| `--workflow` | Workflow script name or alias (optional) |
| `--auto` | Auto-select best offer, no confirmation prompt |
| `--dry-run` | Search and show offers without provisioning |
| `--max-price` | Override max $/hr (default: from GPU profile) |
| `--verified-only` | Only show verified hosts (default: prefer unverified/cheaper) |
| `--no-frp` | Skip FRP tunnels, use Cloudflare quick tunnels |
| `--no-monitor` | Skip post-provision monitoring |
| `--slow` | Use image's built-in provisioner instead of fast-provision.sh |
| `--timeout` | Max seconds to wait for running status (default: 600) |

**Workflow aliases** — use any of these interchangeably:
- `wan22`, `wan`, `wan2.2`, `wanvideo` → wan-22-i2v-keyframe.sh
- `ltx-23-prompt-relay`, `ltx23-prompt-relay`, `prompt-relay` → ltx-23-prompt-relay.sh
- `ltx-23-i2v-keyframe`, `ltx23-keyframe` → ltx-23-i2v-keyframe.sh
- `ltx-23-i2v-distilled`, `ltx23-distilled` → ltx-23-i2v-distilled.sh
- `qwen`, `qwen-image`, `qwen-image-edit` → qwen-image-edit.sh

---

## 🔐 Secrets (.env)

All secrets are stored in `.env` at the project root (git-ignored). Copy from `.env.example`:

```bash
cp .env.example .env
# Then edit .env with your values
```

Required secrets:
- `HF_TOKEN` — HuggingFace token for fast model downloads
- `DISCORD_WEBHOOK_URL` — Discord webhook for notifications
- `FRP_TOKEN` — FRP tunnel auth token (optional if using `--no-frp`)

The script auto-loads `.env` and passes secrets as env vars to each Vast.ai instance.

---

## 🔧 Troubleshooting

Use these if the script fails or you need to debug an instance.

### Docker daemon failure (container stuck `loading`)
```bash
vastai logs <INSTANCE_ID> --daemon-logs
```
- `"No such container"` → Docker failure, destroy and try different host
- Image pull in progress → healthy, just wait

### SSH not responding after `actual_status: running`
Wait 30-60 seconds — SSH daemon starts after container. Use `vastai ssh-url <ID>` (NOT raw `ssh_port` from JSON).

### CUDA Error 804 (driver compatibility)
If instance fails with Error 804, the driver is too old for CUDA 12.9:
```bash
# Auto-fix for driver 570.x:
ssh -p <port> root@<ip> "rm -f /usr/local/cuda-12.9/compat/libcuda.so* && ldconfig"
```
Better: the script filters `driver_version>=570.0.0` to prevent this. Driver 580.x+ is preferred.

### Slow model downloads
- Check if host is in China (GFW throttles HuggingFace to ~1MB/s)
- Verify HF_TOKEN is set (anonymous downloads capped at ~10MB/s)
- See reference: `references/china-host-download-speed.md`

### Large file downloads (8GB+) — download on the server
Don't SCP through relay. SSH in and download directly:
```bash
ssh -p <port> -o StrictHostKeyChecking=no root@<ip> \
  "nohup curl -L '<url>' -o /workspace/ComfyUI/models/<path>/<file> --progress-bar > /workspace/download.log 2>&1 &"
```

---

## 📋 Manual Fallback (only if script fails)

If the script is broken or unavailable, follow these steps manually:

### 1. Search offers
```bash
vastai search offers 'gpu_name=RTX_<GPU> num_gpus=1 cpu_ram>=48 disk_space>=100 inet_down>=500 inet_up>=500 cpu_cores>=4 reliability>0.99 dph<=0.25 cuda_max_good>=12.8 driver_version>=570.0.0 rented=False' -o 'dph+' --limit 10

# For unverified (cheaper):
vastai search offers -n 'gpu_name=RTX_3090 num_gpus=1 verified=False reliability>0.90 driver_version>=570.0.0 rented=False dph<=0.20' -o 'dph+' --limit 10
```

**Note:** `driver_version>=570.0.0` filters out hosts with drivers that fail CUDA 12.9 (Error 804). Drivers 560.x-565.x have compat lib conflicts. Driver 580.x+ preferred (native CUDA 13.0).

### 2. Confirm with user
Present cheapest valid offer, ask permission to spend money. **DO NOT PROCEED WITHOUT YES.**

### 3. Provision
```bash
vastai create instance <OFFER_ID> \
  --image vastai/comfy:v0.20.1-cuda-12.9-py312 \
  --env '-p 8188:8188 -e COMFYUI_ARGS="--disable-auto-launch --port 18188 --enable-cors-header" -e PROVISIONING_SCRIPT="https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/comfyui-bootstrap.sh" -e DISCORD_WEBHOOK_URL="<WEBHOOK>" -e HF_TOKEN="<TOKEN>" -e WORKFLOW_SCRIPT="<URL>" -e PORTAL_CONFIG="localhost:1111:11111:/:Instance Portal|localhost:8188:18188:/:ComfyUI|localhost:8080:18080:/:Jupyter|localhost:8080:8080:/terminals/1:Jupyter Terminal" -e OPEN_BUTTON_PORT="1111" -e JUPYTER_DIR="/" -e DATA_DIRECTORY="/workspace/" -e OPEN_BUTTON_TOKEN="1"' \
  --disk 100 --label "<name>" --direct --ssh --jupyter --onstart-cmd 'entrypoint.sh'
```

### 4. Monitor
```bash
vastai show instance <ID> --raw  # Check every 30s until actual_status=running
```

### 5. Report
SSH: `vastai ssh-url <ID>` | Portal: `https://cloud.vast.ai/instances/<ID>`

---

## General Commands

**List instances:** `vastai show instances`
**Destroy instance:** Confirm first, then `vastai destroy instance <ID>`

---

## Available References

| File | When to use |
|------|-------------|
| `references/china-host-download-speed.md` | China host download slowdowns, HF CLI vs aria2c benchmarks, hf-mirror.com mitigation |
| `references/driver-version-requirements.md` | NVIDIA driver version filtering to avoid CUDA errors on old drivers |
| `references/vast-ai-instance-gotchas.md` | FRP port fixes, Jupyter HTTPS→HTTP, CUDA Error 804 workarounds |
