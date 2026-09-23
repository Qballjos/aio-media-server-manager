"""
applications/catalog.py — Application catalog registry and dependency checks.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Iterable

from applications.base import BaseApplication
from applications.extended import (
    BazarrApp,
    LidarrApp,
    NeutarrApp,
    NzbgetApp,
    ProfilarrApp,
    RecyclarrApp,
)
from applications.community import FlaresolverrApp, GrimmoryApp, ShelfmarkApp
from applications.jellyfin import JellyfinApp
from applications.plex import PlexApp
from applications.prowlarr import ProwlarrApp
from applications.qbittorrent import QBittorrentApp
from applications.radarr import RadarrApp
from applications.sabnzbd import SabnzbdApp
from applications.seerr import SeerrApp
from applications.sonarr import SonarrApp
from applications.manifest import AppTier
from core.installer.arch import detect_system_arch
from core.settings import Settings, settings

logger = logging.getLogger(__name__)

# MVP plus Phase 4 plugins register here.
PLUGIN_CLASSES: tuple[type[BaseApplication], ...] = (
    ProwlarrApp,
    SonarrApp,
    RadarrApp,
    SabnzbdApp,
    NzbgetApp,
    QBittorrentApp,
    JellyfinApp,
    PlexApp,
    SeerrApp,
    BazarrApp,
    RecyclarrApp,
    ProfilarrApp,
    NeutarrApp,
    LidarrApp,
    FlaresolverrApp,
    GrimmoryApp,
    ShelfmarkApp,
)


class DependencyError(ValueError):
    """Raised when required catalog dependencies are missing."""


class ApplicationCatalog:
    """In-memory registry of application plugins."""

    def __init__(
        self,
        plugin_classes: Iterable[type[BaseApplication]] | None = None,
        app_settings: Settings = settings,
    ) -> None:
        self._settings = app_settings
        self._classes = tuple(plugin_classes or PLUGIN_CLASSES)
        self._plugins: dict[str, BaseApplication] = {}
        self.reload()

    def reload(self, ports: dict[str, int] | None = None) -> None:
        ports = ports or {}
        self._plugins = {}
        for cls in self._classes:
            plugin = cls(
                base_config_dir=self._settings.config_dir,
                base_install_dir=self._settings.install_dir,
                download_dir=self._settings.download_dir,
                port=ports.get(cls.manifest.name),
                puid=self._settings.puid,
                pgid=self._settings.pgid,
            )
            self._plugins[plugin.name] = plugin

    def get(self, name: str) -> BaseApplication:
        plugin = self._plugins.get(name)
        if plugin is None:
            raise KeyError(f"Unknown application: {name!r}")
        return plugin

    def has(self, name: str) -> bool:
        return name in self._plugins

    def __contains__(self, name: str) -> bool:
        return name in self._plugins

    def names(self) -> list[str]:
        return list(self._plugins)

    def all_plugins(self) -> list[BaseApplication]:
        return list(self._plugins.values())

    def set_port(self, name: str, port: int) -> None:
        plugin = self.get(name)
        plugin.port = port

    def entries(self) -> list[dict]:
        arch = detect_system_arch().value
        return [plugin.catalog_entry(host_arch=arch) for plugin in self._plugins.values()]

    def counts(self, entries: list[dict] | None = None) -> dict[str, int]:
        rows = entries if entries is not None else self.entries()
        installed = sum(1 for row in rows if row.get("installed"))
        total = len(rows)
        return {
            "catalog": total,
            "installed": installed,
            "available": total - installed,
        }

    def by_tier(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for plugin in self._plugins.values():
            grouped[plugin.manifest.tier.value].append(plugin.name)
        return dict(grouped)

    def resolve_install_order(self, names: Iterable[str]) -> list[str]:
        """
        Topological sort of requested applications plus their hard dependencies.
        """
        requested = set(names)
        for name in list(requested):
            self.get(name)  # validate
            requested.update(self.get(name).manifest.dependencies)

        incoming: dict[str, int] = {name: 0 for name in requested}
        edges: dict[str, list[str]] = {name: [] for name in requested}
        for name in requested:
            for dep in self.get(name).manifest.dependencies:
                if dep not in requested:
                    raise DependencyError(
                        f"'{name}' requires '{dep}', which is not in the catalog selection."
                    )
                edges[dep].append(name)
                incoming[name] += 1

        queue = deque(sorted(n for n, count in incoming.items() if count == 0))
        ordered: list[str] = []
        while queue:
            node = queue.popleft()
            ordered.append(node)
            for child in edges[node]:
                incoming[child] -= 1
                if incoming[child] == 0:
                    queue.append(child)

        if len(ordered) != len(requested):
            raise DependencyError("Circular application dependency detected.")
        return ordered

    def missing_dependencies(self, name: str, installed: set[str]) -> list[str]:
        plugin = self.get(name)
        return [dep for dep in plugin.manifest.dependencies if dep not in installed]

    def core_names(self) -> list[str]:
        return [
            p.name for p in self._plugins.values() if p.manifest.tier == AppTier.CORE
        ]
