"""Private, atomic writes for configuration files containing child-app credentials."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile


def write_private_text(path: Path, text: str) -> None:
    """Publish a complete 0600 file, preserving an existing child-app owner."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        previous = path.stat()
    except FileNotFoundError:
        previous = None
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), 0o600)
            stream.write(text)
            stream.flush()
            if previous is not None:
                current = os.fstat(stream.fileno())
                if (current.st_uid, current.st_gid) != (
                    previous.st_uid,
                    previous.st_gid,
                ):
                    os.fchown(stream.fileno(), previous.st_uid, previous.st_gid)
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
