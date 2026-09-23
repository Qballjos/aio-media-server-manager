"""Plex helpers for libraries and transcode temp directory."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import requests

logger = logging.getLogger(__name__)


class PlexClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 32400,
        token: Optional[str] = None,
        config_dir: Optional[Path] = None,
    ) -> None:
        self.base_url = f"http://{host}:{port}"
        self.config_dir = Path(config_dir) if config_dir else None
        self.token = token or (self._read_token() if self.config_dir else None)

    def _prefs_file(self) -> Optional[Path]:
        if self.config_dir is None:
            return None
        for candidate in (
            self.config_dir / "Preferences.xml",
            self.config_dir / "Plex Media Server" / "Preferences.xml",
        ):
            if candidate.is_file():
                return candidate
        return None

    def _read_token(self) -> Optional[str]:
        prefs = self._prefs_file()
        if prefs is None:
            return None
        try:
            text = prefs.read_text(encoding="utf-8", errors="ignore")
            match = re.search(r'PlexOnlineToken="([^"]+)"', text)
            return match.group(1) if match else None
        except OSError:
            return None

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["X-Plex-Token"] = self.token
        return headers

    def set_transcoder_temp_directory(self, path: str) -> bool:
        xml_ok = self._write_prefs_transcode(path)
        api_ok = False
        try:
            resp = requests.put(
                f"{self.base_url}/:/prefs",
                headers=self._headers(),
                params={"TranscoderTempDirectory": path},
                timeout=5.0,
            )
            api_ok = resp.status_code in (200, 204)
        except Exception as exc:
            logger.debug("Plex set transcoder temp API error: %s", exc)
        return xml_ok or api_ok

    def add_library(self, name: str, section_type: str, location: str) -> bool:
        agent = {
            "movie": "tv.plex.agents.movie",
            "show": "tv.plex.agents.series",
            "artist": "tv.plex.agents.music",
        }.get(section_type, "tv.plex.agents.none")
        scanner = {
            "movie": "Plex Movie Scanner",
            "show": "Plex Series Scanner",
            "artist": "Plex Music Scanner",
        }.get(section_type, "Plex Movie Scanner")
        try:
            existing = requests.get(
                f"{self.base_url}/library/sections",
                headers=self._headers(),
                timeout=5.0,
            )
            if existing.status_code == 200:
                payload = existing.json()
                dirs = payload.get("MediaContainer", {}).get("Directory", [])
                if isinstance(dirs, dict):
                    dirs = [dirs]
                for item in dirs:
                    if item.get("title") == name:
                        return True
            resp = requests.post(
                f"{self.base_url}/library/sections",
                headers=self._headers(),
                params={
                    "name": name,
                    "type": section_type,
                    "agent": agent,
                    "scanner": scanner,
                    "language": "en",
                    "location": location,
                },
                timeout=8.0,
            )
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Plex add_library error: %s", exc)
            return False

    def _write_prefs_transcode(self, path: str) -> bool:
        prefs = self._prefs_file()
        if prefs is None:
            return False
        try:
            tree = ET.parse(prefs)
            root = tree.getroot()
            root.set("TranscoderTempDirectory", path)
            tree.write(prefs, encoding="utf-8", xml_declaration=True)
            return True
        except Exception as exc:
            logger.debug("Plex Preferences.xml update error: %s", exc)
            return False
