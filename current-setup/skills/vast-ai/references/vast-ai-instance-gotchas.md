# Vast.ai Instance Gotchas

Critical pitfalls discovered during provisioning and debugging.

## Service Ports (FRP Tunneling)

| Service | Port | Protocol | Must Change? |
|---------|------|----------|--------------|
| ComfyUI | 18188 | HTTP | No — already uses `--listen 0.0.0.0` |
| Jupyter | 18080 | HTTP | **YES** — image starts HTTPS on 8080, must restart as plain HTTP on 18080 |
| Portal | 11111 | HTTP | **YES** — image binds to `127.0.0.1`, must change to `0.0.0.0` |
| Bridge | 3000 | HTTP | No — nginx catch-all, rejects non-loopback |
| Caddy | — | — | **BROKEN** — FATALs on startup, don't try to fix |

## Critical Fixes After Provisioning

### 1. Jupyter: HTTPS → plain HTTP on 18080
The Vast.ai image starts Jupyter with `--certfile` and `--keyfile` on port 8080 (HTTPS). FRP can only proxy HTTP.

```bash
pkill -f jupyter
tmux new-session -d -s jupyter 'source /venv/main/bin/activate && jupyter notebook \
  --no-browser --ip=0.0.0.0 --port=18080 --allow-root \
  --NotebookApp.token="" --NotebookApp.certfile="" --NotebookApp.keyfile="" \
  --notebook-dir=/workspace > /tmp/jupyter.log 2>&1'
```

FRP config: `localPort = 18080`

### 2. Portal: localhost → 0.0.0.0
The image's `instance_portal` uses `--host 127.0.0.1`. FRP can't reach localhost from outside.

```bash
sed -i 's/--host 127.0.0.1/--host 0.0.0.0/' /opt/supervisor-scripts/instance_portal.sh
supervisorctl start instance_portal
```

### 3. ComfyUI: Must use --listen 0.0.0.0
Without this flag, ComfyUI binds to 127.0.0.1 and returns "Invalid Host header" via the bridge app.

Already handled in `fast-provision.sh`.

## nginx Config: Wildcard Priority Bug

nginx `server_name *.lxc.muneesraja.com` on port 443 **takes priority** over regex blocks like `~^jupyter[0-9]*-comfy\.lxc\.muneesraja\.com$`.

**Fix:** Use `server_name _;` on the port 443 `default_server` block. The port 80 redirect block can keep `*.lxc.muneesraja.com`.

## Error: "Invalid Host header. Bridge accepts loopback hosts only."

This comes from the Vast.ai Express bridge app on port 3000. It means nginx is routing the request to the default_server (which proxies to port 3000) instead of the FRP proxy block.

Root causes:
1. nginx wildcard priority (see above)
2. Service not listening on expected port on the instance
3. Service bound to 127.0.0.1

## Discord Webhook: Cloudflare blocks Python-urllib

Discord's CDN (Cloudflare) blocks `Python-urllib/3.x` with error 1010.

**Fix:** Set custom User-Agent header: `User-Agent: HermesBot/1.0`

## hf_download Not Found from /tmp

The `fast-provision.sh` runs from `/tmp/` but `source _hf_download.sh` uses `$SCRIPT_DIR` to find the helper. If `SCRIPT_DIR=/tmp`, the helper doesn't exist there.

**Fix:** Download `_hf_download.sh` to `/workspace/` and source it explicitly before running workflow scripts.

## vastai CLI Returns Python Dicts (not JSON)

`vastai show instances --raw` can return Python dict repr instead of valid JSON.

**Fix:** Use `ast.literal_eval()` fallback parser in Python scripts.

## CUDA Error 804: Forward Compatibility Layer Conflict

Drivers 560.x-565.x fail with CUDA 12.9 image:

```
RuntimeError: Unexpected error from cudaGetDeviceCount(). Did you run some cuda functions before calling NumCudaDevices() that might have already set an error? Error 804: forward compatibility was attempted on non supported HW
```

**Root cause:** Docker image `vastai/comfy:v0.20.1-cuda-12.9-py312` includes CUDA 12.9 libraries, but older drivers (560.x-565.x) have incomplete forward compatibility layers.

**Fix for driver 570.x:**
```bash
# Remove conflicting compat libraries from container
rm -f /usr/local/cuda-12.9/compat/libcuda.so* && ldconfig
```

**Better fix:** Filter hosts by `driver_version>=570.0.0` in search query. Driver 580.x+ preferred (native CUDA 13.0 support, no workarounds needed).

**Avoid entirely:** Drivers ≤565.x — these cannot run CUDA 12.9 image reliably.

**History:**
- 2026-05-13: Instance 36686102 failed with driver 525.x — driver too old
- 2026-05-14: Multiple instances failed during GPU prep (unverified hosts)

## SSH Key Mismatch: VPS Keys May Not Match Vast.ai Registered Keys

The VPS `~/.ssh/id_ed25519` private key may not match any public key registered on Vast.ai, even if the `.pub` comment says "root-vast.ai". The private key can be regenerated after initial setup, breaking the match.

**Impact:** SSH auth fails silently — health checks, workflow monitoring, and remote debugging all break.

**Fix:** Use a dedicated key per the `detect_ssh_key()` function:
- `~/.ssh/vast_ai_dedicated` — auto-validated against Vast.ai account
- `vastai-provision.py --ssh-key /path/to/key` — manual override
- Auto-adds `Host ssh*.vast.ai IdentityFile ~/.ssh/vast_ai_dedicated` to `~/.ssh/config`

**History:**
- 2026-05-19: Instance 37050866 unreachable — `id_ed25519` fingerprint mismatch. Generated `vast_ai_dedicated` key (ID 853182).

## Cloudflare Named Tunnels Fail Inside Vast.ai Containers

Cloudflared (v2026.3.0–v2026.5.0) fails to connect from inside Vast.ai containers with "control stream encountered a failure" — likely due to container network restrictions blocking Cloudflare edge connections.

**Fix:** Run cloudflared on the VPS with SSH port-forward as the bridge:
```
User → comfy-*.muneesraja.com → Cloudflare → VPS (cloudflared) → SSH tunnel → Instance:18188
```
This is the default behavior of `vastai-provision.py` (`--vps-tunnel`, default: enabled).

**Workaround:** Use `--container-tunnel` flag (deprecated) if you need the old container-side behavior.

**History:**
- 2026-05-19: Instance 37051117 — cloudflared inside container failed repeatedly. VPS-side relay worked immediately.

## Vast.ai Quick Tunnels Conflict with Custom Named Tunnels

The Vast.ai image's `tunnel_manager` supervisor service auto-spawns quick tunnels using `cloudflared tunnel --url`, generating random `.trycloudflare.com` URLs. These conflict with custom named tunnels.

**Fix:** When using VPS-side tunnel (`--vps-tunnel`, default), `setup_vps_tunnel()` kills container-side cloudflared processes and stops `tunnel_manager`:
```bash
pkill -f 'cloudflared tunnel' 2>/dev/null
supervisorctl stop tunnel_manager 2>/dev/null
```

## ComfyUI Port is 18188 (Not 8188)

The current Vast.ai ComfyUI image (`vastai/comfy:v0.20.1-cuda-12.9-py312`) starts ComfyUI on port **18188** (configured via `COMFYUI_ARGS="--port 18188"` in the environment). Port 8188 is not used.

**Impact:** SSH port-forwards and health checks must target port 18188, not 8188.

**History:**
- 2026-05-19: `health_check_instance()` checked both 8188 and 18188 — 18188 responded.