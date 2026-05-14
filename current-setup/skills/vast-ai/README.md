# Vast.ai Skill — Secrets & Environment Setup

This document is a quick reference for where secrets live and how the skill bootstraps itself on a new machine.

---

## Where does `.env` live?

**Canonical path:**

```
~/.hermes/skills/vast-ai/.env
```

Since `~/.hermes/skills/vast-ai` is a symlink to the repo's `current-setup/skills/vast-ai/`, physically placing `.env` in either location writes to the same inode. The skill self-documents using the `~/.hermes/skills/vast-ai/` path because that is the runtime directory the agent sees.

### How the script finds `.env`

`vastai-provision.py` walks **up from its own directory** (`scripts/`) looking for `.env`. It finds it immediately at the skill root:

```
vast-ai/
  .env                 ← found here
  scripts/
    vastai-provision.py ← starts walking up from here
```

---

## Required secrets

Copy from `.env.example` at the repo root and fill in your values:

```bash
cp ~/repos/auto-startups-vast/.env.example ~/.hermes/skills/vast-ai/.env
nano ~/.hermes/skills/vast-ai/.env
```

| Variable | Required? | Source |
|---|---|---|
| `VAST_API_KEY` | **Yes** | https://cloud.vast.ai/manage-keys/ |
| `HF_TOKEN` | **Yes** | https://huggingface.co/settings/tokens |
| `DISCORD_WEBHOOK_URL` | No | Discord Server Settings → Integrations → Webhooks |
| `FRP_TOKEN` | No | Your own FRP server shared secret |
| `FRP_SERVER_ADDR` | No | Defaults to `159.195.52.130` |
| `FRP_SERVER_PORT` | No | Defaults to `7000` |

---

## Python virtual environment

The skill requires the `vastai` Python SDK. Create the venv **once**:

```bash
python3 -m venv ~/.hermes/skills/vast-ai/.venv
source ~/.hermes/skills/vast-ai/.venv/bin/activate
pip install vastai
```

**Always invoke the script with the venv interpreter:**

```bash
~/.hermes/skills/vast-ai/.venv/bin/python3 \
  ~/.hermes/skills/vast-ai/scripts/vastai-provision.py \
  --gpu 3090 --label myrun --auto
```

The agent knows to do this automatically by reading `SKILL.md`.

---

## Quick command reference

```bash
# Rent a bare 3090
~/.hermes/skills/vast-ai/.venv/bin/python3 \
  ~/.hermes/skills/vast-ai/scripts/vastai-provision.py \
  --gpu 3090 --label myrun --auto

# Rent a 4090 with a workflow
~/.hermes/skills/vast-ai/.venv/bin/python3 \
  ~/.hermes/skills/vast-ai/scripts/vastai-provision.py \
  --gpu 4090 --workflow wan22 --label myrun --auto

# Preview only (don't spend money)
~/.hermes/skills/vast-ai/.venv/bin/python3 \
  ~/.hermes/skills/vast-ai/scripts/vastai-provision.py \
  --gpu 3090 --label myrun --dry-run

# Show blacklisted hosts
~/.hermes/skills/vast-ai/.venv/bin/python3 \
  ~/.hermes/skills/vast-ai/scripts/vastai-provision.py \
  --gpu 3090 --label dummy --show-failed
```

---

## Files in this skill

| File | Purpose |
|---|---|
| `SKILL.md` | Agent instructions — how to search, provision, monitor, troubleshoot |
| `scripts/vastai-provision.py` | Main provisioning script (SDK-based, atomic launch) |
| `scripts/failed_hosts.json` | Runtime blacklist — permanent & transient host failures |
| `.env` | **Your secrets** — not committed, loaded at runtime |
| `references/` | Deep-dive docs for specific issues (China downloads, CUDA errors, etc.) |
