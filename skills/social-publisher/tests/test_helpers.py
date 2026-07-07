"""Tests for social-publisher helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from drive import normalize_drive_file_id
from sheets import AccountRegistry, AccountRow
from state import finalize_status


def test_normalize_drive_file_id_plain():
    assert normalize_drive_file_id("15O-l6ddlc1g3IEd17kwLanJeY6NI8Xa5") == "15O-l6ddlc1g3IEd17kwLanJeY6NI8Xa5"


def test_normalize_drive_file_id_url():
    url = "https://drive.google.com/file/d/abc123XYZ/view?usp=sharing"
    assert normalize_drive_file_id(url) == "abc123XYZ"


def test_account_registry_resolve():
    reg = AccountRegistry(
        rows=[
            AccountRow("BrandA", "youtube", "@a", "YT_MAIN", True),
            AccountRow("BrandA", "instagram", "a.ig", "IG_MAIN", True),
        ]
    )
    yt = reg.resolve("BrandA", "youtube")
    assert yt is not None
    assert yt.credential_ref == "YT_MAIN"
    assert reg.resolve("BrandB", "youtube") is None


def test_finalize_status_all_success():
    assert finalize_status(
        requested=["youtube", "instagram"],
        successes=["youtube", "instagram"],
        failures={},
    ) == "published"


def test_finalize_status_partial():
    assert finalize_status(
        requested=["youtube", "instagram"],
        successes=["youtube"],
        failures={"instagram": "timeout"},
    ) == "partial"
