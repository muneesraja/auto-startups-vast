"""Instagram Login API token exchange, refresh, and verification."""

from __future__ import annotations

import os

import requests

IG_GRAPH_HOST = "https://graph.instagram.com"
IG_GRAPH_API_VERSION = os.getenv("IG_GRAPH_API_VERSION", "v21.0")


class InstagramTokenError(RuntimeError):
    pass


def exchange_short_lived_token(short_lived_token: str, app_secret: str) -> dict:
    """Exchange a short-lived Instagram user token for a long-lived token (~60 days)."""
    if not short_lived_token.strip():
        raise InstagramTokenError("short_lived_token is empty")
    if not app_secret.strip():
        raise InstagramTokenError("app_secret is empty")

    resp = requests.get(
        f"{IG_GRAPH_HOST}/access_token",
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": app_secret,
            "access_token": short_lived_token,
        },
        timeout=60,
    )
    body = resp.json() if resp.content else {}
    if not resp.ok:
        raise InstagramTokenError(f"Token exchange failed ({resp.status_code}): {body}")
    access_token = body.get("access_token")
    if not access_token:
        raise InstagramTokenError(f"No access_token in exchange response: {body}")
    return body


def refresh_long_lived_token(access_token: str) -> dict:
    """Refresh a long-lived Instagram user token for another ~60 days."""
    if not access_token.strip():
        raise InstagramTokenError("access_token is empty")

    resp = requests.get(
        f"{IG_GRAPH_HOST}/refresh_access_token",
        params={
            "grant_type": "ig_refresh_token",
            "access_token": access_token,
        },
        timeout=60,
    )
    body = resp.json() if resp.content else {}
    if not resp.ok:
        raise InstagramTokenError(f"Token refresh failed ({resp.status_code}): {body}")
    new_token = body.get("access_token")
    if not new_token:
        raise InstagramTokenError(f"No access_token in refresh response: {body}")
    return body


def verify_token(access_token: str) -> dict:
    """Return Instagram account info for a token."""
    if not access_token.strip():
        raise InstagramTokenError("access_token is empty")

    resp = requests.get(
        f"{IG_GRAPH_HOST}/{IG_GRAPH_API_VERSION}/me",
        params={
            "fields": "user_id,username",
            "access_token": access_token,
        },
        timeout=60,
    )
    body = resp.json() if resp.content else {}
    if not resp.ok:
        raise InstagramTokenError(f"Token verify failed ({resp.status_code}): {body}")
    return body
