#!/usr/bin/env python3
"""Social Publisher — publish Drive videos to YouTube and Instagram from a Google Sheet queue."""

from __future__ import annotations

import argparse
import os
import sys
import traceback

_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SKILL_DIR)

import config  # noqa: E402
from drive import download_asset, download_video  # noqa: E402
from media_server import start_media_server  # noqa: E402
from publishers.instagram import (  # noqa: E402
    InstagramPublishError,
    publish_reel_from_row,
)
from publishers.youtube import upload_video  # noqa: E402
from sheets import (  # noqa: E402
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PUBLISHING,
    AccountRegistry,
    QueueRow,
    load_accounts,
    load_queue,
    update_queue_row,
)
from state import (  # noqa: E402
    StateStore,
    finalize_status,
    recover_stale_publishing,
    should_skip_platform,
)


def _resolve_credential_ref(
    accounts: AccountRegistry,
    row: QueueRow,
    platform: str,
) -> str:
    account = accounts.resolve(row.brand, platform) if row.brand else None
    if account is None:
        account = accounts.default_for_platform(platform)
    if account and account.credential_ref:
        return account.credential_ref
    return "YT_MAIN" if platform == "youtube" else "IG_MAIN"


def _parse_tags(hashtags: str) -> list[str]:
    tags: list[str] = []
    for token in hashtags.replace(",", " ").split():
        token = token.strip().lstrip("#")
        if token:
            tags.append(token[:30])
    return tags[:30]


def _validate_instagram_prereqs(platforms: list[str], *, dry_run: bool = False) -> None:
    if "instagram" not in platforms:
        return

    public_url = (config.PUBLIC_BASE_URL or "").strip().lower()
    if not public_url.startswith("https://"):
        raise ValueError(
            "Instagram requires HTTPS SOCIAL_PUBLISHER_PUBLIC_BASE_URL so Meta can "
            f"fetch video_url (got {config.PUBLIC_BASE_URL!r}). Use ngrok on local "
            "or configure VPS reverse proxy."
        )

    if dry_run:
        return

    try:
        config.get_instagram_access_token("IG_MAIN")
    except ValueError as exc:
        raise ValueError(
            f"Instagram credentials not ready: {exc}"
        ) from exc


