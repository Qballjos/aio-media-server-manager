"""Catalog plugins that are not Servarr core: Flaresolverr, Grimmory, Shelfmark."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from applications.base import SimpleApplication
from applications.install_helpers import child_python, create_venv, venv_bin, write_runner
from applications.manifest import AppCategory, AppManifest, AppTier, InstallMethod
from applications.shelfmark_mirrors import prepare_shelfmark_runtime, write_shelfmark_runner
from core.installer import AppInstaller, InstallResult
from core.library_layout import LibraryLayout
from core.settings import settings as default_settings


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
        supported_architectures=("x86_64",),
        install_method=InstallMethod.GITHUB_RELEASE,
        preferred_patterns=(r"flaresolverr_linux_x64",),
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

    def build_start_command(self, executable: Path) -> list[str]:
        from core.vpn import vpn_manager

        return vpn_manager.wrap_isolated_command(super().build_start_command(executable))


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
        self._write_runner()
        runner = self.install_dir / "run-grimmory"
        if runner.is_file():
            return [str(runner)]
        java = shutil.which("java")
        if not java:
            raise FileNotFoundError("Java is required to run Grimmory (install a JRE).")
        jar = self.install_dir / "grimmory.jar"
        if not jar.is_file():
            jar = self.executable_path()
        return [java, "--enable-preview", "-jar", str(jar)]

    def extra_env(self) -> dict[str, str]:
        layout = LibraryLayout.from_settings(default_settings)
        # Shared inbox with Shelfmark (ebooks + audiobooks) → complete/books.
        for path in (layout.bookdrop, layout.books, layout.comics):
            path.mkdir(parents=True, exist_ok=True)
        mysql_port = 3307
        return {
            "SERVER_PORT": str(self.port),
            "USER_ID": str(self.puid),
            "GROUP_ID": str(self.pgid),
            "TZ": "Etc/UTC",
            "APP_PATH_CONFIG": str(self.data_dir),
            "APP_BOOKDROP_FOLDER": str(layout.bookdrop),
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
        self._write_runner()

    def _write_runner(self) -> None:
        jar = self.install_dir / "grimmory.jar"
        datadir = self.data_dir / "mysql"
        socket = self.data_dir / "mysql.sock"
        runner = self.install_dir / "run-grimmory"
        write_runner(
            runner,
            [
                "#!/bin/sh",
                "set -e",
                f'MARIADB_DATA="{datadir}"',
                f'MARIADB_SOCK="{socket}"',
                "MARIADB_PORT=3307",
                f'JAR="{jar}"',
                "JAVA_BIN=$(command -v java || true)",
                'if [ -z "$JAVA_BIN" ]; then',
                '  echo "Java 25+ is required to run Grimmory" >&2',
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
                '_mariadb_up() { mariadb-admin --socket="$MARIADB_SOCK" ping >/dev/null 2>&1 || mysqladmin --socket="$MARIADB_SOCK" ping >/dev/null 2>&1; }',
                "if ! _mariadb_up; then",
                '  "$MYSQLD" --user=root --datadir="$MARIADB_DATA" --socket="$MARIADB_SOCK" --port="$MARIADB_PORT" --bind-address=127.0.0.1 &',
                "  MYSQLD_PID=$!",
                "  trap 'kill $MYSQLD_PID 2>/dev/null || true' EXIT",
                "  i=0",
                "  while [ $i -lt 30 ]; do",
                "    _mariadb_up && break",
                "    i=$((i + 1))",
                "    sleep 1",
                "  done",
                "fi",
                'mariadb --socket="$MARIADB_SOCK" -e "CREATE DATABASE IF NOT EXISTS grimmory; CREATE USER IF NOT EXISTS \'grimmory\'@\'127.0.0.1\' IDENTIFIED BY \'grimmory\'; GRANT ALL ON grimmory.* TO \'grimmory\'@\'127.0.0.1\'; FLUSH PRIVILEGES;" >/dev/null 2>&1 || true',
                'exec "$JAVA_BIN" --enable-preview -jar "$JAR"',
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
        from applications.shelfmark_mirrors import shelfmark_download_client_env
        from core.app_web_url import grimmory_browser_url

        layout = LibraryLayout.from_settings(default_settings)
        # Ebooks and audiobooks share the same Grimmory bookdrop inbox.
        bookdrop = layout.bookdrop
        bookdrop.mkdir(parents=True, exist_ok=True)
        layout.books.mkdir(parents=True, exist_ok=True)
        # BOOKLORE_HOST stays on loopback for Shelfmark→Grimmory API uploads.
        # AUDIOBOOK_LIBRARY_URL is a browser nav link → prefer public Grimmory URL.
        grimmory_port = 6060
        try:
            from applications.catalog import ApplicationCatalog

            cat = ApplicationCatalog()
            if cat.has("grimmory"):
                grimmory_port = int(cat.get("grimmory").port or 6060)
        except Exception:
            grimmory_port = 6060
        grimmory_lan = f"http://127.0.0.1:{grimmory_port}"
        env = {
            "FLASK_HOST": "0.0.0.0",
            "FLASK_PORT": str(self.port),
            "CONFIG_DIR": str(self.config_dir),
            "INGEST_DIR": str(bookdrop),
            "DESTINATION": str(bookdrop),
            "TZ": "Etc/UTC",
            "SEARCH_MODE": "universal",
            "USING_EXTERNAL_BYPASSER": "true",
            "EXT_BYPASSER_URL": "http://127.0.0.1:8191",
            "EXT_BYPASSER_PATH": "/v1",
            "PROWLARR_ENABLED": "true",
            "PROWLARR_URL": "http://127.0.0.1:9696",
            "BOOKLORE_HOST": grimmory_lan,
            "AUDIOBOOK_LIBRARY_URL": grimmory_browser_url(port=grimmory_port),
            "PYTHONPATH": str(self.install_dir),
        }
        env.update(shelfmark_download_client_env())
        try:
            from core.integrations.credentials import get_application_api_key

            key = get_application_api_key("prowlarr")
            if key:
                env["PROWLARR_API_KEY"] = key
        except Exception:
            pass
        return env

    def start_command(self) -> list[str]:
        prepare_shelfmark_runtime(self.config_dir, self.install_dir, port=self.port)
        return super().start_command()

    def install(self) -> InstallResult:
        self.require_host_arch()
        installer = AppInstaller()
        result = installer.install_from_github_source(
            self.github_repo,
            self.name,
            "pyproject.toml",
        )
        venv_dir = create_venv(self.install_dir, python=child_python())
        pip = venv_bin(venv_dir, "pip")
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
        write_shelfmark_runner(self.install_dir, port=self.port)
        prepare_shelfmark_runtime(self.config_dir, self.install_dir, port=self.port)
        self.post_install()
        return result
