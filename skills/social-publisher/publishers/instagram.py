"""Instagram Reels publishing via Instagram Login API (graph.instagram.com)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests

import config

GRAPH_API_VERSION = os.getenv("IG_GRAPH_API_VERSION", "v21.0")
GRAPH_BASE = f"https://graph.instagram.com/{GRAPH_API_VERSION}"


@dataclass
class InstagramPublishResult:
    media_id: str
    permalink: str


class InstagramPublishError(RuntimeError):
    pass


def _graph_post(path: str, *, access_token: str, data: dict) -> dict:
    url = f"{GRAPH_BASE}/{path.lstrip('/')}"
    payload = {**data, "access_token": access_token}
    resp = requests.post(url, data=payload, timeout=120)
    body = resp.json() if resp.content else {}
    if not resp.ok:
        hint = ""
        if resp.status_code in {400, 403}:
            hint = (
                " Check instagram_business_content_publish permission and that "
                "video_url is a public HTTPS URL reachable by Meta."
            )
        raise InstagramPublishError(
            f"Instagram API POST {path} failed ({resp.status_code}): {body}.{hint}"
        )
    return body


def _graph_get(path: str, *, access_token: str, params: dict | None = None) -> dict:
    url = f"{GRAPH_BASE}/{path.lstrip('/')}"
    query = {"access_token": access_token, **(params or {})}
    resp = requests.get(url, params=query, timeout=60)
    body = resp.json() if resp.content else {}
    if not resp.ok:
        raise InstagramPublishError(
            f"Instagram API GET {path} failed ({resp.status_code}): {body}"
        )
    return body


def _build_caption(description: str, hashtags: str) -> str:
    parts = [description.strip()]
    if hashtags.strip():
        parts.append(hashtags.strip())
    caption = "\n\n".join(p for p in parts if p)
    return caption[:2200]


def publish_reel(
    video_url: str,
    *,
    caption: str,
    credential_ref: str = "IG_MAIN",
    poll_interval_seconds: int = 5,
    poll_timeout_seconds: int = 600,
) -> InstagramPublishResult:
    creds = config.get_instagram_credentials(credential_ref)
    user_id = creds["user_id"]
    token = creds["access_token"]

    container = _graph_post(
        f"{user_id}/media",
        access_token=token,
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
        },
    )
    container_id = container.get("id")
    if not container_id:
        raise InstagramPublishError(f"No container id in response: {container}")

    deadline = time.time() + poll_timeout_seconds
    status_code = ""
    while time.time() < deadline:
        status = _graph_get(
            container_id,
            access_token=token,
            params={"fields": "status_code,status"},
        )
        status_code = (status.get("status_code") or "").upper()
        print(f"  Instagram container {container_id}: {status_code or status}")
        if status_code == "FINISHED":
            break
        if status_code == "ERROR":
            raise InstagramPublishError(f"Container processing failed: {status}")
        time.sleep(poll_interval_seconds)
    else:
        raise InstagramPublishError(
            f"Timed out waiting for container {container_id} (last status={status_code})"
        )

    published = _graph_post(
        f"{user_id}/media_publish",
        access_token=token,
        data={"creation_id": container_id},
    )
    media_id = published.get("id")
    if not media_id:
        raise InstagramPublishError(f"No media id after publish: {published}")

    media = _graph_get(
        media_id,
        access_token=token,
        params={"fields": "permalink"},
    )
    permalink = media.get("permalink") or f"https://www.instagram.com/reel/{media_id}/"
    return InstagramPublishResult(media_id=media_id, permalink=permalink)


def publish_reel_from_row(
    video_url: str,
    *,
    description: str,
    hashtags: str,
    credential_ref: str = "IG_MAIN",
) -> InstagramPublishResult:
    caption = _build_caption(description, hashtags)
    return publish_reel(video_url, caption=caption, credential_ref=credential_ref)
