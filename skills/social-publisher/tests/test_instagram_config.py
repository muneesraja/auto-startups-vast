"""Tests for Instagram token/config helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config


def test_get_instagram_access_token_prefers_long_lived(monkeypatch):
    monkeypatch.setenv("IG_ACCESS_TOKEN", "long-token")
    monkeypatch.setenv("IG_SHORT_LIVED_TOKEN", "short-token")
    monkeypatch.setenv("IG_APP_SECRET", "secret")
    assert config.get_instagram_access_token() == "long-token"


def test_get_instagram_access_token_auto_exchange(monkeypatch):
    monkeypatch.delenv("IG_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("IG_SHORT_LIVED_TOKEN", "short-token")
    monkeypatch.setenv("IG_APP_SECRET", "secret")

    with patch("instagram_tokens.exchange_short_lived_token") as mock_exchange:
        mock_exchange.return_value = {"access_token": "exchanged", "expires_in": 5184000}
        token = config.get_instagram_access_token()
    assert token == "exchanged"
    mock_exchange.assert_called_once_with("short-token", "secret")
