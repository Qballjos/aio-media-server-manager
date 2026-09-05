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
            "puid": self.puid,
            "pgid": self.pgid,
            "api_host": self.api_host,
            "api_port": self.api_port,
            "log_level": self.log_level,
            "github_token_configured": bool(self.github_token),
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
