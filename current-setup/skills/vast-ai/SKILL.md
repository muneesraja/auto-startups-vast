---
name: vast-ai
description: Provision, monitor, and manage Vast.ai GPU servers autonomously. Uses a stable Docker image + bootstrap script approach (no fragile template hashes). Includes extended diagnostics, tmux background execution, and strict SSH-only remote execution.
---

# Vast.ai - GPU Server Provisioning

> Provision GPU servers on Vast.ai for ML/AI workloads. Use this whenever the user needs a GPU server (training, inference, etc.).
>
> **⚠️ Avoid these hosts — Docker daemon issues (containers fail to start):**
> - **Host 344939** — fails on both private and official PyTorch templates
> - **Host 20325** (Quebec) — container never created after 6+ min, "No such container" in logs
> - **Host 201023** (Quebec, RTX 3090) — container never started, stuck `loading` indefinitely
> - **Host 37070** (Netherlands, RTX 3090) — same Docker daemon pattern, container refused to start
> - **Host 148689** (Belgium, RTX 3090) — ✅ WORKING, instance 35051543
>
> **Docker daemon failure pattern:** Container `actual_status=loading` indefinitely, SSH never responds, logs show "No such container". Try a different host before assuming the offer is bad.
>
> **Instance 35051543:** Belgium, RTX 3090, $0.215/hr, Qwen Image Edit workflow. SSH port 11542. Portal: https://cloud.vast.ai/instances/35051543

**⚠️ `CF_TUNNEL_TOKEN` no longer required (updated 2026-04-27):**
The bootstrap script now always sets up quick Cloudflare tunnels for ComfyUI and Jupyter — even without `CF_TUNNEL_TOKEN`. So tunnel URLs will always be in the Discord webhook. The token is only needed for persistent named tunnels.

**⚠️ Discord webhook silently fails — check `provisioning.log` first:**
If the user reports no Discord notification, check `/var/log/portal/provisioning.log` on the server.

**LXC Discord Relay (for regionally blocked hosts):**
Turkish hosts (and some others) block Discord's AS — the direct curl times out. The bootstrap script now:
1. Tries direct Discord POST (3 retries, 2s backoff, direct)
2. Falls back to `https://relay.lxc.muneesraja.com/hook?url=<base64_webhook_url>` — routes through LXC which always has clean Discord access. The relay has **3 retries, 2s backoff (direct) / 3s backoff (relay)**.

The relay runs as a systemd service (`discord-relay`) on the LXC. If it goes down, `sudo systemctl restart discord-relay`.

**Root cause (fixed 2026-04-27, commit `b85ea68`):** The workflow-completion curl was inside a double-quoted tmux string — `$DISCORD_WEBHOOK_URL` ran in a subprocess where the variable was never expanded before the curl call, causing silent failure.

**Fix applied:** Write a standalone `/workspace/workflow-complete.sh` with the URL baked in via `sed`, then call that from the tmux session. The provisioning webhook (step 5/5) was unaffected — only the workflow-completion tmux webhook had the bug.

**Workaround for instances with old bootstrap script:** SSH in and run manually:
```bash
WEBHOOK_URL="<DISCORD_WEBHOOK_URL>"
curl -s -H "Content-Type: application/json" \
  -d '{"embeds": [{"title": "🟢 GPU Server Ready!", "description": "Instance up and running.", "color": 5763719}]}' \
  "$WEBHOOK_URL"
```

**Docker daemon failure is often transient — wait ~5 min before destroying:**
> **Instance 35051543:** Belgium, RTX 3090, $0.215/hr, Qwen Image Edit workflow. SSH port 11542. Portal: https://cloud.vast.ai/instances/35051543

**⚠️ `success` field as early indicator:** When `vastai create instance` returns `"success": false`, the instance will almost certainly fail with the Docker daemon "No such container" pattern. When `"success": true` — boot succeeds. This is a reliable leading signal to try the next offer immediately rather than waiting through a 2+ min failed boot.

**⚠️ Known working hosts can still fail Docker — always wait for `actual_status: running`:**
Even hosts previously verified as working (like Belgium host 148689) can exhibit the Docker "No such container" pattern on a given boot. The instance must transition to `actual_status: running` before it's truly ready — don't trust `cur_state: running` alone. Boots can take **4-5+ minutes** even with pre-cached images.

