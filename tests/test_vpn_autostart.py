"""The VPN comes up on its own after the wizard, and tunneled apps follow it."""

import asyncio

from fastapi.testclient import TestClient

from api.app import create_app
from core.integrations import lifecycle
from core.settings import settings


async def _nothing_stopped(*_args, **_kwargs):
    return []


async def test_bring_up_vpn_starts_every_installed_tunneled_app_when_none_were_running(monkeypatch):
    calls = []
    wiring = []

    async def fake_start(names=None):
        calls.append(names)
        return ["prowlarr", "qbittorrent"]

    async def fake_wiring(*, wait_for_apps=False):
        wiring.append(wait_for_apps)
        return {}

    monkeypatch.setattr(lifecycle, "stop_tunneled_apps", _nothing_stopped)
    monkeypatch.setattr(lifecycle, "start_tunneled_apps", fake_start)
    monkeypatch.setattr(lifecycle, "schedule_full_wiring", fake_wiring)
    monkeypatch.setattr(lifecycle.vpn_manager, "start", lambda: {"status": "ok", "tunnel_up": True})
    result = await lifecycle.bring_up_vpn()
    await asyncio.sleep(0)
    assert calls == [None]
    assert result["started_apps"] == ["prowlarr", "qbittorrent"]
    # Apps that only start once the tunnel is up still need their shared login and links.
    assert wiring == [True]


def test_bring_up_vpn_keeps_apps_stopped_when_tunnel_stays_down(monkeypatch):
    enforced = []

    async def fake_enforce():
        enforced.append(True)
        return []

    async def fake_start(names=None):
        raise AssertionError("must not start tunneled apps off-VPN")

    monkeypatch.setattr(lifecycle, "stop_tunneled_apps", _nothing_stopped)
    monkeypatch.setattr(lifecycle, "start_tunneled_apps", fake_start)
    monkeypatch.setattr(lifecycle, "enforce_vpn_isolation", fake_enforce)
    monkeypatch.setattr(
        lifecycle.vpn_manager, "start", lambda: {"status": "error", "tunnel_up": False, "detail": "no config"}
    )
    result = asyncio.run(lifecycle.bring_up_vpn())
    assert enforced == [True]
    assert result["started_apps"] == []


def test_wizard_execute_brings_vpn_up_only_when_enabled(monkeypatch):
    from api.routers import wizard as wizard_router

    calls = []

    async def fake_bring_up():
        calls.append(True)
        return {}

    async def fake_execute():
        return {"completed": True, "target_apps": [], "installations": []}

    monkeypatch.setattr(wizard_router, "bring_up_vpn", fake_bring_up)
    monkeypatch.setattr(wizard_router.wizard_engine, "execute_installation", fake_execute)
    client = TestClient(create_app())

    monkeypatch.setattr(settings, "vpn_enabled", True)
    assert client.post("/api/wizard/execute").status_code == 200
    assert calls == [True]

    monkeypatch.setattr(settings, "vpn_enabled", False)
    assert client.post("/api/wizard/execute").status_code == 200
    assert calls == [True]
