"""Read-only action prerequisites; enforced before installation or stopping a running app."""
from pathlib import Path
import shutil
import tempfile
import time

import requests

from core.install_jobs import get_job
from core.settings import settings


class PreflightError(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__("; ".join(row["detail"] for row in report["checks"] if row["status"] == "blocked"))


def inspect_action(plugin, cfg=None, *, operation="install", network=False):
    cfg = cfg or settings
    checks = []
    def add(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})
    for label in ("config_dir", "install_dir", "cache_dir", "backup_dir", "download_dir", "media_dir"):
        title = {"config_dir": "Configuration storage", "install_dir": "Application storage", "cache_dir": "Temporary storage", "backup_dir": "Backup storage", "download_dir": "Downloads storage", "media_dir": "Media storage"}[label]
        path = Path(getattr(cfg, label))
        while not path.exists() and path != path.parent:
            path = path.parent
        try:
            with tempfile.TemporaryFile(dir=path):
                pass
            free = shutil.disk_usage(path).free
            minimum = cfg.preflight_min_free_mb * 1024 * 1024
            add(label, "pass" if free >= minimum else "blocked",
                f"{title}: {free // (1024 * 1024)} MiB free; at least {cfg.preflight_min_free_mb} MiB required")
        except OSError:
            add(label, "blocked", f"{title}: the storage location is unavailable or not writable")
    from core.maintenance import action_conflict
    blocked = action_conflict(operation)
    job = get_job(plugin.name) or {}
    restart = job.get("status") == "restart_required"
    add("maintenance", "blocked" if blocked or restart else "pass",
        "Finish the backup/update or pending restart first" if blocked or restart else "No conflicting maintenance")
    if getattr(plugin.manifest, "github_repo", "") and not any(c["status"] == "blocked" for c in checks):
        if network:
            try:
                from core.crypto import secret_store
                token = cfg.github_token or secret_store.get_secret("github_token")
                headers = {"Authorization": f"Bearer {token}"} if token else {}
                response = requests.get("https://api.github.com/rate_limit", headers=headers, timeout=(3, 5))
                response.raise_for_status()
                quota = response.json()["resources"]["core"]
                exhausted = int(quota["remaining"]) == 0 and int(quota["reset"]) > time.time()
                add("github", "blocked" if exhausted else "pass", "GitHub API quota exhausted; wait or configure a GitHub token" if exhausted else "GitHub is reachable and API quota is available")
            except (requests.RequestException, ValueError, KeyError, TypeError):
                add("github", "warning", "Could not verify GitHub connectivity/quota; the download may fail")
        else:
            add("github", "warning", "GitHub connectivity/quota will be checked when downloading")
    return {"ok": not any(row["status"] == "blocked" for row in checks), "operation": operation, "checks": checks}


def require_action(plugin, cfg=None, *, operation="install"):
    report = inspect_action(plugin, cfg, operation=operation, network=True)
    from core.maintenance import action_conflict
    if action_conflict(operation) and report["ok"]:
        report["checks"].append({"name": "maintenance", "status": "blocked", "detail": "Maintenance started during the check; wait and try again"})
        report["ok"] = False
    if not report["ok"]:
        raise PreflightError(report)
    return report
