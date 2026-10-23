"""Seerr reports safe progress while build commands run and preserves failures."""

import json
import os
import shutil
import subprocess
import sys

import pytest

from applications.seerr import SeerrApp, _install_progress, _limit_build_memory


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            "Progress: resolved 123, reused 4, downloaded 52, added 9, done",
            "Installing dependencies: 52 downloaded, 4 cached, 9 installed (123 resolved)",
        ),
        ("Generating static pages (3/42)", "Generating Seerr pages: 3/42"),
        ("Generating static pages using 1 worker (3/42)", "Generating Seerr pages: 3/42"),
        ("Creating an optimized production build ...", "Building Seerr's web interface…"),
        ("Linting and checking validity of types", "Checking Seerr's code and types…"),
        ("Running TypeScript ...", "Checking Seerr's code and types…"),
        ("tsc --project server/tsconfig.build.json", "Building Seerr's server…"),
        ("Fetch failed https://user:secret@example.org/package?token=private", None),
    ],
)
def test_install_progress_only_publishes_known_counts_and_phases(line, expected):
    assert _install_progress(line) == expected


@pytest.fixture
def app(tmp_path):
    plugin = SeerrApp(base_config_dir=tmp_path / "config", base_install_dir=tmp_path / "apps")
    plugin.install_dir.mkdir(parents=True)
    return plugin


@pytest.mark.parametrize("runner_name", ["seerr", "run-seerr"])
def test_seerr_is_installed_only_after_the_build_writes_a_runner(app, runner_name):
    assert app.is_installed() is False
    app.metadata_path().write_text('{"version": "v1"}')
    assert app.is_installed() is False
    runner = app.install_dir / runner_name
    runner.mkdir()
    assert app.is_installed() is False
    runner.rmdir()
    runner.write_text("#!/bin/sh\nexec node dist/index.js\n")
    assert app.is_installed() is True
    app.metadata_path().unlink()
    assert app.is_installed() is False


def test_progress_is_published_before_command_finishes(app, monkeypatch):
    messages = []

    def publish(name, status, message):
        assert (name, status) == ("seerr", "installing")
        messages.append(message)
        (app.install_dir / "progress-seen").touch()

    monkeypatch.setattr("applications.seerr.set_job", publish)
    script = """
import pathlib, time
print('Progress: resolved 123, reused 4, downloaded 52, added 9 https://secret.invalid', flush=True)
deadline = time.monotonic() + 5
while not pathlib.Path('progress-seen').exists() and time.monotonic() < deadline:
    time.sleep(0.01)
if not pathlib.Path('progress-seen').exists():
    raise SystemExit(4)
print('Generating static pages (3/42)', flush=True)
print('https://user:secret@example.org/package?token=private', flush=True)
"""
    app._run_install_step([sys.executable, "-c", script], dict(os.environ))
    assert messages == [
        "Installing dependencies: 52 downloaded, 4 cached, 9 installed (123 resolved)",
        "Generating Seerr pages: 3/42",
    ]


def test_failed_build_keeps_bounded_combined_output(app):
    script = """
import sys
for index in range(60):
    print(str(index) + 'x' * 3000, flush=True)
print('Final compiler error', file=sys.stderr, flush=True)
raise SystemExit(7)
"""
    command = [sys.executable, "-c", script]
    with pytest.raises(subprocess.CalledProcessError) as caught:
        app._run_install_step(command, dict(os.environ))
    assert caught.value.returncode == 7
    assert caught.value.cmd == command
    assert caught.value.output.endswith("Final compiler error\n")
    assert len(caught.value.output) <= 30 * 2048


@pytest.mark.parametrize("existing_limit", [None, 256 * 1024 * 1024, 0, -1])
def test_build_memory_target_preserves_existing_positive_limit_and_config(tmp_path, existing_limit):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to execute Seerr's generated build configuration")
    experimental = {"scrollRestoration": True}
    if existing_limit is not None:
        experimental["turbopackMemoryLimit"] = existing_limit
    config = tmp_path / "next.config.ts"
    config.write_text(
        "const nextConfig = " + json.dumps({"experimental": experimental})
        + ";\nexport default nextConfig;\n"
    )
    _limit_build_memory(config)
    patched = config.read_text()
    _limit_build_memory(config)
    assert config.read_text() == patched
    result = subprocess.run(
        [node, "--input-type=module", "-e", patched + "\nconsole.log(JSON.stringify(nextConfig));"],
        check=True, capture_output=True, text=True,
    )
    actual = json.loads(result.stdout)["experimental"]
    assert actual["scrollRestoration"] is True
    assert actual["turbopackMemoryLimit"] == (
        existing_limit if existing_limit and existing_limit > 0 else 512 * 1024 * 1024
    )


def test_build_memory_target_rejects_unrecognized_upstream_config(tmp_path):
    config = tmp_path / "next.config.ts"
    source = "export default {};\n"
    config.write_text(source)
    with pytest.raises(RuntimeError, match="unrecognized next.config.ts"):
        _limit_build_memory(config)
    assert config.read_text() == source


def test_build_config_skips_type_check_and_lint_for_released_tags(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to execute Seerr's generated build configuration")
    config = tmp_path / "next.config.ts"
    config.write_text(
        "const nextConfig = " + json.dumps({"experimental": {}, "typescript": {"tsconfigPath": "tsconfig.json"}})
        + ";\nexport default nextConfig;\n"
    )
    _limit_build_memory(config)
    result = subprocess.run(
        [node, "--input-type=module", "-e", config.read_text() + "\nconsole.log(JSON.stringify(nextConfig));"],
        check=True, capture_output=True, text=True,
    )
    actual = json.loads(result.stdout)
    # Next.js would otherwise run tsc and ESLint over all of Seerr; the released tag already passed both.
    assert actual["typescript"] == {"tsconfigPath": "tsconfig.json", "ignoreBuildErrors": True}
    assert actual["eslint"]["ignoreDuringBuilds"] is True
