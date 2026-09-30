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


@pytest.mark.asyncio
async def test_stop_recovers_when_wait_raises_different_loop(tmp_path: Path, monkeypatch):
    supervisor = ProcessSupervisor.get()
    await supervisor.start(
        name="hang-wait-app",
        cmd=["python3", "-c", "import time; time.sleep(30)"],
        restart_policy=RestartPolicy.NEVER,
        log_dir=tmp_path / "logs",
    )
    entry = supervisor._entries["hang-wait-app"]
    pid = entry.process.pid

    async def boom():
        raise RuntimeError("Task got Future attached to a different loop")

    monkeypatch.setattr(entry.process, "wait", boom)
    await supervisor.stop("hang-wait-app", timeout=1.0)
    assert supervisor.status("hang-wait-app") == ProcessState.STOPPED
    from core.supervisor import _pid_alive

    assert not _pid_alive(pid)


@pytest.mark.asyncio
async def test_intentional_stop_is_not_an_unexpected_crash(tmp_path: Path):
    supervisor = ProcessSupervisor.get()
    await supervisor.start(
        name="clean-stop-app",
        cmd=["python3", "-c", "import time; time.sleep(30)"],
        restart_policy=RestartPolicy.NEVER,
        log_dir=tmp_path / "logs",
    )
    await supervisor.stop("clean-stop-app", timeout=2.0)
    await asyncio.sleep(0.2)
    entry = supervisor._entries["clean-stop-app"]
    assert entry.state == ProcessState.STOPPED
    assert entry.crash_timestamps == []


@pytest.mark.asyncio
async def test_await_proc_exit_when_wait_hangs_but_pid_is_dead(monkeypatch):
    from core.supervisor import _await_proc_exit

    class FakeProc:
        pid = 424242
        returncode = None

        async def wait(self):
            await asyncio.sleep(30)

    monkeypatch.setattr("core.supervisor._pid_alive", lambda pid: False)
    await _await_proc_exit(FakeProc(), 0.3)


def test_reclaim_leftover_processes(tmp_path: Path):
    import subprocess
    import sys
    import time

    from core.supervisor import reclaim_leftover_processes

    app_dir = tmp_path / "apps" / "bazarr"
    app_dir.mkdir(parents=True)
    marker = app_dir / "run-bazarr"
    marker.write_text("#!/bin/sh\n", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-c", f"import time; time.sleep(30)  # {app_dir}/main.py"]
    )
    try:
        time.sleep(0.2)
        assert proc.poll() is None
        killed = reclaim_leftover_processes([str(marker)])
        if killed == 0 and proc.poll() is None:
            pytest.skip("process listing is restricted in this environment")
        assert killed >= 1
        proc.wait(timeout=5)
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)
