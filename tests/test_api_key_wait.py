"""API-key discovery can restart apps, so it must never run on the supervisor's event loop."""

import asyncio
import threading

from core.integrations import credentials


def _loop_spy(seen):
    def fake_get(name, app_config_dir=None):
        try:
            asyncio.get_running_loop()
            seen.append("on-loop")
        except RuntimeError:
            seen.append(threading.current_thread().name)
        return "k" * 32

    return fake_get


async def test_direct_lookup_runs_in_a_worker_thread(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(credentials, "get_application_api_key", _loop_spy(seen))
    assert await credentials.wait_for_application_api_key("jellyfin") == "k" * 32
    assert seen and "on-loop" not in seen


async def test_polled_lookup_runs_in_a_worker_thread(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(credentials, "get_application_api_key", _loop_spy(seen))
    assert await credentials.wait_for_application_api_key("sonarr", timeout=5.0) == "k" * 32
    assert seen and "on-loop" not in seen
