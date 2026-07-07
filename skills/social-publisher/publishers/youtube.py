"""YouTube resumable upload via Data API v3."""

from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config


YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


@dataclass
class YouTubePublishResult:
    video_id: str
    video_url: str


def _build_service(credential_ref: str):
    creds_info = config.get_youtube_credentials(credential_ref)
    credentials = Credentials(
        token=None,
        refresh_token=creds_info["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=creds_info["client_id"],
        client_secret=creds_info["client_secret"],
        scopes=[YOUTUBE_UPLOAD_SCOPE],
    )
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def _privacy_status(visibility: str) -> str:
    value = (visibility or "public").strip().lower()
    if value in {"public", "unlisted", "private"}:
        return value
    return "public"


def _thumbnail_mimetype(path: str) -> str:
    guessed, _ = mimetypes.guess_type(path)
    if guessed in {"image/jpeg", "image/png"}:
        return guessed
    ext = os.path.splitext(path)[1].lower()
    if ext == ".png":
        return "image/png"
    return "image/jpeg"


def _set_thumbnail(youtube, video_id: str, thumbnail_path: str) -> None:
    mimetype = _thumbnail_mimetype(thumbnail_path)
    media = MediaFileUpload(thumbnail_path, mimetype=mimetype, resumable=True)
    youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
    print(f"  YouTube thumbnail set from {os.path.basename(thumbnail_path)}")


def upload_video(
    video_path: str,
    *,
    title: str,
    description: str,
    visibility: str = "public",
    credential_ref: str = "YT_MAIN",
    category_id: str = "22",
    tags: list[str] | None = None,
    contains_synthetic_media: bool = True,
    thumbnail_path: str | None = None,
) -> YouTubePublishResult:
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    youtube = _build_service(credential_ref)
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": _privacy_status(visibility),
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": contains_synthetic_media,
        },
    }
    if tags:
        body["snippet"]["tags"] = tags[:30]

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  YouTube upload: {pct}%")

    video_id = response["id"]

    if thumbnail_path:
        if not os.path.isfile(thumbnail_path):
            raise FileNotFoundError(f"Thumbnail not found: {thumbnail_path}")
        _set_thumbnail(youtube, video_id, thumbnail_path)

    return YouTubePublishResult(
        video_id=video_id,
        video_url=f"https://www.youtube.com/watch?v={video_id}",
    )
