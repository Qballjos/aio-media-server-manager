"""Configuration backups: selection, SQLite snapshots, verify, restore, jobs, API."""

from __future__ import annotations

import json
import sqlite3
import tarfile
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.backup_jobs import BackupJobs
from core.backup_manager import MANIFEST_NAME, BackupManager
from core.settings import Settings


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = dict(
        config_dir=tmp_path / "config",
        install_dir=tmp_path / "config" / "apps",
        download_dir=tmp_path / "downloads",
        media_dir=tmp_path / "media",
        backup_dir=tmp_path / "backups",
        backup_retention=5,
    )
    values.update(overrides)
    cfg = Settings(**values)
    cfg.config_dir.mkdir(parents=True, exist_ok=True)
    return cfg


def _members(archive: str) -> list[str]:
    with tarfile.open(archive) as tar:
        return tar.getnames()


def _wal_db(path: Path, rows: int) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    conn.executemany("INSERT INTO items (name) VALUES (?)", [(f"row{i}",) for i in range(rows)])
    conn.commit()
    return conn


def test_backup_never_nests_backups_even_inside_config(tmp_path: Path):
    cfg = _settings(tmp_path, backup_dir=None)
    assert cfg.backup_dir == cfg.config_dir / "backups"
    (cfg.config_dir / "amm_config.json").write_text("{}", encoding="utf-8")
    manager = BackupManager(cfg)
    manager.create_backup(label="one")
    manager.create_backup(label="one")
    newest = manager.list_backups()[0]
    names = _members(newest["path"])
    assert not any(name.startswith("backups/") for name in names)
    assert len({row["name"] for row in manager.list_backups()}) == 2


def test_backup_keeps_large_databases_and_skips_caches(tmp_path: Path):
    cfg = _settings(tmp_path)
    root = cfg.config_dir
    big = root / "jellyfin" / "data" / "data" / "library.db"
    big.parent.mkdir(parents=True)
    with big.open("wb") as fh:
        fh.truncate(110 * 1024 * 1024)
    (root / "jellyfin" / "data" / "metadata" / "People").mkdir(parents=True)
    (root / "jellyfin" / "data" / "metadata" / "People" / "a.jpg").write_bytes(b"img")
    (root / "plex" / "config" / "Cache").mkdir(parents=True)
    (root / "plex" / "config" / "Cache" / "blob").write_bytes(b"x")
    (root / "sonarr" / "Backups").mkdir(parents=True)
    (root / "sonarr" / "Backups" / "old.zip").write_bytes(b"z")
    (root / "sonarr" / "config.xml").write_text("<Config/>", encoding="utf-8")
    (root / "sonarr" / "sonarr.db-wal").write_bytes(b"w")
    (root / "apps" / "sonarr").mkdir(parents=True)
    (root / "apps" / "sonarr" / "Sonarr.dll").write_bytes(b"bin")
    (root / "qbittorrent" / "BT_backup").mkdir(parents=True)
    (root / "qbittorrent" / "BT_backup" / "abc.torrent").write_bytes(b"t")

    info = BackupManager(cfg).create_backup()
    names = set(_members(info["path"]))
    assert "jellyfin/data/data/library.db" in names
    assert "sonarr/config.xml" in names
    assert "qbittorrent/BT_backup/abc.torrent" in names
    assert not any("metadata" in n or "Cache" in n or "Backups" in n for n in names)
    assert "sonarr/sonarr.db-wal" not in names
    assert not any(n.startswith("apps/") for n in names)
    assert MANIFEST_NAME in names
    assert {"jellyfin", "sonarr", "qbittorrent"}.issubset(set(info["sections"]))


def test_sqlite_snapshot_includes_uncheckpointed_wal(tmp_path: Path):
    cfg = _settings(tmp_path)
    db = cfg.config_dir / "sonarr" / "sonarr.db"
    conn = _wal_db(db, 50)
    try:
        assert Path(f"{db}-wal").stat().st_size > 0
        info = BackupManager(cfg).create_backup()
    finally:
        conn.close()

    other = _settings(tmp_path / "other", backup_dir=tmp_path / "backups")
    BackupManager(other).restore_backup(info["name"])
    restored = sqlite3.connect(other.config_dir / "sonarr" / "sonarr.db")
    try:
        assert restored.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 50
    finally:
        restored.close()


