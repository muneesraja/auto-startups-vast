---
name: vast-ai
description: Provision, monitor, and manage Vast.ai GPU servers autonomously. Uses a stable Docker image + bootstrap script approach (no fragile template hashes). Includes extended diagnostics, tmux background execution, and strict SSH-only remote execution.
---

# Vast.ai - GPU Server Provisioning

## ⚡ Provisioning — USE THE SCRIPT

When a user asks to "prepare a server", "rent a GPU", "set up a 3090/4090", or similar — **run the script. Do NOT follow manual steps.**

```bash
python3 ~/.hermes/skills/vast-ai/scripts/vastai-provision.py \
  --gpu <3090|4090> \
  --label <name> \
  [--workflow <script_name_or_alias>] \
  [--auto] [--dry-run] [--max-price 0.30] [--no-monitor]
```

**Examples:**
```bash
# Bare ComfyUI (no workflow)
python3 ~/.hermes/skills/vast-ai/scripts/vastai-provision.py --gpu 3090 --label mandi

# With workflow
python3 ~/.hermes/skills/vast-ai/scripts/vastai-provision.py --gpu 3090 --workflow prompt_relay_ltx23_test_02 --label mandi

# Auto-select best offer (no confirmation prompt)
python3 ~/.hermes/skills/vast-ai/scripts/vastai-provision.py --gpu 4090 --workflow wan22 --label balaji --auto

# Preview only (don't provision)
python3 ~/.hermes/skills/vast-ai/scripts/vastai-provision.py --gpu 3090 --workflow wan22 --label mandi --dry-run
```

**What the script does (no manual intervention needed):**
1. Loads GPU profile (specs, filters, skip countries like China)
2. Searches Vast.ai, filters bad offers, ranks by total cost
3. Shows top 5 offers (or auto-selects with `--auto`)
4. Provisions instance with correct env vars (HF token, webhook, workflow URL)
5. Monitors until running, reports SSH/portal URLs

**Workflow aliases** — use any of these interchangeably:
- `wan22`, `wan`, `wan 2.2`, `wanvideo` → wan22-download.sh
- `prompt_relay_ltx23_test_02`, `ltx23-prompt-relay` → prompt_relay_ltx23_test_02.sh
- `qwen`, `qwen-image` → qwen-image-download.sh
- `kijai-ltx2.3`, `ltx2.3-img2video`, etc.

---

## 🔧 Troubleshooting

Use these if the script fails or you need to debug an instance.

### Docker daemon failure (container stuck `loading`)
```bash
vastai logs <INSTANCE_ID> --daemon-logs
```
- `"No such container"` → Docker failure, destroy and try different host
- Image pull in progress → healthy, just wait
- Avoid hosts: 344939, 20325, 201023, 37070, 264182, 446098

### SSH not responding after `actual_status: running`
Wait 30-60 seconds — SSH daemon starts after container. Use `vastai ssh-url <ID>` (NOT raw `ssh_port` from JSON).

### Large file downloads (8GB+) — download on the server
Don't SCP through relay. SSH in and download directly:
```bash
ssh -p <port> -o StrictHostKeyChecking=no root@<ip> \
  "nohup curl -L '<url>' -o /workspace/ComfyUI/models/<path>/<file> --progress-bar > /workspace/download.log 2>&1 &"
```

### Zram (RAM boost on low-memory hosts)
See vault: `infrastructure/zram-notes.md`

---

## 📋 Manual Fallback (only if script fails)

If the script is broken or unavailable, follow these steps manually:

### 1. Search offers
```bash
vastai search offers 'gpu_name=RTX_<GPU> num_gpus=1 cpu_ram>=48 disk_space>=100 inet_down>=500 inet_up>=500 cpu_cores>=4 reliability>0.99 dph<=0.25 cuda_max_good>=12.7 driver_version>=560.0.0 rented=False' -o 'dph+' --limit 10
```

**Note:** `driver_version>=560.0.0` filters out hosts with old NVIDIA drivers that can't run CUDA 12.9.

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
