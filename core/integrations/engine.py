"""
core/integrations/engine.py — Automatic Integration Engine Orchestrator.

Wires download clients, *Arr apps, Seerr, Bazarr, and optimization-tool configs.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from pathlib import Path

from applications.catalog import ApplicationCatalog
from core.crypto import mask_secret
from core.integrations.arr_app import ArrAppClient
from core.integrations.bazarr import BazarrClient
from core.integrations.credentials import get_application_api_key
from core.integrations.hooks import (
    write_neutarr_config,
    write_profilarr_config,
    write_recyclarr_config,
)
from core.recyclarr import run_sync
from core.integrations.jellyfin import JellyfinClient
from core.integrations.local_auth import apply_shared_local_logins
from core.integrations.nzbget import NZBGetClient, nzbget_credentials
from core.integrations.plex import PlexClient
from core.integrations.prowlarr import ProwlarrClient
from core.integrations.qbittorrent import QBittorrentClient, apply_qbittorrent_webui_login, qbittorrent_credentials
from core.integrations.radarr import RadarrClient
from core.integrations.sabnzbd import SABnzbdClient, read_sabnzbd_ini
from core.integrations.seerr import SeerrClient
from core.integrations.sonarr import SonarrClient
from core.integrations.usenet import load_usenet_server
from core.library_layout import (
    DOWNLOAD_CATEGORIES,
    LIBRARY_FOLDERS,
    arr_root_folders,
    jellyfin_libraries,
)
from core.settings import settings
from core.shared_credentials import admin_email, shared_admin_credentials
from core.storage import StorageManager
from core.supervisor import ProcessSupervisor

logger = logging.getLogger(__name__)

WIRE_AFTER_INSTALL = frozenset(
    {
        "sonarr",
        "radarr",
        "lidarr",
        "prowlarr",
        "flaresolverr",
        "sabnzbd",
        "nzbget",
        "qbittorrent",
        "jellyfin",
        "plex",
        "seerr",
        "bazarr",
    }
)

_STATUS_APPS = (
    "sabnzbd",
    "nzbget",
    "qbittorrent",
    "sonarr",
    "radarr",
    "lidarr",
    "prowlarr",
    "jellyfin",
    "plex",
    "seerr",
    "bazarr",
    "recyclarr",
    "profilarr",
    "neutarr",
)


class IntegrationEngine:
    def __init__(self, cfg=None):
        self._settings = cfg or settings
        self._catalog = ApplicationCatalog(app_settings=self._settings)

    def _is_app_running(self, name: str) -> bool:
        supervisor = ProcessSupervisor.get()
        return supervisor.status(name).value == "running"

    def _port(self, name: str, fallback: int) -> int:
        if self._catalog.has(name):
            return self._catalog.get(name).port
        return fallback

    def _installed(self, name: str) -> bool:
        return self._catalog.has(name) and self._catalog.get(name).is_installed()

    def _wizard_selections(self) -> dict[str, Any]:
        try:
            from core.wizard import wizard_engine

            return dict(wizard_engine._state.get("selections") or {})
        except Exception:
            return {}

    def _downloaders_for_arr(self, *, sab_key: str | None) -> list[str]:
        """Register every installed, running downloader *Arr can talk to."""
        ready: list[str] = []
        if self._installed("sabnzbd") and self._is_app_running("sabnzbd") and sab_key:
            ready.append("sabnzbd")
        if self._installed("nzbget") and self._is_app_running("nzbget"):
            ready.append("nzbget")
        if self._installed("qbittorrent") and self._is_app_running("qbittorrent"):
            ready.append("qbittorrent")
        return ready

    def _chosen_apps(self, *names: str, selection_key: str = "") -> list[str]:
        selected = self._wizard_selections().get(selection_key) if selection_key else None
        if isinstance(selected, str):
            selected = [selected] if selected and selected != "none" else []
        chosen = [name for name in names if self._installed(name)]
        if selected is None:
            return chosen
        wanted = {str(item) for item in selected}
        return [name for name in chosen if name in wanted]

    def _skip_uninstalled(self, steps: list[dict[str, Any]], name: str, action: str) -> bool:
        """Skip HTTP wiring until the app is installed *and* running."""
        return self._skip_unavailable(steps, name, action, require_running=True)

    def _skip_unavailable(
        self,
        steps: list[dict[str, Any]],
        name: str,
        action: str,
        *,
        require_running: bool = True,
    ) -> bool:
        if self._installed(name) and (not require_running or self._is_app_running(name)):
            return False
        detail = "not installed" if not self._installed(name) else "not running"
        steps.append(
            {
                "target": name,
                "action": action,
                "status": "skipped",
                "detail": detail,
            }
        )
        return True

    def get_wiring_status(self) -> dict[str, Any]:
        report: dict[str, Any] = {}
        for app_name in _STATUS_APPS:
            plugin = self._catalog.get(app_name) if self._catalog.has(app_name) else None
            installed = plugin.is_installed() if plugin else False
            running = self._is_app_running(app_name)
            key = get_application_api_key(app_name)
            port = plugin.port if plugin else 0
            report[app_name] = {
                "installed": installed,
                "running": running,
                "port": port,
                "has_api_key": bool(key),
                "api_key_masked": mask_secret(key) if key else None,
            }
        return report

    def run_full_wiring(self) -> dict[str, Any]:
        steps: list[dict[str, Any]] = []
        layout = StorageManager(self._settings).create_standard_layout()
        steps.append(
            _step(
                "storage",
                "create_library_layout",
                True,
                f"libraries={','.join(LIBRARY_FOLDERS)}",
            )
        )

        qb_user, qb_pass = qbittorrent_credentials()
        nzb_user, nzb_pass = nzbget_credentials()
        sab_port = self._port("sabnzbd", 8085)
        nzb_port = self._port("nzbget", 6789)
        qb_port = self._port("qbittorrent", 8081)
        sonarr_port = self._port("sonarr", 8989)
        radarr_port = self._port("radarr", 7878)
        lidarr_port = self._port("lidarr", 8686)
        prowlarr_port = self._port("prowlarr", 9696)
        jelly_port = self._port("jellyfin", 8096)
        plex_port = self._port("plex", 32400)
        seerr_port = self._port("seerr", 5055)
        bazarr_port = self._port("bazarr", 6767)

        sab_cfg = self._catalog.get("sabnzbd").config_dir if self._catalog.has("sabnzbd") else self._settings.config_dir / "sabnzbd"
        sab_key = get_application_api_key("sabnzbd", sab_cfg)
        sonarr_key = get_application_api_key("sonarr")
        radarr_key = get_application_api_key("radarr")
        lidarr_key = get_application_api_key("lidarr")
        prowlarr_key = get_application_api_key("prowlarr")
        jellyfin_key = get_application_api_key("jellyfin")
        seerr_key = get_application_api_key("seerr")
        bazarr_key = get_application_api_key("bazarr")

        sonarr_url = f"http://127.0.0.1:{sonarr_port}"
        radarr_url = f"http://127.0.0.1:{radarr_port}"
        lidarr_url = f"http://127.0.0.1:{lidarr_port}"

        if not self._skip_unavailable(steps, "sabnzbd", "configure_folders_and_categories"):
            sab_client = SABnzbdClient(port=sab_port, api_key=sab_key)
            sab_ok = sab_client.set_folders(str(layout.complete), str(layout.incomplete))
            for category in DOWNLOAD_CATEGORIES:
                sab_ok = sab_client.add_category(category.name, dir_path=category.library) and sab_ok
            usenet = load_usenet_server()
            if usenet and usenet.get("host"):
                sab_ok = sab_client.add_news_server(**usenet) and sab_ok
            steps.append(_step("sabnzbd", "configure_folders_and_categories", sab_ok, str(layout.complete)))

        if not self._skip_unavailable(steps, "nzbget", "configure_folders_and_categories"):
            nzb = NZBGetClient(port=nzb_port)
            nzb_ok = nzb.set_download_dirs(str(layout.complete), str(layout.incomplete))
            for category in DOWNLOAD_CATEGORIES:
                nzb_ok = nzb.add_category(category.name, dest_dir=str(layout.complete_path(category.library))) and nzb_ok
            usenet = load_usenet_server()
            if usenet and usenet.get("host"):
                nzb_ok = nzb.add_news_server(**usenet) and nzb_ok
            steps.append(_step("nzbget", "configure_folders_and_categories", nzb_ok, str(layout.complete)))

        if not self._skip_unavailable(steps, "qbittorrent", "configure_folders_and_categories"):
            qb_plugin = self._catalog.get("qbittorrent")
            login_ok = apply_qbittorrent_webui_login(qb_plugin.config_dir, qb_port)
            qb_user, qb_pass = qbittorrent_credentials()
            qb_client = QBittorrentClient(port=qb_port, username=qb_user, password=qb_pass)
            logged_in = qb_client.login() or qb_client.app_accessible()
            qb_ok = login_ok
            if logged_in:
                qb_ok = qb_client.set_download_paths(str(layout.torrents), str(layout.incomplete)) and qb_ok
                for category in DOWNLOAD_CATEGORIES:
                    qb_ok = qb_client.create_category(
                        category.name,
                        save_path=str(layout.torrent_path(category.library)),
                    ) and qb_ok
            steps.append(
                _step(
                    "qbittorrent",
                    "configure_folders_and_categories",
                    qb_ok,
                    f"login={login_ok} paths={logged_in} user={qb_user}",
                )
            )

        sab_plugin = self._catalog.get("sabnzbd") if self._catalog.has("sabnzbd") else None
        sab_cfg = sab_plugin.config_dir if sab_plugin else self._settings.config_dir / "sabnzbd"
        sab_ini = read_sabnzbd_ini(sab_cfg)
        sab_key = get_application_api_key("sabnzbd", sab_cfg) or sab_ini.get("api_key") or sab_key
        sonarr_key = get_application_api_key("sonarr") or sonarr_key
        radarr_key = get_application_api_key("radarr") or radarr_key
        lidarr_key = get_application_api_key("lidarr") or lidarr_key
        qb_user, qb_pass = qbittorrent_credentials()
        shared = shared_admin_credentials()
        sab_user = sab_ini.get("username") or (shared[0] if shared else "")
        sab_pass = sab_ini.get("password") or (shared[1] if shared else "")
        downloader_register = self._downloaders_for_arr(sab_key=sab_key)

        roots = arr_root_folders(layout)
        if not self._skip_uninstalled(steps, "sonarr", "wire_clients_and_storage"):
            sonarr_client = SonarrClient(port=sonarr_port, api_key=sonarr_key)
            sonarr_root = all(sonarr_client.add_root_folder(str(path)) for path in roots["sonarr"])
            sonarr_dl = _register_download_clients(
                downloader_register,
                add_sab=lambda: sonarr_client.add_sabnzbd_client(
                    port=sab_port,
                    api_key=sab_key or "",
                    category="sonarr",
                    username=sab_user,
                    password=sab_pass,
                ),
                add_nzb=lambda: sonarr_client.add_nzbget_client(
                    port=nzb_port, username=nzb_user, password=nzb_pass, category="sonarr"
                ),
                add_qb=lambda: sonarr_client.add_qbittorrent_client(
                    port=qb_port, username=qb_user, password=qb_pass, category="sonarr"
                ),
            )
            sonarr_naming = sonarr_client.configure_naming_defaults()
            steps.append(
                _step(
                    "sonarr",
                    "wire_clients_and_storage",
                    sonarr_root and sonarr_dl,
                    f"roots={','.join(str(p) for p in roots['sonarr'])} clients={','.join(downloader_register) or 'none'} downloaders={sonarr_dl} naming={sonarr_naming}",
                )
            )

        if not self._skip_uninstalled(steps, "radarr", "wire_clients_and_storage"):
            radarr_client = RadarrClient(port=radarr_port, api_key=radarr_key)
            radarr_root = all(radarr_client.add_root_folder(str(path)) for path in roots["radarr"])
            radarr_dl = _register_download_clients(
                downloader_register,
                add_sab=lambda: radarr_client.add_sabnzbd_client(
                    port=sab_port,
                    api_key=sab_key or "",
                    category="radarr",
                    username=sab_user,
                    password=sab_pass,
                ),
                add_nzb=lambda: radarr_client.add_nzbget_client(
                    port=nzb_port, username=nzb_user, password=nzb_pass, category="radarr"
                ),
                add_qb=lambda: radarr_client.add_qbittorrent_client(
                    port=qb_port, username=qb_user, password=qb_pass, category="radarr"
                ),
            )
            radarr_naming = radarr_client.configure_naming_defaults()
            steps.append(
                _step(
                    "radarr",
                    "wire_clients_and_storage",
                    radarr_root and radarr_dl,
                    f"roots={','.join(str(p) for p in roots['radarr'])} clients={','.join(downloader_register) or 'none'} downloaders={radarr_dl} naming={radarr_naming}",
                )
            )

        if not self._skip_uninstalled(steps, "lidarr", "wire_clients_and_storage"):
            lidarr_client = ArrAppClient(
                port=lidarr_port,
                api_key=lidarr_key,
                api_prefix="/api/v1",
                category_field="musicCategory",
                label="Lidarr",
            )
            lidarr_ok = _wire_arr_app(
                lidarr_client,
                roots["lidarr"],
                sab_port=sab_port,
                sab_key=sab_key or "",
                sab_username=sab_user,
                sab_password=sab_pass,
                nzb_port=nzb_port,
                nzb_username=nzb_user,
                nzb_password=nzb_pass,
                qb_port=qb_port,
                qb_username=qb_user,
                qb_password=qb_pass,
                category="lidarr",
                register=downloader_register,
            )
            steps.append(_step("lidarr", "wire_clients_and_storage", lidarr_ok, str(layout.music)))

        if not self._skip_uninstalled(steps, "prowlarr", "sync_applications"):
            prowlarr_client = ProwlarrClient(port=prowlarr_port, api_key=prowlarr_key)
            syncs = []
            if self._installed("sonarr"):
                syncs.append(prowlarr_client.sync_sonarr(sonarr_url=sonarr_url, sonarr_api_key=sonarr_key or ""))
            if self._installed("radarr"):
                syncs.append(prowlarr_client.sync_radarr(radarr_url=radarr_url, radarr_api_key=radarr_key or ""))
            if self._installed("lidarr"):
                syncs.append(prowlarr_client.sync_lidarr(lidarr_url=lidarr_url, lidarr_api_key=lidarr_key or ""))
            if self._installed("flaresolverr"):
                flare_port = self._port("flaresolverr", 8191)
                syncs.append(prowlarr_client.add_flaresolverr(f"http://127.0.0.1:{flare_port}"))
            prowl_ok = all(syncs) if syncs else True
            steps.append(_step("prowlarr", "sync_applications", prowl_ok, "Prowlarr → Sonarr/Radarr/Lidarr/Flaresolverr"))

        if not self._skip_uninstalled(steps, "jellyfin", "configure_libraries_and_transcode"):
            jelly_client = JellyfinClient(port=jelly_port, api_key=jellyfin_key)
            jelly_ok = jelly_client.set_transcoding_temp_path(str(layout.transcode_jellyfin))
            for name, collection_type, path in jellyfin_libraries(layout):
                jelly_ok = jelly_client.add_media_library(name, collection_type, str(path)) and jelly_ok
            steps.append(_step("jellyfin", "configure_libraries_and_transcode", jelly_ok, str(layout.transcode_jellyfin)))

        if not self._skip_uninstalled(steps, "plex", "configure_libraries_and_transcode"):
            plex_config = self._catalog.get("plex").config_dir
            plex_client = PlexClient(port=plex_port, config_dir=plex_config)
            plex_ok = plex_client.set_transcoder_temp_directory(str(layout.transcode_plex))
            plex_ok = plex_client.add_library("TV", "show", str(layout.tv)) and plex_ok
            plex_ok = plex_client.add_library("Movies", "movie", str(layout.movies)) and plex_ok
            plex_ok = plex_client.add_library("Anime", "show", str(layout.anime)) and plex_ok
            plex_ok = plex_client.add_library("Music", "artist", str(layout.music)) and plex_ok
            steps.append(_step("plex", "configure_libraries_and_transcode", plex_ok, str(layout.transcode_plex)))

        if not self._skip_uninstalled(steps, "seerr", "connect_media_services"):
            seerr_client = SeerrClient(port=seerr_port, api_key=seerr_key)
            shared = shared_admin_credentials()
            email = admin_email()
            try:
                from core.auth import auth_manager

                email = email or auth_manager.email()
                seerr_user = auth_manager.username()
            except Exception:
                seerr_user = shared[0] if shared else "admin"
            seerr_pass = shared[1] if shared else ""
            setup_ok = True
            if email and seerr_pass:
                setup_ok = seerr_client.setup_local_admin(email, seerr_user, seerr_pass)
            media_servers = self._chosen_apps("jellyfin", "plex", selection_key="media_servers")
            arr_apps = self._chosen_apps("sonarr", "radarr", selection_key="arr_apps")
            links: list[bool] = []
            if "sonarr" in arr_apps:
                links.append(
                    seerr_client.connect_sonarr(
                        port=sonarr_port, api_key=sonarr_key or "", root_folder=str(layout.tv)
                    )
                )
            if "radarr" in arr_apps:
                links.append(
                    seerr_client.connect_radarr(
                        port=radarr_port, api_key=radarr_key or "", root_folder=str(layout.movies)
                    )
                )
            if "jellyfin" in media_servers:
                links.append(seerr_client.connect_jellyfin(port=jelly_port, api_key=jellyfin_key or ""))
            if "plex" in media_servers:
                links.append(seerr_client.connect_plex(port=plex_port))
            seerr_ok = setup_ok and (any(links) if links else True)
            detail = "Seerr local admin"
            if links:
                wired = []
                if "sonarr" in arr_apps:
                    wired.append("Sonarr")
                if "radarr" in arr_apps:
                    wired.append("Radarr")
                wired.extend(name.title() for name in media_servers)
                detail = "Seerr → " + "/".join(wired) if wired else detail
            steps.append(_step("seerr", "connect_media_services", seerr_ok, detail))

        if not self._skip_uninstalled(steps, "bazarr", "pair_libraries"):
            bazarr_client = BazarrClient(port=bazarr_port, api_key=bazarr_key)
            baz_ok = bazarr_client.pair_sonarr(sonarr_url, sonarr_key or "") and bazarr_client.pair_radarr(
                radarr_url, radarr_key or ""
            )
            steps.append(_step("bazarr", "pair_libraries", baz_ok, "Bazarr ↔ Sonarr/Radarr"))

        try:
            rec_path = write_recyclarr_config(
                self._catalog.get("recyclarr").config_dir if self._catalog.has("recyclarr") else self._settings.config_dir / "recyclarr",
                sonarr_url=sonarr_url,
                sonarr_key=sonarr_key or "",
                radarr_url=radarr_url,
                radarr_key=radarr_key or "",
            )
            steps.append(_step("recyclarr", "write_trash_config", True, str(rec_path)))
            rec_plugin = self._catalog.get("recyclarr") if self._catalog.has("recyclarr") else None
            if rec_plugin and rec_plugin.is_installed():
                result = run_sync()
                log_tail = (result.get("log") or "").strip().splitlines()
                detail = result.get("detail") or ""
                if log_tail:
                    detail = f"{detail} {log_tail[-1]}".strip()
                steps.append(_step("recyclarr", "sync_trash", bool(result.get("ok")), detail[:300]))
            else:
                steps.append(_step("recyclarr", "sync_trash", True, "not installed"))
        except Exception as exc:
            steps.append(_step("recyclarr", "write_trash_config", False, str(exc)))

        try:
            pro_path = write_profilarr_config(
                self._catalog.get("profilarr").config_dir if self._catalog.has("profilarr") else self._settings.config_dir / "profilarr",
                sonarr_url=sonarr_url,
                sonarr_key=sonarr_key or "",
                radarr_url=radarr_url,
                radarr_key=radarr_key or "",
                lidarr_url=lidarr_url if self._installed("lidarr") else "",
                lidarr_key=lidarr_key or "",
            )
            steps.append(_step("profilarr", "write_starter_config", True, str(pro_path)))
        except Exception as exc:
            steps.append(_step("profilarr", "write_starter_config", False, str(exc)))

        try:
            neu_path = write_neutarr_config(
                self._catalog.get("neutarr").config_dir if self._catalog.has("neutarr") else self._settings.config_dir / "neutarr",
                sonarr_url=sonarr_url,
                sonarr_key=sonarr_key or "",
                radarr_url=radarr_url,
                radarr_key=radarr_key or "",
                lidarr_url=lidarr_url if self._installed("lidarr") else "",
                lidarr_key=lidarr_key or "",
            )
            steps.append(_step("neutarr", "write_starter_config", True, str(neu_path)))
        except Exception as exc:
            steps.append(_step("neutarr", "write_starter_config", False, str(exc)))

        def _api_key(name: str) -> str | None:
            return get_application_api_key(name)

        def _config_dir(name: str) -> Path:
            if self._catalog.has(name):
                return self._catalog.get(name).config_dir
            return self._settings.config_dir / name

        steps.extend(
            apply_shared_local_logins(
                installed=self._installed,
                port_for=self._port,
                api_key_for=_api_key,
                config_dir_for=_config_dir,
            )
        )

        return {"timestamp": time.time(), "status": "completed", "steps": steps, "layout": layout.as_dict()}


def _register_download_clients(
    register: list[str],
    *,
    add_sab,
    add_nzb,
    add_qb,
) -> bool:
    results: list[bool] = []
    if "sabnzbd" in register:
        results.append(bool(add_sab()))
    if "nzbget" in register:
        results.append(bool(add_nzb()))
    if "qbittorrent" in register:
        results.append(bool(add_qb()))
    return all(results) if results else True


def _wire_arr_app(
    client: ArrAppClient,
    roots,
    *,
    sab_port: int,
    sab_key: str,
    nzb_port: int,
    qb_port: int,
    category: str,
    sab_username: str = "",
    sab_password: str = "",
    qb_username: str = "admin",
    qb_password: str = "adminadmin",
    nzb_username: str = "nzbget",
    nzb_password: str = "tegbzn6789",
    register: list[str] | None = None,
) -> bool:
    root_ok = all(client.add_root_folder(str(path)) for path in roots)
    dl_ok = _register_download_clients(
        register or [],
        add_sab=lambda: client.add_sabnzbd_client(
            port=sab_port,
            api_key=sab_key,
            category=category,
            username=sab_username,
            password=sab_password,
        ),
        add_nzb=lambda: client.add_nzbget_client(
            port=nzb_port, username=nzb_username, password=nzb_password, category=category
        ),
        add_qb=lambda: client.add_qbittorrent_client(
            port=qb_port, username=qb_username, password=qb_password, category=category
        ),
    )
    return root_ok and dl_ok


def _step(target: str, action: str, ok: bool, detail: str) -> dict[str, Any]:
    return {
        "target": target,
        "action": action,
        "status": "success" if ok else "warning",
        "detail": detail,
    }


integration_engine = IntegrationEngine()
