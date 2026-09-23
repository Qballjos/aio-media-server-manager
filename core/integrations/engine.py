"""
core/integrations/engine.py — Automatic Integration Engine Orchestrator.

Wires download clients, *Arr apps, Seerr, Bazarr, and optimization-tool configs.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from applications.catalog import ApplicationCatalog
from core.crypto import mask_secret
from core.integrations.arr_app import ArrAppClient
from core.integrations.bazarr import BazarrClient
from core.integrations.credentials import get_application_api_key
from core.integrations.hooks import (
    write_neutarr_config,
    write_profilarr_config,
    write_recyclarr_config,
    write_unpackerr_config,
)
from core.integrations.jellyfin import JellyfinClient
from core.integrations.nzbget import NZBGetClient
from core.integrations.plex import PlexClient
from core.integrations.prowlarr import ProwlarrClient
from core.integrations.qbittorrent import QBittorrentClient, qbittorrent_credentials
from core.integrations.radarr import RadarrClient
from core.integrations.sabnzbd import SABnzbdClient
from core.integrations.seerr import SeerrClient
from core.integrations.sonarr import SonarrClient
from core.library_layout import (
    DOWNLOAD_CATEGORIES,
    LIBRARY_FOLDERS,
    arr_root_folders,
    jellyfin_libraries,
)
from core.settings import settings
from core.storage import StorageManager
from core.supervisor import ProcessSupervisor

logger = logging.getLogger(__name__)

WIRE_AFTER_INSTALL = frozenset({"sonarr", "radarr", "lidarr", "prowlarr", "flaresolverr"})

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
    "unpackerr",
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

    def _skip_uninstalled(self, steps: list[dict[str, Any]], name: str, action: str) -> bool:
        if self._installed(name):
            return False
        steps.append(
            {
                "target": name,
                "action": action,
                "status": "skipped",
                "detail": "not installed",
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

        sab_key = get_application_api_key("sabnzbd")
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

        if not self._skip_uninstalled(steps, "sabnzbd", "configure_folders_and_categories"):
            sab_client = SABnzbdClient(port=sab_port, api_key=sab_key)
            sab_ok = sab_client.set_folders(str(layout.complete), str(layout.incomplete))
            for category in DOWNLOAD_CATEGORIES:
                sab_ok = sab_client.add_category(category.name, dir_path=category.library) and sab_ok
            steps.append(_step("sabnzbd", "configure_folders_and_categories", sab_ok, str(layout.complete)))

        if not self._skip_uninstalled(steps, "nzbget", "configure_folders_and_categories"):
            nzb = NZBGetClient(port=nzb_port)
            nzb_ok = nzb.set_download_dirs(str(layout.complete), str(layout.incomplete))
            for category in DOWNLOAD_CATEGORIES:
                nzb_ok = nzb.add_category(category.name, dest_dir=str(layout.complete_path(category.library))) and nzb_ok
            steps.append(_step("nzbget", "configure_folders_and_categories", nzb_ok, str(layout.complete)))

        if not self._skip_uninstalled(steps, "qbittorrent", "configure_folders_and_categories"):
            qb_client = QBittorrentClient(port=qb_port)
            qb_client.login()
            qb_ok = qb_client.set_download_paths(str(layout.torrents), str(layout.incomplete))
            for category in DOWNLOAD_CATEGORIES:
                qb_ok = qb_client.create_category(
                    category.name,
                    save_path=str(layout.torrent_path(category.library)),
                ) and qb_ok
            steps.append(_step("qbittorrent", "configure_folders_and_categories", qb_ok, str(layout.torrents)))

        roots = arr_root_folders(layout)
        if not self._skip_uninstalled(steps, "sonarr", "wire_clients_and_storage"):
            sonarr_client = SonarrClient(port=sonarr_port, api_key=sonarr_key)
            sonarr_root = all(sonarr_client.add_root_folder(str(path)) for path in roots["sonarr"])
            sonarr_dl = any(
                [
                    sonarr_client.add_sabnzbd_client(port=sab_port, api_key=sab_key or "", category="sonarr"),
                    sonarr_client.add_nzbget_client(port=nzb_port, category="sonarr"),
                    sonarr_client.add_qbittorrent_client(
                        port=qb_port, username=qb_user, password=qb_pass, category="sonarr"
                    ),
                ]
            )
            sonarr_naming = sonarr_client.configure_naming_defaults()
            steps.append(
                _step(
                    "sonarr",
                    "wire_clients_and_storage",
                    sonarr_root and sonarr_dl,
                    f"roots={','.join(str(p) for p in roots['sonarr'])} downloaders={sonarr_dl} naming={sonarr_naming}",
                )
            )

        if not self._skip_uninstalled(steps, "radarr", "wire_clients_and_storage"):
            radarr_client = RadarrClient(port=radarr_port, api_key=radarr_key)
            radarr_root = all(radarr_client.add_root_folder(str(path)) for path in roots["radarr"])
            radarr_dl = any(
                [
                    radarr_client.add_sabnzbd_client(port=sab_port, api_key=sab_key or "", category="radarr"),
                    radarr_client.add_nzbget_client(port=nzb_port, category="radarr"),
                    radarr_client.add_qbittorrent_client(
                        port=qb_port, username=qb_user, password=qb_pass, category="radarr"
                    ),
                ]
            )
            radarr_naming = radarr_client.configure_naming_defaults()
            steps.append(
                _step(
                    "radarr",
                    "wire_clients_and_storage",
                    radarr_root and radarr_dl,
                    f"roots={','.join(str(p) for p in roots['radarr'])} downloaders={radarr_dl} naming={radarr_naming}",
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
                nzb_port=nzb_port,
                qb_port=qb_port,
                qb_username=qb_user,
                qb_password=qb_pass,
                category="lidarr",
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
            seerr_ok = any(
                [
                    seerr_client.connect_sonarr(port=sonarr_port, api_key=sonarr_key or "", root_folder=str(layout.tv)),
                    seerr_client.connect_radarr(
                        port=radarr_port, api_key=radarr_key or "", root_folder=str(layout.movies)
                    ),
                    seerr_client.connect_jellyfin(port=jelly_port, api_key=jellyfin_key or ""),
                    seerr_client.connect_plex(port=plex_port),
                ]
            )
            steps.append(_step("seerr", "connect_media_services", seerr_ok, "Seerr → Sonarr/Radarr/Jellyfin/Plex"))

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
            steps.append(_step("recyclarr", "write_starter_config", True, str(rec_path)))
        except Exception as exc:
            steps.append(_step("recyclarr", "write_starter_config", False, str(exc)))

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

        try:
            unpack_dir = (
                self._catalog.get("unpackerr").config_dir
                if self._catalog.has("unpackerr")
                else self._settings.config_dir / "unpackerr"
            )
            unpack_path = write_unpackerr_config(
                unpack_dir,
                complete_paths=[str(layout.complete_path(cat.library)) for cat in DOWNLOAD_CATEGORIES],
                sonarr_url=sonarr_url,
                sonarr_key=sonarr_key or "",
                radarr_url=radarr_url,
                radarr_key=radarr_key or "",
                lidarr_url=lidarr_url,
                lidarr_key=lidarr_key or "",
            )
            steps.append(_step("unpackerr", "write_starter_config", True, str(unpack_path)))
        except Exception as exc:
            steps.append(_step("unpackerr", "write_starter_config", False, str(exc)))

        return {"timestamp": time.time(), "status": "completed", "steps": steps, "layout": layout.as_dict()}


def _wire_arr_app(
    client: ArrAppClient,
    roots,
    *,
    sab_port: int,
    sab_key: str,
    nzb_port: int,
    qb_port: int,
    category: str,
    qb_username: str = "admin",
    qb_password: str = "adminadmin",
) -> bool:
    root_ok = all(client.add_root_folder(str(path)) for path in roots)
    dl_ok = any(
        [
            client.add_sabnzbd_client(port=sab_port, api_key=sab_key, category=category),
            client.add_nzbget_client(port=nzb_port, category=category),
            client.add_qbittorrent_client(
                port=qb_port, username=qb_username, password=qb_password, category=category
            ),
        ]
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
