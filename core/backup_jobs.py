"""Background backup/verify/restore jobs and the backup schedule."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from core.backup_manager import MANAGER_SECTION, BackupManager
from core.maintenance import backup_in_progress, pause_reason
from core.settings import Settings, settings

logger = logging.getLogger(__name__)

_STATE_NAME = "backup_state.json"


class BackupBusyError(RuntimeError):
    pass


class BackupJobs:
    def __init__(self, app_settings: Settings | None = None) -> None:
        self.settings = app_settings or settings
        self.manager = BackupManager(self.settings)
        self.job: dict[str, Any] | None = None
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Job bookkeeping
    # ------------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return bool(self.job and self.job.get("status") == "running")

    def job_status(self) -> dict[str, Any] | None:
        return dict(self.job) if self.job else None

    def _begin(self, kind: str, name: str | None = None) -> dict[str, Any]:
        if self.busy:
            raise BackupBusyError(f"A backup {self.job['kind']} is already running.")
        self.job = {
            "id": uuid.uuid4().hex[:12],
            "kind": kind,
            "name": name,
            "status": "running",
            "stage": "starting",
            "started_at": time.time(),
            "finished_at": None,
            "done": 0,
            "total": 0,
            "result": None,
            "error": "",
        }
        return self.job

    def _progress(self, job: dict[str, Any]) -> Callable[[int, int], None]:
        def update(done: int, total: int) -> None:
            job["done"] = done
            job["total"] = total

        return update

    def _launch(self, job: dict[str, Any], work: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
        async def runner() -> None:
            try:
                job["result"] = await work()
                job["status"] = "done"
            except Exception as exc:
                logger.exception("Backup %s failed", job["kind"])
                job["status"] = "error"
                job["error"] = str(exc) or exc.__class__.__name__
            finally:
                job["finished_at"] = time.time()
                job["stage"] = job["status"]

        self._task = asyncio.create_task(runner())
        return dict(job)

    async def wait(self) -> dict[str, Any] | None:
        if self._task is not None:
            await self._task
        return self.job_status()

    # ------------------------------------------------------------------
    # Backup
    # ------------------------------------------------------------------

    def start_backup(self, label: str | None = None, *, kind: str = "manual") -> dict[str, Any]:
        job = self._begin("backup")
        return self._launch(job, lambda: self._run_backup(job, label, kind))

    async def _run_backup(self, job: dict[str, Any], label: str | None, kind: str) -> dict[str, Any]:
        job["stage"] = "archiving"
        try:
            with backup_in_progress():
                result = await asyncio.to_thread(
                    self.manager.create_backup, label, kind=kind, progress=self._progress(job)
                )
        except Exception as exc:
            self._record(kind, ok=False, error=str(exc))
            raise
        job["name"] = result["name"]
        self._record(kind, ok=True, name=result["name"], warnings=len(result.get("warnings") or []))
        return result

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------

    def start_verify(self, name: str) -> dict[str, Any]:
        self.manager.resolve_archive(name)
        job = self._begin("verify", name)

        async def work() -> dict[str, Any]:
            job["stage"] = "verifying"
            return await asyncio.to_thread(self.manager.verify_backup, name, self._progress(job))

        return self._launch(job, work)

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def start_restore(self, name: str, sections: Optional[list[str]] = None) -> dict[str, Any]:
        self.manager.resolve_archive(name)
        blocked = pause_reason()
        if blocked in {"install", "update", "backup"}:
            raise BackupBusyError(f"Cannot restore while an {blocked} is running.")
        job = self._begin("restore", name)
        return self._launch(job, lambda: self._run_restore(job, name, sections))

    async def _run_restore(self, job: dict[str, Any], name: str, sections: Optional[list[str]]) -> dict[str, Any]:
        from applications.catalog import ApplicationCatalog, refresh_live_catalogs
        from core.supervisor import ProcessSupervisor

        wanted = None if not sections or "all" in sections else {s.lower() for s in sections}
        with backup_in_progress():
            job["stage"] = "verifying"
            check = await asyncio.to_thread(self.manager.verify_backup, name, self._progress(job))
            if not check.get("ok"):
                raise RuntimeError(f"Backup failed verification: {check.get('error')}")

            job["stage"] = "safety backup"
            safety = await asyncio.to_thread(
                self.manager.create_backup,
                "pre-restore",
                kind="pre-restore",
                progress=self._progress(job),
                prune=False,
            )

            supervisor = ProcessSupervisor.get()
            catalog = ApplicationCatalog(app_settings=self.settings)
            running = {row["name"] for row in supervisor.list_processes() if row.get("state") == "running"}
            to_stop = [
                plugin.name
                for plugin in catalog.all_plugins()
                if plugin.name in running and (wanted is None or plugin.name in wanted)
            ]
            job["stage"] = "stopping apps"
            for app_name in to_stop:
                await supervisor.stop(app_name)

            restarted: list[str] = []
            failed: list[str] = []
            try:
                job["stage"] = "restoring files"
                result = await asyncio.to_thread(
                    self.manager.restore_backup, name, sections, self._progress(job)
                )
            finally:
                if wanted is None or MANAGER_SECTION in wanted:
                    reload_runtime_state(self.settings)
                refresh_live_catalogs()
                job["stage"] = "starting apps"
                fresh = ApplicationCatalog(app_settings=self.settings)
                for app_name in to_stop:
                    try:
                        plugin = fresh.get(app_name)
                        await supervisor.start(
                            name=plugin.name,
                            cmd=plugin.start_command(),
                            cwd=plugin.working_directory(),
                            env=plugin.extra_env(),
                            log_dir=self.settings.config_dir / "logs",
                        )
                        restarted.append(app_name)
                    except Exception as exc:
                        logger.warning("Could not restart %s after restore: %s", app_name, exc)
                        failed.append(app_name)
            await asyncio.to_thread(self.manager.prune)
        result["safety_backup"] = safety["name"]
        result["restarted"] = restarted
        result["restart_failed"] = failed
        return result

    # ------------------------------------------------------------------
    # State + schedule
    # ------------------------------------------------------------------

    @property
    def state_file(self) -> Path:
        return Path(self.settings.config_dir) / _STATE_NAME

    def load_state(self) -> dict[str, Any]:
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        for key in ("last_backup_at", "last_scheduled_at", "last_attempt_at"):
            data.setdefault(key, None)
        data.setdefault("last_name", "")
        data.setdefault("last_error", "")
        data.setdefault("last_warnings", 0)
        return data

    def _record(self, kind: str, *, ok: bool, name: str = "", error: str = "", warnings: int = 0) -> None:
        state = self.load_state()
        now = time.time()
        state["last_attempt_at"] = now
        if kind == "scheduled":
            state["last_scheduled_at"] = now
        if ok:
            state["last_backup_at"] = now
            state["last_name"] = name
            state["last_error"] = ""
            state["last_warnings"] = warnings
        else:
            state["last_error"] = error
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.debug("Could not write %s: %s", self.state_file, exc)

    def public_status(self) -> dict[str, Any]:
        from core.update_schedule import parse_hhmm

        state = self.load_state()
        hour, minute = parse_hhmm(self.settings.backup_time)
        return {
            "schedule": self.settings.backup_schedule,
            "time": f"{hour:02d}:{minute:02d}",
            "weekday": int(self.settings.backup_weekday) % 7,
            "day_of_month": max(1, min(28, int(self.settings.backup_day_of_month))),
            "timezone": self.settings.timezone,
            "last_backup_at": state.get("last_backup_at"),
            "last_name": state.get("last_name") or "",
            "last_error": state.get("last_error") or "",
            "last_warnings": state.get("last_warnings") or 0,
        }

    def due(self, now=None) -> bool:
        from core.update_schedule import local_now, parse_hhmm, schedule_due

        hour, minute = parse_hhmm(self.settings.backup_time)
        return schedule_due(
            schedule=self.settings.backup_schedule,
            last_at=self.load_state().get("last_scheduled_at"),
            now=local_now(self.settings.timezone, now=now),
            hour=hour,
            minute=minute,
            weekday=self.settings.backup_weekday,
            day_of_month=self.settings.backup_day_of_month,
        )

    async def tick(self) -> str:
        if self.busy or pause_reason():
            return "paused"
        if not self.due():
            return "idle"
        try:
            self.start_backup("scheduled", kind="scheduled")
        except BackupBusyError:
            return "paused"
        await self.wait()
        return "backed_up"


def reload_runtime_state(app_settings: Settings) -> None:
    from core.crypto import secret_store

    secret_store.reload()
    try:
        app_settings._load_persisted()
        app_settings.apply_timezone()
    except Exception as exc:
        logger.warning("Could not reload settings after restore: %s", exc)


backup_jobs = BackupJobs()
