"""The VPN watchdog rides out a single failed check and restarts what it stopped."""

import asyncio
from unittest.mock import AsyncMock, patch

from core.integrations import lifecycle


def test_watchdog_waits_for_three_failures_and_restarts_after_recovery():
    lifecycle._down_checks = 0
    lifecycle._stopped_for_tunnel.clear()
    tunnel = {"up": False}
    stop = AsyncMock(return_value=["prowlarr", "qbittorrent"])
    start = AsyncMock(side_effect=lambda names: list(names))

    async def run():
        with (
            patch.object(lifecycle.vpn_manager, "tunneled_apps_allowed", lambda: tunnel["up"]),
            patch.object(lifecycle.vpn_manager, "refresh_local_forwards", lambda: None),
            patch.object(lifecycle.vpn_manager, "reclaim_clearnet_tunneled_processes", lambda: []),
            patch.object(lifecycle, "stop_tunneled_apps", stop),
            patch.object(lifecycle, "start_tunneled_apps", start),
        ):
            assert await lifecycle.enforce_vpn_isolation(grace=2) == []
            assert await lifecycle.enforce_vpn_isolation(grace=2) == []
            stop.assert_not_called()
            assert await lifecycle.enforce_vpn_isolation(grace=2) == ["prowlarr", "qbittorrent"]
            tunnel["up"] = True
            await lifecycle.enforce_vpn_isolation(grace=2)
            start.assert_awaited_once_with(["prowlarr", "qbittorrent"])
            await lifecycle.enforce_vpn_isolation(grace=2)
            assert start.await_count == 1  # nothing left to restart

    asyncio.run(run())


def test_explicit_checks_still_stop_at_once():
    lifecycle._down_checks = 0
    lifecycle._stopped_for_tunnel.clear()
    stop = AsyncMock(return_value=["qbittorrent"])

    async def run():
        with (
            patch.object(lifecycle.vpn_manager, "tunneled_apps_allowed", lambda: False),
            patch.object(lifecycle, "stop_tunneled_apps", stop),
        ):
            assert await lifecycle.enforce_vpn_isolation() == ["qbittorrent"]

    asyncio.run(run())


def test_boot_held_apps_wait_for_the_tunnel_and_the_vpn_is_retried(monkeypatch):
    lifecycle._down_checks = 0
    lifecycle._stopped_for_tunnel.clear()
    lifecycle._wire_after_tunnel = False
    monkeypatch.setattr(lifecycle.settings, "vpn_enabled", True)
    tunnel = {"up": False}
    attempts = []

    def fake_vpn_start():
        attempts.append(1)
        tunnel["up"] = len(attempts) >= 2
        return {"tunnel_up": tunnel["up"], "detail": "no handshake"}

    start = AsyncMock(side_effect=lambda names: list(names))
    wiring = AsyncMock(return_value={})

    async def run():
        with (
            patch.object(lifecycle.vpn_manager, "tunneled_apps_allowed", lambda: tunnel["up"]),
            patch.object(lifecycle.vpn_manager, "start", fake_vpn_start),
            patch.object(lifecycle.vpn_manager, "refresh_local_forwards", lambda: None),
            patch.object(lifecycle.vpn_manager, "reclaim_clearnet_tunneled_processes", lambda: []),
            patch.object(lifecycle, "stop_tunneled_apps", AsyncMock(return_value=[])),
            patch.object(lifecycle, "start_tunneled_apps", start),
            patch.object(lifecycle, "schedule_full_wiring", wiring),
        ):
            lifecycle.hold_for_tunnel(["qbittorrent", "prowlarr", "sonarr"])
            await lifecycle.enforce_vpn_isolation(grace=2)
            assert attempts == []  # backoff has not elapsed yet
            start.assert_not_called()

            lifecycle._vpn_retry_at = 0.0
            await lifecycle.enforce_vpn_isolation(grace=2)
            assert attempts == [1]
            assert lifecycle._vpn_retry_delay == lifecycle._VPN_RETRY_FIRST * 2
            start.assert_not_called()

            lifecycle._vpn_retry_at = 0.0
            await lifecycle.enforce_vpn_isolation(grace=2)
            assert attempts == [1, 1]
            start.assert_awaited_once_with(["prowlarr", "qbittorrent"])
            await asyncio.sleep(0)
            wiring.assert_awaited_once()
            assert lifecycle._vpn_retry_delay == 0.0

    asyncio.run(run())


def test_manual_vpn_stop_cancels_the_retry(monkeypatch):
    lifecycle._down_checks = 0
    lifecycle._stopped_for_tunnel.clear()
    monkeypatch.setattr(lifecycle.settings, "vpn_enabled", True)
    vpn_start = []

    async def run():
        with (
            patch.object(lifecycle.vpn_manager, "tunneled_apps_allowed", lambda: False),
            patch.object(lifecycle.vpn_manager, "start", lambda: vpn_start.append(1) or {}),
            patch.object(lifecycle, "stop_tunneled_apps", AsyncMock(return_value=[])),
        ):
            lifecycle.hold_for_tunnel(["qbittorrent"])
            lifecycle.cancel_vpn_retry()
            lifecycle._vpn_retry_at = 0.0
            await lifecycle.enforce_vpn_isolation(grace=2)
            assert vpn_start == []

    asyncio.run(run())
    lifecycle._stopped_for_tunnel.clear()
