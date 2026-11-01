from __future__ import annotations

import os
from pathlib import Path

import requests

from applications.base import BaseApplication
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod
from core.crypto import secret_store
from core.installer.arch import detect_system_arch, detect_system_os, filename_has_cpu_arch, score_asset_match
from core.installer.installer import AppInstaller, InstallResult
from core.settings import settings

_PLEX_LINUX_BUILD = {
    "x86_64": "linux-x86_64",
    "arm64": "linux-aarch64",
}


def plex_linux_build(host_arch: str | None = None) -> str:
    arch = host_arch or detect_system_arch().value
    build = _PLEX_LINUX_BUILD.get(arch)
    if build is None:
        raise RuntimeError(f"Plex Media Server Linux builds are not published for {arch}.")
    return build


MANIFEST = AppManifest(
    name="plex",
    display_name="Plex",
    description="Plex Media Server for movies, TV, and music. Can use the same media library as Jellyfin.",
    github_repo="",
    upstream_url="https://www.plex.tv/",
    tier=AppTier.CORE,
    category=AppCategory.MEDIA,
    default_port=32400,
    executable_name="Plex Media Server",
    supported_architectures=("x86_64", "arm64"),
    install_method=InstallMethod.OFFICIAL_BINARY,
    health_path="/identity",
    config_subdir="plex/config",
    data_subdir="plex/data",
)


class PlexApp(BaseApplication):
    manifest = MANIFEST

    @property
    def home_dir(self) -> Path:
        exe = self.executable_path()
        if exe is not None:
            real_parent = exe.resolve().parent
            if (real_parent / "Resources").is_dir():
                return real_parent

        deb_home = self.install_dir / "usr" / "lib" / "plexmediaserver"
        if (deb_home / "Resources").is_dir():
            return deb_home

        res_path = self.install_dir / "Resources"
        if res_path.is_dir() and not res_path.is_symlink():
            return self.install_dir

        if self.install_dir.is_dir():
            for res_dir in self.install_dir.rglob("Resources"):
                if res_dir.is_dir() and not res_dir.is_symlink() and (res_dir / "cacert.pem").is_file():
                    return res_dir.parent

        if exe is not None:
            return exe.resolve().parent

        return self.install_dir

    def working_directory(self) -> Path | None:
        return self.home_dir

    def _ensure_symlinks(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        home = self.home_dir
        if home != self.install_dir and home.is_dir():
            for item in ("Resources", "lib", self.executable_name):
                src = home / item
                dst = self.install_dir / item
                if src.exists() and not dst.exists():
                    try:
                        dst.symlink_to(src)
                    except OSError:
                        pass

    def post_install(self) -> None:
        self._ensure_symlinks()

    def extra_env(self) -> dict[str, str]:
        self._ensure_symlinks()
        home = self.home_dir
        lib_dir = home / "lib"

        existing_ld = os.environ.get("LD_LIBRARY_PATH", "")
        ld_dirs = [str(home)]
        if lib_dir.is_dir():
            ld_dirs.append(str(lib_dir))
        if existing_ld:
            ld_dirs.append(existing_ld)

        existing_path = os.environ.get("PATH", "")
        path_dirs = [str(home)]
        if existing_path:
            path_dirs.append(existing_path)

        env: dict[str, str] = {
            "PLEX_MEDIA_SERVER_APPLICATION_SUPPORT_DIR": str(self.config_dir),
            "PLEX_MEDIA_SERVER_HOME": str(home),
            "PLEX_MEDIA_SERVER_MAX_PLUGIN_PROCS": "6",
            "PLEX_MEDIA_SERVER_INFO_VENDOR": "aio-media-server-manager",
            "PLEX_MEDIA_SERVER_INFO_DEVICE": "aio-media-server-manager",
            "LD_LIBRARY_PATH": ":".join(ld_dirs),
            "PATH": ":".join(path_dirs),
        }
        claim = secret_store.get_secret("plex_claim")
        if claim:
            env["PLEX_CLAIM"] = claim
        return env

    def build_start_command(self, executable: Path) -> list[str]:
        return [str(executable)]

    def install(self) -> InstallResult:
        self.require_host_arch()
        installer = AppInstaller()
        arch = detect_system_arch().value
        build = plex_linux_build(arch)
        payload = requests.get("https://plex.tv/api/downloads/5.json", timeout=30).json()
        releases = payload.get("computer", {}).get("Linux", {}).get("releases", [])
        match = next(
            (
                item
                for item in releases
                if item.get("build") == build and item.get("distro") in ("debian", "ubuntu", "linux")
            ),
            None,
        )
        if match is None:
            match = next((item for item in releases if item.get("build") == build), None)
        if match is None:
            raise RuntimeError(f"No official Plex Media Server binary found for {arch} ({build}).")
        url = match["url"]
        version = str(payload.get("computer", {}).get("Linux", {}).get("version") or "plex")
        filename = url.split("?")[0].rstrip("/").split("/")[-1]
        host_arch = detect_system_arch()
        if filename_has_cpu_arch(filename) and score_asset_match(filename, host_arch, detect_system_os()) < 0:
            raise ValueError(
                f"Refusing to install Plex asset '{filename}': "
                f"it does not match host arch={host_arch.value}."
            )
        cache_dir = installer.settings.cache_dir / "downloads"
        cache_dir.mkdir(parents=True, exist_ok=True)
        archive_path = cache_dir / filename
        sha = installer.download_file(url, archive_path)
        exe = installer.activate_archive(
            archive_path=archive_path,
            target_install_dir=self.install_dir,
            executable_name=self.executable_name,
            app_name=self.name,
        )
        metadata_path = self.metadata_path()
        metadata_path.write_text(
            __import__("json").dumps(
                {
                    "app_name": self.name,
                    "version": version,
                    "asset_name": filename,
                    "sha256": sha,
                    "url": url,
                    "source": "plex.tv",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        self.post_install()
        return InstallResult(
            app_name=self.name,
            version=version,
            install_dir=self.install_dir,
            executable_path=exe,
            asset_name=filename,
            sha256=sha,
            installed_at=__import__("time").time(),
        )
