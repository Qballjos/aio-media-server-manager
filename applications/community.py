"""Catalog plugins that are not Servarr core: Flaresolverr, Grimmory, Shelfmark."""

from __future__ import annotations

import shutil
import stat
import subprocess
import sys
from pathlib import Path

from applications.base import SimpleApplication
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod
from core.installer import AppInstaller, InstallResult
from core.installer.arch import PlatformArch, detect_system_arch
from core.library_layout import LibraryLayout
from core.settings import settings as default_settings


def _write_runner(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _create_venv(install_root: Path) -> Path:
    venv_dir = install_root / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
    pip = venv_dir / "bin" / "pip"
    if not pip.is_file():
        pip = venv_dir / "Scripts" / "pip.exe"
    subprocess.run(
        [str(pip), "install", "--upgrade", "pip"],
        check=True,
        capture_output=True,
        text=True,
    )
    return venv_dir


class FlaresolverrApp(SimpleApplication):
    manifest = AppManifest(
        name="flaresolverr",
        display_name="Flaresolverr",
        description="Cloudflare challenge proxy used by Prowlarr and Shelfmark.",
        github_repo="FlareSolverr/FlareSolverr",
        upstream_url="https://github.com/FlareSolverr/FlareSolverr",
        tier=AppTier.RECOMMENDED,
        category=AppCategory.INDEXERS,
        default_port=8191,
        executable_name="flaresolverr",
        supported_architectures=("x86_64", "arm64"),
        install_method=InstallMethod.GITHUB_RELEASE,
        preferred_patterns=(r"flaresolverr_linux",),
        optional_dependencies=("prowlarr",),
        health_path="/",
    )

    def extra_env(self) -> dict[str, str]:
        env = {
            "HOST": "0.0.0.0",
            "PORT": str(self.port),
            "LOG_LEVEL": "info",
        }
        chrome = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
        if chrome:
            env["CHROME_BIN"] = chrome
        return env

    def install(self) -> InstallResult:
        installer = AppInstaller()
        try:
            result = installer.install_from_github(
                repo=self.github_repo,
                app_name=self.name,
                executable_name=self.executable_name,
                preferred_patterns=self.preferred_patterns(),
            )
        except (ValueError, FileNotFoundError):
            result = self._install_from_source(installer)
        self.post_install()
        return result

    def _install_from_source(self, installer: AppInstaller) -> InstallResult:
        result = installer.install_from_github_source(
            self.github_repo,
            self.name,
            "src/flaresolverr.py",
        )
        venv_dir = _create_venv(self.install_dir)
        pip = venv_dir / "bin" / "pip"
        if not pip.is_file():
            pip = venv_dir / "Scripts" / "pip.exe"
        requirements = self.install_dir / "requirements.txt"
        if requirements.is_file():
            subprocess.run(
                [str(pip), "install", "-r", str(requirements)],
                check=True,
                capture_output=True,
                text=True,
            )
        python = venv_dir / "bin" / "python"
        if not python.is_file():
            python = venv_dir / "Scripts" / "python.exe"
        script = self.install_dir / "src" / "flaresolverr.py"
        runner = self.install_dir / "flaresolverr"
        _write_runner(
            runner,
            [
                "#!/bin/sh",
                f'exec "{python}" "{script}" "$@"',
            ],
        )
        return result


class GrimmoryApp(SimpleApplication):
    manifest = AppManifest(
        name="grimmory",
        display_name="Grimmory",
        description="Self-hosted library for ebooks, comics, and audiobooks.",
        github_repo="grimmory-tools/grimmory",
        upstream_url="https://github.com/grimmory-tools/grimmory",
        tier=AppTier.OPTIONAL,
        category=AppCategory.MEDIA,
        default_port=6060,
        executable_name="grimmory.jar",
        supported_architectures=("x86_64", "arm64"),
        install_method=InstallMethod.GITHUB_RELEASE,
        preferred_patterns=(r"grimmory\.jar$",),
        health_path="/api/v1/healthcheck",
    )

    def start_command(self) -> list[str]:
        runner = self.install_dir / "run-grimmory"
        if runner.is_file():
            return [str(runner)]
        java = shutil.which("java")
        if not java:
            raise FileNotFoundError("Java is required to run Grimmory (install a JRE).")
        jar = self.install_dir / "grimmory.jar"
        if not jar.is_file():
            jar = self.executable_path()
        return [java, "-jar", str(jar)]

    def extra_env(self) -> dict[str, str]:
        layout = LibraryLayout.from_settings(default_settings)
        bookdrop = layout.bookdrop
        bookdrop.mkdir(parents=True, exist_ok=True)
        mysql_port = 3307
        return {
            "SERVER_PORT": str(self.port),
            "USER_ID": str(self.puid),
            "GROUP_ID": str(self.pgid),
            "TZ": "Etc/UTC",
            "APP_PATH_CONFIG": str(self.data_dir),
            "APP_BOOKDROP_FOLDER": str(bookdrop),
            "DATABASE_URL": (
                f"jdbc:mariadb://127.0.0.1:{mysql_port}/grimmory"
                "?createDatabaseIfNotExist=true&connectionTimeZone=UTC"
            ),
            "DATABASE_USERNAME": "grimmory",
            "DATABASE_PASSWORD": "grimmory",
            "FORCE_DISABLE_OIDC": "true",
            "API_DOCS_ENABLED": "false",
        }

    def post_install(self) -> None:
        java = shutil.which("java") or "java"
        jar = self.install_dir / "grimmory.jar"
        datadir = self.data_dir / "mysql"
        socket = self.data_dir / "mysql.sock"
        runner = self.install_dir / "run-grimmory"
        _write_runner(
            runner,
            [
                "#!/bin/sh",
                "set -e",
                f'MARIADB_DATA="{datadir}"',
                f'MARIADB_SOCK="{socket}"',
                "MARIADB_PORT=3307",
                f'JAR="{jar}"',
                f'JAVA_BIN="{java}"',
                'if ! command -v "$JAVA_BIN" >/dev/null 2>&1; then',
                '  echo "Java is required to run Grimmory" >&2',
                "  exit 1",
                "fi",
                "MYSQLD=$(command -v mariadbd || command -v mysqld || true)",
                'if [ -z "$MYSQLD" ]; then',
                '  echo "MariaDB/MySQL is required for Grimmory (mariadbd not found)" >&2',
                "  exit 1",
                "fi",
                'mkdir -p "$MARIADB_DATA"',
                'if [ ! -d "$MARIADB_DATA/mysql" ]; then',
                "  INIT=$(command -v mariadb-install-db || command -v mysql_install_db || true)",
                '  if [ -n "$INIT" ]; then',
                '    "$INIT" --datadir="$MARIADB_DATA" --auth-root-authentication-method=normal >/dev/null',
                "  else",
                '    "$MYSQLD" --initialize-insecure --datadir="$MARIADB_DATA"',
                "  fi",
                "fi",
                '"$MYSQLD" --datadir="$MARIADB_DATA" --socket="$MARIADB_SOCK" --port="$MARIADB_PORT" --bind-address=127.0.0.1 &',
                "MYSQLD_PID=$!",
                "trap 'kill $MYSQLD_PID 2>/dev/null || true' EXIT",
                "i=0",
                "while [ $i -lt 30 ]; do",
                '  mariadb-admin --socket="$MARIADB_SOCK" ping >/dev/null 2>&1 && break',
                '  mysqladmin --socket="$MARIADB_SOCK" ping >/dev/null 2>&1 && break',
                "  i=$((i + 1))",
                "  sleep 1",
                "done",
                'mariadb --socket="$MARIADB_SOCK" -e "CREATE DATABASE IF NOT EXISTS grimmory; CREATE USER IF NOT EXISTS \'grimmory\'@\'127.0.0.1\' IDENTIFIED BY \'grimmory\'; GRANT ALL ON grimmory.* TO \'grimmory\'@\'127.0.0.1\'; FLUSH PRIVILEGES;" >/dev/null 2>&1 || true',
                'exec "$JAVA_BIN" -jar "$JAR"',
            ],
        )


class ShelfmarkApp(SimpleApplication):
    manifest = AppManifest(
        name="shelfmark",
        display_name="Shelfmark",
        description="Search and request ebooks and audiobooks; pairs with Grimmory and Prowlarr.",
        github_repo="calibrain/shelfmark",
        upstream_url="https://github.com/calibrain/shelfmark",
        tier=AppTier.OPTIONAL,
        category=AppCategory.REQUESTS,
        default_port=8084,
        executable_name="run-shelfmark",
        supported_architectures=("x86_64", "arm64"),
        install_method=InstallMethod.GITHUB_RELEASE,
        optional_dependencies=("prowlarr", "flaresolverr", "grimmory", "qbittorrent"),
        health_path="/api/health",
    )

    def extra_env(self) -> dict[str, str]:
        layout = LibraryLayout.from_settings(default_settings)
        ingest = layout.complete_path("books")
        ingest.mkdir(parents=True, exist_ok=True)
        env = {
            "FLASK_HOST": "0.0.0.0",
            "FLASK_PORT": str(self.port),
            "CONFIG_DIR": str(self.config_dir),
            "INGEST_DIR": str(ingest),
            "TZ": "Etc/UTC",
            "SEARCH_MODE": "universal",
            "USING_EXTERNAL_BYPASSER": "true",
            "EXT_BYPASSER_URL": "http://127.0.0.1:8191",
            "EXT_BYPASSER_PATH": "/v1",
            "PROWLARR_ENABLED": "true",
            "PROWLARR_URL": "http://127.0.0.1:9696",
            "BOOKLORE_HOST": "http://127.0.0.1:6060",
            "PYTHONPATH": str(self.install_dir),
        }
        try:
            from core.integrations.credentials import get_application_api_key

            key = get_application_api_key("prowlarr")
            if key:
                env["PROWLARR_API_KEY"] = key
        except Exception:
            pass
        return env

    def install(self) -> InstallResult:
        installer = AppInstaller()
        result = installer.install_from_github_source(
            self.github_repo,
            self.name,
            "pyproject.toml",
        )
        venv_dir = _create_venv(self.install_dir)
        pip = venv_dir / "bin" / "pip"
        if not pip.is_file():
            pip = venv_dir / "Scripts" / "pip.exe"
        subprocess.run(
            [str(pip), "install", str(self.install_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
        frontend = self.install_dir / "src" / "frontend"
        npm = shutil.which("npm")
        if npm and (frontend / "package.json").is_file():
            subprocess.run([npm, "ci"], cwd=frontend, check=True, capture_output=True, text=True)
            subprocess.run([npm, "run", "build"], cwd=frontend, check=True, capture_output=True, text=True)
            dist = frontend / "dist"
            target = self.install_dir / "frontend-dist"
            if dist.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(dist, target)
        gunicorn = venv_dir / "bin" / "gunicorn"
        if not gunicorn.is_file():
            gunicorn = venv_dir / "Scripts" / "gunicorn.exe"
        runner = self.install_dir / "run-shelfmark"
        _write_runner(
            runner,
            [
                "#!/bin/sh",
                f'cd "{self.install_dir}"',
                f'export PYTHONPATH="{self.install_dir}"',
                f'exec "{gunicorn}" --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker '
                f'--workers 1 -t 300 -b 0.0.0.0:{self.port} shelfmark.main:app',
            ],
        )
        self.post_install()
        return result
