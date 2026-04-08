# Aurora — GrowthLabs GPU Infrastructure

Automated GPU server provisioning for ComfyUI workflows on Vast.ai.

## Repository Structure

```
aurora/
├── scripts/
│   ├── comfyui-bootstrap.sh          # Provisioning script (runs on Vast.ai instances)
│   └── workflows/
│       └── wan22-download.sh          # Wan 2.2 model download script
├── current-setup/
│   └── skills/                        # Hermes agent skill definitions (gitignored)
└── README.md
```

## How It Works

1. **Aurora (Hermes agent)** provisions a Vast.ai GPU server
2. The `comfyui-bootstrap.sh` script runs automatically via `PROVISIONING_SCRIPT` env var
3. If a workflow was requested, `WORKFLOW_SCRIPT` env var points to the download script
4. Discord webhook notifies the team when everything is ready

## Scripts

### `comfyui-bootstrap.sh`
Provisioning script that runs after the Vast.ai ComfyUI image boots. Handles:
- System extras (aria2, tmux, ffmpeg)
- Instance Portal tunnel fix (known Vast.ai image bug)
- Workflow script execution (if `WORKFLOW_SCRIPT` env var is set)
- Discord webhook notification

**Raw URL:** `https://raw.githubusercontent.com/muneesraja/aurora/main/scripts/comfyui-bootstrap.sh`

### Workflow Scripts (`scripts/workflows/`)
Standalone bash scripts for downloading AI models. Each script is self-contained and can be passed via the `WORKFLOW_SCRIPT` env var during provisioning.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `PROVISIONING_SCRIPT` | Yes | URL to `comfyui-bootstrap.sh` |
| `WORKFLOW_SCRIPT` | No | URL to a workflow download script |
| `DISCORD_WEBHOOK_URL` | No | Discord webhook for notifications |
| `CF_TUNNEL_TOKEN` | No | Cloudflare named tunnel token |

## Adding a New Workflow

1. Create a new `.sh` file in `scripts/workflows/`
2. Follow the pattern in `wan22-download.sh`
3. Push to `main` branch
4. Use the raw URL: `https://raw.githubusercontent.com/muneesraja/aurora/main/scripts/workflows/<name>.sh`
