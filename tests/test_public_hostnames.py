"""Public subdomain map + Open UI custom labels."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.app_web_url import app_web_ui_url
from core.cloudflare_api import decode_tunnel_token, managed_hostnames_for_publish, _merge_ingress
from core.cloudflare_tunnel import CloudflareTunnelManager
from core.public_hostnames import (
    PublicHostnameError,
    load_hostnames,
    mark_published,
    save_hostnames,
    subdomain_for,
)
from core.settings import Settings


def test_save_and_load_hostnames(tmp_path: Path):
    cfg = Settings(config_dir=tmp_path)
    saved = save_hostnames(
        {
            "sonarr": {"subdomain": "tv", "enabled": True},
            "jellyfin": {"subdomain": "watch", "enabled": False},
        },
        app_settings=cfg,
    )
    assert saved["sonarr"]["subdomain"] == "tv"
    assert load_hostnames(cfg)["jellyfin"]["enabled"] is False
    assert subdomain_for("sonarr", app_settings=cfg) == "tv"
    assert subdomain_for("jellyfin", app_settings=cfg) is None


def test_duplicate_subdomain_rejected(tmp_path: Path):
    cfg = Settings(config_dir=tmp_path)
    with pytest.raises(PublicHostnameError):
        save_hostnames(
            {
                "sonarr": {"subdomain": "apps", "enabled": True},
                "radarr": {"subdomain": "apps", "enabled": True},
            },
            app_settings=cfg,
        )


def test_open_ui_uses_custom_subdomain(tmp_path: Path, monkeypatch):
    cfg = Settings(config_dir=tmp_path, public_app_base_domain="example.com")
    save_hostnames({"sonarr": {"subdomain": "tv", "enabled": True}}, app_settings=cfg)
    monkeypatch.setattr("core.app_web_url.settings", cfg)
    monkeypatch.setattr("core.public_hostnames.settings", cfg)
    assert (
        app_web_ui_url(app_name="sonarr", port=8989, hostname="media.example.com", scheme="https")
        == "https://tv.example.com"
    )


def test_decode_tunnel_token(tmp_path: Path):
    import base64
    import json

    creds = {"a": "account123", "t": "tunnel-uuid", "s": "x"}

    # Dashboard / cloudflared service install token: single base64 JSON blob (not a JWT).
    b64_token = base64.b64encode(json.dumps(creds).encode()).decode().rstrip("=")
    assert b64_token.startswith("eyJ")
    assert decode_tunnel_token(b64_token) == {
        "account_id": "account123",
        "tunnel_id": "tunnel-uuid",
    }

    # Three-part JWT-shaped token (also accepted).
    payload = base64.urlsafe_b64encode(json.dumps(creds).encode()).decode().rstrip("=")
    jwt_token = f"eyJhbGciOiJub25lIn0.{payload}.sig"
    path = tmp_path / "cloudflare" / "tunnel.token"
    path.parent.mkdir(parents=True)
    path.write_text(jwt_token + "\n", encoding="utf-8")
    mgr = CloudflareTunnelManager(Settings(config_dir=tmp_path, cloudflare_tunnel_token_file=path))
    assert mgr.read_token().startswith("eyJ")
    ids = decode_tunnel_token(mgr.read_token())
    assert ids["account_id"] == "account123"
    assert ids["tunnel_id"] == "tunnel-uuid"


def test_decode_prefers_token_file_over_stale_env(tmp_path: Path, monkeypatch):
    import base64
    import json

    creds = {"a": "acct", "t": "from-file", "s": "x"}
    good = base64.b64encode(json.dumps(creds).encode()).decode().rstrip("=")
    path = tmp_path / "cloudflare" / "tunnel.token"
    path.parent.mkdir(parents=True)
    path.write_text(good + "\n", encoding="utf-8")
    cfg = Settings(
        config_dir=tmp_path,
        cloudflare_tunnel_token="not-a-valid-token",
        cloudflare_tunnel_token_file=path,
    )
    mgr = CloudflareTunnelManager(cfg)
    monkeypatch.setattr("core.cloudflare_api.cloudflare_tunnel", mgr)
    assert decode_tunnel_token()["tunnel_id"] == "from-file"


def test_set_api_token_rejects_connector_token(tmp_path: Path, monkeypatch):
    import base64
    import json

    from core import cloudflare_api as cf_api

    monkeypatch.setattr(cf_api, "secret_store", type("S", (), {
        "save_secret": staticmethod(lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not save"))),
        "delete_secret": staticmethod(lambda *_a, **_k: None),
        "get_secret": staticmethod(lambda *_a, **_k: None),
    })())
    creds = {"a": "acct", "t": "tun", "s": "x"}
    connector = base64.b64encode(json.dumps(creds).encode()).decode().rstrip("=")
    with pytest.raises(cf_api.CloudflareApiError, match="tunnel connector"):
        cf_api.set_api_token(connector)


def test_merge_ingress_keeps_unrelated():
    existing = [
        {"hostname": "other.example.com", "service": "http://127.0.0.1:9000"},
        {"hostname": "sonarr.example.com", "service": "http://127.0.0.1:8989"},
        {"service": "http_status:404"},
    ]
    desired = [{"hostname": "tv.example.com", "service": "http://127.0.0.1:8989", "originRequest": {}}]
    merged = _merge_ingress(
        existing,
        desired,
        managed_hostnames={"sonarr.example.com", "tv.example.com"},
    )
    hosts = [r.get("hostname") for r in merged if r.get("hostname")]
    assert "other.example.com" in hosts
    assert "tv.example.com" in hosts
    assert "sonarr.example.com" not in hosts
    assert merged[-1]["service"] == "http_status:404"


def test_managed_hostnames_do_not_claim_never_published_defaults():
    routes = [
        {
            "name": "manager",
            "enabled": False,
            "hostname": "media.example.com",
        },
        {
            "name": "sonarr",
            "enabled": True,
            "hostname": "tv.example.com",
        },
        {
            "name": "radarr",
            "enabled": False,
            "hostname": "radarr.example.com",
        },
    ]
    stored = {
        "sonarr": {"subdomain": "tv", "enabled": True, "last_published": "sonarr.example.com"},
        "radarr": {"subdomain": "radarr", "enabled": False},
    }
    managed = managed_hostnames_for_publish(routes, stored=stored)
    assert "tv.example.com" in managed
    assert "sonarr.example.com" in managed  # rename cleanup
    assert "media.example.com" not in managed
    assert "radarr.example.com" not in managed


def test_mark_published_and_preserve_on_save(tmp_path: Path):
    cfg = Settings(config_dir=tmp_path)
    save_hostnames({"sonarr": {"subdomain": "tv", "enabled": True}}, app_settings=cfg)
    mark_published({"sonarr": "tv.example.com"}, ports={"sonarr": 8989}, app_settings=cfg)
    assert load_hostnames(cfg)["sonarr"]["last_published"] == "tv.example.com"
    assert load_hostnames(cfg)["sonarr"]["last_published_port"] == 8989
    save_hostnames({"sonarr": {"subdomain": "shows", "enabled": True}}, app_settings=cfg)
    assert load_hostnames(cfg)["sonarr"]["last_published"] == "tv.example.com"
    assert load_hostnames(cfg)["sonarr"]["last_published_port"] == 8989


def test_merge_ingress_updates_service_port_for_same_hostname():
    existing = [
        {"hostname": "tv.example.com", "service": "http://127.0.0.1:8989"},
        {"service": "http_status:404"},
    ]
    desired = [
        {
            "hostname": "tv.example.com",
            "service": "http://127.0.0.1:8990",
            "originRequest": {},
        }
    ]
    merged = _merge_ingress(existing, desired, managed_hostnames={"tv.example.com"})
    rules = [r for r in merged if r.get("hostname") == "tv.example.com"]
    assert len(rules) == 1
    assert rules[0]["service"] == "http://127.0.0.1:8990"
