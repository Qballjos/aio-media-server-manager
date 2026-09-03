"""
applications/base.py — BaseApplication Plugin Contract

Every application plugin must subclass BaseApplication and provide a
class-level AppManifest plus install / start / health behaviour.
"""

from __future__ import annotations

import abc
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from applications.manifest import AppManifest, InstallMethod
from core.installer import AppInstaller, InstallResult
from core.installer.arch import detect_system_arch
from core.settings import settings

if TYPE_CHECKING:
    from core.supervisor import ProcessSupervisor

logger = logging.getLogger(__name__)


class BaseApplication(abc.ABC):
    """
    Abstract base class for all application plugins.

    Subclasses MUST set ``manifest`` and may override install/start/health
    when the default GitHub-release workflow is insufficient.
    """

    manifest: AppManifest

    def __init__(
        self,
        *,
        base_config_dir: Path | None = None,
        base_install_dir: Path | None = None,
        port: int | None = None,
        puid: int | None = None,
        pgid: int | None = None,
    ) -> None:
        if not getattr(self, "manifest", None) or not self.manifest.name:
            raise ValueError(
                f"{type(self).__name__} must define a non-empty AppManifest."
            )
        config_root = Path(base_config_dir or settings.config_dir)
        install_root = Path(base_install_dir or settings.install_dir)
        self.config_dir: Path = config_dir_for(self.manifest, config_root)
        self.data_dir: Path = data_dir_for(self.manifest, config_root)
        self.install_dir: Path = install_root / self.manifest.name
        self.port: int = port if port is not None else self.manifest.default_port
        self.puid = puid if puid is not None else settings.puid
        self.pgid = pgid if pgid is not None else settings.pgid
        self._logger = logging.getLogger(f"applications.{self.name}")

    # ------------------------------------------------------------------
    # Identity helpers
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def default_port(self) -> int:
        return self.manifest.default_port

    @property
    def github_repo(self) -> str:
        return self.manifest.github_repo

    @property
    def executable_name(self) -> str:
        return self.manifest.executable_name

    def supports_current_arch(self) -> bool:
        arch = detect_system_arch().value
        return arch in self.manifest.supported_architectures

    def metadata_path(self) -> Path:
        return self.install_dir / ".amm_installed.json"

    def is_installed(self) -> bool:
        if not self.metadata_path().is_file():
            return False
        exe = self.executable_path()
        return exe is not None and exe.is_file()

    def installed_metadata(self) -> dict | None:
        path = self.metadata_path()
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def executable_path(self) -> Path | None:
        direct = self.install_dir / self.executable_name
        if direct.is_file():
            return direct
        if not self.install_dir.exists():
            return None
        for candidate in self.install_dir.rglob(self.executable_name):
            if candidate.is_file():
                return candidate
        return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def pre_install(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.install_dir.mkdir(parents=True, exist_ok=True)
        self._logger.debug(
            "Pre-install: config_dir=%s install_dir=%s",
            self.config_dir,
            self.install_dir,
        )

    def install(self) -> InstallResult:
        """Default GitHub-release install. Override for PyPI / custom sources."""
        if self.manifest.install_method == InstallMethod.PYPI:
            installer = AppInstaller()
            return installer.install_from_pypi(
                package=self.executable_name,
                app_name=self.name,
            )
        installer = AppInstaller()
        return installer.install_from_github(
            repo=self.github_repo,
            app_name=self.name,
            executable_name=self.executable_name,
            preferred_patterns=self.preferred_patterns(),
        )

    def post_install(self) -> None:
        """Hook called after install() succeeds."""

    def preferred_patterns(self) -> Sequence[str]:
        return self.manifest.preferred_patterns

    def start_command(self) -> list[str]:
        exe = self.executable_path()
        if exe is None:
            raise FileNotFoundError(
                f"{self.manifest.display_name} is not installed "
                f"(expected executable '{self.executable_name}' in {self.install_dir})."
            )
        return self.build_start_command(exe)

    @abc.abstractmethod
    def build_start_command(self, executable: Path) -> list[str]:
        """Return the argv used to launch the installed binary."""

    def extra_env(self) -> dict[str, str]:
        return {}

    def working_directory(self) -> Path | None:
        return self.install_dir

    def health_check_url(self) -> str:
        path = self.manifest.health_path
        if not path.startswith("/"):
            path = "/" + path
        return f"http://127.0.0.1:{self.port}{path}"

    def configure_integration(self, supervisor: "ProcessSupervisor") -> None:
        """Called after applications have started. Default is a no-op."""

    def catalog_entry(self, *, host_arch: str | None = None) -> dict:
        arch = host_arch or detect_system_arch().value
        meta = self.installed_metadata() or {}
        return {
            **self.manifest.to_dict(),
            "port": self.port,
            "installed": self.is_installed(),
            "installed_version": meta.get("version"),
            "arm64_supported": "arm64" in self.manifest.supported_architectures,
            "arm64_available": "arm64" in self.manifest.supported_architectures,
            "current_arch_supported": arch in self.manifest.supported_architectures,
            "current_arch": arch,
        }

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} name={self.name!r} port={self.port} "
            f"install_dir={self.install_dir}>"
        )


def config_dir_for(manifest: AppManifest, config_root: Path) -> Path:
    return config_root / (manifest.config_subdir or manifest.name)


def data_dir_for(manifest: AppManifest, config_root: Path) -> Path:
    sub = manifest.data_subdir or manifest.config_subdir or manifest.name
    return config_root / sub
