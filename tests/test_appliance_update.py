"""Appliance image update check (notify only; host pull/recreate)."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.appliance_update import (
    APPLIANCE_IMAGE,
    APPLIANCE_NAME,
    _same_commit,
    check_appliance_image,
    running_appliance_identity,
)
from core.version import app_version, git_sha


def test_same_commit_prefix():
    assert _same_commit("abcdef1234567890", "abcdef1") is True
    assert _same_commit("abcdef1234567890", "deadbeef") is False
    assert _same_commit("abc", "abcdef1") is False


def test_no_sha_is_not_an_update(monkeypatch):
    monkeypatch.delenv("AMM_GIT_SHA", raising=False)
    monkeypatch.delenv("AMM_VERSION", raising=False)
    github = MagicMock()
    payload = check_appliance_image(github)
    github.get_commit.assert_not_called()
    assert payload["name"] == APPLIANCE_NAME
    assert payload["update_available"] is False
    assert git_sha() == ""
    assert "no git SHA" in (payload.get("detail") or "")


def test_running_identity_uses_env(monkeypatch):
    monkeypatch.setenv("AMM_GIT_SHA", "0123456789abcdef")
    monkeypatch.setenv("AMM_VERSION", "1.2.3")
    ident = running_appliance_identity()
    assert ident["installed_version"] == "1.2.3 (0123456)"
    assert ident["running_sha"] == "0123456789abcdef"
    assert ident["update_available"] is False
    assert APPLIANCE_IMAGE in ident["apply_hint"]
    assert app_version() == "1.2.3"


def test_newer_main_commit_is_available(monkeypatch):
    monkeypatch.setenv("AMM_GIT_SHA", "aaaaaaaaaaaaaaaa")
    github = MagicMock()
    github.get_commit.return_value = {"sha": "bbbbbbbbbbbbbbbb"}
    github.compare_commits.return_value = {"status": "ahead"}
    payload = check_appliance_image(github)
    github.get_commit.assert_called_once()
    github.compare_commits.assert_called_once()
    assert payload["update_available"] is True
    assert payload["latest_sha"] == "bbbbbbbbbbbbbbbb"
    assert payload["latest_version"] == "bbbbbbb"


def test_ahead_of_main_is_not_an_update(monkeypatch):
    monkeypatch.setenv("AMM_GIT_SHA", "cccccccccccccccc")
    github = MagicMock()
    github.get_commit.return_value = {"sha": "bbbbbbbbbbbbbbbb"}
    github.compare_commits.return_value = {"status": "behind"}
    payload = check_appliance_image(github)
    assert payload["update_available"] is False


def test_current_commit_is_not_available(monkeypatch):
    monkeypatch.setenv("AMM_GIT_SHA", "abcdef1234567890deadbeef")
    github = MagicMock()
    github.get_commit.return_value = {"sha": "abcdef1234567890deadbeefcafe"}
    payload = check_appliance_image(github)
    github.compare_commits.assert_not_called()
    assert payload["update_available"] is False
