"""Shelfmark mirror URL sanitizer — keeps Invalid IPv6 URL from crash-looping boot."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from applications.shelfmark_mirrors import (
    coerce_url_list,
    ensure_shelfmark_venv,
    mirror_url_is_safe,
    prepare_shelfmark_runtime,
    sanitize_mirror_list,
    sanitize_shelfmark_settings,
    shelfmark_python,
    write_shelfmark_preload,
    write_shelfmark_runner,
)


def test_mirror_url_is_safe_accepts_normal_https():
    assert mirror_url_is_safe("https://annas-archive.gl")
    assert mirror_url_is_safe("annas-archive.li")
    assert mirror_url_is_safe("auto", allow_special=("auto",))


def test_mirror_url_is_safe_rejects_bracket_pastes():
    assert not mirror_url_is_safe("https://[https://annas-archive.gl]")
    assert not mirror_url_is_safe("https://annas-archive.gl[1]")
    assert not mirror_url_is_safe("http://[::1")


def test_coerce_url_list_handles_json_array_string():
    assert coerce_url_list('["https://a.example","https://b.example"]') == [
        "https://a.example",
        "https://b.example",
    ]
    assert coerce_url_list("https://a.example,https://b.example") == [
        "https://a.example",
        "https://b.example",
    ]


def test_sanitize_mirror_list_drops_bad_keeps_good():
    cleaned = sanitize_mirror_list(
        [
            "https://annas-archive.gl",
            "https://[https://annas-archive.li]",
            "https://annas-archive.org",
        ]
    )
    assert cleaned == ["https://annas-archive.gl", "https://annas-archive.org"]


def test_sanitize_shelfmark_settings_rewrites_bad_aa_mirrors(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "AA_MIRROR_URLS": [
                    "https://annas-archive.gl",
                    "https://[bad-mirror.example]",
                ],
                "AA_BASE_URL": "https://host[broken",
                "ZLIB_PRIMARY_URL": "https://zlib.example[x",
            }
        ),
        encoding="utf-8",
    )

    assert sanitize_shelfmark_settings(tmp_path) is True

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["AA_MIRROR_URLS"] == ["https://annas-archive.gl"]
    assert data["AA_BASE_URL"] == "auto"
    assert data["ZLIB_PRIMARY_URL"] == ""


def test_sanitize_shelfmark_settings_noop_when_clean(tmp_path: Path):
    settings = tmp_path / "settings.json"
    payload = {"AA_MIRROR_URLS": ["https://annas-archive.gl"], "AA_BASE_URL": "auto"}
    settings.write_text(json.dumps(payload), encoding="utf-8")
    assert sanitize_shelfmark_settings(tmp_path) is False


def test_prepare_shelfmark_runtime_writes_hardened_launcher(tmp_path: Path):
    install = tmp_path / "apps" / "shelfmark"
    config = tmp_path / "config" / "shelfmark"
    install.mkdir(parents=True)
    (install / "shelfmark").mkdir()
    (install / "venv" / "bin").mkdir(parents=True)
    (install / "venv" / "bin" / "gunicorn").write_text("#!/bin/sh\n", encoding="utf-8")
    config.mkdir(parents=True)
    (config / "settings.json").write_text(
        json.dumps({"AA_MIRROR_URLS": ["https://[https://annas-archive.gl]"]}),
        encoding="utf-8",
    )

    prepare_shelfmark_runtime(config, install, port=8084)

    data = json.loads((config / "settings.json").read_text(encoding="utf-8"))
    assert data["AA_MIRROR_URLS"] == []
    preload = install / "aio_shelfmark_app.py"
    assert preload.is_file()
    assert "normalize_http_url" in preload.read_text(encoding="utf-8")
    runner = (install / "run-shelfmark").read_text(encoding="utf-8")
    assert "aio_shelfmark_app:app" in runner


def test_write_helpers_are_idempotent(tmp_path: Path):
    install = tmp_path / "shelfmark"
    install.mkdir()
    (install / "venv" / "bin").mkdir(parents=True)
    (install / "venv" / "bin" / "gunicorn").write_text("#!/bin/sh\n", encoding="utf-8")
    first = write_shelfmark_preload(install).read_text(encoding="utf-8")
    second = write_shelfmark_preload(install).read_text(encoding="utf-8")
    assert first == second
    write_shelfmark_runner(install, port=8084)
    assert "aio_shelfmark_app:app" in (install / "run-shelfmark").read_text(encoding="utf-8")


class _Proc:
    def __init__(self, stdout: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def _install_with_bin(tmp_path: Path) -> Path:
    install = tmp_path / "shelfmark"
    (install / "venv" / "bin").mkdir(parents=True)
    return install


def test_shelfmark_python_is_not_the_child_runtime(tmp_path: Path, monkeypatch):
    child = tmp_path / "python3.13"
    child.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("AMM_CHILD_PYTHON", str(child))
    monkeypatch.delenv("AMM_SHELFMARK_PYTHON", raising=False)
    assert shelfmark_python() != str(child)


def test_ensure_rebuilds_venv_when_gunicorn_is_missing(tmp_path: Path, monkeypatch):
    install = _install_with_bin(tmp_path)
    interpreter = tmp_path / "python3.14"
    interpreter.write_text("#!/bin/sh\n", encoding="utf-8")
    created: list[str] = []

    def fake_create(root: Path, python: str | None = None) -> Path:
        created.append(python or "")
        (root / "venv" / "bin").mkdir(parents=True, exist_ok=True)
        return root / "venv"

    def fake_run(cmd, **kwargs):
        argv = [str(part) for part in cmd]
        if "version_info" in " ".join(argv):
            return _Proc("3 14\n")
        if "install" in argv:
            (install / "venv" / "bin" / "gunicorn").write_text("#!/bin/sh\n", encoding="utf-8")
        return _Proc()

    monkeypatch.setattr("applications.shelfmark_mirrors.shelfmark_python", lambda: str(interpreter))
    monkeypatch.setattr("applications.shelfmark_mirrors.create_venv", fake_create)
    monkeypatch.setattr("applications.shelfmark_mirrors.subprocess.run", fake_run)

    ensure_shelfmark_venv(install)

    assert created == [str(interpreter)]
    assert (install / "venv" / "bin" / "gunicorn").is_file()


def test_ensure_rebuilds_a_313_venv_that_already_has_gunicorn(tmp_path: Path, monkeypatch):
    install = _install_with_bin(tmp_path)
    bin_dir = install / "venv" / "bin"
    (bin_dir / "gunicorn").write_text("#!/bin/sh\n", encoding="utf-8")
    (bin_dir / "python").write_text("#!/bin/sh\n", encoding="utf-8")
    interpreter = tmp_path / "python3.14"
    interpreter.write_text("#!/bin/sh\n", encoding="utf-8")
    created: list[str] = []

    def fake_create(root: Path, python: str | None = None) -> Path:
        created.append(python or "")
        (root / "venv" / "bin").mkdir(parents=True, exist_ok=True)
        (root / "venv" / "bin" / "gunicorn").write_text("#!/bin/sh\n", encoding="utf-8")
        (root / "venv" / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")
        return root / "venv"

    def fake_run(cmd, **kwargs):
        argv = [str(part) for part in cmd]
        if "version_info" in " ".join(argv):
            if argv[0].endswith("/python") and not created:
                return _Proc("3 13\n")
            return _Proc("3 14\n")
        return _Proc()

    monkeypatch.setattr("applications.shelfmark_mirrors.shelfmark_python", lambda: str(interpreter))
    monkeypatch.setattr("applications.shelfmark_mirrors.create_venv", fake_create)
    monkeypatch.setattr("applications.shelfmark_mirrors.subprocess.run", fake_run)

    ensure_shelfmark_venv(install)

    assert created == [str(interpreter)]


def test_ensure_keeps_a_314_venv_with_gunicorn(tmp_path: Path, monkeypatch):
    install = _install_with_bin(tmp_path)
    bin_dir = install / "venv" / "bin"
    (bin_dir / "gunicorn").write_text("#!/bin/sh\n", encoding="utf-8")
    (bin_dir / "python").write_text("#!/bin/sh\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        return _Proc("3 14\n")

    def fail_create(*args, **kwargs):
        raise AssertionError("venv should be reused")

    monkeypatch.setattr("applications.shelfmark_mirrors.subprocess.run", fake_run)
    monkeypatch.setattr("applications.shelfmark_mirrors.create_venv", fail_create)

    assert ensure_shelfmark_venv(install) == install / "venv"


def test_ensure_refuses_python_older_than_314(tmp_path: Path, monkeypatch):
    install = _install_with_bin(tmp_path)
    interpreter = tmp_path / "python3.13"
    interpreter.write_text("#!/bin/sh\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        return _Proc("3 13\n")

    monkeypatch.setattr("applications.shelfmark_mirrors.shelfmark_python", lambda: str(interpreter))
    monkeypatch.setattr("applications.shelfmark_mirrors.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="Python >= 3.14"):
        ensure_shelfmark_venv(install)
