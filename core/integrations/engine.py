"""
core/integrations/engine.py — Automatic Integration Engine Orchestrator.

Orchestrates automatic inter-application wiring across the MVP stack:
- Category registration in download clients (SABnzbd, qBittorrent)
- Download client and root folder registration in Sonarr and Radarr
- Automated indexer sync between Prowlarr and Sonarr/Radarr
- Request system linking in Seerr for Sonarr, Radarr, and Jellyfin
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from applications.catalog import ApplicationCatalog
from core.crypto import mask_secret
from core.integrations.credentials import get_application_api_key
from core.integrations.prowlarr import ProwlarrClient
from core.integrations.qbittorrent import QBittorrentClient
from core.integrations.radarr import RadarrClient
from core.integrations.sabnzbd import SABnzbdClient
from core.integrations.seerr import SeerrClient
from core.integrations.sonarr import SonarrClient
from core.settings import settings
from core.supervisor import ProcessSupervisor

logger = logging.getLogger(__name__)


class IntegrationEngine:
    def __init__(self, cfg=None):
        self._settings = cfg or settings
        self._catalog = ApplicationCatalog(app_settings=self._settings)

    def _is_app_running(self, name: str) -> bool:
        supervisor = ProcessSupervisor.get()
        return supervisor.status(name).value == "running"

    def get_wiring_status(self) -> dict[str, Any]:
        """
        Inspect current applications, credential availability, and wiring status.
        """
        apps = ["sabnzbd", "qbittorrent", "sonarr", "radarr", "prowlarr", "jellyfin", "seerr"]
        report: dict[str, Any] = {}

        for app_name in apps:
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
        """
        Execute automatic inter-application integration wiring.
        """
        steps: list[dict[str, Any]] = []

        sab_key = get_application_api_key("sabnzbd")
        sonarr_key = get_application_api_key("sonarr")
        radarr_key = get_application_api_key("radarr")
        prowlarr_key = get_application_api_key("prowlarr")
        jellyfin_key = get_application_api_key("jellyfin")
        seerr_key = get_application_api_key("seerr")

        # 1. SABnzbd categories
        sab_client = SABnzbdClient(port=8080, api_key=sab_key)
        sab_ok_tv = sab_client.add_category("sonarr", dir_path="tv")
        sab_ok_movies = sab_client.add_category("radarr", dir_path="movies")
        steps.append({
            "target": "sabnzbd",
            "action": "configure_categories",
            "status": "success" if (sab_ok_tv and sab_ok_movies) else "warning",
            "detail": "Configured categories 'sonarr' (tv) and 'radarr' (movies) in SABnzbd",
        })

        # 2. qBittorrent categories
        qb_client = QBittorrentClient(port=8085)
        qb_client.login()
        media_root = str(self._settings.media_dir)
        qb_ok_tv = qb_client.create_category("sonarr", save_path=f"{media_root}/downloads/torrents/tv")
        qb_ok_movies = qb_client.create_category("radarr", save_path=f"{media_root}/downloads/torrents/movies")
        steps.append({
            "target": "qbittorrent",
            "action": "configure_categories",
            "status": "success" if (qb_ok_tv and qb_ok_movies) else "warning",
            "detail": "Configured categories 'sonarr' and 'radarr' in qBittorrent",
        })

        # 3. Sonarr integration
        sonarr_client = SonarrClient(port=8989, api_key=sonarr_key)
        sonarr_root = sonarr_client.add_root_folder(f"{media_root}/tv")
        sonarr_sab = sonarr_client.add_sabnzbd_client(port=8080, api_key=sab_key or "", category="sonarr")
        sonarr_qb = sonarr_client.add_qbittorrent_client(port=8085, category="sonarr")
        sonarr_naming = sonarr_client.configure_naming_defaults()
        steps.append({
            "target": "sonarr",
            "action": "wire_clients_and_storage",
            "status": "success" if (sonarr_root and (sonarr_sab or sonarr_qb)) else "warning",
            "detail": f"Sonarr root folder ({sonarr_root}), SABnzbd ({sonarr_sab}), qBittorrent ({sonarr_qb}), Naming ({sonarr_naming})",
        })

        # 4. Radarr integration
        radarr_client = RadarrClient(port=7878, api_key=radarr_key)
        radarr_root = radarr_client.add_root_folder(f"{media_root}/movies")
        radarr_sab = radarr_client.add_sabnzbd_client(port=8080, api_key=sab_key or "", category="radarr")
        radarr_qb = radarr_client.add_qbittorrent_client(port=8085, category="radarr")
        radarr_naming = radarr_client.configure_naming_defaults()
        steps.append({
            "target": "radarr",
            "action": "wire_clients_and_storage",
            "status": "success" if (radarr_root and (radarr_sab or radarr_qb)) else "warning",
            "detail": f"Radarr root folder ({radarr_root}), SABnzbd ({radarr_sab}), qBittorrent ({radarr_qb}), Naming ({radarr_naming})",
        })

        # 5. Prowlarr sync
        prowlarr_client = ProwlarrClient(port=9696, api_key=prowlarr_key)
        prowl_sonarr = prowlarr_client.sync_sonarr(
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key=sonarr_key or "",
        )
        prowl_radarr = prowlarr_client.sync_radarr(
            radarr_url="http://127.0.0.1:7878",
            radarr_api_key=radarr_key or "",
        )
        steps.append({
            "target": "prowlarr",
            "action": "sync_applications",
            "status": "success" if (prowl_sonarr and prowl_radarr) else "warning",
            "detail": f"Prowlarr -> Sonarr sync ({prowl_sonarr}), Prowlarr -> Radarr sync ({prowl_radarr})",
        })

        # 6. Seerr linking
        seerr_client = SeerrClient(port=5055, api_key=seerr_key)
        seerr_sonarr = seerr_client.connect_sonarr(port=8989, api_key=sonarr_key or "", root_folder=f"{media_root}/tv")
        seerr_radarr = seerr_client.connect_radarr(port=7878, api_key=radarr_key or "", root_folder=f"{media_root}/movies")
        seerr_jelly = seerr_client.connect_jellyfin(port=8096, api_key=jellyfin_key or "")
        steps.append({
            "target": "seerr",
            "action": "connect_media_services",
            "status": "success" if (seerr_sonarr or seerr_radarr or seerr_jelly) else "warning",
            "detail": f"Seerr -> Sonarr ({seerr_sonarr}), Seerr -> Radarr ({seerr_radarr}), Seerr -> Jellyfin ({seerr_jelly})",
        })

        return {
            "timestamp": time.time(),
            "status": "completed",
            "steps": steps,
        }


# Global singleton engine
integration_engine = IntegrationEngine()
