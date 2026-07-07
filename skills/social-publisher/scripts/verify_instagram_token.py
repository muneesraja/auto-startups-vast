#!/usr/bin/env python3
"""Verify Instagram token and confirm it matches IG_USER_ID in .env."""

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
from instagram_tokens import InstagramTokenError, verify_token  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Instagram access token")
    parser.add_argument(
        "--credential-ref",
        default="IG_MAIN",
        help="Credential ref prefix (default: IG_MAIN)",
    )
    parser.add_argument(
        "--use-short-lived",
        action="store_true",
        help="Verify IG_SHORT_LIVED_TOKEN instead of IG_ACCESS_TOKEN",
    )
    args = parser.parse_args()

    ref = args.credential_ref.strip().upper()
    if args.use_short_lived:
        token = (
            os.getenv(f"{ref}_SHORT_LIVED_TOKEN")
            or os.getenv("IG_SHORT_LIVED_TOKEN", "")
        ).strip()
    else:
        try:
            token = config.get_instagram_access_token(ref)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1

    expected_user_id = (
        os.getenv(f"{ref}_USER_ID")
        or os.getenv("IG_USER_ID", "")
    ).strip()

    try:
        info = verify_token(token)
    except InstagramTokenError as exc:
        print(f"Verify failed: {exc}", file=sys.stderr)
        return 1

    user_id = str(info.get("user_id", ""))
    username = info.get("username", "")
    print(f"OK: username=@{username} user_id={user_id}")

    if expected_user_id and user_id != expected_user_id:
        print(
            f"WARNING: token user_id {user_id} does not match IG_USER_ID={expected_user_id}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
