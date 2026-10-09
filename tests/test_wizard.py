"""
tests/test_wizard.py — Tests for the first-run setup wizard.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from core.settings import Settings
from core.wizard import WizardEngine, WIZARD_STEPS
from core.crypto import SecretStore
from core.shared_credentials import save_shared_admin_credentials


def test_wizard_engine_lifecycle(tmp_path: Path):
    state_file = tmp_path / "wizard_state.json"
    engine = WizardEngine(state_file=state_file)

    assert engine.is_completed() is False
    status = engine.get_status()
    assert status["current_step"] == 1
    assert len(status["steps"]) == 12

    # Step 1: Welcome
    step1 = engine.get_step_data(1)
    assert step1["step"] == 1

    # Step 2: Platform
    step2 = engine.get_step_data(2)
    assert "platform" in step2
    assert "system" in step2["platform"]

    # Step 3: Storage update
    engine.update_step_selections(3, {"media_dir": "/custom/media", "config_dir": "/custom/config", "download_dir": "/custom/downloads"})
    status = engine.get_status()
    assert status["selections"]["media_dir"] == "/custom/media"
    assert status["selections"]["download_dir"] == "/custom/downloads"
    assert status["current_step"] >= 4

    # Step 5: Download clients
    engine.update_step_selections(5, {"download_clients": ["sabnzbd"]})
    assert engine.get_status()["selections"]["download_clients"] == ["sabnzbd"]

    step5 = engine.get_step_data(5)
    assert {opt["id"] for opt in step5["options"]} >= {"sabnzbd", "nzbget", "qbittorrent"}
    assert all(opt.get("help_url") for opt in step5["options"])

    step10 = engine.get_step_data(10)
    assert "bazarr" in step10["selected"]
    from applications.community import FlaresolverrApp
    from core.installer.arch import detect_system_arch

    if detect_system_arch().value in FlaresolverrApp.manifest.supported_architectures:
        assert "flaresolverr" in step10["selected"]
        assert "flaresolverr" in {opt["id"] for opt in step10["options"]}
    else:
        assert "flaresolverr" not in step10["selected"]
        assert "flaresolverr" not in {opt["id"] for opt in step10["options"]}

    step7 = engine.get_step_data(7)
    assert {opt["id"] for opt in step7["options"]} >= {"prowlarr", "sonarr", "radarr", "lidarr"}

    step8 = engine.get_step_data(8)
    plex = next(opt for opt in step8["options"] if opt["id"] == "plex")
    assert plex.get("disabled") is not True

    engine.update_step_selections(8, {"media_servers": ["jellyfin", "plex"]})
    assert engine.get_status()["selections"]["media_servers"] == ["jellyfin", "plex"]

    engine.update_step_selections(6, {"vpn_provider": "privadovpn"})
    assert engine.get_status()["selections"]["vpn_provider"] == "privadovpn"

    engine.update_step_selections(
        5,
        {
            "download_clients": ["qbittorrent"],
            "preferred_download_client": "qbittorrent",
            "qbittorrent_username": "amm",
            "qbittorrent_password": "secret-pass",
        },
    )
    step5 = engine.get_step_data(5)
    assert step5["preferred_download_client"] == "qbittorrent"
    assert step5["has_qbittorrent_password"] is True
    assert "qbittorrent_password" not in engine.get_status()["selections"]

    engine.update_step_selections(
        5,
        {
            "download_clients": ["sabnzbd"],
            "usenet_host": "news.example.com",
            "usenet_port": 563,
            "usenet_ssl": True,
            "usenet_username": "nzb-user",
            "usenet_password": "nzb-secret",
            "usenet_connections": 20,
        },
    )
    step5 = engine.get_step_data(5)
    assert step5["usenet_host"] == "news.example.com"
    assert step5["has_usenet_password"] is True
    assert "usenet_password" not in engine.get_status()["selections"]

    engine.skip()
    assert engine.is_completed() is True

    # Reload from disk to test persistence
    reloaded_engine = WizardEngine(state_file=state_file)
    assert reloaded_engine.get_status()["selections"]["vpn_provider"] == "privadovpn"


def test_wizard_omits_unsupported_architecture_apps(tmp_path, monkeypatch):
    from core.installer.arch import PlatformArch

    monkeypatch.setattr("applications.base.detect_system_arch", lambda: PlatformArch.ARMV7)
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        install_dir=tmp_path / "apps",
    )
    engine = WizardEngine(state_file=tmp_path / "wizard_state.json", cfg=cfg)

    step5 = engine.get_step_data(5)
    assert {opt["id"] for opt in step5["options"]} == {"sabnzbd", "nzbget", "qbittorrent"}

    step7 = engine.get_step_data(7)
    assert {opt["id"] for opt in step7["options"]} == {"prowlarr", "sonarr", "radarr", "lidarr"}

    step8 = engine.get_step_data(8)
    assert step8["options"] == []
    assert step8["selected"] == []

    step9 = engine.get_step_data(9)
    assert step9["options"] == []
    assert step9["selected"] == "none"

    step10 = engine.get_step_data(10)
    assert step10["options"] == []
    assert step10["selected"] == []

    engine.update_step_selections(8, {"media_servers": ["jellyfin", "plex"]})
    assert engine.get_status()["selections"]["media_servers"] == []
    assert engine.get_status()["selections"]["media_server"] == "none"

    engine.update_step_selections(9, {"request_system": "seerr"})
    engine.update_step_selections(10, {"recommended_preview": ["bazarr", "flaresolverr"]})
    targets = set(engine._target_apps())
    assert "jellyfin" not in targets
    assert "plex" not in targets
    assert "seerr" not in targets
    assert "bazarr" not in targets
    assert "flaresolverr" not in targets


def test_wizard_writes_pasted_vpn_config(tmp_path: Path):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        install_dir=tmp_path / "apps",
    )
    engine = WizardEngine(state_file=tmp_path / "wizard_state.json", cfg=cfg)
    engine.update_step_selections(
        6,
        {
            "vpn_provider": "custom",
            "vpn_protocol": "wireguard",
            "vpn_config_text": "[Interface]\nPrivateKey = dGVzdA==\nAddress = 10.8.0.2/32\n",
        },
    )
    dest = cfg.config_dir / "vpn" / "wg0.conf"
    assert dest.is_file()
    assert "[Interface]" in dest.read_text(encoding="utf-8")
    step6 = engine.get_step_data(6)
    assert step6["has_vpn_config"] is True
    assert "vpn_config_text" not in engine.get_status()["selections"]
    assert engine.get_status()["selections"]["vpn_config_path"] == str(dest)


def test_wizard_blank_qbittorrent_login_uses_manager_account(tmp_path: Path, monkeypatch):
    store = SecretStore(key_path=tmp_path / "secret.key", storage_path=tmp_path / "secrets.enc")
    monkeypatch.setattr("core.wizard.secret_store", store)
    monkeypatch.setattr("core.shared_credentials.secret_store", store)
    save_shared_admin_credentials("qballjos", "ManagerPass123!")
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        install_dir=tmp_path / "apps",
    )
    engine = WizardEngine(state_file=tmp_path / "wizard_state.json", cfg=cfg)
    engine.apply_initial_settings()
    assert store.get_secret("qbittorrent_username") == "qballjos"
    assert store.get_secret("qbittorrent_password") == "ManagerPass123!"


@pytest.mark.asyncio
async def test_wizard_api_endpoints(tmp_path: Path):
    app = create_app()
    client = TestClient(app)

    # Check status
    res = client.get("/api/wizard/status")
    assert res.status_code == 200
    assert "current_step" in res.json()

    # Get step 1
    res_step1 = client.get("/api/wizard/step/1")
    assert res_step1.status_code == 200
    assert res_step1.json()["step"] == 1

    # Submit step 4 (PUID/PGID)
    res_sub = client.post("/api/wizard/step/4", json={"puid": 1001, "pgid": 1001})
    assert res_sub.status_code == 200
    assert res_sub.json()["selections"]["puid"] == 1001

    # Execute wizard
    res_exec = client.post("/api/wizard/execute")
    assert res_exec.status_code == 200
    exec_data = res_exec.json()
    assert exec_data["completed"] is True
    assert exec_data["wiring"]["status"] == "deferred_until_apps_healthy"
    assert "target_apps" in exec_data

    res_skip = client.post("/api/wizard/skip")
    assert res_skip.status_code == 200
    assert res_skip.json()["completed"] is True


def test_wizard_stores_cloudflare_token_outside_state_and_enables_tunnel(tmp_path: Path):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        install_dir=tmp_path / "apps",
    )
    engine = WizardEngine(state_file=tmp_path / "wizard_state.json", cfg=cfg)
    engine.update_step_selections(
        6,
        {"vpn_provider": "none", "cloudflare_tunnel_enabled": True, "cloudflare_tunnel_token": "eyJ-tunnel-token"},
    )
    token_file = Path(cfg.cloudflare_tunnel_token_file)
    assert token_file.read_text(encoding="utf-8").strip() == "eyJ-tunnel-token"
    assert "cloudflare_tunnel_token" not in engine.get_status()["selections"]
    assert "eyJ-tunnel-token" not in (tmp_path / "wizard_state.json").read_text(encoding="utf-8")
    step6 = engine.get_step_data(6)
    assert step6["cloudflare_tunnel_enabled"] is True
    assert step6["has_cloudflare_token"] is True
    assert engine.get_step_data(11)["summary"]["cloudflare_tunnel_enabled"] is True
    engine.apply_initial_settings()
    assert cfg.cloudflare_tunnel_enabled is True
