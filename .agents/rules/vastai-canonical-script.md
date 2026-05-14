# Vast.ai Provisioning — Canonical Script Location

## Single Source of Truth

The **ONLY** canonical `vastai-provision.py` lives at:
```
current-setup/skills/vast-ai/scripts/vastai-provision.py
```

This folder is **symlinked** into the Hermes skills directory on the VPS:
```
~/.hermes/skills/vast-ai/ → current-setup/skills/vast-ai/  (symlink)
```
So changes in either location propagate automatically. SKILL.md references `~/.hermes/skills/vast-ai/scripts/` because that's what the agent on the VPS resolves.

**Rules:**
1. **NEVER** create or maintain a copy of `vastai-provision.py` anywhere else in the repo (e.g., `scripts/vastai-provision.py`).
2. If you need to reference the provisioning script, always point to the canonical path above.
3. The SKILL.md at `current-setup/skills/vast-ai/SKILL.md` is the entrypoint — read it first.
4. All secrets (HF_TOKEN, DISCORD_WEBHOOK_URL, FRP_TOKEN) are loaded from the `.env` file at the project root. **NEVER hardcode tokens in shell scripts or Python files.**
5. The `failed_hosts.json` file lives alongside the script (same directory), NOT at an absolute path.

## FRP is Optional

FRP tunnel setup is **optional**. If `frp-allocate-port` is unavailable or `--no-frp` is passed, the system falls back to Cloudflare quick tunnels. **NEVER** make FRP a hard requirement that exits with `sys.exit(1)`.
