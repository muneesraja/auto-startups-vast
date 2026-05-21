#!/usr/bin/env python3
"""
client.py — Lazy VastAI client initialization, dotenv loading, and secret accessors.
"""

import json
import os
import sys
from pathlib import Path

# Ensure sibling modules are importable when loaded standalone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# =============================================================================
# Module globals
# =============================================================================

VAST_API_KEY = ""
DISCORD_WEBHOOK_URL = ""
HF_TOKEN_PATH = "/root/config/token.json"

# Lazy-initialized client
_client = None
_dotenv_loaded = False


# =============================================================================
# Dotenv
# =============================================================================

def init_dotenv():
    """Load .env file from project root (walks up from this script's location).

    Must be called BEFORE get_client() first use.
    """
    global _dotenv_loaded, VAST_API_KEY, DISCORD_WEBHOOK_URL
    if _dotenv_loaded:
        return
    _dotenv_loaded = True

    search = Path(__file__).resolve().parent
    for _ in range(6):  # Walk up max 6 levels
        env_file = search / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key, value = key.strip(), value.strip()
                    if value and key not in os.environ:  # Don't override existing env
                        os.environ[key] = value
            break
        search = search.parent

    # Refresh globals from env after loading
    VAST_API_KEY = os.environ.get("VAST_API_KEY", "")
    DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


# =============================================================================
# SDK Client (lazy)
# =============================================================================

def get_client():
    """Return initialized VastAI instance. Lazy — not created until first call."""
    global _client
    if _client is not None:
        return _client

    from utils import log
    # Optional: enable SDK request/response tracing
    sdk_explain = os.environ.get("VAST_SDK_EXPLAIN", "").lower() in ("1", "true", "yes")
    api_key = os.environ.get("VAST_API_KEY", "")

    try:
        from vastai import VastAI
    except ImportError:
        log("❌", "vastai SDK not installed — run: pip install vastai>=0.4.0")
        raise SystemExit(1)

    _client = VastAI(
        api_key=api_key if api_key else None,
        raw=True,
        explain=sdk_explain,
    )
    return _client


# =============================================================================
# Secret loaders
# =============================================================================

def load_hf_token() -> str:
    """Load HF token from env var (set by .env) or JSON config file."""
    # Check env var first (loaded by init_dotenv from .env)
    token = os.environ.get("HF_TOKEN", "")
    if token:
        return token
    # Fall back to JSON config file
    try:
        with open(HF_TOKEN_PATH) as f:
            data = json.load(f)
            return data.get("huggingface_token", "")
    except (FileNotFoundError, json.JSONDecodeError):
        return ""


def load_discord_webhook() -> str:
    """Load Discord webhook URL from env or config."""
    if DISCORD_WEBHOOK_URL:
        return DISCORD_WEBHOOK_URL
    # Try loading from token.json (JSON format)
    try:
        with open(HF_TOKEN_PATH) as f:
            data = json.load(f)
            url = data.get("discord_webhook_url", "")
            if url:
                return url
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return ""
