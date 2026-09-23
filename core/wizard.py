"""
core/wizard.py — Guided 12-Step First-Run Setup Wizard Engine.

Implements the 12-step guided setup flow defined in PROMPT.md §26:
1. Welcome
2. Platform detection
3. Storage configuration (with hardlink check)
4. User/permissions (PUID/PGID)
5. Download clients (SABnzbd, qBittorrent)
6. VPN (None / PrivadoVPN preview)
7. *Arr (Prowlarr, Sonarr, Radarr, Lidarr)
8. Media server (Jellyfin and/or Plex)
9. Request system (Seerr)
10. Recommended tools (Bazarr, Flaresolverr, Grimmory, Shelfmark, ...)
11. Review
12. Install & automatic wiring
"""

from __future__ import annotations

import json
import logging
import os
import platform
from pathlib import Path
from typing import Any, Optional

from applications.catalog import ApplicationCatalog
from applications.manifest import help_url_for
from core.crypto import secret_store
from core.integrations.engine import integration_engine
from core.library_layout import LibraryLayout
from core.settings import settings
from core.storage import StorageManager

logger = logging.getLogger(__name__)

WIZARD_STEPS = [
    {"id": 1, "key": "welcome", "title": "Welcome"},
    {"id": 2, "key": "platform", "title": "Platform Detection"},
    {"id": 3, "key": "storage", "title": "Storage Configuration"},
    {"id": 4, "key": "permissions", "title": "User & Permissions"},
    {"id": 5, "key": "download_clients", "title": "Download Clients"},
    {"id": 6, "key": "vpn", "title": "VPN Protection"},
    {"id": 7, "key": "arr_stack", "title": "*Arr Automation"},
    {"id": 8, "key": "media_server", "title": "Media Server"},
    {"id": 9, "key": "request_system", "title": "Request System"},
    {"id": 10, "key": "recommended_tools", "title": "Recommended Tools Preview"},
    {"id": 11, "key": "review", "title": "Review & Confirm"},
    {"id": 12, "key": "install", "title": "Install & Automatic Configuration"},
]


