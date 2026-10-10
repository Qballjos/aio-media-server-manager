"""
core/integrations/prowlarr.py — Prowlarr v1 REST API Client.

Registers Sonarr and Radarr as sync applications in Prowlarr,
so indexers configured in Prowlarr automatically push to Sonarr and Radarr.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Iterable, Optional
import requests

from core.install_jobs import set_wiring_progress

logger = logging.getLogger(__name__)

# Public indexers Prowlarr starts with so searches work right after setup.
# Definitions missing from Prowlarr's catalog are skipped and retried later.
STARTER_INDEXERS = (
    "1337x",
    "The Pirate Bay",
    "YTS",
    "EZTV",
    "Nyaa.si",
    "TorrentGalaxy",
    "LimeTorrents",
    "Knaben",
    "BitSearch",
    "TheRARBG",
)
FLARESOLVERR_TAG = "flaresolverr"
_CLOUDFLARE_MARKERS = ("cloudflare", "flaresolverr")
_MIN_PUBLIC_DEFINITIONS = 20  # fewer means Prowlarr has not downloaded its Cardigann catalog yet


class ProwlarrClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 9696, api_key: Optional[str] = None):
        self.base_url = f"http://{host}:{port}/api/v1"
        self.host = host
        self.port = port
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

    def _get(self, path: str, timeout: float = 5.0) -> Any:
        try:
            resp = requests.get(f"{self.base_url}{path}", headers=self._headers(), timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:
            logger.debug("Prowlarr GET %s error: %s", path, exc)
        return None

    def _post(self, path: str, payload: Any, timeout: float = 5.0) -> requests.Response | None:
        try:
            return requests.post(
                f"{self.base_url}{path}", headers=self._headers(), json=payload, timeout=timeout
            )
        except Exception as exc:
            logger.debug("Prowlarr POST %s error: %s", path, exc)
            return None

    def _put(self, path: str, payload: Any, timeout: float = 30.0) -> bool:
        try:
            resp = requests.put(
                f"{self.base_url}{path}", headers=self._headers(), json=payload, timeout=timeout
            )
            return resp.status_code in (200, 201, 202)
        except Exception as exc:
            logger.debug("Prowlarr PUT %s error: %s", path, exc)
            return False

    def list_indexers(self) -> list[dict[str, Any]]:
        return self._get("/indexer", timeout=30.0) or []

    def indexer_definitions(
        self, wait: float = 0.0, *, progress: Callable[[str], None] | None = None
    ) -> list[dict[str, Any]]:
        """Prowlarr's indexer catalog; nudge the definition download and wait when it is still empty."""
        report = progress or set_wiring_progress
        report("Reading Prowlarr's indexer catalog")
        defs = self._get("/indexer/schema", timeout=120.0) or []
        if wait <= 0 or _public_count(defs) >= _MIN_PUBLIC_DEFINITIONS:
            return defs
        report("Updating Prowlarr's indexer catalog")
        resp = self._post("/command", {"name": "IndexerDefinitionUpdate"})
        command_id = resp.json().get("id") if resp is not None and resp.status_code in (200, 201) else None
        deadline = time.monotonic() + wait
        while command_id is not None and time.monotonic() < deadline:
            time.sleep(3.0)
            status = (self._get(f"/command/{command_id}") or {}).get("status")
            if status in ("completed", "failed", "aborted"):
                break
        report("Reading Prowlarr's updated indexer catalog")
        return self._get("/indexer/schema", timeout=120.0) or defs

    def add_starter_indexers(
        self,
        wanted: Iterable[str] = STARTER_INDEXERS,
        skip: Iterable[str] = (),
        *,
        definitions_wait: float = 0.0,
        progress: Callable[[str], None] | None = None,
    ) -> dict[str, list[str]]:
        """Add the wanted public indexers Prowlarr knows; an unreachable one is saved disabled."""
        report = progress or set_wiring_progress
        report("Checking configured Prowlarr indexers")
        existing = {str(item.get("name")) for item in self.list_indexers()}
        skipped = set(skip)
        definitions = {
            str(item.get("name")): item
            for item in self.indexer_definitions(wait=definitions_wait, progress=report)
            if item.get("privacy") == "public"
        }
        result: dict[str, list[str]] = {"added": [], "disabled": [], "missing": []}
        for name in wanted:
            if name in existing or name in skipped:
                continue
            definition = definitions.get(name)
            if definition is None:
                result["missing"].append(name)
                continue
            body = _starter_body(definition)
            report(f"Checking and adding indexer: {name}")
            if self._create_indexer(body):
                result["added"].append(name)
                continue
            body["enable"] = False
            report(f"Saving unavailable indexer: {name}")
            if self._create_indexer(body):
                result["disabled"].append(name)
        return result

    def _create_indexer(self, body: dict[str, Any]) -> bool:
        # Prowlarr tests an enabled indexer on add; a tracker that does not answer
        # should cost one minute, not two.
        resp = self._post("/indexer", body, timeout=60.0)
        if resp is None:
            return False
        if resp.status_code in (200, 201):
            return True
        logger.info("Prowlarr did not accept indexer '%s': %s", body.get("name"), (resp.text or "")[:200])
        return False

    def ensure_tag(self, label: str) -> int | None:
        for tag in self._get("/tag") or []:
            if tag.get("label") == label and isinstance(tag.get("id"), int):
                return tag["id"]
        resp = self._post("/tag", {"label": label})
        if resp is None or resp.status_code not in (200, 201):
            return None
        tag_id = resp.json().get("id")
        return tag_id if isinstance(tag_id, int) else None

    def ensure_flaresolverr_tag(self) -> int | None:
        """A proxy only serves indexers sharing one of its tags, so give FlareSolverr one."""
        tag_id = self.ensure_tag(FLARESOLVERR_TAG)
        if tag_id is None:
            return None
        for proxy in self._get("/indexerProxy") or []:
            if proxy.get("implementation") != "FlareSolverr" or tag_id in (proxy.get("tags") or []):
                continue
            proxy["tags"] = list(proxy.get("tags") or []) + [tag_id]
            # forceSave skips Prowlarr's proxy test; FlareSolverr may still be starting.
            self._put(f"/indexerProxy/{proxy['id']}?forceSave=true", proxy)
        return tag_id

    def attach_flaresolverr(
        self, names: Iterable[str], *, progress: Callable[[str], None] | None = None
    ) -> list[str]:
        """Tag the named indexers for FlareSolverr when Prowlarr's test says Cloudflare blocks them."""
        report = progress or set_wiring_progress
        wanted = set(names)
        report("Preparing FlareSolverr indexer connections")
        tag_id = self.ensure_flaresolverr_tag()
        if tag_id is None or not wanted:
            return []
        tagged: list[str] = []
        for indexer in self.list_indexers():
            if indexer.get("name") not in wanted or tag_id in (indexer.get("tags") or []):
                continue
            report(f"Checking whether {indexer['name']} needs FlareSolverr")
            resp = self._post("/indexer/test", indexer, timeout=60.0)
            if resp is None or resp.status_code < 400:
                continue
            if not any(marker in (resp.text or "").lower() for marker in _CLOUDFLARE_MARKERS):
                continue
            indexer["tags"] = list(indexer.get("tags") or []) + [tag_id]
            indexer["enable"] = True
            report(f"Connecting {indexer['name']} to FlareSolverr")
            if self._put(f"/indexer/{indexer['id']}?forceSave=true", indexer):
                tagged.append(str(indexer["name"]))
        return tagged

    def get_applications(self) -> list[dict[str, Any]]:
        try:
            resp = requests.get(f"{self.base_url}/applications", headers=self._headers(), timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:
            logger.debug("Prowlarr get_applications error: %s", exc)
        return []

    def sync_sonarr(self, sonarr_url: str = "http://127.0.0.1:8989", sonarr_api_key: str = "") -> bool:
        apps = self.get_applications()
        if any(a.get("implementation") == "Sonarr" for a in apps):
            logger.info("Prowlarr Sonarr sync application already registered.")
            return True

        prowlarr_url = f"http://{self.host}:{self.port}"
        payload = {
            "enable": True,
            "name": "Sonarr (AMM)",
            "syncLevel": "fullSync",
            "implementation": "Sonarr",
            "configContract": "SonarrSettings",
            "fields": [
                {"name": "prowlarrUrl", "value": prowlarr_url},
                {"name": "baseUrl", "value": sonarr_url},
                {"name": "apiKey", "value": sonarr_api_key},
                {"name": "syncCategories", "value": [5000, 5010, 5020, 5030, 5040, 5045, 5050]},
            ],
        }
        try:
            resp = requests.post(f"{self.base_url}/applications", headers=self._headers(), json=payload, timeout=5.0)
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Prowlarr sync_sonarr error: %s", exc)
            return False

    def sync_radarr(self, radarr_url: str = "http://127.0.0.1:7878", radarr_api_key: str = "") -> bool:
        apps = self.get_applications()
        if any(a.get("implementation") == "Radarr" for a in apps):
            logger.info("Prowlarr Radarr sync application already registered.")
            return True

        prowlarr_url = f"http://{self.host}:{self.port}"
        payload = {
            "enable": True,
            "name": "Radarr (AMM)",
            "syncLevel": "fullSync",
            "implementation": "Radarr",
            "configContract": "RadarrSettings",
            "fields": [
                {"name": "prowlarrUrl", "value": prowlarr_url},
                {"name": "baseUrl", "value": radarr_url},
                {"name": "apiKey", "value": radarr_api_key},
                {"name": "syncCategories", "value": [2000, 2010, 2020, 2030, 2040, 2045, 2050]},
            ],
        }
        try:
            resp = requests.post(f"{self.base_url}/applications", headers=self._headers(), json=payload, timeout=5.0)
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Prowlarr sync_radarr error: %s", exc)
            return False

    def sync_lidarr(self, lidarr_url: str = "http://127.0.0.1:8686", lidarr_api_key: str = "") -> bool:
        return self._sync_app(
            "Lidarr",
            "LidarrSettings",
            "Lidarr (AMM)",
            lidarr_url,
            lidarr_api_key,
            [3000, 3010, 3020, 3030, 3040],
        )

    def _sync_app(
        self,
        implementation: str,
        config_contract: str,
        name: str,
        base_url: str,
        api_key: str,
        categories: list[int],
    ) -> bool:
        apps = self.get_applications()
        if any(item.get("implementation") == implementation for item in apps):
            logger.info("Prowlarr %s sync application already registered.", implementation)
            return True
        payload = {
            "enable": True,
            "name": name,
            "syncLevel": "fullSync",
            "implementation": implementation,
            "configContract": config_contract,
            "fields": [
                {"name": "prowlarrUrl", "value": f"http://{self.host}:{self.port}"},
                {"name": "baseUrl", "value": base_url},
                {"name": "apiKey", "value": api_key},
                {"name": "syncCategories", "value": categories},
            ],
        }
        try:
            resp = requests.post(
                f"{self.base_url}/applications",
                headers=self._headers(),
                json=payload,
                timeout=5.0,
            )
            return resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Prowlarr sync %s error: %s", implementation, exc)
            return False

    def add_flaresolverr(self, flaresolverr_url: str = "http://127.0.0.1:8191") -> bool:
        """Register Flaresolverr as a Prowlarr indexer proxy."""
        try:
            resp = requests.get(
                f"{self.base_url}/indexerProxy",
                headers=self._headers(),
                timeout=5.0,
            )
            proxies = resp.json() if resp.status_code == 200 else []
        except Exception as exc:
            logger.debug("Prowlarr list indexerProxy error: %s", exc)
            proxies = []
        if any(item.get("implementation") == "FlareSolverr" for item in proxies):
            logger.info("Prowlarr Flaresolverr proxy already registered.")
            return True
        payload = {
            "enable": True,
            "name": "Flaresolverr (AMM)",
            "implementation": "FlareSolverr",
            "configContract": "FlareSolverrSettings",
            "fields": [
                {"name": "host", "value": flaresolverr_url.rstrip("/")},
                {"name": "requestTimeout", "value": 60},
            ],
        }
        try:
            resp = requests.post(
                f"{self.base_url}/indexerProxy",
                headers=self._headers(),
                json=payload,
                timeout=5.0,
            )
            ok = resp.status_code in (200, 201)
        except Exception as exc:
            logger.debug("Prowlarr add_flaresolverr error: %s", exc)
            return False
        if ok:
            self.ensure_flaresolverr_tag()
        return ok


def _public_count(definitions: list[dict[str, Any]]) -> int:
    return sum(1 for item in definitions if item.get("privacy") == "public")


def _starter_body(definition: dict[str, Any]) -> dict[str, Any]:
    """Turn a schema template into an add request the way the Prowlarr UI does."""
    body = {key: value for key, value in definition.items() if key not in ("presets", "id")}
    body["name"] = definition.get("name")
    body["enable"] = True
    body["appProfileId"] = 1
    body["priority"] = definition.get("priority") or 25
    body["tags"] = []
    urls = definition.get("indexerUrls") or []
    fields = []
    for field in definition.get("fields") or []:
        field = dict(field)
        if field.get("name") == "baseUrl" and not field.get("value") and urls:
            field["value"] = urls[0]
        fields.append(field)
    body["fields"] = fields
    return body
