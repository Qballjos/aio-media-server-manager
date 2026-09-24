"""Scheduled catalog update checks and applies."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from applications.catalog import ApplicationCatalog
from core.installer.github import GitHubRateLimitError, GitHubReleaseClient
from core.maintenance import pause_reason, update_in_progress
from core.settings import Settings, settings
from core.supervisor import ProcessState, ProcessSupervisor
from core.updater import ApplicationUpdater

logger = logging.getLogger(__name__)

CHECK_SCHEDULES = frozenset({"off", "daily", "weekly", "monthly"})
APPLY_SCHEDULES = CHECK_SCHEDULES | {"same"}
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_STATE_NAME = "update_schedule.json"


def _zone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo((tz_name or "UTC").strip() or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def local_now(tz_name: str, *, now: datetime | None = None) -> datetime:
    if now is not None:
        if now.tzinfo is None:
            return now.replace(tzinfo=_zone(tz_name))
        return now.astimezone(_zone(tz_name))
    return datetime.now(_zone(tz_name))


def parse_hhmm(value: str) -> tuple[int, int]:
    match = _TIME_RE.match((value or "04:00").strip())
    if not match:
        return 4, 0
    hour = min(23, max(0, int(match.group(1))))
    minute = min(59, max(0, int(match.group(2))))
    return hour, minute


def normalize_check_schedule(value: str) -> str:
    item = str(value or "off").strip().lower()
    return item if item in CHECK_SCHEDULES else "off"


def normalize_apply_schedule(value: str) -> str:
    item = str(value or "off").strip().lower()
    return item if item in APPLY_SCHEDULES else "off"


def schedule_due(
    *,
    schedule: str,
    last_at: float | None,
    now: datetime,
    hour: int,
    minute: int,
    weekday: int = 0,
    day_of_month: int = 1,
) -> bool:
    kind = normalize_check_schedule(schedule)
    if kind == "off":
        return False
    today_slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < today_slot:
        return False
    if kind == "weekly" and now.weekday() != int(weekday) % 7:
        return False
    if kind == "monthly" and now.day != max(1, min(28, int(day_of_month))):
        return False
    if last_at is None:
        return True
    last = datetime.fromtimestamp(last_at, tz=now.tzinfo)
    return last < today_slot


class UpdateScheduler:
    def __init__(self, app_settings: Settings | None = None) -> None:
        self.settings = app_settings or settings
        self.updater = ApplicationUpdater(app_settings=self.settings)

    @property
    def state_file(self) -> Path:
        return Path(self.settings.config_dir) / _STATE_NAME

    def load_state(self) -> dict[str, Any]:
        if not self.state_file.is_file():
            return {
                "last_check_at": None,
                "last_apply_at": None,
                "last_error": "",
                "available": [],
                "last_results": [],
            }
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {
                "last_check_at": None,
                "last_apply_at": None,
                "last_error": "",
                "available": [],
                "last_results": [],
            }
        if not isinstance(data, dict):
            data = {}
        data.setdefault("last_check_at", None)
        data.setdefault("last_apply_at", None)
        data.setdefault("last_error", "")
        data.setdefault("available", [])
        data.setdefault("last_results", [])
        return data

    def save_state(self, data: dict[str, Any]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _refresh_github(self) -> None:
        from core.crypto import secret_store

        token = self.settings.github_token or secret_store.get_secret("github_token")
        self.updater.github = GitHubReleaseClient(token=token, max_rate_limit_wait=30)

    def public_status(self) -> dict[str, Any]:
        state = self.load_state()
        hour, minute = parse_hhmm(self.settings.update_time)
        now = local_now(self.settings.timezone)
        paused = pause_reason()
        check = normalize_check_schedule(self.settings.update_check_schedule)
        apply = normalize_apply_schedule(self.settings.update_apply_schedule)
        apply_kind = check if apply == "same" else apply
        return {
            "check_schedule": check,
            "apply_schedule": apply,
            "time": f"{hour:02d}:{minute:02d}",
            "weekday": int(self.settings.update_weekday) % 7,
            "day_of_month": max(1, min(28, int(self.settings.update_day_of_month))),
            "timezone": self.settings.timezone,
            "paused": bool(paused),
            "paused_reason": paused,
            "check_due": schedule_due(
                schedule=check,
                last_at=state.get("last_check_at"),
                now=now,
                hour=hour,
                minute=minute,
                weekday=self.settings.update_weekday,
                day_of_month=self.settings.update_day_of_month,
            ),
            "apply_due": schedule_due(
                schedule=apply_kind,
                last_at=state.get("last_apply_at"),
                now=now,
                hour=hour,
                minute=minute,
                weekday=self.settings.update_weekday,
                day_of_month=self.settings.update_day_of_month,
            ),
            "last_check_at": state.get("last_check_at"),
            "last_apply_at": state.get("last_apply_at"),
            "last_error": state.get("last_error") or "",
            "available": state.get("available") or [],
        }

    def _skip_reason(self, plugin, supervisor: ProcessSupervisor) -> str | None:
        if not plugin.is_installed():
            return "not_installed"
        if supervisor.status(plugin.name) == ProcessState.CRASH_LOOP:
            return "crash_loop"
        return None

    def check_installed(self) -> dict[str, Any]:
        self._refresh_github()
        catalog = ApplicationCatalog(app_settings=self.settings)
        supervisor = ProcessSupervisor.get()
        available: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        now_ts = datetime.now().timestamp()
        try:
            for plugin in catalog.all_plugins():
                reason = self._skip_reason(plugin, supervisor)
                if reason:
                    skipped.append({"name": plugin.name, "reason": reason})
                    continue
                info = self.updater.update_available(plugin)
                if info.get("update_available"):
                    available.append(info)
        except GitHubRateLimitError as exc:
            state = self.load_state()
            state["last_error"] = str(exc)
            state["last_check_at"] = now_ts
            self.save_state(state)
            raise
        state = self.load_state()
        state["last_check_at"] = now_ts
        state["last_error"] = ""
        state["available"] = available
        self.save_state(state)
        return {"checked_at": now_ts, "available": available, "skipped": skipped}

    async def apply_available(self, names: list[str] | None = None) -> dict[str, Any]:
        self._refresh_github()
        catalog = ApplicationCatalog(app_settings=self.settings)
        supervisor = ProcessSupervisor.get()
        wanted = {item.lower() for item in names} if names else None
        state = self.load_state()
        targets = state.get("available") or []
        results: list[dict[str, Any]] = []
        with update_in_progress():
            for item in targets:
                name = item.get("name")
                if not name or (wanted is not None and name not in wanted):
                    continue
                if not catalog.has(name):
                    continue
                plugin = catalog.get(name)
                reason = self._skip_reason(plugin, supervisor)
                if reason:
                    results.append({"name": name, "status": "skipped", "reason": reason})
                    continue
                current = self.updater.update_available(plugin)
                if not current.get("update_available"):
                    results.append({"name": name, "status": "skipped", "reason": "already_current"})
                    continue
                outcome = await self.updater.update(plugin)
                results.append(outcome)
        still_available = []
        for item in targets:
            name = item.get("name")
            match = next((row for row in results if row.get("name") == name), None)
            if match and match.get("status") == "updated":
                continue
            if match and match.get("status") == "skipped" and match.get("reason") == "already_current":
                continue
            still_available.append(item)
        state = self.load_state()
        state["last_apply_at"] = datetime.now().timestamp()
        state["last_results"] = results
        state["available"] = still_available
        self.save_state(state)
        return {"applied_at": state["last_apply_at"], "results": results}

    async def tick(self, *, force_check: bool = False, force_apply: bool = False) -> dict[str, Any]:
        paused = pause_reason()
        if paused and not force_check:
            return {"status": "paused", "reason": paused}
        hour, minute = parse_hhmm(self.settings.update_time)
        now = local_now(self.settings.timezone)
        state = self.load_state()
        check = normalize_check_schedule(self.settings.update_check_schedule)
        apply = normalize_apply_schedule(self.settings.update_apply_schedule)
        apply_kind = check if apply == "same" else apply
        ran_check = False
        report: dict[str, Any] = {"status": "idle"}
        if force_check or schedule_due(
            schedule=check,
            last_at=state.get("last_check_at"),
            now=now,
            hour=hour,
            minute=minute,
            weekday=self.settings.update_weekday,
            day_of_month=self.settings.update_day_of_month,
        ):
            report.update(self.check_installed())
            ran_check = True
            report["status"] = "checked"
        should_apply = force_apply or (
            apply_kind != "off"
            and schedule_due(
                schedule=apply_kind,
                last_at=state.get("last_apply_at"),
                now=now,
                hour=hour,
                minute=minute,
                weekday=self.settings.update_weekday,
                day_of_month=self.settings.update_day_of_month,
            )
        )
        if should_apply:
            if paused:
                return {"status": "paused", "reason": paused, **report}
            if not ran_check and not (self.load_state().get("available") or []):
                report.update(self.check_installed())
            applied = await self.apply_available()
            report["apply"] = applied
            report["status"] = "applied" if applied.get("results") else report.get("status", "checked")
        return report


scheduler = UpdateScheduler()


async def scheduler_loop() -> None:
    import asyncio

    from core.backup_jobs import backup_jobs

    while True:
        await asyncio.sleep(60)
        try:
            await backup_jobs.tick()
        except Exception:
            logger.exception("Scheduled backup tick failed")
        try:
            await scheduler.tick()
        except GitHubRateLimitError as exc:
            logger.warning("Scheduled update check hit GitHub rate limit: %s", exc)
        except Exception:
            logger.exception("Scheduled update tick failed")
