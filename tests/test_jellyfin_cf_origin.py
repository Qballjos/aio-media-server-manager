"""Cloudflare → Jellyfin origin rewrites CF-Connecting-IP into X-Forwarded-For."""

from pathlib import Path

from applications.jellyfin import JellyfinApp
from core.cloudflare_api import _service_url, planned_routes
from core.jellyfin_cf_origin import CF_ORIGIN_PORT, JellyfinCfOrigin, jellyfin_tunnel_service_url


def test_jellyfin_tunnel_service_uses_cf_origin_port():
    assert jellyfin_tunnel_service_url() == f"http://127.0.0.1:{CF_ORIGIN_PORT}"
    assert _service_url(8096, app_name="jellyfin") == jellyfin_tunnel_service_url()
    assert _service_url(8989, app_name="sonarr") == "http://127.0.0.1:8989"


def test_planned_routes_jellyfin_service_is_cf_origin(monkeypatch):
    monkeypatch.setattr(
        "core.cloudflare_api.catalog_public_apps",
        lambda: [
            {
                "name": "jellyfin",
                "display_name": "Jellyfin",
                "port": 8096,
                "installed": True,
                "default_subdomain": "jellyfin",
            },
            {
                "name": "sonarr",
                "display_name": "Sonarr",
                "port": 8989,
                "installed": True,
                "default_subdomain": "sonarr",
            },
        ],
    )
    monkeypatch.setattr(
        "core.cloudflare_api.load_hostnames",
        lambda: {
            "jellyfin": {"enabled": True, "subdomain": "jellyfin"},
            "sonarr": {"enabled": True, "subdomain": "sonarr"},
        },
    )
    routes = {row["name"]: row for row in planned_routes(base_domain="example.com")}
    assert routes["jellyfin"]["service"] == f"http://127.0.0.1:{CF_ORIGIN_PORT}"
    assert routes["sonarr"]["service"] == "http://127.0.0.1:8989"


def test_render_nginx_config_substitutes_ports(tmp_path: Path, monkeypatch):
    from core.settings import settings

    template = tmp_path / "tmpl.conf"
    template.write_text(
        "listen __LISTEN_PORT__; upstream __UPSTREAM_PORT__; "
        "log __ERROR_LOG__; access __ACCESS_LOG__;\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    origin = JellyfinCfOrigin(template_path=template)
    path = origin.render_config(upstream_port=18096)
    text = path.read_text(encoding="utf-8")
    assert f"listen {CF_ORIGIN_PORT};" in text
    assert "upstream 18096;" in text
    assert "jellyfin-cf-origin.err.log" in text
    assert "jellyfin-cf-origin.access.log" in text


def test_jellyfin_ensures_known_proxies(tmp_path: Path, monkeypatch):
    from core.settings import settings

    monkeypatch.setattr(settings, "cache_dir", tmp_path / "cache")
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    app = JellyfinApp(base_config_dir=tmp_path / "config", base_install_dir=tmp_path / "apps")
    app._ensure_known_proxies()
    text = (app.config_dir / "network.xml").read_text(encoding="utf-8")
    assert "<string>127.0.0.1</string>" in text
    assert "<string>::1</string>" in text
    assert "<string>::ffff:127.0.0.1</string>" in text
    assert "<string>127.0.0.0/8</string>" in text


def test_dockerfile_ships_nginx_cf_origin_template():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    assert "nginx-light" in dockerfile
    assert "jellyfin-cf-origin.conf.template" in dockerfile
    assert (root / "packaging/nginx/jellyfin-cf-origin.conf.template").is_file()