**⚠️ SSH may not respond immediately after `actual_status: running`:**
Even after `actual_status` transitions to `"running"`, the container's SSH daemon may take **20-60 seconds** to become available. SSH connection attempts will time out during this window. Always wait ~30s after first seeing `actual_status: running` before attempting SSH. Use `vastai ssh-url <id>` (not the raw JSON `ssh_port`) to get the correct direct port.

**Docker daemon failure hosts (verified):**
| Host ID | Location | Notes |
|---------|----------|-------|
| 344939 | — | Docker fails on private + official PyTorch templates |
| 20325 | Quebec | Container never created after 6+ min |
| 201023 | Quebec | RTX 3090 — stuck `loading` indefinitely |
| 37070 | Netherlands | RTX 3090 — Docker refuses to start |
| 264182 | Bulgaria | `success: false` on create |
| 446098 | Sweden | `success: false` on create |
| 148689 | Belgium | **Was working previously — but can fail on new boots** (instance 35351926 failed). Driver 565.x, CUDA cap 12.7 — incompatible with cuda-13.2 images |

> **💡 Zram:** Use for RAM boost on low-memory hosts. See vault: `infrastructure/zram-notes.md`

**⚠️ SSH port — use `vastai ssh-url`, NOT the raw JSON `ssh_port` field:**
The `ssh_port` in `--raw` JSON (e.g., 32104) may be stale/proxy-based. Use `vastai ssh-url <instance_id>` to get the correct direct SSH endpoint (e.g., `ssh://root@IP:42761`). This is the port that actually works for SCP and SSH commands.

**Large file downloads (8GB+) — download directly on the server:**
For big model files (8GB+), do NOT download to LXC then SCP — that pipes 8GB through the relay and takes 20+ min. Instead, SSH into the server and run:
```bash
ssh -p <ssh_port> -o StrictHostKeyChecking=no root@<ip> \
  "nohup curl -L '<url>' -o /workspace/ComfyUI/models/<path>/<filename> --progress-bar > /workspace/download.log 2>&1 & echo PID: \$!"
```
Then monitor with `ssh "tail -3 /workspace/download.log"`. The server downloads at full speed from HuggingFace/CivitAI directly.