class WizardEngine:
    def __init__(self, state_file: Optional[Path] = None, cfg=None):
        self._settings = cfg or settings
        self.state_file = state_file or (self._settings.config_dir / "wizard_state.json")
        self._state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Could not read wizard state: %s", e)
        # Default state
        return {
            "current_step": 1,
            "completed": False,
            "selections": {
                "media_dir": str(self._settings.media_dir),
                "download_dir": str(self._settings.download_dir),
                "config_dir": str(self._settings.config_dir),
                "puid": int(self._settings.puid),
                "pgid": int(self._settings.pgid),
                "download_clients": ["sabnzbd", "qbittorrent"],
                "vpn_provider": "none",
                "arr_apps": ["prowlarr", "sonarr", "radarr"],
                "media_server": "jellyfin",
                "media_servers": ["jellyfin"],
                "request_system": "seerr",
                "preferred_download_client": "qbittorrent",
                "qbittorrent_username": "admin",
                "qbittorrent_password": "",
                "vpn_config_path": "",
                "vpn_protocol": "wireguard",
                "vpn_enforce": False,
                "plex_claim": "",
                "recommended_preview": ["bazarr", "flaresolverr"],
            },
        }

    def _save_state(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        except OSError as e:
            logger.debug("Could not write wizard state to %s (in-memory state maintained): %s", self.state_file, e)

    def is_completed(self) -> bool:
        return bool(self._state.get("completed", False))

    def skip(self) -> dict[str, Any]:
        self._state["completed"] = True
        self._state["current_step"] = 12
        self._save_state()
        return self.get_status()

    def _annotate_options(self, options: list[dict[str, Any]]) -> list[dict[str, Any]]:
        catalog = ApplicationCatalog(app_settings=self._settings)
        annotated = []
        for option in options:
            item = dict(option)
            name = item.get("id") or ""
            if catalog.has(name):
                plugin = catalog.get(name)
                item["help_url"] = help_url_for(
                    plugin.name, plugin.manifest.github_repo, plugin.manifest.upstream_url
                )
                item["display_name"] = plugin.manifest.display_name
            annotated.append(item)
        return annotated

    def get_status(self) -> dict[str, Any]:
        selections = dict(self._state.get("selections", {}))
        selections.pop("qbittorrent_password", None)
        return {
            "current_step": self._state.get("current_step", 1),
            "completed": self.is_completed(),
            "steps": WIZARD_STEPS,
            "selections": selections,
        }

    def get_step_data(self, step_id: int) -> dict[str, Any]:
        """Provide context & metadata for a given wizard step."""
        selections = self._state.get("selections", {})

        if step_id == 1:
            return {
                "step": 1,
                "title": "Welcome to AIO Media Server Manager",
                "description": "All-in-One supervisor and manager for the *Arr ecosystem, download clients, and media servers without container overhead.",
            }

        if step_id == 2:
            return {
                "step": 2,
                "platform": {
                    "system": platform.system(),
                    "release": platform.release(),
                    "machine": platform.machine(),
                    "python_version": platform.python_version(),
                    "is_container": Path("/.dockerenv").exists() or Path("/run/.containerenv").exists(),
                },
            }

        if step_id == 3:
            mgr = StorageManager(self._settings)
            info = mgr.validate_all()
            dl_info = info.get("download_dir")
            hardlinks = dl_info.hardlinks_supported if (dl_info and dl_info.hardlinks_supported is not None) else True
            return {
                "step": 3,
                "media_dir": selections.get("media_dir"),
                "download_dir": selections.get("download_dir"),
                "config_dir": selections.get("config_dir"),
                "hardlink_supported": hardlinks,
                "hardlink_message": (
                    "Hardlinks supported between download and media directories."
                    if hardlinks else
                    "Hardlinks not supported. Keep downloads and media on the same host "
                    "filesystem (and the same btrfs subvolume), mounted as one /data parent."
                ),
                "layout": LibraryLayout.from_settings(self._settings).as_dict(),
            }

        if step_id == 4:
            return {
                "step": 4,
                "puid": selections.get("puid", self._settings.puid),
                "pgid": selections.get("pgid", self._settings.pgid),
                "current_uid": self._settings.puid,
                "current_gid": self._settings.pgid,
            }

        if step_id == 5:
            return {
                "step": 5,
                "options": self._annotate_options(
                    [
                        {"id": "sabnzbd", "name": "SABnzbd (Usenet)", "recommended": True},
                        {"id": "nzbget", "name": "NZBGet (Usenet)", "recommended": False},
                        {"id": "qbittorrent", "name": "qBittorrent (BitTorrent)", "recommended": True},
                    ]
                ),
                "selected": selections.get("download_clients", []),
                "preferred_download_client": selections.get("preferred_download_client", "qbittorrent"),
                "qbittorrent_username": selections.get("qbittorrent_username", "admin"),
                "has_qbittorrent_password": bool(selections.get("qbittorrent_password")),
            }

        if step_id == 6:
            return {
                "step": 6,
                "options": [
                    {"id": "none", "name": "None / Direct Connection", "recommended": True},
                    {"id": "privadovpn", "name": "PrivadoVPN (Network Namespace Isolation)"},
                    {"id": "custom", "name": "Custom WireGuard / OpenVPN config"},
                ],
                "selected": selections.get("vpn_provider", "none"),
                "vpn_config_path": selections.get("vpn_config_path", ""),
                "vpn_protocol": selections.get("vpn_protocol", "wireguard"),
                "vpn_enforce": bool(selections.get("vpn_enforce", False)),
            }

        if step_id == 7:
            return {
                "step": 7,
                "options": self._annotate_options(
                    [
                        {"id": "prowlarr", "name": "Prowlarr (Indexer Manager)", "recommended": True},
                        {"id": "sonarr", "name": "Sonarr (TV Automation)", "recommended": True},
                        {"id": "radarr", "name": "Radarr (Movie Automation)", "recommended": True},
                        {"id": "lidarr", "name": "Lidarr (Music Automation)", "recommended": False},
                    ]
                ),
                "selected": selections.get("arr_apps", []),
            }

        if step_id == 8:
            return {
                "step": 8,
                "options": self._annotate_options(
                    [
                        {"id": "jellyfin", "name": "Jellyfin (Open Source Media Server)", "recommended": True},
                        {"id": "plex", "name": "Plex Media Server (can share the same library as Jellyfin)"},
                    ]
                ),
                "selected": selections.get("media_servers")
                or ([selections["media_server"]] if selections.get("media_server") else ["jellyfin"]),
                "plex_claim": selections.get("plex_claim", ""),
            }

        if step_id == 9:
            return {
                "step": 9,
                "options": self._annotate_options(
                    [
                        {"id": "seerr", "name": "Seerr (Media Request Management)", "recommended": True},
                    ]
                ),
                "selected": selections.get("request_system", "seerr"),
            }

        if step_id == 10:
            return {
                "step": 10,
                "options": self._annotate_options(
                    [
                        {"id": "bazarr", "name": "Bazarr (Subtitles)"},
                        {"id": "recyclarr", "name": "Recyclarr (TRaSH Guides Sync)"},
                        {"id": "profilarr", "name": "Profilarr (Profile Management)"},
                        {"id": "neutarr", "name": "NeutArr (Automation Optimizer)"},
                        {"id": "flaresolverr", "name": "Flaresolverr (Cloudflare bypass for indexers)"},
                        {"id": "grimmory", "name": "Grimmory (ebooks, comics, audiobooks)"},
                        {"id": "shelfmark", "name": "Shelfmark (book search and requests)"},
                    ]
                ),
                "selected": selections.get("recommended_preview", ["bazarr", "flaresolverr"]),
            }

        if step_id == 11:
            return {
                "step": 11,
                "summary": selections,
            }

        return {
            "step": 12,
            "status": "ready_to_install",
            "selections": selections,
        }

    def update_step_selections(self, step_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Validate and record choices for a wizard step, advancing to the next."""
        selections = self._state.setdefault("selections", {})

        if step_id == 3:
            if "media_dir" in data:
                selections["media_dir"] = data["media_dir"]
            if "download_dir" in data:
                selections["download_dir"] = data["download_dir"]
            if "config_dir" in data:
                selections["config_dir"] = data["config_dir"]
        elif step_id == 4:
            if "puid" in data:
                selections["puid"] = int(data["puid"])
            if "pgid" in data:
                selections["pgid"] = int(data["pgid"])
        elif step_id == 5:
            selections["download_clients"] = data.get("download_clients", selections.get("download_clients", []))
            clients = selections.get("download_clients") or []
            selections["preferred_download_client"] = clients[0] if clients else "qbittorrent"
            if "qbittorrent_username" in data:
                selections["qbittorrent_username"] = data["qbittorrent_username"]
            if data.get("qbittorrent_password"):
                selections["qbittorrent_password"] = data["qbittorrent_password"]
        elif step_id == 6:
            selections["vpn_provider"] = data.get("vpn_provider", "none")
            if "vpn_config_path" in data:
                selections["vpn_config_path"] = data["vpn_config_path"]
            if "vpn_protocol" in data:
                selections["vpn_protocol"] = data["vpn_protocol"]
            if "vpn_enforce" in data:
                selections["vpn_enforce"] = bool(data["vpn_enforce"])
        elif step_id == 7:
            selections["arr_apps"] = data.get("arr_apps", selections.get("arr_apps", []))
        elif step_id == 8:
            if "media_servers" in data:
                servers = [name for name in data.get("media_servers", []) if name and name != "none"]
                selections["media_servers"] = servers
                selections["media_server"] = servers[0] if servers else "none"
            else:
                selections["media_server"] = data.get("media_server", "jellyfin")
                val = selections["media_server"]
                selections["media_servers"] = [val] if val and val != "none" else []
            if "plex_claim" in data:
                selections["plex_claim"] = data["plex_claim"]
        elif step_id == 9:
            selections["request_system"] = data.get("request_system", "seerr")
        elif step_id == 10:
            selections["recommended_preview"] = data.get(
                "recommended_preview",
                selections.get("recommended_preview", ["bazarr", "flaresolverr"]),
            )

        # Advance step
        if step_id < 12:
            self._state["current_step"] = max(self._state.get("current_step", 1), step_id + 1)
        self._save_state()

        return self.get_status()

    def _target_apps(self) -> list[str]:
        selections = self._state.get("selections", {})
        catalog = ApplicationCatalog(app_settings=self._settings)
        target: set[str] = set(selections.get("download_clients", []))
        target.update(selections.get("arr_apps", []))
        target.update(selections.get("recommended_preview", []))
        media_servers = selections.get("media_servers")
        if media_servers:
            target.update(media_servers)
        elif selections.get("media_server") and selections["media_server"] != "none":
            target.add(selections["media_server"])
        if selections.get("request_system") and selections["request_system"] != "none":
            target.add(selections["request_system"])
        try:
            ordered = catalog.resolve_install_order(list(target))
        except Exception:
            ordered = sorted(target)
        return [name for name in ordered if catalog.has(name)]

    def apply_initial_settings(self) -> None:
        """Persist path/VPN/credential choices from the wizard into runtime settings."""
        selections = self._state.get("selections", {})
        cfg = self._settings
        if selections.get("media_dir"):
            cfg.media_dir = Path(selections["media_dir"]).expanduser().resolve()
        if selections.get("download_dir"):
            cfg.download_dir = Path(selections["download_dir"]).expanduser().resolve()
        if selections.get("config_dir"):
            cfg.config_dir = Path(selections["config_dir"]).expanduser().resolve()
        if selections.get("puid"):
            cfg.puid = int(selections["puid"])
        if selections.get("pgid"):
            cfg.pgid = int(selections["pgid"])

        vpn_provider = selections.get("vpn_provider") or "none"
        if vpn_provider != "none":
            cfg.vpn_enabled = True
            cfg.vpn_provider = "privadovpn" if vpn_provider == "privadovpn" else vpn_provider
            cfg.vpn_protocol = selections.get("vpn_protocol") or "wireguard"
            cfg.vpn_enforce = bool(selections.get("vpn_enforce"))
            if selections.get("vpn_config_path"):
                cfg.vpn_config_path = Path(selections["vpn_config_path"]).expanduser().resolve()
        else:
            cfg.vpn_enabled = False
            cfg.vpn_enforce = False

        try:
            cfg.save()
        except Exception as exc:
            logger.warning("Could not persist wizard settings: %s", exc)

        from core.shared_credentials import shared_admin_credentials

        shared = shared_admin_credentials()
        username = selections.get("qbittorrent_username") or (shared[0] if shared else "admin")
        password = selections.get("qbittorrent_password") or (shared[1] if shared else "")
        try:
            secret_store.save_secret("qbittorrent_username", str(username))
            if password:
                secret_store.save_secret("qbittorrent_password", str(password))
                selections["qbittorrent_password"] = ""
            preferred = selections.get("preferred_download_client") or (
                (selections.get("download_clients") or ["qbittorrent"])[0]
            )
            secret_store.save_secret("preferred_download_client", str(preferred))
            claim = selections.get("plex_claim")
            if claim:
                secret_store.save_secret("plex_claim", str(claim))
                selections["plex_claim"] = ""
        except Exception as exc:
            logger.warning("Could not persist wizard secrets: %s", exc)

    async def execute_installation(self) -> dict[str, Any]:
        """
        Persist first-run settings, then report which catalog apps should be installed.
        Catalog POST /install is kicked off by the UI so this request stays short.
        """
        self.apply_initial_settings()
        catalog = ApplicationCatalog(app_settings=self._settings)
        target_apps = self._target_apps()
        install_results: list[dict[str, Any]] = []

        for app_name in target_apps:
            plugin = catalog.get(app_name)
            if plugin.is_installed():
                install_results.append({"app": app_name, "installed": True, "status": "already_installed"})
            else:
                install_results.append({"app": app_name, "installed": False, "status": "pending_catalog_install"})

        wiring_report = integration_engine.run_full_wiring()

        self._state["completed"] = True
        self._state["current_step"] = 12
        self._save_state()

        return {
            "completed": True,
            "target_apps": target_apps,
            "installations": install_results,
            "wiring": wiring_report,
        }


# Global singleton wizard engine
wizard_engine = WizardEngine()
