"""Google Sheets queue and account registry for social-publisher."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import config
from gws_cli import read_sheet_range, update_sheet_range

QUEUE_COLUMNS = [
    "id",
    "brand",
    "drive_file_id",
    "thumbnail_drive_file_id",
    "title",
    "description",
    "hashtags",
    "platforms",
    "visibility",
    "status",
    "yt_url",
    "ig_url",
    "errors",
]

ACCOUNTS_COLUMNS = [
    "brand",
    "platform",
    "account_ref",
    "credential_ref",
    "enabled",
]

STATUS_PENDING = "pending"
STATUS_PUBLISHING = "publishing"
STATUS_PUBLISHED = "published"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"


@dataclass
class QueueRow:
    row_number: int  # 1-based sheet row (includes header)
    id: str
    brand: str
    drive_file_id: str
    thumbnail_drive_file_id: str
    title: str
    description: str
    hashtags: str
    platforms: str
    visibility: str
    status: str
    yt_url: str
    ig_url: str
    errors: str

    def platform_list(self) -> list[str]:
        return [p.strip().lower() for p in self.platforms.split(",") if p.strip()]

    def youtube_caption(self) -> str:
        parts = [self.description.strip()]
        if self.hashtags.strip():
            parts.append(self.hashtags.strip())
        return "\n\n".join(p for p in parts if p)


@dataclass
class AccountRow:
    brand: str
    platform: str
    account_ref: str
    credential_ref: str
    enabled: bool = True


@dataclass
class AccountRegistry:
    rows: list[AccountRow] = field(default_factory=list)

    def resolve(self, brand: str, platform: str) -> AccountRow | None:
        brand_l = brand.strip().lower()
        platform_l = platform.strip().lower()
        for row in self.rows:
            if (
                row.brand.strip().lower() == brand_l
                and row.platform.strip().lower() == platform_l
                and row.enabled
            ):
                return row
        return None

    def default_for_platform(self, platform: str) -> AccountRow | None:
        platform_l = platform.strip().lower()
        enabled = [r for r in self.rows if r.platform.strip().lower() == platform_l and r.enabled]
        return enabled[0] if enabled else None


def _row_to_dict(headers: list[str], values: list[str]) -> dict[str, str]:
    padded = values + [""] * (len(headers) - len(values))
    return {headers[i]: padded[i].strip() for i in range(len(headers))}


def _truthy(value: str) -> bool:
    return value.strip().upper() in {"TRUE", "YES", "1", "Y"}


def load_accounts(spreadsheet_id: str | None = None) -> AccountRegistry:
    sheet_id = spreadsheet_id or config.SHEET_ID
    if not sheet_id:
        raise ValueError("SOCIAL_PUBLISHER_SHEET_ID is not set")
    raw = read_sheet_range(sheet_id, f"{config.ACCOUNTS_TAB}!A:E")
    if not raw:
        return AccountRegistry()
    headers = [h.strip().lower() for h in raw[0]]
    rows: list[AccountRow] = []
    for line in raw[1:]:
        if not any(cell.strip() for cell in line):
            continue
        data = _row_to_dict(headers, line)
        rows.append(
            AccountRow(
                brand=data.get("brand", ""),
                platform=data.get("platform", ""),
                account_ref=data.get("account_ref", ""),
                credential_ref=data.get("credential_ref", ""),
                enabled=_truthy(data.get("enabled", "TRUE")),
            )
        )
    return AccountRegistry(rows=rows)


def load_queue(
    spreadsheet_id: str | None = None,
    *,
    statuses: Iterable[str] | None = None,
    row_id: str | None = None,
) -> list[QueueRow]:
    sheet_id = spreadsheet_id or config.SHEET_ID
    if not sheet_id:
        raise ValueError("SOCIAL_PUBLISHER_SHEET_ID is not set")

    raw = read_sheet_range(sheet_id, f"{config.QUEUE_TAB}!A:M")
    if not raw:
        return []

    headers = [h.strip().lower() for h in raw[0]]
    allowed_statuses = {s.lower() for s in statuses} if statuses else None
    rows: list[QueueRow] = []

    for idx, line in enumerate(raw[1:], start=2):
        if not any(cell.strip() for cell in line):
            continue
        data = _row_to_dict(headers, line)
        row_id_val = data.get("id", "")
        status = data.get("status", "").lower()
        if row_id and row_id_val != row_id:
            continue
        if allowed_statuses is not None and status not in allowed_statuses:
            continue
        rows.append(
            QueueRow(
                row_number=idx,
                id=row_id_val,
                brand=data.get("brand", ""),
                drive_file_id=data.get("drive_file_id", ""),
                thumbnail_drive_file_id=data.get("thumbnail_drive_file_id", ""),
                title=data.get("title", ""),
                description=data.get("description", ""),
                hashtags=data.get("hashtags", ""),
                platforms=data.get("platforms", ""),
                visibility=data.get("visibility", "public") or "public",
                status=data.get("status", ""),
                yt_url=data.get("yt_url", ""),
                ig_url=data.get("ig_url", ""),
                errors=data.get("errors", ""),
            )
        )
    return rows


def _col_letter(index: int) -> str:
    """Convert 0-based column index to A1 letter."""
    result = ""
    n = index + 1
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def update_queue_row(
    row: QueueRow,
    *,
    spreadsheet_id: str | None = None,
    status: str | None = None,
    yt_url: str | None = None,
    ig_url: str | None = None,
    errors: str | None = None,
) -> None:
    sheet_id = spreadsheet_id or config.SHEET_ID
    if status is not None:
        row.status = status
    if yt_url is not None:
        row.yt_url = yt_url
    if ig_url is not None:
        row.ig_url = ig_url
    if errors is not None:
        row.errors = errors

    # Batch update status (I), yt_url (J), ig_url (K), errors (L)
    start_col = _col_letter(QUEUE_COLUMNS.index("status"))
    end_col = _col_letter(QUEUE_COLUMNS.index("errors"))
    range_a1 = f"{config.QUEUE_TAB}!{start_col}{row.row_number}:{end_col}{row.row_number}"
    values = [[row.status, row.yt_url, row.ig_url, row.errors]]
    update_sheet_range(sheet_id, range_a1, values)
