#!/usr/bin/env python3
"""
config.py — GPU profiles, workflow aliases, and shared constants.
"""

import os
from pathlib import Path

# =============================================================================
# GPU Profiles
# =============================================================================

GPU_PROFILES = {
    "3090": {
        "name": "RTX_3090",
        "num_gpus": 1,
        "min_ram_gb": 24,           # VRAM is bottleneck, not system RAM
        "min_disk_gb": 150,         # Bumped 2026-06-05: flux-2-dev-turbo needs ~150GB for full model set
        "min_inet_down_mbps": 400,  # 400 Mbps min — still good for 25GB+ model downloads
        "min_inet_up_mbps": 300,
        "min_cpu_cores": 2,
        "min_reliability": 0.98,    # Bumped 2026-06-05: Munees wants "high reliability" for 3090 instances
        "cuda_min": 12.8,           # cuda-13.2 image requires CUDA 12.8+ hardware capability (3090/4090 both fine)
        "driver_min": "570.0.0",    # NV driver 570+ REQUIRED for CUDA 12.9 (560/565 fail with Error 804)
        "max_price_hr": 0.30,       # Relaxed from 0.25 to show more options
        "max_inet_down_cost_tb": 0.05,
        "docker_image": "vastai/comfy:v0.22.0-cuda-13.2-py312",
        "skip_countries": ["CN"],        # China hosts have slow/failed downloads
        "notes": "32GB system RAM is fine for ComfyUI. Driver 580.x preferred (native CUDA 13.2). Driver 570.x works but may need compat lib fix.",
    },
    "4090": {
        "name": "RTX_4090",
        "num_gpus": 1,
        "min_ram_gb": 24,
        "min_disk_gb": 100,
        "min_inet_down_mbps": 400,
        "min_inet_up_mbps": 300,
        "min_cpu_cores": 2,
        "min_reliability": 0.95,
        "cuda_min": 12.8,
        "driver_min": "570.0.0",    # NV driver 570+ REQUIRED for CUDA 12.9
        "max_price_hr": 0.50,       # Relaxed from 0.40
        "max_inet_down_cost_tb": 0.05,
        "docker_image": "vastai/comfy:v0.22.0-cuda-13.2-py312",
        "skip_countries": ["CN"],
        "notes": "4090 has 24GB VRAM, better perf/$ than 3090 for many workloads",
    },
}

# =============================================================================
# Workflow Registry — maps aliases to GitHub raw URLs
# =============================================================================

WORKFLOWS_REPO = "muneesraja/auto-startups-vast"
WORKFLOWS_BRANCH = "main"
WORKFLOWS_PATH = "scripts/workflows"

# Maps friendly names/aliases -> actual filenames in scripts/workflows/
# IMPORTANT: These MUST match real files. See .agents/rules/workflow-alias-maintenance.md
WORKFLOW_ALIASES = {
    # Wan 2.2
    "wan22": "wan-22-i2v-keyframe.sh",
    "wan": "wan-22-i2v-keyframe.sh",
    "wan 2.2": "wan-22-i2v-keyframe.sh",
    "wan2.2": "wan-22-i2v-keyframe.sh",
    "wanvideo": "wan-22-i2v-keyframe.sh",
    "wan-22-i2v-keyframe": "wan-22-i2v-keyframe.sh",
    # LTX 2.3 — Prompt Relay
    "ltx-23-prompt-relay": "ltx-23-prompt-relay.sh",
    "ltx23-prompt-relay": "ltx-23-prompt-relay.sh",
    "prompt-relay": "ltx-23-prompt-relay.sh",
    # LTX 2.3 — I2V Keyframe
    "ltx-23-i2v-keyframe": "ltx-23-i2v-keyframe.sh",
    "ltx23-keyframe": "ltx-23-i2v-keyframe.sh",
    # LTX 2.3 — I2V Distilled
    "ltx-23-i2v-distilled": "ltx-23-i2v-distilled.sh",
    "ltx23-distilled": "ltx-23-i2v-distilled.sh",
    # LTX 2.3 — I2V Official (Lightricks)
    "ltx-23-i2v-official": "ltx-23-i2v-official.sh",
    "ltx23-official": "ltx-23-i2v-official.sh",
    "ltx-official": "ltx-23-i2v-official.sh",
    # Qwen Image Edit
    "qwen": "qwen-image-edit.sh",
    "qwen-image": "qwen-image-edit.sh",
    "qwen-image-edit": "qwen-image-edit.sh",
    # Qwen Image Edit 2511 4-Step Lightning
    "qwen-image-edit-2511-4steps": "qwen-image-edit-2511-4steps.sh",
    "qwen-2511": "qwen-image-edit-2511-4steps.sh",
    "qwen-image-edit-2511": "qwen-image-edit-2511-4steps.sh",
    "qwen-image-lightning-4steps": "qwen-image-edit-2511-4steps.sh",
    # HiDream O1 Image Dev I2I
    "hidream-o1-dev-i2i": "hidream-o1-dev-i2i.sh",
    "hidream-o1": "hidream-o1-dev-i2i.sh",
    "hidream-o1-image-dev": "hidream-o1-dev-i2i.sh",
    "hidream-i2i": "hidream-o1-dev-i2i.sh",
    "hidream": "hidream-o1-dev-i2i.sh",
}

# =============================================================================
# Config constants
# =============================================================================

FAILED_HOSTS_PATH = str(Path(__file__).resolve().parent / "failed_hosts.json")
FAST_PROVISION_URL = "https://raw.githubusercontent.com/muneesraja/auto-startups-vast/main/scripts/fast-provision.sh"
CF_DOMAIN = "muneesraja.com"
