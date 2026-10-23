"""App updates: steps reported as the app's job, the API free meanwhile, one old version kept for a rollback."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

from core import install_jobs
from core.settings import Settings
from core.updater import ApplicationUpdater


def _setup(tmp_path: Path, install):
    cfg = Settings(
        config_dir=tmp_path / "config",
        install_dir=tmp_path / "config" / "apps",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        backup_dir=tmp_path / "backups",
    )
    (cfg.config_dir / "demo").mkdir(parents=True)
    install_dir = cfg.install_dir / "demo"
    install_dir.mkdir(parents=True)
    (install_dir / "old.txt").write_text("old", encoding="utf-8")
    plugin = SimpleNamespace(
        name="demo",
        install_dir=install_dir,
        manifest=SimpleNamespace(display_name="Demo", daemon=False),
        is_installed=lambda: True,
        require_host_arch=lambda: None,
        install=install,
    )
    install_jobs.clear_jobs()
    return ApplicationUpdater(app_settings=cfg), plugin


def _old_versions(plugin) -> list[Path]:
    return list(plugin.install_dir.parent.glob(".demo.pre-update*"))


def _wait_for_cleanup(plugin) -> None:
    deadline = time.monotonic() + 5
    while _old_versions(plugin) and time.monotonic() < deadline:
        time.sleep(0.05)


async def test_update_reports_each_step_while_the_api_keeps_answering(tmp_path: Path):
    def install():
        install_jobs.set_job("demo", "installing", "Downloading Demo…")
        time.sleep(0.4)
        (plugin.install_dir / "new.txt").write_text("new", encoding="utf-8")
        return SimpleNamespace(version="2.0")

    updater, plugin = _setup(tmp_path, install)
    task = asyncio.create_task(updater.update(plugin))
    seen = []
    while not task.done():
        job = install_jobs.get_job("demo")
        if job and (job["status"], job["message"]) not in seen:
            seen.append((job["status"], job["message"]))
        await asyncio.sleep(0.02)
    outcome = task.result()

    assert outcome["status"] == "updated"
    # The install ran in a thread: the loop kept turning and saw the app's own step, reported as part of the update.
    assert ("updating", "Downloading Demo…") in seen
    assert install_jobs.get_job("demo")["status"] == "updated"
    assert sorted(path.name for path in plugin.install_dir.iterdir()) == ["new.txt"]
    _wait_for_cleanup(plugin)
    assert _old_versions(plugin) == []


async def test_a_failed_update_puts_the_old_version_back_and_keeps_no_extra_copies(tmp_path: Path):
    def install():
        (plugin.install_dir / "half.txt").write_text("broken", encoding="utf-8")
        raise RuntimeError("boom")

    updater, plugin = _setup(tmp_path, install)
    # Left by an update the container restart interrupted.
    (plugin.install_dir.parent / ".demo.pre-update-1a2b3c4d").mkdir()
    outcome = await updater.update(plugin)

    assert outcome["status"] == "rolled_back"
    assert sorted(path.name for path in plugin.install_dir.iterdir()) == ["old.txt"]
    assert install_jobs.get_job("demo")["status"] == "rolled_back"
    _wait_for_cleanup(plugin)
    assert _old_versions(plugin) == []
    snapshots = list((tmp_path / "backups" / "app-snapshots" / "demo").glob("*.tar.gz"))
    assert len(snapshots) == 1
