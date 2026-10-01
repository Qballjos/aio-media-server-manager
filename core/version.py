"""Running appliance version (pyproject / image build args)."""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version as pkg_version


def app_version() -> str:
    env = (os.environ.get("AMM_VERSION") or "").strip()
    if env:
        return env
    try:
        return pkg_version("aio-media-manager")
    except PackageNotFoundError:
        return "0.1.0"


def git_sha() -> str:
    return (os.environ.get("AMM_GIT_SHA") or "").strip()
