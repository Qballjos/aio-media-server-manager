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
from core.integrations.bazarr import BazarrClient
from core.integrations.credentials import get_application_api_key
from core.integrations.hooks import (
    write_neutarr_config,
    write_profilarr_config,
    write_recyclarr_config,
)
from core.integrations.nzbget import NZBGetClient
from core.integrations.prowlarr import ProwlarrClient
from core.integrations.qbittorrent import QBittorrentClient
from core.integrations.radarr import RadarrClient
from core.integrations.sabnzbd import SABnzbdClient
from core.integrations.seerr import SeerrClient
from core.integrations.sonarr import SonarrClient
from core.settings import settings
from core.supervisor import ProcessSupervisor

logger = logging.getLogger(__name__)

_STATUS_APPS = (
    "sabnzbd",
    "nzbget",
    "qbittorrent",
    "sonarr",
    "radarr",
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
        media_root = str(self._settings.media_dir)
        sab_port = self._port("sabnzbd", 8085)
        nzb_port = self._port("nzbget", 6789)
        qb_port = self._port("qbittorrent", 8081)
        sonarr_port = self._port("sonarr", 8989)
        radarr_port = self._port("radarr", 7878)
        prowlarr_port = self._port("prowlarr", 9696)
        jelly_port = self._port("jellyfin", 8096)
        plex_port = self._port("plex", 32400)
        seerr_port = self._port("seerr", 5055)
        bazarr_port = self._port("bazarr", 6767)

        sab_key = get_application_api_key("sabnzbd")
        sonarr_key = get_application_api_key("sonarr")
        radarr_key = get_application_api_key("radarr")
        prowlarr_key = get_application_api_key("prowlarr")
        jellyfin_key = get_application_api_key("jellyfin")
        seerr_key = get_application_api_key("seerr")
        bazarr_key = get_application_api_key("bazarr")

        sonarr_url = f"http://127.0.0.1:{sonarr_port}"
        radarr_url = f"http://127.0.0.1:{radarr_port}"

        sab_client = SABnzbdClient(port=sab_port, api_key=sab_key)
        sab_ok = sab_client.add_category("sonarr", dir_path="tv") and sab_client.add_category(
            "radarr", dir_path="movies"
        )
        steps.append(_step("sabnzbd", "configure_categories", sab_ok, "SABnzbd categories sonarr/radarr"))

        if self._catalog.has("nzbget"):
            nzb = NZBGetClient(port=nzb_port)
            nzb_ok = nzb.add_category("sonarr", dest_dir="tv") and nzb.add_category("radarr", dest_dir="movies")
            steps.append(_step("nzbget", "configure_categories", nzb_ok, "NZBGet categories sonarr/radarr"))

        qb_client = QBittorrentClient(port=qb_port)
        qb_client.login()
        qb_ok = qb_client.create_category(
            "sonarr", save_path=f"{media_root}/downloads/torrents/tv"
        ) and qb_client.create_category(
            "radarr", save_path=f"{media_root}/downloads/torrents/movies"
        )
        steps.append(_step("qbittorrent", "configure_categories", qb_ok, "qBittorrent categories sonarr/radarr"))

        sonarr_client = SonarrClient(port=sonarr_port, api_key=sonarr_key)
        sonarr_root = sonarr_client.add_root_folder(f"{media_root}/tv")
        sonarr_dl = any(
            [
                sonarr_client.add_sabnzbd_client(port=sab_port, api_key=sab_key or "", category="sonarr"),
                sonarr_client.add_nzbget_client(port=nzb_port, category="sonarr"),
                sonarr_client.add_qbittorrent_client(port=qb_port, category="sonarr"),
            ]
        )
        sonarr_naming = sonarr_client.configure_naming_defaults()
        steps.append(
            _step(
                "sonarr",
                "wire_clients_and_storage",
                sonarr_root and sonarr_dl,
                f"root={sonarr_root} downloaders={sonarr_dl} naming={sonarr_naming}",
            )
        )

        radarr_client = RadarrClient(port=radarr_port, api_key=radarr_key)
        radarr_root = radarr_client.add_root_folder(f"{media_root}/movies")
        radarr_dl = any(
            [
                radarr_client.add_sabnzbd_client(port=sab_port, api_key=sab_key or "", category="radarr"),
                radarr_client.add_nzbget_client(port=nzb_port, category="radarr"),
                radarr_client.add_qbittorrent_client(port=qb_port, category="radarr"),
            ]
        )
        radarr_naming = radarr_client.configure_naming_defaults()
        steps.append(
            _step(
                "radarr",
                "wire_clients_and_storage",
                radarr_root and radarr_dl,
                f"root={radarr_root} downloaders={radarr_dl} naming={radarr_naming}",
            )
        )

        prowlarr_client = ProwlarrClient(port=prowlarr_port, api_key=prowlarr_key)
        prowl_ok = prowlarr_client.sync_sonarr(
            sonarr_url=sonarr_url, sonarr_api_key=sonarr_key or ""
        ) and prowlarr_client.sync_radarr(radarr_url=radarr_url, radarr_api_key=radarr_key or "")
        steps.append(_step("prowlarr", "sync_applications", prowl_ok, "Prowlarr → Sonarr/Radarr"))

        seerr_client = SeerrClient(port=seerr_port, api_key=seerr_key)
        seerr_ok = any(
            [
                seerr_client.connect_sonarr(port=sonarr_port, api_key=sonarr_key or "", root_folder=f"{media_root}/tv"),
                seerr_client.connect_radarr(
                    port=radarr_port, api_key=radarr_key or "", root_folder=f"{media_root}/movies"
                ),
                seerr_client.connect_jellyfin(port=jelly_port, api_key=jellyfin_key or ""),
                seerr_client.connect_plex(port=plex_port),
            ]
        )
        steps.append(_step("seerr", "connect_media_services", seerr_ok, "Seerr → Sonarr/Radarr/Jellyfin/Plex"))

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
            )
            steps.append(_step("neutarr", "write_starter_config", True, str(neu_path)))
        except Exception as exc:
            steps.append(_step("neutarr", "write_starter_config", False, str(exc)))

        return {"timestamp": time.time(), "status": "completed", "steps": steps}


def _step(target: str, action: str, ok: bool, detail: str) -> dict[str, Any]:
    return {
        "target": target,
        "action": action,
        "status": "success" if ok else "warning",
        "detail": detail,
    }


integration_engine = IntegrationEngine()
