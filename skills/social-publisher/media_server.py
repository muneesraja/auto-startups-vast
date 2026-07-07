"""Ephemeral HTTP server to expose a local video file to Instagram Graph API."""

from __future__ import annotations

import os
import secrets
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import urlparse

import config


@dataclass
class MediaServerHandle:
    token: str
    public_url: str
    stop: Callable[[], None]


class _MediaHandler(BaseHTTPRequestHandler):
    file_path: str = ""
    token: str = ""

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        expected = f"/media/{self.token}.mp4"
        if parsed.path != expected:
            self.send_error(404, "Not found")
            return
        if not os.path.isfile(self.file_path):
            self.send_error(404, "File missing")
            return
        try:
            with open(self.file_path, "rb") as fh:
                data = fh.read()
        except OSError:
            self.send_error(500, "Read error")
            return
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        expected = f"/media/{self.token}.mp4"
        if parsed.path != expected or not os.path.isfile(self.file_path):
            self.send_error(404, "Not found")
            return
        size = os.path.getsize(self.file_path)
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(size))
        self.end_headers()


def start_media_server(file_path: str) -> MediaServerHandle:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Cannot serve missing file: {file_path}")

    token = secrets.token_urlsafe(24)
    handler_cls = type(
        "BoundMediaHandler",
        (_MediaHandler,),
        {"file_path": file_path, "token": token},
    )
    server = ThreadingHTTPServer(
        (config.MEDIA_SERVER_HOST, config.MEDIA_SERVER_PORT),
        handler_cls,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base = config.PUBLIC_BASE_URL.rstrip("/")
    public_url = f"{base}/media/{token}.mp4"

    def stop() -> None:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    return MediaServerHandle(token=token, public_url=public_url, stop=stop)
