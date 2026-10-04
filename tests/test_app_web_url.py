"""LAN vs public subdomain Open UI URL helpers."""

from __future__ import annotations

from core.app_web_url import app_web_ui_url, derive_public_app_base_domain


def test_lan_uses_host_port():
    assert (
        app_web_ui_url(app_name="sonarr", port=8989, hostname="192.168.2.223", scheme="http")
        == "http://192.168.2.223:8989"
    )


def test_https_uses_app_subdomain():
    assert (
        app_web_ui_url(app_name="sonarr", port=8989, hostname="media.example.com", scheme="https")
        == "https://sonarr.example.com"
    )


def test_configured_base_domain_does_not_break_lan():
    assert (
        app_web_ui_url(
            app_name="jellyfin",
            port=8096,
            hostname="192.168.2.223",
            scheme="http",
            base_domain="example.com",
        )
        == "http://192.168.2.223:8096"
    )


def test_configured_base_domain_used_on_https():
    assert (
        app_web_ui_url(
            app_name="jellyfin",
            port=8096,
            hostname="media.example.com",
            scheme="https",
            base_domain="example.com",
        )
        == "https://jellyfin.example.com"
    )


def test_derive_base_domain():
    assert derive_public_app_base_domain("media.example.com") == "example.com"
    assert derive_public_app_base_domain("example.com") == "example.com"
    assert derive_public_app_base_domain("media.example.co.uk") == "example.co.uk"
    assert derive_public_app_base_domain("sonarr.media.example.co.uk") == "example.co.uk"
    assert derive_public_app_base_domain("app.example.com.au") == "example.com.au"
    assert derive_public_app_base_domain("example.co.uk") == "example.co.uk"
