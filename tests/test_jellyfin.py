from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from applications.jellyfin import JellyfinApp, jellyfin_repo_arch, pick_jellyfin_archive
from core.crypto import secret_store
from core.integrations.credentials import get_application_api_key
from core.installer.installer import InstallResult


def test_pick_jellyfin_archive_prefers_xz():
    listing = """
    <a href="jellyfin_12.1-amd64.tar.gz">jellyfin_12.1-amd64.tar.gz</a>
    <a href="jellyfin_12.1-amd64.tar.xz">jellyfin_12.1-amd64.tar.xz</a>
    """
    filename, version = pick_jellyfin_archive(listing, "amd64")
    assert filename == "jellyfin_12.1-amd64.tar.xz"
    assert version == "12.1"


def test_pick_jellyfin_archive_rejects_other_arch():
    listing = '<a href="jellyfin_12.1-arm64.tar.xz">jellyfin_12.1-arm64.tar.xz</a>'
    with pytest.raises(RuntimeError, match="amd64"):
        pick_jellyfin_archive(listing, "amd64")


def test_jellyfin_repo_arch_map():
    assert jellyfin_repo_arch("x86_64") == "amd64"
    assert jellyfin_repo_arch("arm64") == "arm64"
    with pytest.raises(RuntimeError):
        jellyfin_repo_arch("armv7")


def test_jellyfin_install_uses_official_repo(tmp_path, monkeypatch):
    listing = '<a href="jellyfin_12.1-amd64.tar.xz">jellyfin_12.1-amd64.tar.xz</a>'
    captured: dict[str, str] = {}

    def fake_get(url, timeout=30):
        response = MagicMock()
        response.text = listing
        response.raise_for_status = lambda: None
        captured["listing_url"] = url
        return response

    def fake_install_from_url(self, url, app_name, executable_name, version="custom", **_kwargs):
        captured["url"] = url
        captured["version"] = version
        captured["app_name"] = app_name
        captured["executable_name"] = executable_name
        exe = tmp_path / "apps" / "jellyfin" / "jellyfin"
        exe.parent.mkdir(parents=True)
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        return InstallResult(
            app_name=app_name,
            version=version,
            install_dir=exe.parent,
            executable_path=exe,
            asset_name="jellyfin_12.1-amd64.tar.xz",
            sha256="abc",
            installed_at=0.0,
        )

    monkeypatch.setattr("applications.jellyfin.requests.get", fake_get)
    monkeypatch.setattr("applications.jellyfin.jellyfin_repo_arch", lambda: "amd64")
    monkeypatch.setattr("core.installer.installer.AppInstaller.install_from_url", fake_install_from_url)

    app = JellyfinApp(base_config_dir=tmp_path / "config", base_install_dir=tmp_path / "apps")
    result = app.install()

    assert captured["listing_url"].endswith("/latest-stable/amd64/")
    assert captured["url"].endswith("/latest-stable/amd64/jellyfin_12.1-amd64.tar.xz")
    assert captured["version"] == "12.1"
    assert result.executable_path.name == "jellyfin"


def test_jellyfin_start_passes_webdir(tmp_path: Path):
    install_root = tmp_path / "apps"
    web = install_root / "jellyfin" / "jellyfin-web"
    web.mkdir(parents=True)
    exe = install_root / "jellyfin" / "jellyfin"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    exe.chmod(0o755)

    app = JellyfinApp(base_config_dir=tmp_path / "config", base_install_dir=install_root)
    cmd = app.start_command()
    assert "--webdir" in cmd
    assert str(web) in cmd
    assert "--datadir" in cmd
    assert "--http-port" not in cmd
    network = app.config_dir / "network.xml"
    assert network.is_file()
    xml = network.read_text(encoding="utf-8")
    assert f"<InternalHttpPort>{app.port}</InternalHttpPort>" in xml
    app.apply_listen_port(18096)
    assert "<InternalHttpPort>18096</InternalHttpPort>" in network.read_text(encoding="utf-8")


def test_discover_jellyfin_api_key_from_login(tmp_path, monkeypatch):
    secret_store.save_secret("jellyfin_api_key", "")
    monkeypatch.setattr(
        "core.shared_credentials.shared_admin_credentials",
        lambda: ("admin", "SharedPass123!"),
    )
    monkeypatch.setattr("core.app_prefs.load_app_ports", lambda: {"jellyfin": 18096})

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"AccessToken": "jellyfin-access-token-abcdefghijklmnopqrstuvwxyz"}
    mock_resp.content = b"{}"

    public = MagicMock()
    public.status_code = 200
    public.json.return_value = [{"Name": "admin"}]

    info = MagicMock()
    info.status_code = 200
    info.json.return_value = {"StartupWizardCompleted": True}
    info.content = b"{}"

    def fake_get(url, timeout=4.0, headers=None):
        if url.endswith("/Users/Public"):
            return public
        return info

    def fake_post(url, headers=None, json=None, params=None, timeout=5.0):
        return mock_resp

    with (
        patch("core.integrations.jellyfin.requests.get", side_effect=fake_get),
        patch("core.integrations.jellyfin.requests.post", side_effect=fake_post) as posted,
    ):
        key = get_application_api_key("jellyfin", app_config_dir=tmp_path / "missing-jellyfin")
    assert key == "jellyfin-access-token-abcdefghijklmnopqrstuvwxyz"
    assert any("AuthenticateByName" in str(call.args[0]) for call in posted.call_args_list)
