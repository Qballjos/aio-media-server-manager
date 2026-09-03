"""
applications/base.py — BaseApplication Plugin Contract

Every application plugin (e.g., Sonarr, Radarr, qBittorrent) must subclass
BaseApplication and implement the required abstract methods.

Example
-------
    from applications.base import BaseApplication
    from pathlib import Path

    class Sonarr(BaseApplication):
        name = "sonarr"
        default_port = 8989

        def install(self) -> None:
            # Download binary from GitHub releases, extract, chown
            ...

        def start_command(self) -> list[str]:
            return [
                str(self.install_dir / "Sonarr"),
                "--no-browser",
                f"--data={self.config_dir}",
            ]

        def health_check_url(self) -> str:
            return f"http://localhost:{self.port}/ping"
"""

from __future__ import annotations

import abc
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.supervisor import ProcessSupervisor

logger = logging.getLogger(__name__)


class BaseApplication(abc.ABC):
    """
    Abstract base class for all application plugins.

    Subclasses MUST implement:
      - install()
      - start_command()
      - health_check_url()

    Subclasses MAY override:
      - configure_integration(supervisor)
      - name               (class attribute)
      - default_port       (class attribute)
    """

    # ------------------------------------------------------------------
    # Class-level identity — subclasses should override these
    # ------------------------------------------------------------------

    #: Unique identifier for this application (used as process name, dir name, etc.)
    name: str = ""

    #: Default TCP port the application listens on
    default_port: int = 0

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    def __init__(
        self,
        *,
        base_config_dir: Path,
        base_install_dir: Path,
        port: int | None = None,
        puid: int = 1000,
        pgid: int = 1000,
    ) -> None:
        if not self.name:
            raise ValueError(
                f"{type(self).__name__} must define a non-empty 'name' class attribute."
            )
        self.config_dir: Path = base_config_dir / self.name
        self.install_dir: Path = base_install_dir / self.name
        self.port: int = port if port is not None else self.default_port
        self.puid = puid
        self.pgid = pgid
        self._logger = logging.getLogger(f"applications.{self.name}")

    # ------------------------------------------------------------------
    # Abstract methods — MUST be implemented by subclasses
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def install(self) -> None:
        """
        Download and install the application binary.

        Typical implementation:
          1. Detect the host architecture (x86_64 / arm64).
          2. Find the latest GitHub release matching the arch.
          3. Download and verify the archive.
          4. Extract to self.install_dir.
          5. Apply self.puid / self.pgid ownership.
        """

    @abc.abstractmethod
    def start_command(self) -> list[str]:
        """
        Return the command list used to launch the application.

        Example::

            return [str(self.install_dir / "Sonarr"), "--no-browser"]
        """

    @abc.abstractmethod
    def health_check_url(self) -> str:
        """
        Return the URL polled to determine if the application is healthy.

        Example::

            return f"http://localhost:{self.port}/ping"
        """

    # ------------------------------------------------------------------
    # Optional hooks — subclasses may override
    # ------------------------------------------------------------------

    def configure_integration(self, supervisor: "ProcessSupervisor") -> None:
        """
        Called after all applications have started.

        Use this to wire the application into the rest of the stack via
        REST API calls (e.g., adding download clients to Sonarr).

        The default implementation does nothing.
        """

    def pre_install(self) -> None:
        """Hook called before install().  Ensure directories exist by default."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.install_dir.mkdir(parents=True, exist_ok=True)
        self._logger.debug(
            "Pre-install: config_dir=%s  install_dir=%s", self.config_dir, self.install_dir
        )

    def post_install(self) -> None:
        """Hook called after install() succeeds."""

    # ------------------------------------------------------------------
    # Convenience helpers available to all subclasses
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} name={self.name!r} port={self.port} "
            f"install_dir={self.install_dir}>"
        )