def test_restore_drops_stale_wal_and_supports_single_app(tmp_path: Path):
    cfg = _settings(tmp_path)
    root = cfg.config_dir
    (root / "sonarr").mkdir()
    (root / "radarr").mkdir()
    (root / "sonarr" / "config.xml").write_text("sonarr-v1", encoding="utf-8")
    (root / "radarr" / "config.xml").write_text("radarr-v1", encoding="utf-8")
    manager = BackupManager(cfg)
    info = manager.create_backup()

    (root / "sonarr" / "config.xml").write_text("sonarr-v2", encoding="utf-8")
    (root / "radarr" / "config.xml").write_text("radarr-v2", encoding="utf-8")
    (root / "sonarr" / "config.xml-wal").write_text("stale", encoding="utf-8")

    result = manager.restore_backup(info["name"], sections=["sonarr"])
    assert result["sections"] == ["sonarr"]
    assert (root / "sonarr" / "config.xml").read_text(encoding="utf-8") == "sonarr-v1"
    assert (root / "radarr" / "config.xml").read_text(encoding="utf-8") == "radarr-v2"
    assert not (root / "sonarr" / "config.xml-wal").exists()


def test_verify_detects_checksum_mismatch(tmp_path: Path):
    cfg = _settings(tmp_path)
    (cfg.config_dir / "amm_config.json").write_text("{}", encoding="utf-8")
    manager = BackupManager(cfg)
    info = manager.create_backup()
    assert manager.verify_backup(info["name"])["ok"] is True

    sidecar = Path(info["path"] + ".json")
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    data["files"]["amm_config.json"]["sha256"] = "0" * 64
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    result = manager.verify_backup(info["name"])
    assert result["ok"] is False
    assert result["mismatched"] == ["amm_config.json"]


def test_legacy_v1_archive_restores_without_nested_backups(tmp_path: Path):
    cfg = _settings(tmp_path)
    legacy = cfg.config_dir / "backups"
    legacy.mkdir(parents=True)
    staging = tmp_path / "v1"
    (staging / "sonarr").mkdir(parents=True)
    (staging / "sonarr" / "config.xml").write_text("old", encoding="utf-8")
    (staging / "backups").mkdir()
    (staging / "backups" / "amm-nested.tar.gz").write_bytes(b"nested")
    archive = legacy / "amm-20240101-000000-manual.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(staging / "sonarr" / "config.xml", arcname="sonarr/config.xml")
        tar.add(staging / "backups" / "amm-nested.tar.gz", arcname="backups/amm-nested.tar.gz")

    manager = BackupManager(cfg)
    listed = {row["name"]: row for row in manager.list_backups()}
    assert listed[archive.name]["location"] == "legacy"
    assert listed[archive.name]["format"] == 1
    assert manager.verify_backup(archive.name)["ok"] is True
    manager.restore_backup(archive.name)
    assert (cfg.config_dir / "sonarr" / "config.xml").read_text(encoding="utf-8") == "old"
    assert not (cfg.config_dir / "backups" / "amm-nested.tar.gz").exists()


def test_invalid_backup_names_are_rejected(tmp_path: Path):
    manager = BackupManager(_settings(tmp_path))
    for name in ("../secret.key", "amm-x.tar.gz/../../etc", "notes.txt"):
        with pytest.raises(FileNotFoundError):
            manager.resolve_archive(name)


def test_update_snapshots_are_pruned_and_restorable(tmp_path: Path):
    cfg = _settings(tmp_path)
    (cfg.config_dir / "sonarr").mkdir()
    target = cfg.config_dir / "sonarr" / "config.xml"
    manager = BackupManager(cfg)
    snapshots = []
    for index in range(5):
        target.write_text(f"v{index}", encoding="utf-8")
        snapshots.append(manager.snapshot_application("sonarr"))
    remaining = sorted((cfg.backup_dir / "app-snapshots" / "sonarr").glob("*.tar.gz"))
    assert len(remaining) == 3
    target.write_text("broken", encoding="utf-8")
    manager.restore_application_snapshot(snapshots[-1])
    assert target.read_text(encoding="utf-8") == "v4"


