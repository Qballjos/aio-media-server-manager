"""In-memory error ring and time-limited debug share links."""

from __future__ import annotations

import html
import json
import logging
import secrets
import traceback
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.log_redactor import redact_log_line
from core.settings import settings

logger = logging.getLogger(__name__)

SHARE_TTL_HOURS = 24
_ERROR_RING_SIZE = 200
_SHARE_NAME = "debug_share.json"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DiagnosticsLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR:
            return
        try:
            message = record.getMessage()
            exc = None
            if record.exc_info and record.exc_info[1] is not None:
                exc = "".join(traceback.format_exception(*record.exc_info))
            diagnostics.record_error(
                source=record.name,
                message=message,
                traceback_text=exc,
                level=record.levelname,
            )
        except Exception:
            pass


class DiagnosticsStore:
    def __init__(self) -> None:
        self._errors: deque[dict[str, Any]] = deque(maxlen=_ERROR_RING_SIZE)
        self._handler_installed = False

    def _share_path(self) -> Path:
        return Path(settings.config_dir) / _SHARE_NAME

    def install_logging_hook(self) -> None:
        if self._handler_installed:
            return
        root = logging.getLogger()
        if any(isinstance(handler, DiagnosticsLogHandler) for handler in root.handlers):
            self._handler_installed = True
            return
        handler = DiagnosticsLogHandler()
        handler.setLevel(logging.ERROR)
        root.addHandler(handler)
        self._handler_installed = True

    def record_error(
        self,
        source: str,
        message: str,
        traceback_text: str | None = None,
        level: str = "ERROR",
    ) -> None:
        self._errors.append(
            {
                "timestamp": _utcnow().isoformat(),
                "level": level,
                "source": source,
                "message": redact_log_line(message or ""),
                "traceback": redact_log_line(traceback_text) if traceback_text else None,
            }
        )

    def record_exception(self, exc: BaseException, source: str = "exception") -> None:
        self.record_error(
            source=source,
            message=f"{type(exc).__name__}: {exc}",
            traceback_text="".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
        )

    def recent_errors(self, limit: int = 50) -> list[dict[str, Any]]:
        items = list(self._errors)
        return items[-limit:]

    def _read_share(self) -> dict[str, Any] | None:
        path = self._share_path()
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        expires = payload.get("expires_at")
        if not expires:
            return None
        try:
            expiry = datetime.fromisoformat(expires)
        except ValueError:
            return None
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= _utcnow():
            path.unlink(missing_ok=True)
            return None
        return payload

    def share_status(self) -> dict[str, Any]:
        payload = self._read_share()
        if not payload:
            return {"active": False, "token": None, "expires_at": None}
        return {
            "active": True,
            "token": payload.get("token"),
            "expires_at": payload.get("expires_at"),
            "created_at": payload.get("created_at"),
        }

    def create_share(self) -> dict[str, Any]:
        token = secrets.token_urlsafe(24)
        now = _utcnow()
        payload = {
            "token": token,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=SHARE_TTL_HOURS)).isoformat(),
        }
        path = self._share_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        logger.warning("Created debug share link (expires %s).", payload["expires_at"])
        return payload

    def revoke_share(self) -> None:
        path = self._share_path()
        if path.is_file():
            path.unlink()

    def validate_token(self, token: str) -> bool:
        payload = self._read_share()
        return bool(payload and secrets.compare_digest(str(payload.get("token") or ""), token))

    def build_report(self) -> dict[str, Any]:
        from applications.catalog import ApplicationCatalog
        from core.installer.arch import detect_system_arch
        from core.library_layout import LibraryLayout
        from core.supervisor import ProcessSupervisor

        catalog = ApplicationCatalog(app_settings=settings)
        entries = catalog.entries()
        supervisor = ProcessSupervisor.get()
        processes = supervisor.list_processes()
        logs: dict[str, list[str]] = {}
        for proc in processes:
            name = proc["name"]
            raw = supervisor.get_logs(name)[-80:]
            logs[name] = [redact_log_line(line) for line in raw]

        return {
            "generated_at": _utcnow().isoformat(),
            "purpose": "debug-share",
            "version": "0.1.0",
            "architecture": detect_system_arch().value,
            "catalog": {
                "counts": catalog.counts(entries),
                "applications": [
                    {
                        "name": row.get("name"),
                        "installed": row.get("installed"),
                        "version": row.get("installed_version"),
                        "tier": row.get("tier"),
                    }
                    for row in entries
                ],
            },
            "processes": processes,
            "process_logs": logs,
            "storage": settings.as_serialisable_dict(),
            "library": LibraryLayout.from_settings(settings).as_dict(),
            "errors": self.recent_errors(100),
        }

    def render_html(self, report: dict[str, Any]) -> str:
        counts = report.get("catalog", {}).get("counts", {})
        errors = report.get("errors") or []
        apps = report.get("catalog", {}).get("applications") or []
        processes = report.get("processes") or []

        def _pre(text: str) -> str:
            return f"<pre>{html.escape(text)}</pre>"

        error_blocks = []
        for item in errors[-40:]:
            body = f"{item.get('timestamp')}  {item.get('level')}  {item.get('source')}\n{item.get('message')}"
            if item.get("traceback"):
                body += "\n" + item["traceback"]
            error_blocks.append(_pre(body))

        app_rows = "".join(
            f"<tr><td>{html.escape(str(app.get('name')))}</td>"
            f"<td>{'yes' if app.get('installed') else 'no'}</td>"
            f"<td>{html.escape(str(app.get('version') or ''))}</td></tr>"
            for app in apps
        )
        proc_rows = "".join(
            f"<tr><td>{html.escape(str(proc.get('name')))}</td>"
            f"<td>{html.escape(str(proc.get('state')))}</td>"
            f"<td>{html.escape(str(proc.get('pid') or ''))}</td></tr>"
            for proc in processes
        )
        log_blocks = []
        for name, lines in (report.get("process_logs") or {}).items():
            if not lines:
                continue
            log_blocks.append(f"<h3>{html.escape(name)}</h3>" + _pre("\n".join(lines[-40:])))

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>AIO debug report</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; background: #0b0f17; color: #e5e7eb; margin: 2rem; }}
    a {{ color: #67e8f9; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{ border-bottom: 1px solid #1f2937; text-align: left; padding: 0.4rem 0.6rem; font-family: ui-monospace, monospace; font-size: 13px; }}
    pre {{ background: #111827; padding: 1rem; overflow: auto; white-space: pre-wrap; font-size: 12px; }}
    .muted {{ color: #94a3b8; }}
  </style>
</head>
<body>
  <h1>AIO Media Manager debug report</h1>
  <p class="muted">Generated {html.escape(str(report.get("generated_at")))} · testing only · secrets redacted</p>
  <p>Catalog: {counts.get("installed", 0)} installed, {counts.get("available", 0)} available, {counts.get("catalog", 0)} in catalog · arch {html.escape(str(report.get("architecture")))}</p>
  <p><a href="?format=json">JSON</a></p>
  <h2>Errors</h2>
  {''.join(error_blocks) or '<p class="muted">No captured errors.</p>'}
  <h2>Applications</h2>
  <table><thead><tr><th>name</th><th>installed</th><th>version</th></tr></thead><tbody>{app_rows}</tbody></table>
  <h2>Processes</h2>
  <table><thead><tr><th>name</th><th>state</th><th>pid</th></tr></thead><tbody>{proc_rows}</tbody></table>
  <h2>Recent process logs</h2>
  {''.join(log_blocks) or '<p class="muted">No process logs.</p>'}
  <h2>Storage</h2>
  {_pre(json.dumps(report.get("storage") or {{}}, indent=2))}
</body>
</html>
"""


diagnostics = DiagnosticsStore()