## ⚡ Quick Rent Workflow (3 Steps)
1. **Search** with all filters (inet_down_cost in query — trust it, don't manually cross-check)
2. **Confirm** — report cheapest valid offer to user in one message
3. **Rent** on user approval

Do NOT add extra steps between search and confirm.

## Tools Required
You have the `vastai` CLI installed natively on the system. You execute it directly via the console.

## The Provisioning Workflow

When a user asks you to "setup a [GPU] server" or similar, execute the following steps:

### Step 1: Read Configuration from Vault

Read GPU specs and (optionally) a workflow script from the `growthlabs-docs` vault.

**A. Fetching GPU Server Specs:**
Use the **growthlabs-docs skill's folder structure table** to determine the exact file path, then read it directly. Do NOT search.

- "3090" → Read `growthlabs-docs/references/gpu/3090.md`
- "4090" → Read `growthlabs-docs/references/gpu/4090.md`

Extract the following variables:
- `num_gpus`: Number of GPUs (usually 1)
- `gpu_name`: GPU model (e.g., RTX_3090, RTX_4090)
- `cpu_ram`: Minimum RAM in GB (e.g., 48)
- `disk_space`: Disk space in GB (e.g., 100)
- `inet_down` / `inet_up`: Minimum network speeds in Mbps (e.g., 500)
- `cpu_cores`: Minimum CPU cores (e.g., 4)
- `reliability`: Minimum reliability score (e.g., 0.99)
- `docker_image`: The Docker image to use (e.g., `pytorch/pytorch:latest`)
- `max_price`: Maximum price per hour ($/hr)
- `max_inet_down_cost`: Maximum internet download cost per TB (default $0.01 i.e. $10/TB)

**B. Fetching Workflow Script (if requested):**
Check if the user requested a specific workflow (e.g., "with Wan 2.2" or "with LTX").

**Discovery via GitHub API — always up to date, no registry to maintain:**
```bash
curl -s https://api.github.com/repos/muneesraja/auto-startups-vast/contents/scripts/workflows
```

This returns a JSON array of all `.sh` files. For each file, read its raw URL and check the frontmatter `aliases` field (embedded as bash comments at the top of each script) to find the one that matches the user's request.

**Frontmatter format** (first ~10 lines of every workflow script):
```bash
#!/bin/bash
# ---
# name: Wan 2.2
# aliases: [wan, wan 2.1, wan 2.2, wan2.2]
# description: ...
# size: ~25GB
# min_vram: 24GB
# ---
```

**Matching rule:** If the user says "wan 2.2", "wan", or "wanvideo" — any of those should match the script whose `aliases` list contains that term (case-insensitive).

**Construct `WORKFLOW_SCRIPT` URL** from the matched filename:
```
https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/workflows/<filename>
```

If no match is found, tell the user: "I couldn't find a workflow script matching '[request]'. Available workflows are: [list names from frontmatter]."


### Step 2: Search for Offers
Construct a `vastai search offers` command using the exact parameters from Step 1. Wait to get the output.

```bash
vastai search offers 'gpu_name=[GPU] num_gpus=[NUM] cpu_ram>=[RAM] disk_space>=[DISK] inet_down>=[DOWN] inet_up>=[UP] cpu_cores>=[CORES] reliability>[REL] dph<=[MAX_PRICE] inet_down_cost<[MAX_INET_DOWN_COST] inet_up_cost<[MAX_INET_UP_COST] cuda_max_good>=12.9 rented=False' -o 'dph+' --limit 10
```
*Note: Ensure NO spaces are around the `>=` or `<=` operators in the query string.*

**Internet Cost Filtering:**
GrowthLabs regularly downloads ~100 GB of model files per server setup. Many hosts charge usage-based internet fees. Always filter by `inet_down_cost<0.01` in the search query — this already screens out expensive bandwidth hosts. Do NOT do extra manual checks of inet costs after the search. Trust the filter.

### Step 3: Confirm with User (CRITICAL SAFETY STEP)
Select the cheapest valid offer from the search results (the top result, since it's sorted by `dph+`).
Post a summary to the user in Discord and explicitly ASK FOR PERMISSION to spend money.

> 🔍 Found a matching offer for **[GPU_NAME]**:
> - **Offer ID:** `[ID]`
> - **Specs:** [RAM] RAM, [CORES] Cores, [DISK] Disk, [UP]/[DOWN] Mbps Internet
> - **Location:** [Country/Region]
> - **Cost:** **$[DPH]/hr**
> - **Internet Cost:** $[INET_DOWN_COST]/TB download, $[INET_UP_COST]/TB upload
>
> Shall I rent this server?

*DO NOT PROCEED UNTIL THE USER SAYS YES.*

**⚠️ Price Too Good to Be True?**
If an offer is significantly cheaper than others, it may be unreliable. When in doubt, prefer a slightly more expensive offer from a known-good host.

### Step 4: Provision Instance

**Instance Labeling (REQUIRED):**
Always tag the instance with the requester's name using `--label`. Use lowercase, no spaces (e.g., `--label "balaji"`).

**Provisioning command — uses official Vast.ai ComfyUI image (pre-cached, instant boot):**

**Without workflow (bare ComfyUI):**
```bash
vastai create instance <OFFER_ID> \
  --image vastai/comfy:v0.20.1-cuda-12.9-py312 \
  --env '-p 8188:8188 -e COMFYUI_ARGS="--disable-auto-launch --port 18188 --enable-cors-header" -e PROVISIONING_SCRIPT="https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/comfyui-bootstrap.sh" -e DISCORD_WEBHOOK_URL="<DISCORD_WEBHOOK_URL>" -e PORTAL_CONFIG="localhost:1111:11111:/:Instance Portal|localhost:8188:18188:/:ComfyUI|localhost:8080:18080:/:Jupyter|localhost:8080:8080:/terminals/1:Jupyter Terminal" -e OPEN_BUTTON_PORT="1111" -e JUPYTER_DIR="/" -e DATA_DIRECTORY="/workspace/" -e OPEN_BUTTON_TOKEN="1"' \
  --disk <DISK> \
  --label "<requester_name>" \
  --direct \
  --ssh \
  --jupyter \
  --onstart-cmd 'entrypoint.sh'
```

**With workflow (e.g., Wan 2.2) — add `WORKFLOW_SCRIPT` env var:**
```bash
vastai create instance <OFFER_ID> \
  --image vastai/comfy:v0.20.1-cuda-12.9-py312 \
  --env '-p 8188:8188 -e COMFYUI_ARGS="--disable-auto-launch --port 18188 --enable-cors-header" -e PROVISIONING_SCRIPT="https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/comfyui-bootstrap.sh" -e DISCORD_WEBHOOK_URL="<DISCORD_WEBHOOK_URL>" -e WORKFLOW_SCRIPT="<WORKFLOW_SCRIPT_URL>" -e PORTAL_CONFIG="localhost:1111:11111:/:Instance Portal|localhost:8188:18188:/:ComfyUI|localhost:8080:18080:/:Jupyter|localhost:8080:8080:/terminals/1:Jupyter Terminal" -e OPEN_BUTTON_PORT="1111" -e JUPYTER_DIR="/" -e DATA_DIRECTORY="/workspace/" -e OPEN_BUTTON_TOKEN="***"' \
  --disk <DISK> \
  --label "<requester_name>" \
  --direct \
  --ssh \
  --jupyter \
  --onstart-cmd 'entrypoint.sh'
```

**Workflow script URLs** (use in `WORKFLOW_SCRIPT` env var):
- Wan 2.2: `https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/workflows/wan22-download.sh`

**Key env vars:**
- `PROVISIONING_SCRIPT` — Bootstrap script URL. Runs after entrypoint. Handles system extras, portal fix, workflow, and Discord webhook.
- `DISCORD_WEBHOOK_URL` — Discord webhook for auto-notifications when server is ready.
- `WORKFLOW_SCRIPT` — (Optional) URL to a workflow download script. Runs in background tmux, sends a second webhook when complete.
- **RTX 3090 template hash:** `21a9ec596c941d25556db58129ee7262` (verified working)
- **Cloudflare tunnel token:** `<CF_TUNNEL_TOKEN>`
- **Zram:** See `infrastructure/zram-notes.md` in vault for RAM boost setup
- `COMFYUI_ARGS` — `--port 18188` is the internal port (mapped to 8188 externally).
- `PORTAL_CONFIG` — Instance Portal (hub), ComfyUI, Jupyter tabs. **Port 1111 must be mapped.**

Capture the `new_contract` ID from the JSON output. This is your `INSTANCE_ID`.

**⚠️ Why `vastai/comfy:v0.20.1-cuda-12.9-py312` with `entrypoint.sh`?**
Vast.ai's official ComfyUI image — pre-cached on most hosts, instant boots. Uses `cuda-12.9` for broad host driver compatibility (works with NV driver 565+). **Never override `--onstart-cmd`** — always use `entrypoint.sh` and pass customizations via env vars.

**⚠️ CUDA version compatibility (learned 2026-04-30):**
`cuda-13.2` images require NV driver 575+ (CUDA 13.2 cap). Many RTX 3090 hosts run older drivers (565.x = CUDA 12.7 cap). Always use `cuda-12.9` images and filter by `cuda_max_good>=12.9` in search queries.

### Step 5: Monitoring Loop

**Phase A: Initial Monitoring (0-2 minutes)**
Every 30 seconds, check status:
```bash
vastai show instance <INSTANCE_ID> --raw
```
- **`actual_status` = `"running"`** → Proceed to Step 6
- **`actual_status` = `"loading"` AND `duration` > 120 seconds** → Proceed to Phase B

**Phase B: Extended Diagnostics (2+ minutes)**
The image is pre-cached on most hosts — expect 1-2 min boots. If it takes longer, investigate:

1. **Report status to user:**
   > ⏳ **Instance still loading** (Duration: [X] min)
   > - Image should be pre-cached — checking if host needs to pull it
   > - Current cost: ~$[Y] so far

2. **Check daemon logs FIRST (not container logs):**
   ```bash
   vastai logs <INSTANCE_ID> --daemon-logs
   ```
   Note: the command is `vastai logs`, NOT `vastai show logs` (that will error).

   **Interpreting daemon logs:**
   - **Image pull in progress** (layers downloading, "Already exists", "Verifying Checksum") → **Healthy.** Host just needs to pull uncached layers. Keep waiting — can take 5+ min on slow connections.
   - **"No such container: C.<ID>"** → Docker daemon failure. Container was never created. This is the actual failure pattern.
   - **No output / empty logs** → Host hasn't started processing yet. Wait another 30s and retry.

   ⚠️ **Do NOT assume Docker daemon failure based on slow loading alone.** Always check `--daemon-logs` first. A host pulling uncached image layers looks identical to a stuck host from `actual_status` alone — only the daemon logs tell the difference.

3. **Only check container logs if daemon logs show errors:**
   ```bash
   vastai logs <INSTANCE_ID>
   ```

4. **Continue monitoring until:**
   - **`actual_status` = `"running"`** → Proceed to Step 6
   - **Daemon logs confirm "No such container"** → Docker daemon failure, destroy and try next offer
   - **Logs show other unrecoverable errors** → Report error, ask user if they want to destroy
   - **User says `/stop` or asks to destroy** → Destroy the instance
   - **Duration exceeds 10 minutes with no progress** → Ask user whether to continue or destroy

**Phase C: User-Initiated Destroy**
Only destroy when the user explicitly requests it, logs show unrecoverable errors, or duration > 10 min AND user confirms.

```bash
vastai destroy instance <INSTANCE_ID>
```

> ❌ **Instance Destroyed:** `[INSTANCE_ID]`
> - Reason: [User request / Error in logs / Timeout]
> - Total duration: [X] minutes

### Step 6: Report Server Ready

Once the instance status is "running", ComfyUI is already up. **The provisioning script automatically sends a Discord webhook with all tunnel URLs, credentials, and GPU info — you do NOT need to SSH in to extract these.**

```bash
vastai show instance <INSTANCE_ID> --raw
```

Extract from the `--raw` JSON:
- `jupyter_token` — login password
- `public_ipaddr` + SSH port from `ports` map (look for `"22/tcp"` → `HostPort`)
- `dph_total` — cost per hour

**DO NOT SSH into the instance to get tunnel URLs.** The webhook already posted them to Discord. Just report the basics:

> ✅ **Server Ready!**
> - **GPU:** [GPU_NAME]
> - **Instance ID:** `[ID]`
> - **Cost:** $[COST]/hr
>
> 💻 **SSH:** `ssh -p [direct_ssh_port] root@[public_ipaddr]`
> 🔐 **Login:** `vastai` / `[jupyter_token]`
>
> 📬 Tunnel URLs (ComfyUI, Jupyter, Instance Portal) were sent via webhook notification above.

**⚠️ STOP HERE.** Do not run any more commands unless the user asks for something specific (e.g., workflow script execution). The server is ready.

**Fallback — if the webhook didn't fire or user asks for URLs:**
1. Use `vastai ssh-url <INSTANCE_ID>` to get the correct direct SSH endpoint (more reliable than `ssh_port`/`ssh_host` from `--raw` JSON which may be stale or proxy-based)
2. SSH in and tunnel URLs are managed by `portal-aio` TUI — not written to files. The cloudflare URLs are captured by the TUI process stdout and not easily extractable via SSH
3. Direct the user to the Vast.ai portal: `https://cloud.vast.ai/instances/<INSTANCE_ID>` — the "Open" button takes them to the Instance Portal (port 1111) which displays all tunnel URLs

### Step 7: Execute Workflow Script (If requested)

If the user requested a workflow in Step 1, it was already included as the `WORKFLOW_SCRIPT` env var in the provisioning command (Step 4). **No SSH needed.**

The provisioning script automatically:
1. Downloads the workflow script from the URL
2. Runs it in a background tmux session (`workflow`)
3. Sends a second Discord webhook when the download completes

Just inform the user:
> 📦 **Workflow models downloading in background.**
> A Discord notification will be sent when the download is complete.

**If the user asks "is it done?" before the webhook fires:**
This is the ONE case where SSH is needed:
```bash
ssh -p [direct_ssh_port] -o StrictHostKeyChecking=no -o ConnectTimeout=15 root@[public_ipaddr] \
  "tail -3 /workspace/workflow.log 2>/dev/null || echo 'Log not found'"
```

---

## General Commands

If the user asks to **"List my instances"**:
```bash
vastai show instances
```

If the user asks to **"Destroy instance [ID]"**:
Always confirm first: "⚠️ You are about to irrevocably destroy instance [ID]. Are you sure?"
Then run: `vastai destroy instance [ID]`