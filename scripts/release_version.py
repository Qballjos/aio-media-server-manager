"""Choose a stable release version from source metadata and existing Git tags."""
from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path


def _stable_version(value: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", value)
    return tuple(map(int, match.groups())) if match else None


def next_release_version(base: str, tags: list[str], head_tags: list[str] = ()) -> str:
    base_version = _stable_version(base)
    if base_version is None:
        raise ValueError(f"Expected a stable source version, got {base!r}")
    existing = [version for tag in head_tags if (version := _stable_version(tag)) and tag.startswith("v")]
    if existing:
        return ".".join(map(str, max(existing)))
    released = [version for tag in tags if tag.startswith("v") and (version := _stable_version(tag))]
    if released:
        latest = max(released)
        base_version = max(base_version, (latest[0], latest[1], latest[2] + 1))
    return ".".join(map(str, base_version))


if __name__ == "__main__":
    def git_tags(*args: str) -> list[str]:
        return subprocess.check_output(["git", "tag", *args], text=True).splitlines()

    base = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    print(next_release_version(base, git_tags(), git_tags("--points-at", "HEAD")))
