"""
api/routers/logs.py — Centralized Log Viewer & Live Log Streaming

Provides REST query, error filtering, log downloading, and WebSocket live log streaming
with automatic secret and credential redaction.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect, status

from core.auth import auth_manager
from core.log_redactor import redact_log_line
from core.supervisor import ProcessSupervisor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logs", tags=["Logs"])


def _ensure_authenticated(request: Request) -> None:
    if not auth_manager.setup_required():
        auth_manager.authenticate_request(request)


def _authenticate_ws(websocket: WebSocket, token: Optional[str] = None) -> bool:
    if auth_manager.setup_required():
        return True
    # Try token from query param or cookie
    auth_token = token or websocket.cookies.get("amm_session")
    if not auth_token:
        return False
    user = auth_manager.validate_jwt(auth_token)
    return user is not None


@router.get("", summary="Query centralized logs")
async def get_logs(
    request: Request,
    app: Optional[str] = Query(None, description="Filter logs by application name"),
    search: Optional[str] = Query(None, description="Case-insensitive text search"),
    level: Optional[str] = Query(None, description="Filter by level: error, warning, info, debug"),
    limit: int = Query(200, ge=1, le=2000, description="Max lines to return"),
) -> dict[str, Any]:
    """
    Returns recent in-memory ring buffer log entries across all applications or a specific one,
    scrubbed of secrets and credentials.
    """
    _ensure_authenticated(request)
    supervisor = ProcessSupervisor.get()

    entries = supervisor.list_processes()
    all_lines: list[dict[str, Any]] = []

    for entry_info in entries:
        app_name = entry_info["name"]
        if app and app != app_name:
            continue
        raw_lines = supervisor.get_logs(app_name)
        for line in raw_lines:
            all_lines.append({"app": app_name, "raw": line})

    # Filter by search string
    if search:
        s = search.lower()
        all_lines = [item for item in all_lines if s in item["raw"].lower()]

    # Filter by level
    if level:
        lvl = level.lower()
        if lvl == "error":
            all_lines = [
                item for item in all_lines
                if any(w in item["raw"].lower() for w in ("error", "fatal", "exception", "critical", "fail"))
            ]
        elif lvl == "warning":
            all_lines = [
                item for item in all_lines
                if any(w in item["raw"].lower() for w in ("warn", "warning", "error", "fatal", "exception"))
            ]

    # Limit
    sliced = all_lines[-limit:] if len(all_lines) > limit else all_lines

    # Redact secrets
    scrubbed = [
        {
            "app": item["app"],
            "line": redact_log_line(item["raw"]),
        }
        for item in sliced
    ]

    return {
        "total": len(scrubbed),
        "app": app,
        "logs": scrubbed,
    }


@router.get("/download", summary="Download logs as plain text file")
async def download_logs(
    request: Request,
    app: Optional[str] = Query(None, description="Filter logs by application name"),
) -> Response:
    """
    Exports recent application logs as an attachment with secrets scrubbed.
    """
    _ensure_authenticated(request)
    supervisor = ProcessSupervisor.get()
    entries = supervisor.list_processes()

    output_lines: list[str] = []
    for entry_info in entries:
        app_name = entry_info["name"]
        if app and app != app_name:
            continue
        raw_lines = supervisor.get_logs(app_name)
        for line in raw_lines:
            output_lines.append(f"[{app_name}] {redact_log_line(line)}")

    content = "\n".join(output_lines)
    filename = f"{app if app else 'aio-media-manager'}-logs.txt"

    return Response(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.websocket("/ws")
@router.websocket("/ws/{app_name}")
async def websocket_logs(
    websocket: WebSocket,
    app_name: Optional[str] = None,
    token: Optional[str] = None,
) -> None:
    """
    WebSocket endpoint streaming live logs from ProcessSupervisor in real-time.
    """
    if not _authenticate_ws(websocket, token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    supervisor = ProcessSupervisor.get()
    q = supervisor.subscribe_logs(app_name=app_name)

    try:
        while True:
            # Wait for next log event or client message
            event = await q.get()
            event_data = {
                "app": event["app"],
                "stream": event["stream"],
                "line": redact_log_line(event["line"]),
                "timestamp": event.get("timestamp"),
            }
            await websocket.send_json(event_data)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("WebSocket live logs error: %s", exc)
    finally:
        supervisor.unsubscribe_logs(q)