@pytest.mark.asyncio
async def test_restore_job_makes_safety_backup_and_keeps_target(tmp_path: Path):
    cfg = _settings(tmp_path, backup_retention=2)
    config_file = cfg.config_dir / "amm_config.json"
    config_file.write_text(json.dumps({"backup_retention": 2, "timezone": "UTC"}), encoding="utf-8")
    jobs = BackupJobs(cfg)
    jobs.start_backup("first")
    first = (await jobs.wait())["result"]["name"]
    jobs.start_backup("second")
    await jobs.wait()

    config_file.write_text(json.dumps({"backup_retention": 2, "timezone": "Europe/Amsterdam"}), encoding="utf-8")
    jobs.start_restore(first)
    job = await jobs.wait()
    assert job["status"] == "done", job["error"]
    assert job["result"]["safety_backup"].startswith("amm-")
    assert json.loads(config_file.read_text(encoding="utf-8"))["timezone"] == "UTC"
    names = [row["name"] for row in jobs.manager.list_backups()]
    assert job["result"]["safety_backup"] in names
    assert len(names) == 2
    assert jobs.load_state()["last_name"]


def test_backup_schedule_due(tmp_path: Path):
    cfg = _settings(tmp_path, backup_schedule="daily", backup_time="03:30", timezone="UTC")
    jobs = BackupJobs(cfg)
    assert jobs.due(now=datetime(2026, 9, 24, 3, 0)) is False
    assert jobs.due(now=datetime(2026, 9, 24, 3, 31)) is True
    cfg.backup_schedule = "off"
    assert jobs.due(now=datetime(2026, 9, 24, 3, 31)) is False


def test_backup_api_download_upload_roundtrip(tmp_path: Path, monkeypatch):
    from api.app import create_app
    from api.routers import backups as backups_router
    from core.auth import auth_manager

    cfg = _settings(tmp_path)
    cfg.initialise()
    (cfg.config_dir / "sonarr").mkdir(exist_ok=True)
    (cfg.config_dir / "sonarr" / "config.xml").write_text("<Config/>", encoding="utf-8")
    monkeypatch.setattr(auth_manager, "_settings", cfg)
    jobs = BackupJobs(cfg)
    monkeypatch.setattr(backups_router, "backup_jobs", jobs)
    monkeypatch.setattr(backups_router, "manager", jobs.manager)
    auth_manager._rate._hits.clear()
    client = TestClient(create_app())
    setup = client.post(
        "/api/auth/setup",
        json={"username": "admin", "email": "admin@example.com", "password": "StrongPassword123!"},
    )
    assert setup.status_code == 200
    headers = {
        "Authorization": f"Bearer {setup.json()['access_token']}",
        "X-CSRF-Token": setup.json()["csrf_token"],
    }

    info = jobs.manager.create_backup(label="api")
    download = client.get(f"/api/backups/{info['name']}/download", headers=headers)
    assert download.status_code == 200
    payload = download.content
    jobs.manager.delete_backup(info["name"])

    bad = client.post(
        "/api/backups/upload?filename=junk.tar.gz",
        content=b"not a tarball",
        headers={**headers, "Content-Type": "application/octet-stream"},
    )
    assert bad.status_code == 400

    uploaded = client.post(
        f"/api/backups/upload?filename={info['name']}",
        content=payload,
        headers={**headers, "Content-Type": "application/octet-stream"},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["backup"]["name"] == info["name"]
    assert uploaded.json()["backup"]["format"] == 2

    details = client.get(f"/api/backups/{info['name']}", headers=headers)
    assert details.status_code == 200
    assert "sonarr" in details.json()["sections"]
    assert client.get("/api/backups/amm-missing.tar.gz/download", headers=headers).status_code == 404
