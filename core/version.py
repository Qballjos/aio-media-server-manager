"""Running appliance identity, fixed at image build time when packaged."""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version as pkg_version

try:
    from core._build import VERSION as _IMAGE_VERSION, GIT_SHA as _IMAGE_GIT_SHA
except ModuleNotFoundError as exc:
    if exc.name != "core._build":
        raise
    _IMAGE_VERSION = _IMAGE_GIT_SHA = None


def app_version() -> str:
    # Recreated containers may retain an older image's AMM_* environment values.
    if _IMAGE_VERSION is not None:
        return _IMAGE_VERSION
    env = (os.environ.get("AMM_VERSION") or "").strip()
    if env:
        return env
    try:
        return pkg_version("aio-media-manager")
    except PackageNotFoundError:
        return "0.4.1"


def git_sha() -> str:
    if _IMAGE_GIT_SHA is not None:
        return _IMAGE_GIT_SHA
    return (os.environ.get("AMM_GIT_SHA") or "").strip()
