"""Security boundaries for parsing, public errors and child-app credentials."""

import os
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from core.auth import AuthManager, normalize_email
from core.backup_jobs import BackupJobs
from core.integrations.credentials import _read_bazarr_api_key
from core.integrations.sabnzbd import write_bootstrap_ini
from core.recyclarr import save_prefs, save_yaml, write_recyclarr_config
from core.settings import Settings


@pytest.mark.parametrize("case", ["email", "bazarr"])
def test_malformed_input_does_not_stall_parsing(case, tmp_path):
    # Keep the timeout outside the parser so a backtracking regression cannot hang pytest.
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.yaml").write_text("auth:\n" + "  \n" * 40)
    program = {
        "email": """
from core.auth import normalize_email
from fastapi import HTTPException
try:
    normalize_email('!@' + '!.' * 100000 + '@')
except HTTPException as exc:
    assert exc.status_code == 422
else:
    raise AssertionError('invalid email accepted')
""",
        "bazarr": """
from pathlib import Path
import sys
from core.integrations.credentials import _read_bazarr_api_key
assert _read_bazarr_api_key(Path(sys.argv[1])) is None
""",
    }[case]
    subprocess.run(
        [sys.executable, "-c", program, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        timeout=10,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        (" Admin@Example.COM ", "admin@example.com"),
        ("a+b@sub.example.com", "a+b@sub.example.com"),
        ("a@b", None),
        ("a@@b.com", None),
        ("a b@example.com", None),
        ("a@.b", None),
        ("a@b.", None),
    ],
)
def test_email_validation_preserves_supported_addresses(value, expected):
    if expected is None:
        with pytest.raises(HTTPException):
            normalize_email(value)
    else:
        assert normalize_email(value) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "auth:\n  enabled: true\n  apikey: abc123\ngeneral:\n  apikey: wrong\n",
            "abc123",
        ),
        ("auth:\n  enabled: true\ngeneral:\n  apikey: wrong\n", None),
        ("general:\n  apikey: wrong\nauth:\n  apikey: abc123\n", "abc123"),
    ],
)
def test_bazarr_key_is_read_only_from_auth_section(tmp_path, text, expected):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "config.yaml").write_text(text)
    assert _read_bazarr_api_key(tmp_path) == expected


@pytest.mark.parametrize("operation", ["generated", "edited", "refreshed", "preserved"])
def test_recyclarr_credentials_are_private(tmp_path, operation):
    path = tmp_path / "recyclarr.yml"
    if operation != "generated":
        path.write_text(
            "sonarr:\n  tv:\n    base_url: http://old\n    api_key: old-key\n    trash_id: abc\n"
        )
        path.chmod(0o666)
    if operation == "edited":
        save_yaml(tmp_path, "sonarr:\n  tv:\n    api_key: edited-key\n")
    else:
        if operation == "preserved":
            save_prefs(tmp_path, {"manual_override": True})
        write_recyclarr_config(
            tmp_path,
            sonarr_url="http://new",
            sonarr_key="new-key",
            radarr_url="http://radarr",
            radarr_key="radarr-key",
        )
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.stat().st_uid == os.getuid()
    assert path.stat().st_gid == os.getgid()
    text = path.read_text()
    assert {
        "generated": "new-key",
        "edited": "edited-key",
        "refreshed": "new-key",
        "preserved": "old-key",
    }[operation] in text


@pytest.mark.parametrize("exists", [False, True])
def test_sabnzbd_bootstrap_protects_new_and_existing_credentials(tmp_path, exists):
    path = tmp_path / "sabnzbd.ini"
    if exists:
        path.write_text("existing credentials\n")
        path.chmod(0o666)
    write_bootstrap_ini(
        path,
        port=8085,
        complete_dir="/downloads/complete",
        incomplete_dir="/downloads/incomplete",
        password="bootstrap-password",
    )
    assert path.stat().st_mode & 0o777 == 0o600
    assert (
        "existing credentials" if exists else "bootstrap-password"
    ) in path.read_text()


def test_private_config_write_is_atomic_and_preserves_owner(tmp_path, monkeypatch):
    from core import file_io

    path = tmp_path / "credentials.ini"
    path.write_text("old password")
    owner = path.stat()

    def failed_replace(source, destination):
        temporary = Path(source)
        assert temporary.stat().st_mode & 0o777 == 0o600
        assert (temporary.stat().st_uid, temporary.stat().st_gid) == (
            owner.st_uid,
            owner.st_gid,
        )
        assert temporary.read_text() == "new password"
        assert path.read_text() == "old password"
        raise OSError("disk failure")

    with monkeypatch.context() as patcher:
        patcher.setattr(file_io.os, "replace", failed_replace)
        with pytest.raises(OSError, match="disk failure"):
            file_io.write_private_text(path, "new password")
    assert list(tmp_path.iterdir()) == [path]
    assert path.read_text() == "old password"
    file_io.write_private_text(path, "new password")
    assert path.read_text() == "new password"
    assert path.stat().st_mode & 0o777 == 0o600
    assert (path.stat().st_uid, path.stat().st_gid) == (owner.st_uid, owner.st_gid)


