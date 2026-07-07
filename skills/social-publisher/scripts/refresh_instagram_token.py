#!/usr/bin/env python3
"""Refresh a long-lived Instagram access token before it expires."""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _SKILL_DIR)

_workspace_root = os.path.dirname(os.path.dirname(_SKILL_DIR))
load_dotenv(os.path.join(_workspace_root, ".env"), override=False)
load_dotenv(os.path.join(os.path.expanduser("~"), ".hermes", ".env"), override=False)

from instagram_tokens import InstagramTokenError, refresh_long_lived_token  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh Instagram long-lived access token")
    parser.add_argument(
        "--credential-ref",
        default="IG_MAIN",
        help="Credential ref prefix (default: IG_MAIN)",
    )
    args = parser.parse_args()

    ref = args.credential_ref.strip().upper()
    access_token = (
        os.getenv(f"{ref}_ACCESS_TOKEN")
        or os.getenv("IG_ACCESS_TOKEN", "")
    ).strip()

    if not access_token:
        print(
            f"Set IG_ACCESS_TOKEN (or {ref}_ACCESS_TOKEN) in .env first.",
            file=sys.stderr,
        )
        return 1

    try:
        result = refresh_long_lived_token(access_token)
    except InstagramTokenError as exc:
        print(f"Refresh failed: {exc}", file=sys.stderr)
        return 1

    token = result["access_token"]
    expires_in = result.get("expires_in", "?")

    print("\nUpdate in ~/.hermes/.env or project .env:\n")
    print(f"IG_ACCESS_TOKEN={token}")
    print(f"\n# expires_in: {expires_in} seconds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
