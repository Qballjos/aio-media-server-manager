"""Appliance image update check (notify only; host pull/recreate)."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.appliance_update import (
    APPLIANCE_DOCKER_WORKFLOW,
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
    github.latest_workflow_run_sha.assert_not_called()
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


def test_newer_published_image_is_available(monkeypatch):
    monkeypatch.setenv("AMM_GIT_SHA", "aaaaaaaaaaaaaaaa")
    github = MagicMock()
    github.latest_workflow_run_sha.return_value = "bbbbbbbbbbbbbbbb"
    github.compare_commits.return_value = {"status": "ahead"}
    payload = check_appliance_image(github)
    github.latest_workflow_run_sha.assert_called_once_with(
        "Qballjos/aio-media-server-manager",
        APPLIANCE_DOCKER_WORKFLOW,
        branch="main",
        status="success",
    )
    github.compare_commits.assert_called_once_with(
        "Qballjos/aio-media-server-manager",
        "aaaaaaaaaaaaaaaa",
        "bbbbbbbbbbbbbbbb",
    )
    assert payload["update_available"] is True
    assert payload["latest_sha"] == "bbbbbbbbbbbbbbbb"
    assert payload["latest_version"] == "bbbbbbb"


def test_docs_commits_on_main_do_not_count_as_image_update(monkeypatch):
    """main may move for docs; only a newer Docker workflow SHA should notify."""
    monkeypatch.setenv("AMM_GIT_SHA", "aaaaaaaaaaaaaaaa")
    github = MagicMock()
    github.latest_workflow_run_sha.return_value = "aaaaaaaaaaaaaaaa"
    payload = check_appliance_image(github)
    github.compare_commits.assert_not_called()
    assert payload["update_available"] is False


def test_running_newer_than_published_is_not_an_update(monkeypatch):
    monkeypatch.setenv("AMM_GIT_SHA", "cccccccccccccccc")
    github = MagicMock()
    github.latest_workflow_run_sha.return_value = "bbbbbbbbbbbbbbbb"
    github.compare_commits.return_value = {"status": "behind"}
    payload = check_appliance_image(github)
    assert payload["update_available"] is False


def test_no_docker_runs_is_not_an_update(monkeypatch):
    monkeypatch.setenv("AMM_GIT_SHA", "aaaaaaaaaaaaaaaa")
    github = MagicMock()
    github.latest_workflow_run_sha.return_value = ""
    payload = check_appliance_image(github)
    assert payload["update_available"] is False
    assert "No successful Docker" in (payload.get("detail") or "")
