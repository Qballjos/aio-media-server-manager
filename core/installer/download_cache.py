"""Short-lived installer packages, separate from media downloads and runtime caches."""

from contextlib import contextmanager
import logging
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

logger = logging.getLogger(__name__)


@contextmanager
def temporary_package(cache_dir: Path, filename: str):
    """Give each install its own package path and clean it on every exit."""
    if not filename or Path(filename).name != filename or filename in {".", ".."}:
        raise ValueError("Invalid installation package filename")
    downloads = Path(cache_dir) / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="amm-package-", dir=downloads) as directory:
        yield Path(directory) / filename


def cleanup_download_cache(cache_dir: Path) -> None:
    """Run before installers start; remove legacy packages and interrupted workspaces."""
    downloads = Path(cache_dir) / "downloads"
    # Never follow a redirected cache into an unrelated folder.
    if downloads.is_symlink() or not downloads.is_dir():
        return
    try:
        entries = list(downloads.iterdir())
    except OSError:
        logger.warning("Could not inspect installation download cache")
        return
    for path in entries:
        try:
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.name.startswith("amm-package-") and path.is_dir():
                shutil.rmtree(path)
        except OSError:
            logger.warning("Could not remove cached installation package %s", path.name)
