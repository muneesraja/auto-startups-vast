"""Local idempotency and stale publishing recovery."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import config
from sheets import (
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_PENDING,
    STATUS_PUBLISHED,
    STATUS_PUBLISHING,
    QueueRow,
    load_queue,
    update_queue_row,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class RowState:
    row_id: str
    started_at: str = ""
    youtube_done: bool = False
    instagram_done: bool = False


@dataclass
class StateStore:
    path: str
    rows: dict[str, RowState] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | None = None) -> "StateStore":
        file_path = path or config.STATE_FILE
        if not os.path.isfile(file_path):
            return cls(path=file_path)
        with open(file_path, encoding="utf-8") as fh:
            raw = json.load(fh)
        rows = {
            key: RowState(**value)
            for key, value in (raw.get("rows") or {}).items()
        }
        return cls(path=file_path, rows=rows)

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        payload = {
            "rows": {
                key: {
                    "row_id": st.row_id,
                    "started_at": st.started_at,
                    "youtube_done": st.youtube_done,
                    "instagram_done": st.instagram_done,
                }
                for key, st in self.rows.items()
            }
        }
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

    def get(self, row_id: str) -> RowState:
        if row_id not in self.rows:
            self.rows[row_id] = RowState(row_id=row_id)
        return self.rows[row_id]

    def mark_started(self, row_id: str) -> None:
        st = self.get(row_id)
        st.started_at = _utcnow().isoformat()
        self.save()

    def mark_platform_done(self, row_id: str, platform: str) -> None:
        st = self.get(row_id)
        if platform == "youtube":
            st.youtube_done = True
        elif platform == "instagram":
            st.instagram_done = True
        self.save()


def recover_stale_publishing(
    spreadsheet_id: str | None = None,
    *,
    stale_minutes: int | None = None,
) -> list[str]:
    """Reset rows stuck in publishing longer than stale_minutes."""
    minutes = stale_minutes if stale_minutes is not None else config.STALE_PUBLISHING_MINUTES
    cutoff = _utcnow() - timedelta(minutes=minutes)
    store = StateStore.load()
    recovered: list[str] = []

    publishing_rows = load_queue(spreadsheet_id, statuses=[STATUS_PUBLISHING])
    for row in publishing_rows:
        st = store.get(row.id)
        started = _parse_ts(st.started_at)
        if started and started > cutoff:
            continue
        row.status = STATUS_PENDING
        row.errors = (
            f"Recovered stale publishing state at {_utcnow().isoformat()}"
        )
        update_queue_row(row, status=STATUS_PENDING, errors=row.errors)
        recovered.append(row.id)
        st.started_at = ""
        store.save()
    return recovered


def should_skip_platform(row: QueueRow, platform: str, store: StateStore) -> bool:
    platform = platform.lower()
    if platform == "youtube" and row.yt_url.strip():
        return True
    if platform == "instagram" and row.ig_url.strip():
        return True
    st = store.get(row.id)
    if platform == "youtube" and st.youtube_done:
        return True
    if platform == "instagram" and st.instagram_done:
        return True
    return False


def finalize_status(
    *,
    requested: list[str],
    successes: list[str],
    failures: dict[str, str],
) -> str:
    if failures and successes:
        return STATUS_PARTIAL
    if failures:
        return STATUS_FAILED
    if successes and len(successes) == len(requested):
        return STATUS_PUBLISHED
    return STATUS_FAILED
