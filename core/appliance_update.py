"""Notify when a newer GHCR appliance image exists. The manager cannot replace itself."""

from __future__ import annotations

from typing import Any

from core.installer.github import GitHubReleaseClient
from core.version import app_version, git_sha

APPLIANCE_NAME = "aio-media-server-manager"
APPLIANCE_REPO = "Qballjos/aio-media-server-manager"
APPLIANCE_IMAGE = "ghcr.io/qballjos/aio-media-server-manager:latest"
APPLIANCE_HINT = (
    f"On the host: docker pull {APPLIANCE_IMAGE} and recreate the container "
    "(compose up -d). The manager cannot replace its own image."
)


def running_appliance_identity() -> dict[str, Any]:
    sha = git_sha()
    version = app_version()
    label = f"{version} ({sha[:7]})" if sha else version
    return {
        "name": APPLIANCE_NAME,
        "display_name": "AIO Media Server Manager",
        "kind": "appliance",
        "installed_version": label,
        "running_sha": sha,
        "latest_version": None,
        "latest_sha": None,
        "update_available": False,
        "apply_hint": APPLIANCE_HINT,
    }


def _same_commit(left: str, right: str) -> bool:
    a = (left or "").lower()
    b = (right or "").lower()
    if len(a) < 7 or len(b) < 7:
        return False
    n = min(len(a), len(b), 40)
    return a[:n] == b[:n]


def check_appliance_image(github: GitHubReleaseClient | None = None) -> dict[str, Any]:
    payload = running_appliance_identity()
    running = payload.get("running_sha") or ""
    if not running:
        payload["detail"] = (
            "This build has no git SHA. Published GHCR images include one so "
            "Settings can notify when :latest moves."
        )
        return payload
    client = github or GitHubReleaseClient()
    try:
        commit = client.get_commit(APPLIANCE_REPO, "main")
    except Exception as exc:
        payload["detail"] = str(exc)[:240]
        return payload
    latest_sha = str(commit.get("sha") or "").strip()
    payload["latest_sha"] = latest_sha
    payload["latest_version"] = latest_sha[:7] if latest_sha else None
    if not latest_sha or _same_commit(running, latest_sha):
        payload["update_available"] = False
        return payload
    try:
        compared = client.compare_commits(APPLIANCE_REPO, running, "main")
        status = str(compared.get("status") or "")
        # head is main: ahead/diverged means published :latest has commits we do not.
        payload["update_available"] = status in {"ahead", "diverged"}
    except Exception:
        payload["update_available"] = True
    return payload
