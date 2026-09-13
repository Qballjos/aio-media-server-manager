"""
tests/test_supervisor_resilience.py — Tests for crash loop detection and auto-restart backoff.
"""

import asyncio
import time
import pytest
from pathlib import Path
from core.supervisor import ProcessSupervisor, ProcessState, RestartPolicy


@pytest.mark.asyncio
async def test_crash_loop_detection_and_reset(tmp_path: Path):
    supervisor = ProcessSupervisor.get()

    # Start it once (exits with code 1 immediately)
    await supervisor.start(
        name="crashing-app",
        cmd=["python3", "-c", "import sys; sys.exit(1)"],
        restart_policy=RestartPolicy.ON_FAILURE,
        log_dir=tmp_path / "logs",
    )
    entry = supervisor._entries["crashing-app"]

    # Wait for the first exit
    await asyncio.sleep(0.15)
    assert entry.state == ProcessState.FAILED
    assert len(entry.crash_timestamps) == 1

    # Simulate 4 additional crashes within the sliding window
    now = time.monotonic()
    entry.crash_timestamps = [now - 100, now - 80, now - 60, now - 40]

    # Trigger one more exit watch to hit the threshold of 5
    await supervisor.start(
        name="crashing-app",
        cmd=["python3", "-c", "import sys; sys.exit(1)"],
        restart_policy=RestartPolicy.ON_FAILURE,
        log_dir=tmp_path / "logs",
    )
    await asyncio.sleep(0.15)

    assert entry.state == ProcessState.CRASH_LOOP
    assert len(entry.crash_timestamps) >= 5

    # Verify status report
    statuses = supervisor.list_processes()
    app_status = next(s for s in statuses if s["name"] == "crashing-app")
    assert app_status["is_crash_loop"] is True
    assert app_status["recent_crashes"] >= 5

    # Reset crash loop
    supervisor.reset_crash_loop("crashing-app")
    assert entry.state == ProcessState.STOPPED
    assert len(entry.crash_timestamps) == 0

    statuses_after = supervisor.list_processes()
    app_status_after = next(s for s in statuses_after if s["name"] == "crashing-app")
    assert app_status_after["is_crash_loop"] is False
    assert app_status_after["recent_crashes"] == 0
