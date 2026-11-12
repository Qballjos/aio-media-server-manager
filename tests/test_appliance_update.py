"""Appliance image update check (notify only; host pull/recreate)."""

from __future__ import annotations

from unittest.mock import MagicMock

import core.version as version
from core.appliance_update import (
    APPLIANCE_DOCKER_WORKFLOW,
    APPLIANCE_IMAGE,
    APPLIANCE_NIGHTLY_IMAGE,
    APPLIANCE_NIGHTLY_WORKFLOW,
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


def test_image_identity_overrides_stale_compose_environment(monkeypatch):
    monkeypatch.setenv("AMM_VERSION", "0.3.0")
    monkeypatch.setenv("AMM_GIT_SHA", "06c3ca0a5088894580846fad30a4dac0e32afa68")
    current_sha = "22be3d7713bbe4ac693188d70645695bf0999104"
    monkeypatch.setattr(version, "_IMAGE_VERSION", "0.4.1-nightly")
    monkeypatch.setattr(version, "_IMAGE_GIT_SHA", current_sha)
    github = MagicMock()
    github.latest_workflow_run_sha.return_value = current_sha

    payload = check_appliance_image(github)

    assert payload["installed_version"] == "0.4.1-nightly (22be3d7)"
    assert payload["running_sha"] == current_sha
    assert payload["update_available"] is False
    github.compare_commits.assert_not_called()
    github.latest_workflow_run_sha.assert_called_once_with(
        "Qballjos/aio-media-server-manager",
        APPLIANCE_NIGHTLY_WORKFLOW,
        branch="beta",
        status="success",
    )
    github.latest_workflow_run_sha.return_value = "b" * 40
    github.compare_commits.return_value = {"status": "ahead"}
    assert check_appliance_image(github)["update_available"] is True
    github.compare_commits.assert_called_once_with(
        "Qballjos/aio-media-server-manager", current_sha, "b" * 40
    )


def test_image_without_revision_does_not_inherit_an_old_revision(monkeypatch):
    monkeypatch.setenv("AMM_GIT_SHA", "06c3ca0a5088894580846fad30a4dac0e32afa68")
    monkeypatch.setattr(version, "_IMAGE_VERSION", "0.4.1")
    monkeypatch.setattr(version, "_IMAGE_GIT_SHA", "")
    github = MagicMock()
    assert check_appliance_image(github)["update_available"] is False
    assert git_sha() == ""
    github.latest_workflow_run_sha.assert_not_called()


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
    assert "main" in (payload.get("detail") or "")


def test_nightly_checks_nightly_not_main(monkeypatch):
    monkeypatch.setenv("AMM_GIT_SHA", "aaaaaaaaaaaaaaaa")
    monkeypatch.setenv("AMM_VERSION", "0.3.0-nightly")
    github = MagicMock()
    github.latest_workflow_run_sha.return_value = "bbbbbbbbbbbbbbbb"
    github.compare_commits.return_value = {"status": "ahead"}
    payload = check_appliance_image(github)
    github.latest_workflow_run_sha.assert_called_once_with(
        "Qballjos/aio-media-server-manager",
        APPLIANCE_NIGHTLY_WORKFLOW,
        branch="beta",
        status="success",
    )
    assert payload["channel"] == "nightly"
    assert payload["update_available"] is True
    assert APPLIANCE_NIGHTLY_IMAGE in payload["apply_hint"]
    assert ":latest" not in payload["apply_hint"]


def test_main_does_not_check_nightly(monkeypatch):
    monkeypatch.setenv("AMM_GIT_SHA", "aaaaaaaaaaaaaaaa")
    monkeypatch.setenv("AMM_VERSION", "0.3.0")
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
    assert payload["channel"] == "main"
    assert APPLIANCE_IMAGE in payload["apply_hint"]
    assert ":nightly" not in payload["apply_hint"]
