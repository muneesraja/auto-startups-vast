#!/usr/bin/env python3
"""Exchange IG_SHORT_LIVED_TOKEN for a long-lived IG_ACCESS_TOKEN."""

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

import config  # noqa: E402
from instagram_tokens import InstagramTokenError, exchange_short_lived_token  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Exchange Instagram short-lived token for long-lived")
    parser.add_argument(
        "--credential-ref",
        default="IG_MAIN",
        help="Credential ref prefix (default: IG_MAIN)",
    )
    args = parser.parse_args()

    ref = args.credential_ref.strip().upper()
    short_token = (
        os.getenv(f"{ref}_SHORT_LIVED_TOKEN")
        or os.getenv("IG_SHORT_LIVED_TOKEN", "")
    ).strip()
    app_secret = (
        os.getenv(f"{ref}_APP_SECRET")
        or os.getenv("IG_APP_SECRET", "")
    ).strip()

    if not short_token:
        print(
            f"Set IG_SHORT_LIVED_TOKEN (or {ref}_SHORT_LIVED_TOKEN) in .env first.",
            file=sys.stderr,
        )
        return 1
    if not app_secret:
        print(
            f"Set IG_APP_SECRET (or {ref}_APP_SECRET) in .env first.",
            file=sys.stderr,
        )
        return 1

    try:
        result = exchange_short_lived_token(short_token, app_secret)
    except InstagramTokenError as exc:
        print(f"Exchange failed: {exc}", file=sys.stderr)
        return 1

    token = result["access_token"]
    expires_in = result.get("expires_in", "?")

    print("\nAdd to ~/.hermes/.env or project .env:\n")
    print(f"IG_ACCESS_TOKEN={token}")
    print(f"\n# expires_in: {expires_in} seconds (~{int(expires_in) // 86400 if str(expires_in).isdigit() else '?'} days)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
