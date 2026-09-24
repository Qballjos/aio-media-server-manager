"""Flags that pause scheduled catalog updates."""

from __future__ import annotations

from contextlib import contextmanager

_install_depth = 0
_update_depth = 0


def begin_install() -> None:
    global _install_depth
    _install_depth += 1


def end_install() -> None:
    global _install_depth
    _install_depth = max(0, _install_depth - 1)


def begin_update() -> None:
    global _update_depth
    _update_depth += 1


def end_update() -> None:
    global _update_depth
    _update_depth = max(0, _update_depth - 1)


@contextmanager
def install_in_progress():
    begin_install()
    try:
        yield
    finally:
        end_install()


@contextmanager
def update_in_progress():
    begin_update()
    try:
        yield
    finally:
        end_update()


def pause_reason() -> str | None:
    try:
        from core.wizard import wizard_engine

        if not wizard_engine.is_completed():
            return "wizard"
    except Exception:
        pass
    if _install_depth > 0:
        return "install"
    if _update_depth > 0:
        return "update"
    return None
