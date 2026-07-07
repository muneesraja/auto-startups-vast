"""Configuration for social-publisher skill.

Loads credentials from ~/.hermes/.env first, then project .env (override).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

config_dir = os.path.dirname(os.path.abspath(__file__))
workspace_root = os.path.dirname(os.path.dirname(config_dir))

_shared_dotenv = os.path.join(workspace_root, ".env")
load_dotenv(_shared_dotenv, override=False)


def _load_project_dotenv() -> str | None:
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        candidate = parent / ".env"
        if candidate.is_file() and str(candidate) != _shared_dotenv:
            load_dotenv(candidate, override=True)
            return str(candidate)
    return None


_load_project_dotenv()

# Google Sheet queue
SHEET_ID = os.getenv("SOCIAL_PUBLISHER_SHEET_ID", "")
QUEUE_TAB = os.getenv("SOCIAL_PUBLISHER_QUEUE_TAB", "Queue")
ACCOUNTS_TAB = os.getenv("SOCIAL_PUBLISHER_ACCOUNTS_TAB", "Accounts")

# VPS public URL for Instagram video_url (must be HTTPS in production)
PUBLIC_BASE_URL = os.getenv("SOCIAL_PUBLISHER_PUBLIC_BASE_URL", "http://localhost:8765")

# Media server bind (internal)
MEDIA_SERVER_HOST = os.getenv("SOCIAL_PUBLISHER_MEDIA_HOST", "0.0.0.0")
MEDIA_SERVER_PORT = int(os.getenv("SOCIAL_PUBLISHER_MEDIA_PORT", "8765"))

# Stale publishing recovery (minutes)
STALE_PUBLISHING_MINUTES = int(os.getenv("SOCIAL_PUBLISHER_STALE_MINUTES", "30"))

# Local temp dir for downloads
TEMP_DIR = os.getenv(
    "SOCIAL_PUBLISHER_TEMP_DIR",
    os.path.join(workspace_root, "outputs", "social-publisher", "tmp"),
)

# Local state file for idempotency timestamps
STATE_FILE = os.getenv(
    "SOCIAL_PUBLISHER_STATE_FILE",
    os.path.join(workspace_root, "outputs", "social-publisher", "state.json"),
)

# gws CLI
GWS_BIN = os.getenv("GWS_BIN", "gws")


def _env_key(credential_ref: str, suffix: str, fallback: str) -> str:
    """Resolve env var: {CRED_REF}_{SUFFIX} then global {FALLBACK}."""
    ref = (credential_ref or "MAIN").strip().upper()
    specific = os.getenv(f"{ref}_{suffix}")
    if specific:
        return specific
    return os.getenv(fallback, "")


def get_youtube_credentials(credential_ref: str = "YT_MAIN") -> dict[str, str]:
    ref = credential_ref.strip().upper()
    client_id = _env_key(ref, "CLIENT_ID", "YT_CLIENT_ID")
    client_secret = _env_key(ref, "CLIENT_SECRET", "YT_CLIENT_SECRET")
    refresh_token = _env_key(ref, "REFRESH_TOKEN", "YT_REFRESH_TOKEN")
    missing = [k for k, v in {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }.items() if not v]
    if missing:
        raise ValueError(
            f"YouTube credentials incomplete for {ref}: missing {', '.join(missing)}. "
            f"Set {ref}_CLIENT_ID, {ref}_CLIENT_SECRET, {ref}_REFRESH_TOKEN "
            f"or YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN in .env"
        )
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }


def get_instagram_app_secret(credential_ref: str = "IG_MAIN") -> str:
    ref = credential_ref.strip().upper()
    return _env_key(ref, "APP_SECRET", "IG_APP_SECRET")


def get_instagram_access_token(credential_ref: str = "IG_MAIN", *, auto_exchange: bool = True) -> str:
    """Resolve Instagram access token, optionally exchanging short-lived → long-lived."""
    ref = credential_ref.strip().upper()
    access_token = _env_key(ref, "ACCESS_TOKEN", "IG_ACCESS_TOKEN")
    if access_token:
        return access_token

    short_lived = _env_key(ref, "SHORT_LIVED_TOKEN", "IG_SHORT_LIVED_TOKEN")
    if not short_lived:
        raise ValueError(
            f"Instagram credentials incomplete for {ref}: set IG_ACCESS_TOKEN "
            f"or IG_SHORT_LIVED_TOKEN (+ IG_APP_SECRET for auto-exchange) in .env"
        )
    if not auto_exchange:
        return short_lived

    app_secret = get_instagram_app_secret(ref)
    if not app_secret:
        raise ValueError(
            f"IG_SHORT_LIVED_TOKEN is set but IG_APP_SECRET is missing for {ref}. "
            "Add IG_APP_SECRET or set IG_ACCESS_TOKEN directly."
        )

    from instagram_tokens import InstagramTokenError, exchange_short_lived_token

    try:
        result = exchange_short_lived_token(short_lived, app_secret)
    except InstagramTokenError as exc:
        print(
            f"  Instagram: token exchange failed ({exc}). "
            "Using short-lived token for this run (~1 hour). "
            "Fix IG_APP_SECRET and run scripts/exchange_instagram_token.py."
        )
        return short_lived

    print(
        "  Instagram: exchanged short-lived token for long-lived "
        f"(expires_in={result.get('expires_in', '?')}s). "
        "Run scripts/exchange_instagram_token.py to persist IG_ACCESS_TOKEN in .env."
    )
    return result["access_token"]


def get_instagram_credentials(credential_ref: str = "IG_MAIN") -> dict[str, str]:
    ref = credential_ref.strip().upper()
    access_token = get_instagram_access_token(ref)
    user_id = _env_key(ref, "USER_ID", "IG_USER_ID")
    missing = [k for k, v in {"user_id": user_id}.items() if not v]
    if missing:
        raise ValueError(
            f"Instagram credentials incomplete for {ref}: missing {', '.join(missing)}. "
            f"Set {ref}_USER_ID or IG_USER_ID in .env"
        )
    return {
        "access_token": access_token,
        "user_id": user_id,
        "app_secret": get_instagram_app_secret(ref),
    }
