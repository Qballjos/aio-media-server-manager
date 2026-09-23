"""
core/settings.py — Application settings via Pydantic BaseSettings.

Reads from environment variables (prefixed AMM_) and from a JSON config
file located at {config_dir}/config.json.  Environment variables take
precedence over the file.

On first run the config file is created from built-in defaults.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_NAME = "amm_config.json"


class Settings(BaseSettings):
    """All runtime-configurable parameters for the AIO Media Manager."""

    model_config = SettingsConfigDict(
        env_prefix="AMM_",
        env_file=".env",
        env_file_encoding="utf-8",
        # Don't crash on unknown env vars
        extra="ignore",
        # Allow mutation after construction (useful for tests)
        frozen=False,
        populate_by_name=True,
    )

    # ------------------------------------------------------------------
    # Storage paths
    # ------------------------------------------------------------------
    config_dir: Path = Field(
        default=Path("/config"),
        description="Directory for app config files and logs.",
        validation_alias="AMM_CONFIG_DIR",
    )
    download_dir: Path = Field(
        default=Path("/downloads"),
        description="Root download directory.",
        validation_alias="AMM_DOWNLOAD_DIR",
    )
    media_dir: Path = Field(
        default=Path("/media"),
        description="Root media library directory.",
        validation_alias="AMM_MEDIA_DIR",
    )
    cache_dir: Path | None = Field(
        default=None,
        description="Cache directory for downloaded archives. Defaults to {config_dir}/cache.",
        validation_alias="AMM_CACHE_DIR",
    )
    install_dir: Path | None = Field(
        default=None,
        description="Installation directory for managed applications. Defaults to {config_dir}/apps.",
        validation_alias="AMM_INSTALL_DIR",
    )

    # ------------------------------------------------------------------
    # External APIs / Integrations
    # ------------------------------------------------------------------
    github_token: str | None = Field(
        default=None,
        description="Optional GitHub personal access token to avoid API rate limits (60/hr -> 5000/hr).",
        validation_alias="GITHUB_TOKEN",
    )

    # ------------------------------------------------------------------
    # User / Permissions
    # ------------------------------------------------------------------
    puid: int = Field(
        default=1000,
        description="UID for child processes and file ownership.",
        validation_alias="PUID",
    )
    pgid: int = Field(
        default=1000,
        description="GID for child processes and file ownership.",
        validation_alias="PGID",
    )

    # ------------------------------------------------------------------
    # API server
    # ------------------------------------------------------------------
    api_host: str = Field(default="0.0.0.0", description="Bind address for FastAPI.")
    api_port: int = Field(default=8080, description="Port for FastAPI.")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    log_level: str = Field(default="INFO", description="Root log level.")

    # ------------------------------------------------------------------
    # Backups
    # ------------------------------------------------------------------
    backup_dir: Path | None = Field(
        default=None,
        description="Local backup destination. Defaults to {config_dir}/backups.",
        validation_alias="AMM_BACKUP_DIR",
    )
    backup_retention: int = Field(
        default=7,
        description="Number of full configuration backups to retain.",
        validation_alias="AMM_BACKUP_RETENTION",
    )

    # ------------------------------------------------------------------
    # Reverse proxy (optional)
    # ------------------------------------------------------------------
    trusted_proxies: str = Field(
        default="",
        description="Comma-separated proxy IPs/CIDRs. Empty disables forwarded-header trust.",
        validation_alias="AMM_TRUSTED_PROXIES",
    )
    root_path: str = Field(
        default="",
        description="Optional URL prefix when served behind a reverse proxy subpath.",
        validation_alias="AMM_ROOT_PATH",
    )

    # ------------------------------------------------------------------
    # Cloudflare Tunnel (optional remotely managed cloudflared)
    # ------------------------------------------------------------------
    cloudflare_tunnel_enabled: bool = Field(
        default=False,
        validation_alias="AMM_CLOUDFLARE_TUNNEL_ENABLED",
    )
    cloudflare_tunnel_token: str = Field(
        default="",
        description="Tunnel token from the Cloudflare dashboard. Prefer the token file.",
        validation_alias="AMM_CLOUDFLARE_TUNNEL_TOKEN",
    )
    cloudflare_tunnel_token_file: Path | None = Field(
        default=None,
        validation_alias="AMM_CLOUDFLARE_TUNNEL_TOKEN_FILE",
    )
    cloudflare_tunnel_metrics_addr: str = Field(
        default="127.0.0.1:2000",
        validation_alias="AMM_CLOUDFLARE_TUNNEL_METRICS",
    )

    # ------------------------------------------------------------------
    # VPN (torrent traffic only)
    # ------------------------------------------------------------------
    vpn_enabled: bool = Field(default=False, validation_alias="AMM_VPN_ENABLED")
    vpn_enforce: bool = Field(
        default=False,
        description="Warn/block qBittorrent when the tunnel is down.",
        validation_alias="AMM_VPN_ENFORCE",
    )
    vpn_provider: str = Field(default="privadovpn", validation_alias="AMM_VPN_PROVIDER")
    vpn_protocol: str = Field(default="wireguard", validation_alias="AMM_VPN_PROTOCOL")
    vpn_config_path: Path | None = Field(default=None, validation_alias="AMM_VPN_CONFIG")

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("puid", "pgid", mode="before")
    @classmethod
    def _positive_id(cls, v: Any, info: Any) -> int:
        v = int(v)
        if v <= 0:
            raise ValueError(
                f"{info.field_name.upper()} must be a positive integer > 0 "
                "(UID/GID 0 would run managed services with root privileges)."
            )
        return v

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, v: Any) -> str:
        level = str(v).upper()
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in valid:
            raise ValueError(f"log_level must be one of {valid}, got {v!r}.")
        return level

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        """Expand user-home shortcuts and make all paths absolute."""
        self.config_dir = self.config_dir.expanduser().resolve()
        self.download_dir = self.download_dir.expanduser().resolve()
        self.media_dir = self.media_dir.expanduser().resolve()
        if self.cache_dir is None:
            self.cache_dir = self.config_dir / "cache"
        else:
            self.cache_dir = self.cache_dir.expanduser().resolve()
        if self.install_dir is None:
            self.install_dir = self.config_dir / "apps"
        else:
            self.install_dir = self.install_dir.expanduser().resolve()
        if self.backup_dir is None:
            self.backup_dir = self.config_dir / "backups"
        else:
            self.backup_dir = self.backup_dir.expanduser().resolve()
        if self.backup_retention < 1:
            raise ValueError("backup_retention must be at least 1.")
        if self.vpn_config_path is None:
            self.vpn_config_path = self.config_dir / "vpn" / "wg0.conf"
        else:
            self.vpn_config_path = self.vpn_config_path.expanduser().resolve()
        if self.cloudflare_tunnel_token_file is None:
            self.cloudflare_tunnel_token_file = (
                self.config_dir / "cloudflare" / "tunnel.token"
            )
        else:
            self.cloudflare_tunnel_token_file = (
                self.cloudflare_tunnel_token_file.expanduser().resolve()
            )
        self.cloudflare_tunnel_token = (self.cloudflare_tunnel_token or "").strip()
        self.vpn_protocol = str(self.vpn_protocol).lower()
        if self.vpn_protocol not in {"wireguard", "openvpn"}:
            raise ValueError("vpn_protocol must be 'wireguard' or 'openvpn'.")
        return self

    # ------------------------------------------------------------------
    # Config-file persistence
    # ------------------------------------------------------------------

    @property
    def config_file(self) -> Path:
        return self.config_dir / _DEFAULT_CONFIG_NAME

    def as_serialisable_dict(self) -> dict:
        """Return a JSON-serialisable representation (paths as strings)."""
        return {
            "config_dir": str(self.config_dir),
            "download_dir": str(self.download_dir),
            "media_dir": str(self.media_dir),
            "cache_dir": str(self.cache_dir),
            "install_dir": str(self.install_dir),
            "backup_dir": str(self.backup_dir),
            "backup_retention": self.backup_retention,
            "puid": self.puid,
            "pgid": self.pgid,
            "api_host": self.api_host,
            "api_port": self.api_port,
            "log_level": self.log_level,
            "github_token_configured": bool(self.github_token),
            "trusted_proxies": self.trusted_proxies,
            "root_path": self.root_path,
            "vpn_enabled": self.vpn_enabled,
            "vpn_enforce": self.vpn_enforce,
            "vpn_provider": self.vpn_provider,
            "vpn_protocol": self.vpn_protocol,
            "cloudflare_tunnel_enabled": self.cloudflare_tunnel_enabled,
        }

    def save(self) -> None:
        """Persist current settings to the config JSON file."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with self.config_file.open("w", encoding="utf-8") as fh:
            json.dump(self.as_serialisable_dict(), fh, indent=2)
        logger.debug("Settings saved to %s", self.config_file)

    def initialise(self) -> None:
        """
        Create config_dir and write the default config file if needed.

        Call this explicitly during application startup — NOT at import time,
        so that importing core.settings on a dev machine without /config
        doesn't raise an OSError.
        """
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Could not create config_dir %s: %s", self.config_dir, exc)
            return
        if not self.config_file.exists():
            self.save()
            logger.info("Created default config file at %s", self.config_file)

    @classmethod
    def load_or_create(cls) -> "Settings":
        """
        Instantiate settings from environment + .env file.
        Directory creation is deferred — call instance.initialise() during startup.
        """
        return cls()


# Module-level singleton — import this everywhere.
settings: Settings = Settings.load_or_create()
