"""First-run wizard skip and health-gated wiring."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from core.integrations.credentials import wait_for_application_api_key
from core.integrations.engine import IntegrationEngine
from core.integrations.lifecycle import finalize_application_install


@pytest.mark.asyncio
async def test_flaresolverr_api_key_wait_returns_immediately():
    t0 = time.monotonic()
    key = await wait_for_application_api_key("flaresolverr", timeout=90.0)
    assert key is None
    assert time.monotonic() - t0 < 1.0


@pytest.mark.asyncio
async def test_skip_wizard_returns_quickly():
    client = TestClient(create_app())
    t0 = time.monotonic()
    res = client.post("/api/wizard/skip")
    elapsed = time.monotonic() - t0
    assert res.status_code == 200
    assert res.json()["completed"] is True
    assert elapsed < 2.0


def test_engine_skips_installed_but_not_running_arr():
    engine = IntegrationEngine()
    steps: list[dict] = []
    with patch.object(engine, "_installed", return_value=True), patch.object(
        engine, "_is_app_running", return_value=False
    ):
        skipped = engine._skip_uninstalled(steps, "sonarr", "wire_clients_and_storage")
    assert skipped is True
    assert steps[0]["detail"] == "not running"


@pytest.mark.asyncio
async def test_finalize_waits_for_health_before_wiring():
    plugin = MagicMock()
    plugin.name = "sonarr"
    plugin.manifest.daemon = True
    plugin.health_check_url.return_value = "http://127.0.0.1:8989/ping"
    plugin.start_command.return_value = ["true"]
    plugin.working_directory.return_value = None
    plugin.extra_env.return_value = {}

    async def fake_start(**_kwargs):
        return None

    supervisor = MagicMock()
    supervisor.start = fake_start

    with (
        patch("core.integrations.lifecycle.ProcessSupervisor.get", return_value=supervisor),
        patch(
            "core.integrations.lifecycle._wait_healthy",
            new_callable=AsyncMock,
            return_value=True,
        ) as healthy,
        patch(
            "core.integrations.lifecycle.wait_for_application_api_key",
            new_callable=AsyncMock,
            return_value="0123456789abcdef0123456789abcdef",
        ) as wait_key,
        patch(
            "core.integrations.lifecycle.schedule_full_wiring",
            new_callable=AsyncMock,
            return_value={"status": "completed", "steps": []},
        ) as wiring,
    ):
        report = await finalize_application_install(plugin)

    healthy.assert_awaited()
    wait_key.assert_awaited()
    wiring.assert_awaited()
    assert report["wired"] is True
    assert report["healthy"] is True