def publish_row(
    row: QueueRow,
    *,
    accounts: AccountRegistry,
    platforms: list[str],
    dry_run: bool = False,
    keep_file: bool = False,
    spreadsheet_id: str | None = None,
) -> None:
    requested = [p.lower() for p in platforms]
    store = StateStore.load()
    successes: list[str] = []
    failures: dict[str, str] = {}

    print(f"\n=== Row {row.id} (sheet row {row.row_number}) ===")
    print(f"  brand={row.brand!r} platforms={requested}")

    _validate_instagram_prereqs(requested, dry_run=dry_run)

    if dry_run:
        print("  [dry-run] Would set status=publishing and download from Drive")
        if row.thumbnail_drive_file_id.strip():
            print(f"  [dry-run] Would download thumbnail: {row.thumbnail_drive_file_id}")
        for platform in requested:
            cred_ref = _resolve_credential_ref(accounts, row, platform)
            print(f"  [dry-run] Would publish to {platform} using {cred_ref}")
            if platform == "instagram":
                print(f"  [dry-run] Instagram video_url base: {config.PUBLIC_BASE_URL}")
        return

    update_queue_row(row, spreadsheet_id=spreadsheet_id, status=STATUS_PUBLISHING)
    store.mark_started(row.id)

    video_path: str | None = None
    thumbnail_path: str | None = None
    media_handle = None

    try:
        video_path = download_video(row.drive_file_id)
        print(f"  Downloaded: {video_path}")

        if row.thumbnail_drive_file_id.strip():
            thumbnail_path = download_asset(
                row.thumbnail_drive_file_id,
                ext=".jpg",
            )
            print(f"  Thumbnail downloaded: {thumbnail_path}")

        for platform in requested:
            if should_skip_platform(row, platform, store):
                print(f"  Skip {platform} (already published)")
                successes.append(platform)
                continue

            cred_ref = _resolve_credential_ref(accounts, row, platform)
            try:
                if platform == "youtube":
                    result = upload_video(
                        video_path,
                        title=row.title,
                        description=row.youtube_caption(),
                        visibility=row.visibility,
                        credential_ref=cred_ref,
                        tags=_parse_tags(row.hashtags),
                        contains_synthetic_media=True,
                        thumbnail_path=thumbnail_path,
                    )
                    row.yt_url = result.video_url
                    update_queue_row(
                        row,
                        spreadsheet_id=spreadsheet_id,
                        yt_url=result.video_url,
                    )
                    store.mark_platform_done(row.id, "youtube")
                    print(f"  YouTube OK: {result.video_url}")

                elif platform == "instagram":
                    media_handle = start_media_server(video_path)
                    print(f"  Serving video at {media_handle.public_url}")
                    result = publish_reel_from_row(
                        media_handle.public_url,
                        description=row.description,
                        hashtags=row.hashtags,
                        credential_ref=cred_ref,
                    )
                    row.ig_url = result.permalink
                    update_queue_row(
                        row,
                        spreadsheet_id=spreadsheet_id,
                        ig_url=result.permalink,
                    )
                    store.mark_platform_done(row.id, "instagram")
                    print(f"  Instagram OK: {result.permalink}")

                else:
                    raise ValueError(f"Unsupported platform: {platform}")

                successes.append(platform)

            except Exception as exc:  # noqa: BLE001
                failures[platform] = str(exc)
                print(f"  {platform} FAILED: {exc}")
            finally:
                if media_handle is not None:
                    media_handle.stop()
                    media_handle = None

        error_text = "; ".join(f"{k}: {v}" for k, v in failures.items())
        final_status = finalize_status(
            requested=requested,
            successes=successes,
            failures=failures,
        )
        update_queue_row(
            row,
            spreadsheet_id=spreadsheet_id,
            status=final_status,
            errors=error_text,
        )
        print(f"  Final status: {final_status}")

    except Exception as exc:  # noqa: BLE001
        update_queue_row(
            row,
            spreadsheet_id=spreadsheet_id,
            status=STATUS_FAILED,
            errors=str(exc),
        )
        print(f"  Row failed: {exc}")
        traceback.print_exc()
        raise
    finally:
        if media_handle is not None:
            media_handle.stop()
        if video_path and os.path.isfile(video_path) and not keep_file:
            try:
                os.remove(video_path)
            except OSError:
                pass
        if thumbnail_path and os.path.isfile(thumbnail_path) and not keep_file:
            try:
                os.remove(thumbnail_path)
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish videos from Google Sheet queue")
    parser.add_argument("--sheet-id", default=config.SHEET_ID, help="Google Sheet ID")
    parser.add_argument("--row", help="Publish a single queue row by id")
    parser.add_argument(
        "--all-pending",
        action="store_true",
        help="Publish all rows with status=pending",
    )
    parser.add_argument(
        "--platforms",
        default="youtube,instagram",
        help="Comma-separated platforms (default: youtube,instagram)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate without publishing")
    parser.add_argument(
        "--keep-file",
        action="store_true",
        help="Keep downloaded video file after publish",
    )
    parser.add_argument(
        "--recover-stale",
        action="store_true",
        help="Reset rows stuck in publishing before running",
    )
    args = parser.parse_args(argv)

    sheet_id = (args.sheet_id or "").strip()
    if not sheet_id:
        print("Error: set SOCIAL_PUBLISHER_SHEET_ID or pass --sheet-id", file=sys.stderr)
        return 1

    platforms = [p.strip().lower() for p in args.platforms.split(",") if p.strip()]
    if not platforms:
        print("Error: no platforms specified", file=sys.stderr)
        return 1

    if args.recover_stale:
        recovered = recover_stale_publishing(sheet_id)
        if recovered:
            print(f"Recovered stale rows: {', '.join(recovered)}")

    accounts = load_accounts(sheet_id)

    if args.row:
        rows = load_queue(sheet_id, row_id=args.row)
        if not rows:
            print(f"No queue row found with id={args.row!r}", file=sys.stderr)
            return 1
    elif args.all_pending:
        rows = load_queue(sheet_id, statuses=[STATUS_PENDING])
        if not rows:
            print("No pending rows found.")
            return 0
    else:
        parser.error("Specify --row <id> or --all-pending")

    exit_code = 0
    for row in rows:
        try:
            publish_row(
                row,
                accounts=accounts,
                platforms=platforms,
                dry_run=args.dry_run,
                keep_file=args.keep_file,
                spreadsheet_id=sheet_id,
            )
        except Exception:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
