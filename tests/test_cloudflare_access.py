"""Cloudflare Access apps created from AIO for *Arr, downloads, and Seerr."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.cloudflare_access import apply_access, policy_include, save_access_state
from core.cloudflare_api import CloudflareApiError
from core.public_hostnames import ACCESS_GATE_APPS
from core.settings import Settings


def test_access_gate_includes_seerr_and_skips_media_servers():
    assert "seerr" in ACCESS_GATE_APPS
    assert "sonarr" in ACCESS_GATE_APPS
    assert "qbittorrent" in ACCESS_GATE_APPS
    assert "neutarr" in ACCESS_GATE_APPS
    for name in ("jellyfin", "plex", "manager", "shelfmark", "grimmory"):
        assert name not in ACCESS_GATE_APPS


def test_policy_include_emails_or_locked_cloudflare_only():
    google = [{"id": "g", "type": "google", "restrict_to_account_members": False}]
    assert policy_include(google, ["me@example.com"]) == [{"email": {"email": "me@example.com"}}]
    with pytest.raises(CloudflareApiError):
        policy_include(google, [])
    locked = [{"id": "cf", "type": "cloudflare", "restrict_to_account_members": True}]
    assert policy_include(locked, []) == [{"login_method": {"id": "cf"}}]


def _routes():
    return [
        {
            "name": "sonarr",
            "display_name": "Sonarr",
            "enabled": True,
            "hostname": "tv.example.com",
            "access_gate": True,
        },
        {
            "name": "seerr",
            "display_name": "Seerr",
            "enabled": True,
            "hostname": "requests.example.com",
            "access_gate": True,
        },
        {
            "name": "jellyfin",
            "display_name": "Jellyfin",
            "enabled": True,
            "hostname": "watch.example.com",
            "access_gate": False,
        },
        {
            "name": "manager",
            "display_name": "AIO",
            "enabled": True,
            "hostname": "media.example.com",
            "access_gate": False,
        },
    ]


@pytest.mark.asyncio
async def test_apply_access_creates_arr_and_seerr_only(tmp_path: Path, monkeypatch):
    cfg = Settings(config_dir=tmp_path)
    monkeypatch.setattr("core.cloudflare_access.settings", cfg)
    calls: list[tuple] = []

    async def fake_cf(method, path, **kwargs):
        calls.append((method, path, kwargs.get("json_body")))
        if method == "GET" and path.endswith("/identity_providers"):
            return [{"id": "idp1", "name": "Google", "type": "google", "config": {}}]
        if method == "GET" and path.endswith("/access/policies"):
            return []
        if method == "POST" and path.endswith("/access/policies"):
            return {"id": "pol1"}
        if method == "GET" and path.endswith("/access/apps"):
            return []
        if method == "POST" and path.endswith("/access/apps"):
            return {"id": "app-" + kwargs["json_body"]["domain"].split(".")[0]}
        raise AssertionError((method, path))

    monkeypatch.setattr("core.cloudflare_access._cf_request", fake_cf)
    monkeypatch.setattr("core.cloudflare_access.decode_tunnel_token", lambda: {"account_id": "acc"})
    monkeypatch.setattr("core.cloudflare_access.planned_routes", lambda **kwargs: _routes())

    result = await apply_access(emails="me@example.com")
    assert {row["name"] for row in result["applied"]} == {"sonarr", "seerr"}
    posts = [body for method, path, body in calls if method == "POST" and path.endswith("/access/apps")]
    assert {body["domain"] for body in posts} == {"tv.example.com", "requests.example.com"}
    seerr = next(body for body in posts if body["domain"] == "requests.example.com")
    assert seerr["session_duration"] == "24h"
    assert seerr["type"] == "self_hosted"
    assert seerr["policies"] == [{"id": "pol1", "precedence": 1}]
    assert seerr["allowed_idps"] == ["idp1"]
    sonarr = next(body for body in posts if body["domain"] == "tv.example.com")
    assert sonarr["session_duration"] == "8h"


@pytest.mark.asyncio
async def test_apply_access_removes_only_apps_aio_created(tmp_path: Path, monkeypatch):
    cfg = Settings(config_dir=tmp_path)
    monkeypatch.setattr("core.cloudflare_access.settings", cfg)
    save_access_state(
        {
            "emails": ["me@example.com"],
            "policy_id": "pol1",
            "apps": {
                "sonarr": {"id": "app-sonarr", "hostname": "tv.example.com", "created": True},
                "seerr": {"id": "hand-made", "hostname": "requests.example.com", "created": False},
            },
        }
    )
    deleted: list[str] = []

    async def fake_cf(method, path, **kwargs):
        if method == "DELETE":
            deleted.append(path)
            return {}
        if method == "GET" and path.endswith("/identity_providers"):
            return [{"id": "cf", "name": "Cloudflare", "type": "cloudflare", "config": {"restrict_to_account_members": True}}]
        if method == "GET" and path.endswith("/access/policies/pol1"):
            return {"id": "pol1", "name": "AIO Access", "decision": "allow", "include": []}
        if method == "PUT" and path.endswith("/access/policies/pol1"):
            return {"id": "pol1"}
        if method == "GET" and path.endswith("/access/apps"):
            return []
        raise AssertionError((method, path))

    routes = _routes()
    for row in routes:
        row["enabled"] = False
    monkeypatch.setattr("core.cloudflare_access._cf_request", fake_cf)
    monkeypatch.setattr("core.cloudflare_access.decode_tunnel_token", lambda: {"account_id": "acc"})
    monkeypatch.setattr("core.cloudflare_access.planned_routes", lambda **kwargs: routes)

    result = await apply_access(emails=None)
    assert deleted == ["/accounts/acc/access/apps/app-sonarr"]
    assert result["removed"] == ["sonarr"]
    assert "hand-made" not in "".join(deleted)
