"""
core/port_manager.py — Port registry, collision detection, and suggestions.
"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass

from core.settings import Settings, settings

logger = logging.getLogger(__name__)

_MAX_PORT = 65535
_SCAN_LIMIT = 50


@dataclass
class PortAllocation:
    app_name: str
    port: int
    default_port: int
    in_use: bool
    conflict: bool
    suggested_port: int | None = None


class PortManager:
    """Tracks application ports and detects collisions on the host."""

    def __init__(self, app_settings: Settings = settings) -> None:
        self._settings = app_settings
        self._registry: dict[str, int] = {}

    @property
    def reserved_ports(self) -> set[int]:
        return {self._settings.api_port}

    def register(self, app_name: str, port: int) -> None:
        self._registry[app_name] = port

    def unregister(self, app_name: str) -> None:
        self._registry.pop(app_name, None)

    def get_port(self, app_name: str, default_port: int) -> int:
        return self._registry.get(app_name, default_port)

    def list_registry(self) -> dict[str, int]:
        return dict(self._registry)

    def load(self, mapping: dict[str, int]) -> None:
        self._registry = {name: int(port) for name, port in mapping.items()}

    @staticmethod
    def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
        """Return True if something is already accepting connections on port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            return sock.connect_ex((host, port)) == 0

    def allocated_by_others(self, app_name: str, port: int) -> str | None:
        for name, assigned in self._registry.items():
            if name != app_name and assigned == port:
                return name
        return None

    def suggest_alternative(
        self,
        app_name: str,
        start_port: int,
        *,
        exclude: set[int] | None = None,
    ) -> int | None:
        blocked = set(self.reserved_ports)
        blocked.update(self._registry.values())
        if exclude:
            blocked.update(exclude)
        blocked.discard(self._registry.get(app_name, -1))

        candidate = start_port
        scanned = 0
        while scanned < _SCAN_LIMIT and candidate <= _MAX_PORT:
            taken_by = self.allocated_by_others(app_name, candidate)
            if (
                candidate not in blocked
                and taken_by is None
                and candidate not in self.reserved_ports
                and not self.is_port_open(candidate)
            ):
                return candidate
            candidate += 1
            scanned += 1
        return None

    def allocate(self, app_name: str, default_port: int) -> PortAllocation:
        """
        Choose a port for an application.

        Uses the existing registry entry when it is still free. Otherwise
        suggests the next available port starting from the default.
        """
        requested = self._registry.get(app_name, default_port)
        conflict_app = self.allocated_by_others(app_name, requested)
        host_busy = requested in self.reserved_ports or self.is_port_open(requested)
        conflict = bool(conflict_app) or host_busy

        chosen = requested
        suggested = None
        if conflict:
            suggested = self.suggest_alternative(app_name, default_port)
            if suggested is not None:
                chosen = suggested
                logger.warning(
                    "Port %d for '%s' is in use%s — assigning %d instead.",
                    requested,
                    app_name,
                    f" by '{conflict_app}'" if conflict_app else "",
                    chosen,
                )

        self.register(app_name, chosen)
        return PortAllocation(
            app_name=app_name,
            port=chosen,
            default_port=default_port,
            in_use=self.is_port_open(chosen),
            conflict=conflict,
            suggested_port=suggested,
        )

    def inspect(self, app_name: str, default_port: int) -> PortAllocation:
        port = self.get_port(app_name, default_port)
        conflict_app = self.allocated_by_others(app_name, port)
        host_busy = port in self.reserved_ports or self.is_port_open(port)
        conflict = bool(conflict_app) or (host_busy and self._registry.get(app_name) != port)
        suggested = self.suggest_alternative(app_name, default_port) if conflict else None
        return PortAllocation(
            app_name=app_name,
            port=port,
            default_port=default_port,
            in_use=host_busy,
            conflict=bool(conflict_app) or host_busy,
            suggested_port=suggested,
        )
