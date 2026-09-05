"""
core/supervisor.py — Async Process Supervisor

Manages the lifecycle of named child processes:
  - Start   : asyncio.create_subprocess_exec, stdout/stderr routing
  - Stop    : SIGTERM → wait → SIGKILL (timeout)
  - Restart : stop + start with the same command/env
  - Zombie reaping : SIGCHLD handler calling os.waitpid(-1, WNOHANG)
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


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class ProcessState(str, enum.Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"
    STOPPING = "stopping"


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

        # Register OS-level signal handlers (if running in main thread)
        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda s=sig: asyncio.ensure_future(self._shutdown(s)))
            # SIGCHLD: reap zombie children
            signal.signal(signal.SIGCHLD, self._sigchld_handler)
        except (ValueError, RuntimeError, NotImplementedError):
            logger.debug("Signal handlers could not be installed (not running in main thread).")

        # Background auto-restart task
        self._restart_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        async with self._lock:
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

            await self._do_start(entry)

            if name not in self._start_order:
                self._start_order.append(name)

        # Kick off the auto-restart watcher if not already running
        if self._restart_task is None or self._restart_task.done():
            self._restart_task = asyncio.ensure_future(self._restart_watcher())

    async def stop(self, name: str, timeout: float = _STOP_TIMEOUT) -> None:
        """Gracefully stop a named process (SIGTERM then SIGKILL)."""
        async with self._lock:
            entry = self._entries.get(name)
            if entry is None or entry.state == ProcessState.STOPPED:
                logger.debug("stop(%s): already stopped", name)
                return
            await self._do_stop(entry, timeout=timeout)

    async def restart(self, name: str) -> None:
        """Stop then start a named process with the same spec."""
        async with self._lock:
            entry = self._entries.get(name)
            if entry is None:
                raise KeyError(f"Unknown process: {name!r}")
            await self._do_stop(entry)
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
                }
            )
        return result

    def get_logs(self, name: str) -> list[str]:
        """Return the in-memory log ring for a named process."""
        entry = self._entries.get(name)
        if entry is None:
            return []
        return list(entry.log_ring)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _do_start(self, entry: ProcessEntry) -> None:
        """Low-level start (must be called with self._lock held)."""
        spec = entry.spec
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
            )
        except FileNotFoundError as exc:
            logger.error("Cannot start '%s': executable not found — %s", spec.name, exc)
            entry.state = ProcessState.FAILED
            entry.exit_code = -1
            return

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
        """Low-level stop (must be called with self._lock held)."""
        if entry.process is None or entry.state == ProcessState.STOPPED:
            return

        entry.state = ProcessState.STOPPING
        proc = entry.process
        name = entry.spec.name
        logger.info("Stopping process '%s' (PID %d)…", name, proc.pid)

        try:
            proc.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            pass  # Already gone

        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "Process '%s' did not exit within %.0fs — sending SIGKILL.", name, timeout
            )
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()

        entry.exit_code = proc.returncode
        entry.state = ProcessState.STOPPED
        entry.process = None
        logger.info(
            "Process '%s' stopped (exit code %s).", name, entry.exit_code
        )

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
        await proc.wait()
        entry.exit_code = proc.returncode
        if entry.state != ProcessState.STOPPING:
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
        while not self._shutting_down:
            await asyncio.sleep(1.0)
            now = time.monotonic()
            async with self._lock:
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
                    await self._do_start(entry)

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

    # ------------------------------------------------------------------
    # SIGCHLD — zombie reaping
    # ------------------------------------------------------------------

    @staticmethod
    def _sigchld_handler(_signum: int, _frame: object) -> None:
        """
        Reap any exited child processes immediately to avoid zombies.

        Called in the main thread's signal context; must be fast and
        non-blocking.  We loop with WNOHANG until no more children are
        available to reap.
        """
        try:
            while True:
                pid, _status = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
        except ChildProcessError:
            pass  # No children — expected
        except OSError:
            pass