@pytest.fixture
def backup_client(tmp_path, monkeypatch):
    from api.routers import backups

    cfg = Settings(config_dir=tmp_path / "config", backup_dir=tmp_path / "backups")
    cfg.config_dir.mkdir()
    auth = AuthManager(cfg)
    auth.create_admin("admin", "StrongPassword123!")
    jobs = BackupJobs(cfg)
    monkeypatch.setattr(backups, "auth_manager", auth)
    monkeypatch.setattr(backups, "settings", cfg)
    monkeypatch.setattr(backups, "backup_jobs", jobs)
    monkeypatch.setattr(backups, "manager", jobs.manager)
    app = FastAPI()
    app.include_router(backups.router)
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {auth.issue_token('admin')}"
    return client, jobs


@pytest.mark.parametrize("failure", ["upload", "missing", "busy", "external"])
def test_backup_responses_do_not_expose_exception_details(
    backup_client, monkeypatch, failure
):
    from api.routers import backups
    from core.backup_jobs import BackupBusyError
    from core.external_backups import ExternalBackups

    client, jobs = backup_client
    private = "private-exception /config/internal.ini password=example-secret"

    def fail(*args, **kwargs):
        raise {
            "upload": OSError,
            "missing": FileNotFoundError,
            "busy": BackupBusyError,
            "external": ValueError,
        }[failure](private)

    if failure == "upload":
        monkeypatch.setattr(backups, "_check_archive", fail)
        response = client.post("/api/backups/upload", content=b"invalid")
    elif failure == "missing":
        monkeypatch.setattr(jobs.manager, "resolve_archive", fail)
        response = client.get("/api/backups/amm-missing.tar.gz/download")
    elif failure == "busy":
        monkeypatch.setattr(jobs, "start_backup", fail)
        response = client.post("/api/backups")
    else:
        monkeypatch.setattr(ExternalBackups, "save", fail)
        response = client.put("/api/backups/external/config", json={})
    assert (
        response.status_code
        == {"upload": 400, "missing": 404, "busy": 409, "external": 422}[failure]
    )
    assert "private-exception" not in response.text
    assert "example-secret" not in response.text
    assert response.json()["detail"]


async def test_backup_job_and_schedule_hide_uncontrolled_failure(tmp_path, monkeypatch):
    jobs = BackupJobs(
        Settings(config_dir=tmp_path / "config", backup_dir=tmp_path / "backups")
    )

    def fail(*args, **kwargs):
        raise OSError("private-exception password=example-secret")

    monkeypatch.setattr(jobs.manager, "create_backup", fail)
    monkeypatch.setattr("core.notifications.notify", lambda *a, **kw: None)
    jobs.start_backup("scheduled", kind="scheduled")
    job = await jobs.wait()
    assert job["status"] == "error"
    for error in (job["error"], jobs.public_status()["last_error"]):
        assert error
        assert "private-exception" not in error and "example-secret" not in error


def test_application_port_sync_hides_uncontrolled_failure(tmp_path, monkeypatch):
    from api.routers import applications
    from applications.catalog import ApplicationCatalog
    from core import app_prefs, cloudflare_api, public_hostnames

    cfg = Settings(config_dir=tmp_path / "config")
    cfg.config_dir.mkdir()
    auth = AuthManager(cfg)
    auth.create_admin("admin", "StrongPassword123!")
    monkeypatch.setattr(applications, "auth_manager", auth)
    monkeypatch.setattr(applications, "settings", cfg)
    monkeypatch.setattr(app_prefs, "settings", cfg)
    monkeypatch.setattr(applications, "catalog", ApplicationCatalog(app_settings=cfg))
    monkeypatch.setattr(applications, "refresh_live_catalogs", lambda: None)
    monkeypatch.setattr(applications, "_application_settings", lambda *a: {})
    monkeypatch.setattr(
        public_hostnames,
        "load_hostnames",
        lambda: {"sonarr": {"last_published": "tv.example.com"}},
    )
    monkeypatch.setattr(cloudflare_api, "api_token_configured", lambda: True)

    async def fail(*a):
        raise RuntimeError("private-exception password=example-secret")

    monkeypatch.setattr(cloudflare_api, "sync_published_app_port", fail)
    app = FastAPI()
    app.include_router(applications.router)
    response = TestClient(app).patch(
        "/api/applications/sonarr/settings",
        json={"port": 18989, "restart": False},
        headers={"Authorization": f"Bearer {auth.issue_token('admin')}"},
    )
    assert response.status_code == 200
    assert response.json()["cloudflare_tunnel_sync"]["ok"] is False
    assert (
        "private-exception" not in response.text
        and "example-secret" not in response.text
    )
