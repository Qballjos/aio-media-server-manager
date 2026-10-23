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
