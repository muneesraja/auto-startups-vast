#!/usr/bin/env python3
"""One-time helper to mint a YouTube refresh token with youtube.upload scope."""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _SKILL_DIR)

# Load project .env (repo root) and optional ~/.hermes/.env via config conventions
_workspace_root = os.path.dirname(os.path.dirname(_SKILL_DIR))
load_dotenv(os.path.join(_workspace_root, ".env"), override=False)
load_dotenv(os.path.join(os.path.expanduser("~"), ".hermes", ".env"), override=False)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> int:
    client_id = os.getenv("YT_CLIENT_ID", "").strip()
    client_secret = os.getenv("YT_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        print(
            "Set YT_CLIENT_ID and YT_CLIENT_SECRET in .env before running.",
            file=sys.stderr,
        )
        return 1

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\nAdd to ~/.hermes/.env or project .env:\n")
    print(f"YT_REFRESH_TOKEN={creds.refresh_token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
