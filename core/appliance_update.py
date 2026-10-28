"""Notify when a newer GHCR appliance image exists. The manager cannot replace itself."""

from __future__ import annotations

from typing import Any

from core.installer.github import GitHubReleaseClient
from core.version import app_version, git_sha

APPLIANCE_NAME = "aio-media-server-manager"
APPLIANCE_REPO = "Qballjos/aio-media-server-manager"
APPLIANCE_IMAGE_NAME = "ghcr.io/qballjos/aio-media-server-manager"
APPLIANCE_IMAGE = f"{APPLIANCE_IMAGE_NAME}:latest"
APPLIANCE_NIGHTLY_IMAGE = f"{APPLIANCE_IMAGE_NAME}:nightly"
# Compare against the last successful publish of this image's own tag.
# Docs-only commits advance a branch without rebuilding GHCR.
# :nightly follows nightly.yml on beta. :latest follows docker.yml on main.
APPLIANCE_DOCKER_WORKFLOW = "docker.yml"
APPLIANCE_NIGHTLY_WORKFLOW = "nightly.yml"


def appliance_channel(version: str | None = None) -> str:
    """'nightly' for a -nightly image, otherwise the main :latest line."""
    ver = app_version() if version is None else str(version)
    if ver.strip().lower().endswith("-nightly"):
        return "nightly"
    return "main"


def appliance_track(version: str | None = None) -> dict[str, str]:
    if appliance_channel(version) == "nightly":
        return {
            "channel": "nightly",
            "workflow": APPLIANCE_NIGHTLY_WORKFLOW,
            "branch": "beta",
            "image": APPLIANCE_NIGHTLY_IMAGE,
        }
    return {
        "channel": "main",
        "workflow": APPLIANCE_DOCKER_WORKFLOW,
        "branch": "main",
        "image": APPLIANCE_IMAGE,
    }


def _apply_hint(image: str) -> str:
    return (
        f"On the host: docker pull {image} and recreate the container "
        "(compose up -d). The manager cannot replace its own image."
    )


def running_appliance_identity() -> dict[str, Any]:
    sha = git_sha()
    version = app_version()
    track = appliance_track(version)
    label = f"{version} ({sha[:7]})" if sha else version
    return {
        "name": APPLIANCE_NAME,
        "display_name": "AIO Media Server Manager",
        "kind": "appliance",
        "channel": track["channel"],
        "installed_version": label,
        "running_sha": sha,
        "latest_version": None,
        "latest_sha": None,
        "update_available": False,
        "apply_hint": _apply_hint(track["image"]),
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
    track = appliance_track()
    running = payload.get("running_sha") or ""
    if not running:
        tag = track["image"].rsplit(":", 1)[-1]
        payload["detail"] = (
            "This build has no git SHA. Published GHCR images include one so "
            f"Settings can notify when :{tag} moves."
        )
        return payload
    client = github or GitHubReleaseClient()
    try:
        published_sha = client.latest_workflow_run_sha(
            APPLIANCE_REPO,
            track["workflow"],
            branch=track["branch"],
            status="success",
        )
    except Exception as exc:
        payload["detail"] = str(exc)[:240]
        return payload
    if not published_sha:
        payload["detail"] = (
            f"No successful Docker workflow run found on {track['branch']} yet."
        )
        return payload
    payload["latest_sha"] = published_sha
    payload["latest_version"] = published_sha[:7]
    if _same_commit(running, published_sha):
        payload["update_available"] = False
        return payload
    try:
        compared = client.compare_commits(APPLIANCE_REPO, running, published_sha)
        status = str(compared.get("status") or "")
        # head is this channel's published image: ahead/diverged means that tag is newer.
        payload["update_available"] = status in {"ahead", "diverged"}
    except Exception:
        payload["update_available"] = not _same_commit(running, published_sha)
    return payload
