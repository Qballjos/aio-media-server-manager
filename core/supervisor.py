"""
core/supervisor.py — Async Process Supervisor

Manages the lifecycle of named child processes:
  - Start   : asyncio.create_subprocess_exec, stdout/stderr routing
  - Stop    : SIGTERM → wait → SIGKILL (timeout)
  - Restart : stop + start with the same command/env
  - Auto-restart   : configurable restart policy with exponential backoff
  - Shutdown       : SIGTERM/SIGINT handler for graceful teardown

Usage
-----
    supervisor = ProcessSupervisor.get()
    await supervisor.start("sonarr", ["/opt/Sonarr/Sonarr", "--no-browser"])
    await supervisor.stop("sonarr")
"""

from __future__ import annotations

import asyncio
import collections
import enum
import logging
import os
import signal
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_LOG_RING_MAXLEN = 500          # Lines kept in-memory per process
_STOP_TIMEOUT = 10.0            # Seconds before SIGKILL is sent
_RESTART_MAX_ATTEMPTS = 5       # Give up after this many consecutive failures
_RESTART_BASE_DELAY = 2.0       # First backoff delay (seconds)
_RESTART_MAX_DELAY = 60.0       # Upper cap for backoff delay
_CRASH_WINDOW_SECONDS = 600.0   # 10 minutes sliding window
_CRASH_THRESHOLD = 5            # Halt auto-restart if >= 5 crashes in window


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class ProcessState(str, enum.Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"
    STOPPING = "stopping"
    CRASH_LOOP = "crash_loop"


class RestartPolicy(str, enum.Enum):
    NEVER = "never"         # Never restart automatically
    ON_FAILURE = "on_failure"  # Restart only if exit code != 0
    ALWAYS = "always"       # Always restart


@dataclass
class ProcessSpec:
    """Everything needed to (re)start a named process."""

    name: str
    cmd: Sequence[str]
    cwd: Path | None = None
    env: dict[str, str] | None = None
    restart_policy: RestartPolicy = RestartPolicy.ON_FAILURE
    log_dir: Path | None = None


@dataclass
class ProcessEntry:
    """Live state for a running (or recently exited) process."""

    spec: ProcessSpec
    state: ProcessState = ProcessState.STOPPED
    process: asyncio.subprocess.Process | None = None
    started_at: float = 0.0
    exit_code: int | None = None
    restart_attempts: int = 0
    next_restart_at: float = 0.0
    crash_timestamps: list[float] = field(default_factory=list)
    # In-memory ring buffer: last N lines of stdout+stderr interleaved
    log_ring: collections.deque = field(
        default_factory=lambda: collections.deque(maxlen=_LOG_RING_MAXLEN)
    )
    # Tasks draining stdout/stderr
    _stdout_task: asyncio.Task | None = None
    _stderr_task: asyncio.Task | None = None


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------

class ProcessSupervisor:
    """
    Singleton async process supervisor.

    Obtain the instance with ``ProcessSupervisor.get()``.
    """

    _instance: "ProcessSupervisor | None" = None

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def get(cls) -> "ProcessSupervisor":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        if ProcessSupervisor._instance is not None:
            raise RuntimeError(
                "Use ProcessSupervisor.get() to obtain the singleton instance."
            )
        self._entries: dict[str, ProcessEntry] = {}
        self._lock = asyncio.Lock()
        self._shutting_down = False
        self._start_order: list[str] = []  # Ordered list for reverse-shutdown
        self._subscribers: list[tuple[asyncio.Queue, str | None]] = []

        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda s=sig: asyncio.ensure_future(self._shutdown(s)))
        except (ValueError, RuntimeError, NotImplementedError):
            logger.debug("Signal handlers could not be installed (not running in main thread).")

        # Background auto-restart task
        self._restart_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_coroutine_sync(self, coro, timeout: float = 90.0):
        """Run a supervisor coroutine from a worker thread (integration wiring)."""
        loop = getattr(self, "_loop", None)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if loop is not None and loop.is_running() and running is not loop:
            return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=timeout)
        if running is not None:
            raise RuntimeError("Cannot block the process supervisor event loop.")
        return asyncio.run(coro)

    async def start(
        self,
        name: str,
        cmd: Sequence[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        restart_policy: RestartPolicy = RestartPolicy.ON_FAILURE,
        log_dir: Path | None = None,
    ) -> None:
        """Start a named process.  Raises RuntimeError if already running."""
        async with self._locked():
            entry = self._entries.get(name)
            if entry and entry.state == ProcessState.RUNNING:
                raise RuntimeError(f"Process '{name}' is already running.")

            spec = ProcessSpec(
                name=name,
                cmd=list(cmd),
                cwd=cwd,
                env=env,
                restart_policy=restart_policy,
                log_dir=log_dir,
            )
            if entry is None:
                entry = ProcessEntry(spec=spec)
                self._entries[name] = entry
            else:
                entry.spec = spec
            if entry.state == ProcessState.CRASH_LOOP:
                entry.crash_timestamps.clear()
                entry.restart_attempts = 0
                entry.state = ProcessState.STOPPED
            reclaim_leftover_processes(spec.cmd)

            await self._do_start(entry)
            self._loop = asyncio.get_running_loop()

            if name not in self._start_order:
                self._start_order.append(name)

        # Kick off the auto-restart watcher if not already running
        if self._restart_task is None or self._restart_task.done():
            self._restart_task = asyncio.ensure_future(self._restart_watcher())

    async def stop(self, name: str, timeout: float = _STOP_TIMEOUT) -> None:
        """Gracefully stop a named process (SIGTERM then SIGKILL)."""
        async with self._locked():
            entry = self._entries.get(name)
            if entry is None or entry.state in (ProcessState.STOPPED, ProcessState.STOPPING):
                logger.debug("stop(%s): already stopped", name)
                if entry is not None:
                    entry.state = ProcessState.STOPPED
                    entry.process = None
                    reclaim_leftover_processes(entry.spec.cmd)
                return
            await self._do_stop(entry, timeout=timeout)
            reclaim_leftover_processes(entry.spec.cmd if entry.spec else [])

    async def restart(self, name: str) -> None:
        """Stop then start a named process with the same spec."""
        async with self._locked():
            entry = self._entries.get(name)
            if entry is None:
                raise KeyError(f"Unknown process: {name!r}")
            await self._do_stop(entry)
            reclaim_leftover_processes(entry.spec.cmd)
            entry.crash_timestamps.clear()
            entry.restart_attempts = 0
            await self._do_start(entry)

    def status(self, name: str) -> ProcessState:
        """Return current state of a named process."""
        entry = self._entries.get(name)
        if entry is None:
            return ProcessState.STOPPED
        return entry.state

    def list_processes(self) -> list[dict]:
        """Return a summary list of all managed processes."""
        result = []
        for name, entry in self._entries.items():
            result.append(
                {
                    "name": name,
                    "state": entry.state.value,
                    "pid": entry.process.pid if entry.process else None,
                    "exit_code": entry.exit_code,
                    "started_at": entry.started_at or None,
                    "restart_attempts": entry.restart_attempts,
                    "restart_policy": entry.spec.restart_policy.value,
                    "is_crash_loop": entry.state == ProcessState.CRASH_LOOP,
                    "recent_crashes": len(entry.crash_timestamps),
                }
            )
        return result

    def get_logs(self, name: str) -> list[str]:
        """Return the in-memory log ring for a named process."""
        entry = self._entries.get(name)
        if entry is None:
            return []
        return list(entry.log_ring)

    def subscribe_logs(self, app_name: str | None = None) -> asyncio.Queue:
        """Subscribe to live log output for all or a specific app."""
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.append((q, app_name))
        return q

    def unsubscribe_logs(self, queue: asyncio.Queue) -> None:
        """Unsubscribe a previously subscribed log queue."""
        self._subscribers = [sub for sub in self._subscribers if sub[0] is not queue]

    def reset_crash_loop(self, name: str) -> None:
        """Manually clear crash history and reset state from CRASH_LOOP to STOPPED."""
        entry = self._entries.get(name)
        if entry:
            entry.crash_timestamps.clear()
            entry.restart_attempts = 0
            if entry.state in (ProcessState.CRASH_LOOP, ProcessState.FAILED):
                entry.state = ProcessState.STOPPED

    def forget(self, name: str) -> None:
        """Drop a managed process after uninstall so status is not leftover."""
        self._entries.pop(name, None)
        self._start_order = [item for item in self._start_order if item != name]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _do_start(self, entry: ProcessEntry) -> None:
        """Low-level start (must be called with self._lock held)."""
        from core.vpn import VPN_TUNNELED_APPS, VpnIsolationError, vpn_manager

        spec = entry.spec
        if spec.name in VPN_TUNNELED_APPS:
            vpn_manager.assert_can_start_tunneled_app(spec.name)
        entry.state = ProcessState.STARTING
        logger.info("Starting process '%s': %s", spec.name, " ".join(spec.cmd))

        # Build environment (inherit + overlay)
        process_env = os.environ.copy()
        if spec.env:
            process_env.update(spec.env)

        try:
            proc = await asyncio.create_subprocess_exec(
                *spec.cmd,
                cwd=str(spec.cwd) if spec.cwd else None,
                env=process_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            logger.error("Cannot start '%s': executable not found — %s", spec.name, exc)
            entry.state = ProcessState.FAILED
            entry.exit_code = -1
            raise RuntimeError(f"Cannot start '{spec.name}': executable not found — {exc}") from exc
        except OSError as exc:
            logger.error("Cannot start '%s': %s", spec.name, exc)
            entry.state = ProcessState.FAILED
            entry.exit_code = -1
            raise RuntimeError(f"Cannot start '{spec.name}': {exc}") from exc

        entry.process = proc
        entry.state = ProcessState.RUNNING
        entry.started_at = time.monotonic()
        entry.exit_code = None

        # Launch log-drain tasks
        entry._stdout_task = asyncio.ensure_future(
            self._drain_stream(proc.stdout, entry, "stdout", spec.log_dir)
        )
        entry._stderr_task = asyncio.ensure_future(
            self._drain_stream(proc.stderr, entry, "stderr", spec.log_dir)
        )

        # Watch for exit asynchronously
        asyncio.ensure_future(self._watch_exit(entry))
        logger.info("Process '%s' started (PID %d)", spec.name, proc.pid)

    async def _do_stop(self, entry: ProcessEntry, timeout: float = _STOP_TIMEOUT) -> None:
        """Low-level stop (must be called with self._lock held). Never hangs forever."""
        proc = entry.process
        if proc is None or entry.state == ProcessState.STOPPED:
            entry.state = ProcessState.STOPPED
            entry.process = None
            return

        entry.state = ProcessState.STOPPING
        name = entry.spec.name
        pid = proc.pid
        logger.info("Stopping process '%s' (PID %s)…", name, pid)

        try:
            if not _pid_alive(pid) and proc.returncode is not None:
                entry.exit_code = proc.returncode
                logger.info("Process '%s' was already exited (code %s).", name, entry.exit_code)
                return

            _signal_tree(pid, signal.SIGTERM)
            try:
                proc.send_signal(signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass

            try:
                await _await_proc_exit(proc, timeout)
            except asyncio.TimeoutError:
                logger.warning(
                    "Process '%s' did not exit within %.0fs — sending SIGKILL.", name, timeout
                )
                _signal_tree(pid, signal.SIGKILL)
                try:
                    proc.kill()
                except (ProcessLookupError, OSError):
                    pass
                try:
                    await _await_proc_exit(proc, 2.0)
                except (asyncio.TimeoutError, RuntimeError, ProcessLookupError):
                    logger.warning(
                        "Process '%s' PID %s still did not report exit after SIGKILL.",
                        name,
                        pid,
                    )
                    _signal_tree(pid, signal.SIGKILL)
                    reclaim_leftover_processes(entry.spec.cmd if entry.spec else [])
                    kill_deadline = time.monotonic() + 5.0
                    while _pid_alive(pid) and time.monotonic() < kill_deadline:
                        await asyncio.sleep(0.1)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error stopping '%s': %s", name, exc)
            _signal_tree(pid, signal.SIGKILL)
        finally:
            entry.exit_code = proc.returncode
            entry.state = ProcessState.STOPPED
            entry.process = None
            logger.info("Process '%s' stopped (exit code %s).", name, entry.exit_code)

    @asynccontextmanager
    async def _locked(self):
        """Acquire the supervisor lock, replacing it if it is bound to a closed loop."""
        lock = self._lock
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        stored = self._loop
        if stored is not None and loop is not None and stored is not loop and stored.is_closed():
            lock = asyncio.Lock()
            self._lock = lock
            self._loop = loop
        try:
            await lock.acquire()
        except RuntimeError:
            lock = asyncio.Lock()
            self._lock = lock
            if loop is not None:
                self._loop = loop
            await lock.acquire()
        try:
            yield
        finally:
            lock.release()

    async def _drain_stream(
        self,
        stream: asyncio.StreamReader | None,
        entry: ProcessEntry,
        stream_name: str,
        log_dir: Path | None,
    ) -> None:
        """Read lines from stdout/stderr and write to ring buffer + log file."""
        if stream is None:
            return

        log_file = None
        if log_dir is not None:
            log_dir = Path(log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"{entry.spec.name}.log"
            try:
                log_file = open(log_path, "a", encoding="utf-8", errors="replace")  # noqa: ASYNC101
            except OSError as exc:
                logger.warning("Cannot open log file %s: %s", log_path, exc)

        try:
            async for raw_line in stream:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                entry.log_ring.append(line)
                if log_file:
                    log_file.write(line + "\n")
                    log_file.flush()

                # Broadcast to subscribers
                if self._subscribers:
                    payload = {
                        "app": entry.spec.name,
                        "stream": stream_name,
                        "line": line,
                        "timestamp": time.time(),
                    }
                    for q, target_app in list(self._subscribers):
                        if target_app is None or target_app == entry.spec.name:
                            try:
                                q.put_nowait(payload)
                            except asyncio.QueueFull:
                                pass

                # Surface stderr at WARNING, stdout at DEBUG
                if stream_name == "stderr":
                    logger.warning("[%s] %s", entry.spec.name, line)
                else:
                    logger.debug("[%s] %s", entry.spec.name, line)
        finally:
            if log_file:
                log_file.close()

    async def _watch_exit(self, entry: ProcessEntry) -> None:
        """Wait for a process to exit and update state accordingly."""
        proc = entry.process
        if proc is None:
            return
        try:
            await proc.wait()
        except (RuntimeError, ProcessLookupError) as exc:
            logger.debug("watch_exit wait failed for %s: %s", entry.spec.name, exc)
            return
        if entry.process is not proc:
            return
        entry.exit_code = proc.returncode
        if entry.state in (ProcessState.STOPPING, ProcessState.STOPPED):
            return
        now = time.monotonic()
        # Retain crashes in sliding window
        entry.crash_timestamps = [
            t for t in entry.crash_timestamps if now - t <= _CRASH_WINDOW_SECONDS
        ]
        entry.crash_timestamps.append(now)
        if len(entry.crash_timestamps) >= _CRASH_THRESHOLD:
            entry.state = ProcessState.CRASH_LOOP
            logger.error(
                "Process '%s' entered CRASH_LOOP: %d crashes in last %ds. Auto-restart halted.",
                entry.spec.name,
                len(entry.crash_timestamps),
                int(_CRASH_WINDOW_SECONDS),
            )
        else:
            entry.state = ProcessState.FAILED
            logger.warning(
                "Process '%s' exited unexpectedly (exit code %s).",
                entry.spec.name,
                entry.exit_code,
            )
        # Schedule a restart evaluation (handled by _restart_watcher)
        entry.next_restart_at = time.monotonic()  # Evaluate immediately

    async def _restart_watcher(self) -> None:
        """
        Periodically evaluates all FAILED processes and restarts eligible ones
        according to their restart policy with exponential backoff.
        """
        try:
            while not self._shutting_down:
                await asyncio.sleep(1.0)
                now = time.monotonic()
                async with self._locked():
                    for entry in list(self._entries.values()):
                        if entry.state != ProcessState.FAILED:
                            continue
                        policy = entry.spec.restart_policy
                        if policy == RestartPolicy.NEVER:
                            continue
                        if policy == RestartPolicy.ON_FAILURE and entry.exit_code == 0:
                            entry.state = ProcessState.STOPPED
                            continue
                        if entry.restart_attempts >= _RESTART_MAX_ATTEMPTS:
                            logger.error(
                                "Process '%s' has failed %d times. Giving up.",
                                entry.spec.name,
                                entry.restart_attempts,
                            )
                            continue
                        if now < entry.next_restart_at:
                            continue
                        # Calculate next backoff delay
                        delay = min(
                            _RESTART_BASE_DELAY * (2 ** entry.restart_attempts),
                            _RESTART_MAX_DELAY,
                        )
                        entry.restart_attempts += 1
                        entry.next_restart_at = now + delay
                        logger.info(
                            "Auto-restarting '%s' (attempt %d/%d, next in %.0fs if this fails).",
                            entry.spec.name,
                            entry.restart_attempts,
                            _RESTART_MAX_ATTEMPTS,
                            delay,
                        )
                        try:
                            await self._do_start(entry)
                        except Exception as exc:
                            from core.vpn import VpnIsolationError

                            if isinstance(exc, VpnIsolationError):
                                logger.warning(
                                    "Not auto-restarting '%s' off-VPN: %s",
                                    entry.spec.name,
                                    exc,
                                )
                                entry.state = ProcessState.STOPPED
                                entry.process = None
                                continue
                            raise
        except asyncio.CancelledError:
            pass

    async def _shutdown(self, sig: signal.Signals) -> None:
        """Graceful shutdown: stop all processes in reverse-start order."""
        if self._shutting_down:
            return
        self._shutting_down = True
        logger.info("Received %s — shutting down all supervised processes…", sig.name)

        for name in reversed(self._start_order):
            entry = self._entries.get(name)
            if entry and entry.state not in (ProcessState.STOPPED, ProcessState.STOPPING):
                try:
                    await self._do_stop(entry)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Error stopping '%s': %s", name, exc)

        logger.info("All processes stopped.")
        # Give the event loop a chance to clean up before the process exits
        asyncio.get_event_loop().stop()


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _signal_tree(pid: int | None, sig: int) -> None:
    if not pid:
        return
    try:
        os.killpg(pid, sig)
        return
    except OSError:
        pass
    try:
        os.kill(pid, sig)
    except OSError:
        pass


def reclaim_leftover_processes(cmd: Sequence[str] | None) -> int:
    """Kill leftover children (Bazarr's launcher, etc.) that still match this app command."""
    token = _reclaim_token(cmd)
    if not token:
        return 0
    try:
        import psutil
    except ImportError:
        return 0

    killed = 0
    mine = {os.getpid(), os.getppid()}
    try:
        processes = list(psutil.process_iter(["pid", "cmdline"]))
    except (psutil.Error, PermissionError, OSError):
        return 0
    for proc in processes:
        pid = proc.info.get("pid")
        if not pid or pid in mine:
            continue
        cmdline = proc.info.get("cmdline") or []
        if not _cmdline_belongs_to_app(cmdline, token):
            continue
        try:
            logger.warning("Killing leftover process PID %s for %s", pid, token)
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
            killed += 1
        except (psutil.Error, OSError):
            continue
    return killed


def _reclaim_token(cmd: Sequence[str] | None) -> str:
    if not cmd:
        return ""
    try:
        path = Path(cmd[0]).resolve()
    except OSError:
        path = Path(cmd[0])
    parent = path.parent
    if parent.name in {"bin", "Scripts"} and parent.parent.name == "venv":
        return str(parent.parent.parent)
    if parent.name in {"bin", "sbin", "Scripts"}:
        return ""
    return str(parent)


def _cmdline_belongs_to_app(cmdline: Sequence[str], token: str) -> bool:
    marker = token.rstrip("/") + "/"
    joined = " ".join(cmdline)
    return marker in joined or joined.endswith(token.rstrip("/"))


async def _await_proc_exit(proc: asyncio.subprocess.Process, timeout: float) -> None:
    """Wait for an asyncio subprocess without hanging if wait() is broken."""
    pid = proc.pid
    deadline = time.monotonic() + timeout

    def _exited() -> bool:
        return proc.returncode is not None or not _pid_alive(pid)

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
        return
    except asyncio.TimeoutError:
        if _exited():
            return
        raise
    except (RuntimeError, ProcessLookupError) as exc:
        logger.debug("proc.wait() failed: %s", exc)

    while time.monotonic() < deadline:
        if _exited():
            return
        await asyncio.sleep(0.1)
    if _exited():
        return
    raise asyncio.TimeoutError()
