"""Exercise the image's actual build stamp and runtime import in isolation."""

import os
from pathlib import Path
import subprocess
import sys


def test_packaged_identity_survives_environment_overrides(tmp_path):
    root = Path(__file__).resolve().parents[1]
    core = tmp_path / "core"
    core.mkdir()
    (core / "__init__.py").touch()
    (core / "version.py").write_bytes((root / "core/version.py").read_bytes())
    recipe = (root / "Dockerfile").read_text().split("RUN python - <<'PY'\n", 1)[1]
    recipe = recipe.split("\nPY\n", 1)[0]
    build_env = {**os.environ, "AMM_VERSION": "0.4.1-nightly", "AMM_GIT_SHA": "b" * 40}
    subprocess.run(
        [sys.executable, "-c", recipe], cwd=tmp_path, env=build_env, check=True
    )
    runtime_env = {**os.environ, "AMM_VERSION": "0.3.0", "AMM_GIT_SHA": "a" * 40}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from core.version import app_version, git_sha; print(app_version(), git_sha())",
        ],
        cwd=tmp_path,
        env=runtime_env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "0.4.1-nightly " + "b" * 40
