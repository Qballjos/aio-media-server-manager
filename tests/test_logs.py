"""
tests/test_logs.py — Tests for centralized logs, secret redaction, and log downloading.
"""

import asyncio
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from core.crypto import secret_store
from core.log_redactor import redact_log_line
from core.supervisor import ProcessSupervisor, RestartPolicy


def test_redact_log_line():
    # Test API key patterns
    line1 = "Connecting to Sonarr with api_key=abcdef1234567890abcdef at http://localhost:8989"
    redacted1 = redact_log_line(line1)
    assert "abcdef1234567890abcdef" not in redacted1
    assert "[REDACTED_API_KEY]" in redacted1

    # Test token patterns
    line2 = "Bearer token=secret_jwt_token_value_9999"
    redacted2 = redact_log_line(line2)
    assert "secret_jwt_token_value_9999" not in redacted2
    assert "[REDACTED_TOKEN]" in redacted2

    # Test stored secrets in SecretStore
    secret_store.save_secret("test_wire_token", "super_duper_secret_xyz123")
    line3 = "Request with authorization: super_duper_secret_xyz123 inside URL"
    redacted3 = redact_log_line(line3)
    assert "super_duper_secret_xyz123" not in redacted3
    assert "[REDACTED_SECRET]" in redacted3

    secret_store.save_secret("preferred_download_client", "sabnzbd")
    path_line = "Cannot write to INI file /config/sabnzbd/sabnzbd.ini"
    assert redact_log_line(path_line) == path_line


def test_log_websocket_accepts_access_cookie(monkeypatch):
    from types import SimpleNamespace

    from api.routers.logs import _authenticate_ws
    from core.auth import COOKIE_ACCESS, auth_manager

    monkeypatch.setattr(auth_manager, "setup_required", lambda: False)
    monkeypatch.setattr(auth_manager, "jwt_secret", lambda: "test-jwt-secret-for-logs-websocket-32b")
    token = auth_manager.issue_token("tester")
    websocket = SimpleNamespace(
        cookies={COOKIE_ACCESS: token},
        query_params={},
    )
    assert _authenticate_ws(websocket) is True
    assert _authenticate_ws(SimpleNamespace(cookies={}, query_params={"token": token})) is True
    assert _authenticate_ws(SimpleNamespace(cookies={}, query_params={})) is False


@pytest.mark.asyncio
async def test_logs_api_and_websocket(tmp_path: Path):
    app = create_app()
    client = TestClient(app)

    supervisor = ProcessSupervisor.get()
    # Start process to generate logs
    await supervisor.start(
        name="test-logger-app",
        cmd=["python3", "-c", "import sys; sys.stdout.write('Hello from test app\\n'); sys.stdout.flush()"],
        restart_policy=RestartPolicy.NEVER,
        log_dir=tmp_path / "logs",
    )
    await asyncio.sleep(0.2)

    # Test REST query
    res = client.get("/api/logs?app=test-logger-app")
    assert res.status_code == 200
    data = res.json()
    assert data["app"] == "test-logger-app"
    assert any("Hello from test app" in entry["line"] for entry in data["logs"])

    # Test Search filter
    res_search = client.get("/api/logs?search=test%20app")
    assert res_search.status_code == 200
    assert len(res_search.json()["logs"]) >= 1

    # Test Download endpoint
    res_dl = client.get("/api/logs/download?app=test-logger-app")
    assert res_dl.status_code == 200
    assert "Hello from test app" in res_dl.text
    assert 'attachment; filename="test-logger-app-logs.txt"' in res_dl.headers.get("Content-Disposition", "")

    # Test live stream subscriber queue
    q = supervisor.subscribe_logs("test-logger-app")
    await supervisor.start(
        name="test-logger-app",
        cmd=["python3", "-c", "import sys; sys.stdout.write('Stream event msg\\n'); sys.stdout.flush()"],
        restart_policy=RestartPolicy.NEVER,
        log_dir=tmp_path / "logs",
    )
    event = await asyncio.wait_for(q.get(), timeout=2.0)
    assert event["app"] == "test-logger-app"
    assert "Stream event msg" in event["line"]
    supervisor.unsubscribe_logs(q)
