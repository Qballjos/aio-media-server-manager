"""Scheduled catalog update checks."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from core.maintenance import begin_install, end_install, pause_reason
from core.settings import Settings
from core.supervisor import ProcessState
from core.update_schedule import UpdateScheduler, schedule_due
from core.updater import _is_newer


def test_schedule_due_daily_after_slot():
    tz = ZoneInfo("UTC")
    now = datetime(2026, 9, 24, 5, 0, tzinfo=tz)
    assert schedule_due(schedule="daily", last_at=None, now=now, hour=4, minute=0) is True
    last = datetime(2026, 9, 24, 4, 1, tzinfo=tz).timestamp()
    assert schedule_due(schedule="daily", last_at=last, now=now, hour=4, minute=0) is False
    before = datetime(2026, 9, 24, 3, 0, tzinfo=tz)
    assert schedule_due(schedule="daily", last_at=None, now=before, hour=4, minute=0) is False


def test_schedule_due_weekly_and_off():
    tz = ZoneInfo("UTC")
    thursday = datetime(2026, 9, 24, 12, 0, tzinfo=tz)  # weekday 3
    assert schedule_due(
        schedule="weekly", last_at=None, now=thursday, hour=4, minute=0, weekday=3
    )
    assert not schedule_due(
        schedule="weekly", last_at=None, now=thursday, hour=4, minute=0, weekday=0
    )
    assert not schedule_due(schedule="off", last_at=None, now=thursday, hour=4, minute=0)


def test_is_newer_versions():
    assert _is_newer("2.0.0", "1.9.0") is True
    assert _is_newer("1.0.0", "1.0.0") is False


def test_check_skips_missing_and_crash_loop(tmp_path: Path):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        install_dir=tmp_path / "apps",
    )
    cfg.initialise()
    sched = UpdateScheduler(app_settings=cfg)
    plugin = MagicMock()
    plugin.name = "sonarr"
    plugin.is_installed.return_value = False
    crash = MagicMock()
    crash.name = "radarr"
    crash.is_installed.return_value = True
    supervisor = MagicMock()
    supervisor.status.return_value = ProcessState.CRASH_LOOP
    catalog = MagicMock()
    catalog.all_plugins.return_value = [plugin, crash]
    with (
        patch("core.update_schedule.ApplicationCatalog", return_value=catalog),
        patch("core.update_schedule.ProcessSupervisor.get", return_value=supervisor),
        patch.object(sched.updater, "update_available") as check,
    ):
        result = sched.check_installed()
    check.assert_not_called()
    reasons = {row["name"]: row["reason"] for row in result["skipped"]}
    assert reasons["sonarr"] == "not_installed"
    assert reasons["radarr"] == "crash_loop"
    assert result["available"] == []


def test_pause_during_install_and_wizard():
    begin_install()
    try:
        assert pause_reason() in {"install", "wizard"}
    finally:
        end_install()


@pytest.mark.asyncio
async def test_tick_paused_when_wizard_open(tmp_path: Path, monkeypatch):
    cfg = Settings(
        config_dir=tmp_path / "config",
        download_dir=tmp_path / "dl",
        media_dir=tmp_path / "media",
        install_dir=tmp_path / "apps",
        update_check_schedule="daily",
    )
    cfg.initialise()
    monkeypatch.setattr("core.update_schedule.pause_reason", lambda: "wizard")
    sched = UpdateScheduler(app_settings=cfg)
    report = await sched.tick()
    assert report["status"] == "paused"
    assert report["reason"] == "wizard"
