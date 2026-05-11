---
name: china-host-download-speed
description: Research findings on China host download speed limitations and mitigation options for Vast.ai GPU servers.
---

# China Host Download Speed Research (2026-05-08)

## Problem
China-hosted Vast.ai instances have severely limited international bandwidth to HuggingFace.
- Typical speed: 300KB/s – 1.5MB/s (vs 50-100MB/s on Belgium/Quebec)
- A 61GB workflow takes 2+ hours instead of 15 min
- Root cause: China's congested international peering (GFW, limited ISP uplinks)
- NOT the host's rated bandwidth — the host may advertise 1Gbps but international routes are throttled

## Verified on Instance 36332716 (Host 155385, China)
- `prompt_relay_ltx23_test_02.sh` — 61.4GB LTX 2.3 models
- aria2c speed: fluctuating 300KB/s – 1.5MB/s
- After 90 min: 4/6 files done, 1 still downloading, 1 failed (TLS error)
- TLS error on Gemma encoder: `SocketCore.cc:886 — Failed to receive data, TLS packet decode error`
- SSH from LXC consistently timed out after 20+ min (China routing issue)

## Benchmark: HF CLI vs aria2c (Czechia host, 8Gbps peering)
Tested on instance 36337539 (host 3497, Czechia, $0.22/hr):

| File Size | aria2c (no auth) | HF CLI (auth + hf_transfer) |
|-----------|-------------------|-----------------------------|
| 348MB | 363 MiB/s (1.35s) | 141 MiB/s (2.47s) |
| 24GB | 423 MiB/s (57.8s) | **~690 MB/s (35.6s)** |

**Key findings:**
- HF CLI with auth wins on large files (1.6x faster for 24GB)
- aria2c faster on small files (lower connection overhead)
- HF CLI has reliable resume (no 0-byte files on failure)
- Authenticated HF account: no bandwidth cap, no volume limit, no speed cap
- Anonymous HF: capped at ~10.4 MB/s server-side
- `hf_transfer` (Rust) is required for speed — Python HTTP alone is slow
- HF CLI token: `/root/config/token.json`

**HF CLI setup on server:**
```bash
pip install huggingface_hub[cli] hf_transfer
export HF_HUB_ENABLE_HF_TRANSFER=1
export HF_TOKEN=$(python3 -c "import json; print(json.load(open('/root/config/token.json'))['huggingface_token'])")

# Python API (most reliable)
python3 -c "
from huggingface_hub import hf_hub_download
hf_hub_download(repo_id='Kijai/LTX2.3_comfy', filename='vae/LTX23_audio_vae_bf16.safetensors', local_dir='/workspace/benchmark', token='$HF_TOKEN')
"
```

**Note:** `huggingface-cli` is deprecated in newer versions — use `hf` command or Python API directly.

## Mitigation Options Evaluated

### 1. Avoid China Hosts (RECOMMENDED)
- Belgium/Quebec/Japan hosts at $0.15-0.20/hr — only $0.05/hr more
- Downloads complete in 15 min vs 2+ hours
- Cost savings from cheap China host ($0.13/hr) are eaten by longer download time anyway

### 2. HuggingFace CLI + hf-mirror.com
- `hf-mirror.com` is a community mirror with China CDN nodes
- Set `HF_ENDPOINT=https://hf-mirror.com` → `huggingface-cli download` routes through it
- `hf_transfer` (Rust-based) is fast — users report 500MB/s+ on good connections
- Built-in resume support

**Limitations:**
- Community-maintained, not official — could have sync delays or go down
- May itself be blocked by GFW (GitHub issues #1914, #436 report this)
- Only works with `huggingface-cli`, NOT with `curl` or `aria2c`
- Gated repos still need auth from huggingface.co (blocked in China)
- Would require rewriting all workflow scripts from aria2c to huggingface-cli

### 3. Cloudflare WARP
- Free VPN-like service, routes through Cloudflare backbone
- **Capped at ~100-120 Mbps** — not sufficient for large model downloads (need 500Mbps+ for 60GB files)
- Requires installation, registration, proxy configuration
- **User decision: Not worth it.** Munees confirmed cap is too low, reverted bootstrap script changes.
- Verdict: Do NOT add to bootstrap script. Not a viable solution.

## Decision
Munees prefers avoiding China hosts. When presenting offers:
- If cheapest is China and next cheapest is Europe/NA at less than $0.05/hr more → recommend non-China
- If user explicitly wants cheapest regardless → warn about download speed, proceed
